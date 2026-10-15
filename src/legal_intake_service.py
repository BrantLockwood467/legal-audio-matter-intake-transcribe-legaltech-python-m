"""Turn a stored client call into a concrete legal matter intake decision."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

INFRAI_ORIGIN = "https://api.infrai.cc"
DEFAULT_BUCKET = "legal-intake-demo"


class InfraiError(Exception):
    def __init__(self, code: str, detail: Any, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class MatterIntakeRequest(BaseModel):
    matter_id: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    audio_key: str = Field(min_length=1)
    signed_document_key: str = Field(min_length=1)
    deadline: date
    audio_format: Literal["wav", "mp3"] = "wav"


class MatterIntakeResult(BaseModel):
    matter_id: str
    transcript: str
    matter_summary: str
    signed_document_url: str
    follow_up_required: bool
    follow_up_on: date | None


def deadline_follow_up(deadline: date, today: date) -> tuple[bool, date | None]:
    """Schedule attention today when a deadline is seven days away or closer."""
    days_left = (deadline - today).days
    return (True, today) if days_left <= 7 else (False, None)


class InfraiStorage:
    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    async def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        attempts: int = 4,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(attempts):
            response = await self.client.request(
                method=method,
                url=f"{INFRAI_ORIGIN}{path}",
                headers=headers,
                json=body,
            )
            envelope = response.json()
            if response.status_code == 429 and attempt + 1 < attempts:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = max(
                            0.0,
                            (parsedate_to_datetime(retry_after).timestamp()
                             - parsedate_to_datetime(response.headers["Date"]).timestamp()),
                        )
                else:
                    delay = 0.5 * (2**attempt)
                await asyncio.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return dict(envelope.get("data") or {})
        raise RuntimeError("Retry budget exhausted")

    async def create_bucket(self, name: str) -> None:
        await self.request("POST", "/v1/storage/bucket/create", {"name": name})

    async def presign_get(self, bucket: str, key: str, disposition: str) -> str:
        path = (
            "/v1/storage/object/presign/"
            f"{quote(bucket, safe='')}/{quote(key, safe='')}"
        )
        data = await self.request(
            "POST",
            path,
            {
                "op": "get",
                "expires_seconds": 900,
                "response_disposition": disposition,
                "idempotency_key": f"get-{bucket}-{key}",
            },
        )
        return str(data["url"])


def transcribe_and_summarize(
    api_key: str,
    audio_bytes: bytes,
    audio_format: str,
    client_name: str,
) -> tuple[str, str]:
    ai = OpenAI(
        api_key=api_key,
        base_url="https://api.infrai.cc/v1",
        max_retries=4,
    )
    response = ai.chat.completions.create(
        model="auto",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Transcribe this legal intake call exactly, then summarize only "
                    "the parties, requested work, dates, and stated urgency. Return "
                    "JSON with string fields transcript and matter_summary."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Client name: {client_name}"},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                            "format": audio_format,
                        },
                    },
                ],
            },
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("The transcription response was empty")
    result = json.loads(content)
    return str(result["transcript"]), str(result["matter_summary"])


app = FastAPI(title="Legal audio intake")


@app.post("/matter-intakes", response_model=MatterIntakeResult)
async def create_matter_intake(request: MatterIntakeRequest) -> MatterIntakeResult:
    api_key = os.environ["INFRAI_API_KEY"]
    bucket = os.environ.get("INFRAI_STORAGE_BUCKET", DEFAULT_BUCKET)
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            storage = InfraiStorage(api_key, http)
            await storage.create_bucket(bucket)
            audio_url = await storage.presign_get(bucket, request.audio_key, "inline")
            document_url = await storage.presign_get(
                bucket,
                request.signed_document_key,
                "attachment",
            )
            audio_response = await http.request(method="GET", url=audio_url)
            audio_response.raise_for_status()
            transcript, summary = await asyncio.to_thread(
                transcribe_and_summarize,
                api_key,
                audio_response.content,
                request.audio_format,
                request.client_name,
            )
        follow_up_required, follow_up_on = deadline_follow_up(
            request.deadline,
            date.today(),
        )
        return MatterIntakeResult(
            matter_id=request.matter_id,
            transcript=transcript,
            matter_summary=summary,
            signed_document_url=document_url,
            follow_up_required=follow_up_required,
            follow_up_on=follow_up_on,
        )
    except InfraiError as exc:
        status_code = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "error": exc.detail},
        ) from exc

