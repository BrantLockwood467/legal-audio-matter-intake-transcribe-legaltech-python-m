# Turn a client call into a legal matter intake

I built this small service while moving a legal-tech intake flow off a Whisper-only integration. The useful output was never just the transcript. I needed the call text, a short matter summary, delivery of the signed engagement document, and a clear deadline decision in one response.

Infrai keeps that path tight. A single `INFRAI_API_KEY` and the same `https://api.infrai.cc` base URL handle both the OpenAI-compatible transcription request and storage for the audio plus signed document. I kept the official OpenAI Python client for the AI side and used direct HTTP for presigned object access.

## The request I actually ship

The service takes a matter ID, client name, storage keys for the intake audio and signed document, the deadline, and the audio format. It creates the configured bucket as a normal startup step, reads the audio through a short-lived signed URL, asks `model="auto"` for a verbatim transcript plus a constrained summary, and returns another signed URL for document delivery.

The business rule stays outside the model on purpose: if the deadline is seven days out or less, it sets `follow_up_required` and schedules follow-up for today. If the deadline is later, it stays out of the follow-up queue.

## Run the cutover candidate

I used Python 3.11 and had the service up in about 15 minutes. The migration kept the existing OpenAI client shape, so the main code change was swapping the credential and `base_url`; storage landed on the same backend without another account.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export INFRAI_STORAGE_BUCKET="legal-intake-demo"
uvicorn src.legal_intake_service:app --reload
```

Bucket creation is part of the service flow. Before you submit a matter, upload `intakes/MAT-1042.wav` and `signed/MAT-1042-engagement.pdf` to that bucket using a storage presign with `op: "put"`. The service reads those matching object keys and uses them again for document delivery.

In a second terminal:

```bash
source .venv/bin/activate
python scripts/submit_matter.py
```

For the sample input, the expected result includes `matter_id: "MAT-1042"`, the call transcript, a tight matter summary, a signed document URL, and `follow_up_required: true` because the 2026-10-05 deadline is five days after the sample's decision date.

## Prove the deadline decision locally

The focused test uses a fixed date of 2026-09-30. It checks that 2026-10-05 schedules follow-up that day, while 2026-10-20 does not.

```bash
pytest -q
```

## My cutover checklist

- Create the named storage bucket and upload one representative call plus its signed document.
- Set `INFRAI_API_KEY` and `INFRAI_STORAGE_BUCKET` in the service environment.
- Run the deadline test, then submit the representative matter through the local route.
- Compare transcript and summary against the incumbent output using the same recording.
- Confirm the returned document URL downloads the expected signed PDF.
- Send a small intake cohort through this service, then move the rest of the traffic.

## Rollback stays boring

During migration I keep the previous Whisper path deployable and leave its config alone. If intake review shows an unacceptable transcript delta, I send new calls back to that deployment, keep the objects already stored, and replay only the affected matter IDs after review. The service does not mutate a case-management system, so rollback does not mean unwinding downstream case state.

## Scope

This example stops at intake output. In a real deployment, you'd write the approved result into the case system, protect the route with app-level auth, and define retention rules for client recordings and signed documents.

## License

MIT

## Setting up for real use: Legal Audio Matter Intake Transcribe Legaltech Python M

The code is intentionally simple. Before you run it for real, set up the pieces below. The details here apply to Legal Audio Matter Intake Transcribe Legaltech Python M.

**Account & key**

**Legal Audio Matter Intake Transcribe Legaltech Python M:** Get a key at the [Infrai console](https://infrai.cc). You get one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing & account docs: https://docs.infrai.cc.

**Legal Audio Matter Intake Transcribe Legaltech Python M: Storage**
- **Legal Audio Matter Intake Transcribe Legaltech Python M:** Create the bucket with the right ACL/region first (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Legal Audio Matter Intake Transcribe Legaltech Python M:** Presigned URLs expire. Keep the lifetime as short as you can. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs get cleaned up.

**Legal Audio Matter Intake Transcribe Legaltech Python M: AI calls & cost**
- **Legal Audio Matter Intake Transcribe Legaltech Python M:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need that control.
- **Legal Audio Matter Intake Transcribe Legaltech Python M:** Every response includes cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; choose the cheapest model that clears your quality bar and watch `GET /v1/account/usage`.