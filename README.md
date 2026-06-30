# OpenRead

OpenRead is a mobile-first picture-book reading helper built for the Kaggle Gemma 4 Good Hackathon. A caregiver opens the web app on a phone, takes one photo of a children's book page, and gets a layout-aware read-aloud experience with large follow-along text, generated audio, reading-order notes, and optional caregiver questions. The same screen also includes an optional Word Explorer mode: center a word in the camera target, take a photo, and hear a kid-friendly explanation.

The core technical idea is the story-plan layer. OpenRead does not send OCR text directly to TTS. It sends the page image to Gemma 4, optionally with PaddleOCR evidence, and asks Gemma to return a validated JSON reading plan. Kokoro TTS then receives only the child-facing `spoken_script`. Word Explorer uses the same Gemma vision and Kokoro pattern for a narrower task: crop around the camera target, locate the centered word, and return a structured child-friendly vocabulary explanation.

## What Makes OpenRead Different

OpenRead starts from a real picture-book page photo, not a prepared ebook, audiobook, PDF, web page, or fixed lesson library. The intended moment is simple: a child brings a physical book, a caregiver takes one photo, and the app helps keep the story going.

OpenRead is not OCR-first. OCR can recognize letters, but children's books are visual stories with speech bubbles, curved text, captions, jokes hidden in illustrations, and clues that may need to be understood before a sentence makes sense. OpenRead uses Gemma 4 as a multimodal story compiler to reason over the full page image, not just extracted text.

OpenRead can include the picture in the reading experience. When an illustration adds meaningful context, the story compiler can add a short child-facing narration beat, while still preserving visible page text where possible.

OpenRead can also slow down at a single word. Word Explorer is not a chatbot prompt or a full-page tutor; it is a camera mode for the common moment when a child asks, "What does this word mean?" and the caregiver points at the printed word.

OpenRead returns a structured reading plan instead of one opaque paragraph. The plan separates the final spoken script, ordered reading beats, illustration narration, caregiver cues, diagnostics, and TTS-ready output. This makes the system easier to validate, debug, audit, display in the frontend, and send safely to Kokoro TTS.

OpenRead is designed as an open-source, self-hostable public-interest tool. It does not require user accounts in the current deployment model, does not persist uploaded page photos, and keeps temporary diagnostics focused on abuse investigation and reproducible errors.

There are already powerful OCR tools, AI chatbots, accessibility apps, and reading toys. OpenRead is not claiming that OCR or TTS is new. The gap is the family reading workflow. Existing tools are often general-purpose, closed, account-based, hardware-bound, tutoring-focused, or not designed for the moment when a caregiver simply wants to turn one printed page into spoken language without friction.

OpenRead focuses on that narrow but common moment: no prompt engineering, no toy hardware, no account requirement, no content lock-in, and no long-term storage by default. The goal is a simple, open, self-hostable reading layer for families, libraries, schools, and caregivers.

Key differentiation:

- One-button, not prompt-based.
- Web-first, not hardware-bound.
- Open-source, not closed ecosystem.
- Stateless, not account-driven.
- Story-aware, not OCR-only.
- Caregiver-centered, not AI babysitting.

OpenRead is not trying to be the most powerful AI reader. It is trying to be the easiest trustworthy way to keep a child's page from going silent.

## Governance and Ownership

OpenRead is an independent open-source public-interest AI project for early literacy access, currently maintained by Hewei Li with infrastructure support from Sperion LLC.

## Citation

If you reference OpenRead in a writeup, demo, research note, benchmark, or derivative project, please cite it as:

```text
Li, Hewei. OpenRead: A layout-aware picture-book read-aloud system using Gemma 4 and Kokoro TTS. 2026. GitHub: https://github.com/windrider2010/OpenRead
```

BibTeX:

```bibtex
@software{li2026openread,
  author = {Li, Hewei},
  title = {OpenRead: A Layout-Aware Picture-Book Read-Aloud System Using Gemma 4 and Kokoro TTS},
  year = {2026},
  url = {https://github.com/windrider2010/OpenRead},
  note = {Independent open-source public-interest AI project for early literacy access}
}
```

## What It Does

- Captures a page photo from the phone camera in a one-screen Vue app.
- Uses Gemma 4 through the Google GenAI SDK as a page-level story compiler.
- Reconstructs reading order for non-linear picture-book layouts.
- Preserves visible text where possible and adds brief picture narration only when useful.
- Keeps caregiver cues on screen and out of the spoken audio.
- Provides optional Word Explorer mode for center-targeted vocabulary explanations without a physical pointer.
- Generates 24 kHz WAV read-aloud audio with Kokoro TTS.
- Keeps `/api/ocr` available as a PaddleOCR diagnostic endpoint and `ocr_assisted` comparison path.

## Repo Layout

```text
OpenRead/
  backend/   FastAPI API, Gemma story compiler, OCR/TTS services, tests
  docs/      Technical writeup for the hackathon pitch
  deploy/    Nginx and systemd examples for a self-hosted Docker deploy
  web/       Vue 3 + Vite mobile web app and public OpenRead initiative page
```

## Runtime Requirements

- Python 3.12 managed with `uv`.
- Node 22 or another current Node release compatible with Vite 7.
- A Google GenAI API key in `GEMINI_API_KEY` for image-based story compilation.
- Local, non-Docker TTS requires eSpeak NG because Kokoro uses phonemizer for English text. Linux hosts can install the `espeak-ng` package. On Windows, install eSpeak NG and set `ESPEAK_NG_PATH` to the install directory, the library file, or the `espeak-ng-data` directory if it is not auto-detected.
- Docker builds install eSpeak NG and the Linux shared libraries required by PaddleOCR/OpenCV and Kokoro.

## Architecture

```text
Phone camera
  -> Read Page: POST /api/read/jobs
     -> image validation and normalization
     -> Gemma 4 story compiler
        -> gemma_vision: image directly to Gemma
        -> ocr_assisted: PaddleOCR blocks plus image to Gemma
     -> validated StoryCompilation JSON
     -> Kokoro TTS receives spoken_script only
     -> mobile UI shows audio, large text, reading order, and questions
  -> Explore Word: POST /api/word/jobs
     -> image validation and normalization
     -> Center crop keeps the selected word and nearby context
     -> Faster Gemma 4 word explorer locates the centered word
     -> validated WordExplorerResult JSON
     -> Kokoro TTS receives spoken_script only
     -> mobile UI shows the word, meaning, example, and audio
```

The structured story plan contains ordered `beats`, `source_text`, optional illustration narration, caregiver cues, diagnostics, and the final TTS-ready `spoken_script`.
The structured word result contains the selected word, normalized word, language, optional pronunciation, child-friendly explanation, example sentence, page context, diagnostics, and the final TTS-ready `spoken_script`.

## Local Development

Create local environment settings first:

```powershell
cd C:\home\dev\OpenRead
Copy-Item .env.example .env
```

### Backend

```powershell
cd C:\home\dev\OpenRead
uv sync --project backend
uv run --directory backend python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The first real OCR/TTS request may download model assets required by PaddleOCR and Kokoro.

### Frontend

```powershell
cd C:\home\dev\OpenRead\web
npm ci
npm run dev
```

Vite defaults to `http://localhost:5173` and proxies `/api`, `/media`, and `/healthz` to `http://localhost:8000`. If that port is already busy, run `npm run dev -- --port 5174`.

## API Flow

- The mobile UI captures a JPEG from the visible camera crop and submits it to `POST /api/read/jobs` with `lang_hint=bilingual` and `compiler_mode=gemma_vision` by default.
- `POST /api/read/jobs` accepts either `image` or `text`, never both, and returns `202` with a `request_id`.
- Image jobs run through the OpenRead story compiler before TTS. `gemma_vision` sends the image directly to Gemma; `ocr_assisted` runs PaddleOCR first and sends OCR blocks plus the image to Gemma.
- The UI polls `GET /api/read/jobs/{request_id}` every 1.5 seconds. Job statuses are `queued`, `processing`, `completed`, and `failed`; stages are `queued`, `story_compile`, `ocr`, `tts`, `completed`, and `failed`.
- Read and Word Explorer job status payloads include millisecond `timings` for normalization, queue wait, Gemma processing, TTS, media storage, and total request time.
- Completed jobs return the compiled `spoken_script` as `text`, the structured `story` payload, and `/media/audio/{request_id}`. Audio is WAV at 24 kHz and expires according to `MEDIA_TTL_SECONDS`.
- `POST /api/word/jobs` accepts an uploaded `image` plus optional `lang_hint` and returns `202` with a `request_id`.
- Word jobs crop the normalized image around the camera target, then use the faster `WORD_EXPLORER_MODEL` to identify the centered printed word, explain it for a child, and return a structured `word` payload. The UI polls `GET /api/word/jobs/{request_id}`; stages are `queued`, `word_detect`, `tts`, `completed`, and `failed`.
- Completed word jobs return the `spoken_script` as `text`, the structured `word` payload, and `/media/audio/{request_id}`.
- `POST /api/read` is still available for synchronous API use. It supports JSON metadata responses by default and `response_mode=stream` for direct WAV streaming.
- `/api/ocr` remains a diagnostics endpoint. OCR language hinting maps `en` to PaddleOCR English; all other hints, including `bilingual` and `zh`, use PaddleOCR Chinese.

## Frontend Behavior

The default UI is intentionally simple:

- one screen
- one primary `Open Camera` / `Take Photo` button
- default `Read Page` mode with a small toggle for optional `Explore Word`
- a center target in `Explore Word`, so selecting a word does not require a pen or finger
- large generated text for follow-along reading
- large word, meaning, and example text in Word Explorer mode
- audio player when synthesis completes
- plain labels: `Reading Order` and `Questions to Ask`

The app does not expose the model selector in the caregiver UI. The default read-page compiler mode is `gemma_vision`; `ocr_assisted` remains available through the API and benchmark script.

## Configuration Notes

Important environment variables from `.env.example`:

- `ALLOW_ORIGINS` controls browser CORS during split frontend/backend development.
- `MAX_UPLOAD_BYTES` and `IMAGE_MAX_SIDE` bound uploaded camera frames before OCR.
- `MAX_TEXT_CHARS` bounds direct text input and OCR output sent to TTS.
- `MAX_ACTIVE_READS` controls async read-job worker count and synchronous `/api/read` concurrency.
- `GEMINI_API_KEY`, `GEMMA_MODEL`, `STORY_COMPILER_MODE`, `STORY_COMPILER_TIMEOUT_SECONDS`, `STORY_COMPILER_MAX_OUTPUT_TOKENS`, and `STORY_COMPILER_TEMPERATURE` control the Gemma story compiler. The output-token cap helps prevent runaway malformed JSON responses from masking user-visible timeouts.
- `WORD_EXPLORER_MODEL` selects the latency-focused Word Explorer model; it defaults to `gemma-4-26b-a4b-it` while page compilation remains on `GEMMA_MODEL`.
- `WORD_EXPLORER_CROP_FRACTION` controls the centered fraction retained for Word Explorer. The default `0.62` keeps nearby context while reducing image tokens.
- `OPENREAD_LOG_GEMMA_FAILURES`, `OPENREAD_LOG_GEMMA_SUCCESSES`, and `OPENREAD_GEMMA_LOG_TTL_SECONDS` control temporary raw Gemma-output diagnostics. By default, success and failure diagnostics are enabled and retained for 7 days.
- `PRELOAD_MODELS=1` enables startup preloading. `PRELOAD_TTS=1` warms Kokoro by default; `PRELOAD_OCR=0` leaves PaddleOCR lazy-loaded because OCR is only used for diagnostics and `ocr_assisted`.
- `MEDIA_TTL_SECONDS`, `MEDIA_CLEANUP_INTERVAL_SECONDS`, and `MEDIA_MAX_BYTES` control generated-audio retention.
- `DEFAULT_ZH_VOICE`, `DEFAULT_EN_VOICE`, `KOKORO_SPEED`, `KOKORO_DEVICE`, and `ESPEAK_NG_PATH` control Kokoro synthesis.
- `PADDLE_USE_GPU`, `PADDLE_ENABLE_MKLDNN`, `PADDLE_ENABLE_HPI`, and `PADDLE_CPU_THREADS` control PaddleOCR runtime behavior.

## Privacy and Trust Notes

- Uploaded page photos are validated, normalized, and processed in memory by the backend. They are not durably stored by the application.
- Read jobs and Word Explorer jobs are in-memory for the hackathon build. They are not durable across backend restarts.
- Generated audio is cached under `backend/var/media` with TTL and disk-budget cleanup.
- Gemma diagnostics are cached under `backend/var/diagnostics/gemma/{request_id}.json` with a 7-day default TTL. These records include raw Gemma text output, validation errors, fallback status, final spoken script, task/mode, model name, client IP, per-attempt generation/parsing timings, and end-to-end pipeline timings. They do not include uploaded page images.
- `.env`, local logs, generated media, diagnostics, private keys, certificates, credentials, and local support notes are ignored by Git.
- The structured Gemma output is auditable before speech synthesis: the UI can inspect the plan, while Kokoro receives only `spoken_script`.

## Test

### Backend

```powershell
cd C:\home\dev\OpenRead
uv run --directory backend python -m pytest
```

### Story Compiler Benchmark

```powershell
cd C:\home\dev\OpenRead
uv run --directory backend python scripts/benchmark_story_compiler.py
```

The benchmark runs both `gemma_vision` and `ocr_assisted` over fixtures and writes reports under `backend/var/diagnostics/openread/`.

### Word Explorer Model Benchmark

```powershell
uv run --directory backend python scripts/benchmark_word_explorer.py `
  --model gemma-4-31b-it `
  --model gemma-4-26b-a4b-it
```

This benchmark uses the five real camera photos under `backend/tests/fixtures/word_explorer/` by default, applies production image normalization and the centered Word Explorer crop, runs every photo through each model, and writes detailed JSON/CSV reports under `backend/var/diagnostics/word-explorer-benchmark/`. Pass `--fixture-dir` or repeated `--fixture` arguments to use another fixture set. Use `--no-center-crop` for a full-frame comparison. It measures Gemma image encoding, generation, structured-output parsing, retries, and service total time while excluding TTS from the model comparison.

### Frontend

```powershell
cd C:\home\dev\OpenRead\web
npm test
```

## Hackathon Materials

- [Technical design writeup](docs/openread-technical-writeup.md)
- Parent-child friendly initiative page: `/openread` in the web app, or `https://reader.sperion.io/openread` on the public deployment.
- Local Vite example: `http://localhost:5173/openread`.

## Open Source Acknowledgements and Attribution

OpenRead is released under the Apache License 2.0. It also depends on third-party open-source projects and hosted model/API services. The lockfiles are the source of truth for exact transitive package versions; this section acknowledges the main direct dependencies used by the project.

Model and API services:

- Google GenAI SDK: Python SDK used to call the Gemma model endpoint. Project: <https://github.com/googleapis/python-genai>. License: Apache 2.0.
- Gemma 4: multimodal model used as OpenRead's story compiler through the Google GenAI API. Project information: <https://deepmind.google/models/gemma/gemma-4/>. Model/API use is governed by Google's applicable model and API terms, separate from this repository's Apache 2.0 license.
- Kokoro-82M: text-to-speech model used by the Kokoro package for generated read-aloud audio. Model page: <https://huggingface.co/hexgrad/Kokoro-82M>. License listed by upstream: Apache 2.0.

Backend runtime:

- FastAPI: backend web framework. Project: <https://github.com/fastapi/fastapi>. License listed by upstream/package metadata: MIT.
- Uvicorn: ASGI server. Project: <https://uvicorn.dev/>. License listed by upstream/package metadata: BSD 3-Clause.
- PaddleOCR: OCR diagnostics and `ocr_assisted` mode. Project: <https://github.com/PaddlePaddle/PaddleOCR>. License listed by upstream/package metadata: Apache 2.0.
- PaddlePaddle: PaddleOCR runtime. Project: <https://github.com/PaddlePaddle/Paddle>. License listed by upstream/package metadata: Apache 2.0.
- Kokoro Python package: TTS pipeline wrapper used by `KokoroTtsService`. Project: <https://github.com/hexgrad/kokoro>. License listed by upstream/package metadata: Apache 2.0.
- Misaki: text processing dependency used with Kokoro for multilingual/CJK support. Package metadata lists Apache 2.0.
- PyTorch: tensor runtime used by Kokoro. Project: <https://pytorch.org/>. License listed by upstream/package metadata: BSD 3-Clause.
- Pillow: image decoding and JPEG normalization. Project: <https://python-pillow.github.io/>. License listed by upstream/package metadata: HPND.
- NumPy: numerical array handling for audio and image data. Project: <https://numpy.org/>. License listed by upstream/package metadata: BSD 3-Clause.
- python-dotenv: local environment loading. Project: <https://github.com/theskumar/python-dotenv>. License listed by upstream/package metadata: BSD 3-Clause.
- python-multipart: multipart upload parsing for FastAPI. Project: <https://github.com/Kludex/python-multipart>. License listed by upstream/package metadata: Apache 2.0.
- eSpeak NG: system dependency installed in Docker for English phonemization used by Kokoro. Project: <https://github.com/espeak-ng/espeak-ng>. License listed by upstream: GPL 3.0 or later.

Frontend runtime and tooling:

- Vue: frontend framework. Project: <https://vuejs.org/>. License listed by upstream/package metadata: MIT.
- Vite: frontend dev server and build tool. Project: <https://vite.dev/>. License listed by upstream/package metadata: MIT.
- TypeScript: type system and compiler. Project: <https://www.typescriptlang.org/>. License listed by upstream/package metadata: Apache 2.0.
- Vitest: frontend unit test runner. Project: <https://vitest.dev/>. License listed by upstream/package metadata: MIT.
- jsdom: DOM environment for frontend tests. Project: <https://github.com/jsdom/jsdom>. License listed by upstream/package metadata: MIT.

This acknowledgement is not a substitute for a full legal review before production distribution. For redistribution, review the generated Python and npm lockfiles, container base image notices, system packages, and model/provider terms for the exact build being shipped.

## Production Notes

- The app must run behind HTTPS for iPhone Safari camera access.
- The backend serves the built `web/dist` directory in production for same-origin camera upload and audio playback.
- Build the web bundle before running the backend directly in production, or use the Docker image, which builds and copies `web/dist` automatically.
- Uploaded images are validated and normalized entirely in memory; they are not persisted to disk.
- Story compilation requires `GEMINI_API_KEY`; text-only TTS requests still work without it.
- Word Explorer requires `GEMINI_API_KEY` because identifying the centered word is a Gemma vision task.
- Audio files and their JSON metadata are cached under `backend/var/media` on local disk with a TTL, a background cleanup loop, and an overall disk budget guard.
- In production, Kokoro TTS is preloaded by default so the first read-aloud request does not pay the TTS cold-start cost. PaddleOCR is lazy-loaded unless `PRELOAD_OCR=1`.
- `MAX_ACTIVE_READS=1` limits concurrent OCR+TTS jobs on CPU-first deployments.
- The Docker image is aligned for Oracle Ubuntu hosts running Linux containers: Node builds the Vue bundle in a separate stage, Python 3.12 runs the API, and the runtime image includes the Linux shared libraries commonly required by PaddleOCR/OpenCV and Kokoro/eSpeak.
- This stack is aligned for Oracle Ubuntu `arm64` and `x86_64` CPU hosts. `paddlepaddle` is resolved from Paddle's official CPU wheel index instead of PyPI so Linux `aarch64` builds can install the official ARM wheel in Docker.
- The provided Nginx config sets `client_max_body_size 12m`, matching the default `MAX_UPLOAD_BYTES=10485760`, and 600-second proxy timeouts for slow CPU OCR/TTS requests.

## Docker On Oracle Ubuntu

Build:

```bash
docker build -t openread:latest .
```

Run:

```bash
docker run --rm -p 8000:8000 --env-file .env openread:latest
```

Recommended host checks on Oracle Ubuntu before deploy:

```bash
uname -m
docker --version
docker info
```

If `uname -m` returns `aarch64`, build and run the same image normally. The repo is configured to pull Paddle's ARM CPU wheel during image build.

## Server Deployment

This repo includes server-side deploy artifacts for an Oracle Ubuntu host:

- `docker-compose.yml` runs the app container on `127.0.0.1:8001`, persists generated audio in a named volume, and persists runtime model downloads in a cache volume.
- `deploy/nginx/openread.conf` is a host-level Nginx reverse-proxy config that terminates HTTPS and forwards traffic to the local Docker app.
- `deploy/systemd/openread.service` manages the Docker Compose stack under `systemd`.

Suggested server layout:

```bash
sudo mkdir -p /opt/openread
sudo chown $USER:$USER /opt/openread
```

Copy this repo to `/opt/openread`, then create `/opt/openread/.env` from `.env.example` and set at least:

```dotenv
APP_ENV=production
ALLOW_ORIGINS=https://your-domain.example
MAX_ACTIVE_READS=1
MAX_TEXT_CHARS=10000
GEMINI_API_KEY=your-google-genai-key
GEMMA_MODEL=gemma-4-31b-it
WORD_EXPLORER_MODEL=gemma-4-26b-a4b-it
WORD_EXPLORER_CROP_FRACTION=0.62
STORY_COMPILER_MODE=gemma_vision
STORY_COMPILER_TIMEOUT_SECONDS=90
STORY_COMPILER_MAX_OUTPUT_TOKENS=4096
STORY_COMPILER_TEMPERATURE=0.1
OPENREAD_LOG_GEMMA_FAILURES=1
OPENREAD_LOG_GEMMA_SUCCESSES=1
OPENREAD_GEMMA_LOG_TTL_SECONDS=604800
PRELOAD_MODELS=1
PRELOAD_TTS=1
PRELOAD_OCR=0
MEDIA_TTL_SECONDS=3600
MEDIA_CLEANUP_INTERVAL_SECONDS=300
MEDIA_MAX_BYTES=536870912
KOKORO_DEVICE=cpu
PADDLE_USE_GPU=0
PADDLE_ENABLE_MKLDNN=0
PADDLE_ENABLE_HPI=0
PADDLE_CPU_THREADS=4
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
```

Install the Compose stack:

```bash
cd /opt/openread
docker compose build
docker compose up -d
docker compose ps
curl http://127.0.0.1:8001/healthz
```

Install Nginx:

```bash
sudo cp deploy/nginx/openread.conf /etc/nginx/sites-available/openread.conf
sudo ln -s /etc/nginx/sites-available/openread.conf /etc/nginx/sites-enabled/openread.conf
sudo nginx -t
sudo systemctl reload nginx
```

Update the placeholder domain and certificate paths in the Nginx config before enabling it.

Install the `systemd` unit:

```bash
sudo cp deploy/systemd/openread.service /etc/systemd/system/openread.service
sudo systemctl daemon-reload
sudo systemctl enable --now openread.service
sudo systemctl status openread.service
```
