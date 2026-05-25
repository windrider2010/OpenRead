# OpenRead Backend

FastAPI backend for the OpenRead picture-book read-aloud app.

Core endpoints:

- `POST /api/ocr`
- `POST /api/read`
- `POST /api/read/jobs`
- `GET /api/read/jobs/{request_id}`
- `GET /media/audio/{request_id}`
- `GET /healthz`

Endpoint notes:

- `/api/ocr` accepts an uploaded `image` plus optional `lang_hint` and returns recognized text, OCR blocks, confidence values, boxes, and detected script names.
- `/api/read` accepts either uploaded `image` or form `text`, never both. Image reads run through the Gemma story compiler before Kokoro TTS; text reads go directly to Kokoro. It returns JSON metadata by default or streams WAV bytes with `response_mode=stream`.
- `/api/read/jobs` is the mobile UI path. It accepts optional `compiler_mode=gemma_vision|ocr_assisted`, returns `202` with a `request_id`, and is polled through `/api/read/jobs/{request_id}` until the job is `completed` or `failed`.
- Read-job stages are `queued`, `story_compile`, `ocr`, `tts`, `completed`, and `failed`. During `tts`, paragraph progress is exposed as `paragraphs_completed` and `paragraphs_total`.
- Completed image jobs include a `story` payload with ordered story beats, caregiver cues, compiler diagnostics, and the `spoken_script` used for TTS.
- Generated audio is served from `/media/audio/{request_id}` as 24 kHz WAV until the media TTL expires or disk-budget cleanup removes it.
- `lang_hint=en` selects PaddleOCR English. Other values, including `bilingual` and `zh`, select PaddleOCR Chinese for mixed Chinese/English target pages.
- Raw Gemma text outputs and validation diagnostics are temporarily written to `backend/var/diagnostics/gemma/{request_id}.json` when image story compilation runs. These diagnostics include client IP for abuse investigation but do not include uploaded images.
- `PRELOAD_MODELS=1` enables startup preload; `PRELOAD_TTS=1` warms Kokoro, while `PRELOAD_OCR=0` keeps PaddleOCR lazy-loaded by default.

Diagnostics:

- `uv run --directory backend python scripts/run_fixture_pipeline.py`
- Runs `tests/ocr_voice_test.png` through the real OCR + Kokoro TTS stack.
- Saves `.txt`, `.wav`, and timing `.json` outputs under `backend/var/diagnostics/`.

Story compiler benchmark:

- `uv run --directory backend python scripts/benchmark_story_compiler.py`
- Runs `gemma_vision` and `ocr_assisted` over fixture images.
- Saves JSON reports under `backend/var/diagnostics/openread/`.
