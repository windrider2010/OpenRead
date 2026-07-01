# OpenRead Backend

FastAPI backend for the OpenRead picture-book read-aloud and Word Explorer app.

Core endpoints:

- `POST /api/ocr`
- `POST /api/read`
- `POST /api/read/jobs`
- `GET /api/read/jobs/{request_id}`
- `POST /api/word/jobs`
- `GET /api/word/jobs/{request_id}`
- `GET /media/audio/{request_id}`
- `GET /healthz`

Endpoint notes:

- `/api/ocr` accepts an uploaded `image` plus optional `lang_hint` and returns recognized text, OCR blocks, confidence values, boxes, and detected script names.
- `/api/read` accepts either uploaded `image` or form `text`, never both. Image reads run through the Gemma story compiler before Kokoro TTS; text reads go directly to Kokoro. It returns JSON metadata by default or streams WAV bytes with `response_mode=stream`.
- `/api/read/jobs` is the mobile UI path. It accepts optional `compiler_mode=gemma_vision|ocr_assisted` and `compiler_provider=google_genai|cerebras`, returns `202` with a `request_id`, and is polled through `/api/read/jobs/{request_id}` until the job is `completed` or `failed`.
- Read-job stages are `queued`, `story_compile`, `ocr`, `tts`, `completed`, and `failed`. During `tts`, paragraph progress is exposed as `paragraphs_completed` and `paragraphs_total`.
- Read and Word Explorer job status responses include millisecond `timings` for image normalization, queue wait, Gemma processing, TTS, media storage, and end-to-end total time.
- Completed image jobs include a `story` payload with ordered story beats, caregiver cues, compiler diagnostics, and the `spoken_script` used for TTS.
- `/api/word/jobs` is the Word Explorer path. It accepts an uploaded `image` plus optional `lang_hint`, returns `202` with a `request_id`, and is polled through `/api/word/jobs/{request_id}` until the job is `completed` or `failed`.
- Word jobs retain a centered crop around the camera target, use the configured Word Explorer Gemma provider to identify the centered printed word, return a structured child-friendly explanation, and send only the result `spoken_script` to Kokoro TTS. Cerebras `gemma-4-31b` is the default; Google GenAI can be selected with `WORD_EXPLORER_PROVIDER=google_genai`. No physical pointer is required.
- Word-job stages are `queued`, `word_detect`, `tts`, `completed`, and `failed`. Completed word jobs include a `word` payload with the selected word, explanation, optional pronunciation/example, diagnostics, and the `spoken_script` used for TTS.
- Generated audio is served from `/media/audio/{request_id}` as 24 kHz WAV until the media TTL expires or disk-budget cleanup removes it.
- `lang_hint=en` selects PaddleOCR English. Other values, including `bilingual` and `zh`, select PaddleOCR Chinese for mixed Chinese/English target pages.
- Raw Gemma text outputs and validation diagnostics are temporarily written to `backend/var/diagnostics/gemma/{request_id}.json` when image story compilation or Word Explorer runs. These diagnostics include per-attempt image encoding, generation, parsing, pipeline, and total timings plus client IP for abuse investigation, but do not include uploaded images.
- Page story compilation uses `STORY_COMPILER_MAX_OUTPUT_TOKENS` and `STORY_COMPILER_TEMPERATURE` to bound Gemma generation and reduce malformed runaway JSON. Keep the output-token cap high enough for one page, but low enough to avoid multi-minute repeated-character responses.
- `compiler_provider=cerebras` uses Cerebras Chat Completions with image input and strict JSON schema output. It is the default for page reads; `compiler_provider=google_genai` remains available as an API/env fallback.
- `PRELOAD_MODELS=1` enables startup preload; `PRELOAD_TTS=1` warms Kokoro, while `PRELOAD_OCR=0` keeps PaddleOCR lazy-loaded by default.

Diagnostics:

- `uv run --directory backend python scripts/run_fixture_pipeline.py`
- Runs `tests/ocr_voice_test.png` through the real OCR + Kokoro TTS stack.
- Saves `.txt`, `.wav`, and timing `.json` outputs under `backend/var/diagnostics/`.

Story compiler benchmark:

- `uv run --directory backend python scripts/benchmark_story_compiler.py`
- Runs `gemma_vision` and `ocr_assisted` over fixture images.
- Saves JSON reports under `backend/var/diagnostics/openread/`.

Word Explorer model benchmark:

- `uv run --directory backend python scripts/benchmark_word_explorer.py --model gemma-4-31b-it --model gemma-4-26b-a4b-it`
- Uses the five real camera fixtures under `tests/fixtures/word_explorer/` by default and applies the production center crop; pass `--fixture-dir` or repeated `--fixture` arguments to override them, or `--no-center-crop` for a full-frame comparison.
- Runs the same photos through each model with production image normalization.
- Saves per-run JSON, aggregate JSON, and CSV timing reports under `backend/var/diagnostics/word-explorer-benchmark/` by default.
- Measures Gemma image encoding, generation, structured-output parsing, retries, and total service latency. It deliberately excludes TTS so model comparisons are not distorted by the voice engine.
