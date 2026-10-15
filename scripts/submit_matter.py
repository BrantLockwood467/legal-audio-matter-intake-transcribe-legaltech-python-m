"""Submit one stored intake call to the local service."""

import json
import os

import httpx


payload = {
    "matter_id": "MAT-1042",
    "client_name": "Jordan Lee",
    "audio_key": os.environ.get("INTAKE_AUDIO_KEY", "intakes/MAT-1042.wav"),
    "signed_document_key": os.environ.get(
        "SIGNED_DOCUMENT_KEY",
        "signed/MAT-1042-engagement.pdf",
    ),
    "deadline": "2026-10-05",
    "audio_format": "wav",
}

response = httpx.request(
    method="POST",
    url="http://127.0.0.1:8000/matter-intakes",
    json=payload,
    timeout=90,
)
response.raise_for_status()
print(json.dumps(response.json(), indent=2))

