# Backend

FastAPI backend for the Book Voice web app.

Core endpoints:

- `POST /api/ocr`
- `POST /api/read`
- `POST /api/read/jobs`
- `GET /api/read/jobs/{request_id}`
- `GET /media/audio/{request_id}`
- `GET /healthz`

Endpoint notes:

- `/api/ocr` accepts an uploaded `image` plus optional `lang_hint` and returns recognized text, OCR blocks, confidence values, boxes, and detected script names.
- `/api/read` accepts either uploaded `image` or form `text`, never both. It returns JSON metadata by default or streams WAV bytes with `response_mode=stream`.
- `/api/read/jobs` is the mobile UI path. It returns `202` with a `request_id`; poll `/api/read/jobs/{request_id}` until the job is `completed` or `failed`.
- Read-job stages are `queued`, `ocr`, `tts`, `completed`, and `failed`. During `tts`, paragraph progress is exposed as `paragraphs_completed` and `paragraphs_total`.
- Generated audio is served from `/media/audio/{request_id}` as 24 kHz WAV until the media TTL expires or disk-budget cleanup removes it.
- `lang_hint=en` selects PaddleOCR English. Other values, including `bilingual` and `zh`, select PaddleOCR Chinese for mixed Chinese/English target pages.

Diagnostics:

- `uv run --directory backend python scripts/run_fixture_pipeline.py`
- Runs `tests/ocr_voice_test.png` through the real OCR + Kokoro TTS stack.
- Saves `.txt`, `.wav`, and timing `.json` outputs under `backend/var/diagnostics/`.
