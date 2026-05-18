# OpenRead

OpenRead is a mobile-first picture-book read-aloud app built for the Kaggle Gemma 4 Good Hackathon. A caregiver opens the web app on a phone, takes one photo of a children's book page, and gets a layout-aware read-aloud experience with large follow-along text, generated audio, reading-order notes, and optional caregiver questions.

The core technical idea is the story-plan layer. OpenRead does not send OCR text directly to TTS. It sends the page image to Gemma 4, optionally with PaddleOCR evidence, and asks Gemma to return a validated JSON reading plan. Kokoro TTS then receives only the child-facing `spoken_script`.

## What It Does

- Captures a page photo from the phone camera in a one-screen Vue app.
- Uses Gemma 4 through the Google GenAI SDK as a page-level story compiler.
- Reconstructs reading order for non-linear picture-book layouts.
- Preserves visible text where possible and adds brief picture narration only when useful.
- Keeps caregiver cues on screen and out of the spoken audio.
- Generates 24 kHz WAV read-aloud audio with Kokoro TTS.
- Keeps `/api/ocr` available as a PaddleOCR diagnostic endpoint and `ocr_assisted` comparison path.

## Repo Layout

```text
OpenRead/
  backend/   FastAPI API, Gemma story compiler, OCR/TTS services, tests
  docs/      Technical writeup for the hackathon pitch
  deploy/    Nginx and systemd examples for a self-hosted Docker deploy
  web/       Vue 3 + Vite mobile web app and HTML/CSS pitch demo
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
  -> POST /api/read/jobs
  -> image validation and normalization
  -> Gemma 4 story compiler
     -> gemma_vision: image directly to Gemma
     -> ocr_assisted: PaddleOCR blocks plus image to Gemma
  -> validated StoryCompilation JSON
  -> Kokoro TTS receives spoken_script only
  -> /media/audio/{request_id}
  -> mobile UI shows audio, large text, reading order, and questions
```

The structured story plan contains ordered `beats`, `source_text`, optional illustration narration, caregiver cues, diagnostics, and the final TTS-ready `spoken_script`.

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
- Completed jobs return the compiled `spoken_script` as `text`, the structured `story` payload, and `/media/audio/{request_id}`. Audio is WAV at 24 kHz and expires according to `MEDIA_TTL_SECONDS`.
- `POST /api/read` is still available for synchronous API use. It supports JSON metadata responses by default and `response_mode=stream` for direct WAV streaming.
- `/api/ocr` remains a diagnostics endpoint. OCR language hinting maps `en` to PaddleOCR English; all other hints, including `bilingual` and `zh`, use PaddleOCR Chinese.

## Frontend Behavior

The default UI is intentionally simple:

- one screen
- one primary `Open Camera` / `Take Photo` button
- large generated text for follow-along reading
- audio player when synthesis completes
- plain labels: `Reading Order` and `Questions to Ask`

The app does not expose the model selector in the caregiver UI. The default submitted mode is `gemma_vision`; `ocr_assisted` remains available through the API and benchmark script.

## Configuration Notes

Important environment variables from `.env.example`:

- `ALLOW_ORIGINS` controls browser CORS during split frontend/backend development.
- `MAX_UPLOAD_BYTES` and `IMAGE_MAX_SIDE` bound uploaded camera frames before OCR.
- `MAX_TEXT_CHARS` bounds direct text input and OCR output sent to TTS.
- `MAX_ACTIVE_READS` controls async read-job worker count and synchronous `/api/read` concurrency.
- `GEMINI_API_KEY`, `GEMMA_MODEL`, `STORY_COMPILER_MODE`, and `STORY_COMPILER_TIMEOUT_SECONDS` control the Gemma story compiler.
- `PRELOAD_MODELS=1` warms PaddleOCR and Kokoro at startup; this improves first-request latency but makes startup slower and may download model assets.
- `MEDIA_TTL_SECONDS`, `MEDIA_CLEANUP_INTERVAL_SECONDS`, and `MEDIA_MAX_BYTES` control generated-audio retention.
- `DEFAULT_ZH_VOICE`, `DEFAULT_EN_VOICE`, `KOKORO_SPEED`, `KOKORO_DEVICE`, and `ESPEAK_NG_PATH` control Kokoro synthesis.
- `PADDLE_USE_GPU`, `PADDLE_ENABLE_MKLDNN`, `PADDLE_ENABLE_HPI`, and `PADDLE_CPU_THREADS` control PaddleOCR runtime behavior.

## Privacy and Trust Notes

- Uploaded page photos are validated, normalized, and processed in memory by the backend. They are not durably stored by the application.
- Read jobs are in-memory for the hackathon build. They are not durable across backend restarts.
- Generated audio is cached under `backend/var/media` with TTL and disk-budget cleanup.
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

### Frontend

```powershell
cd C:\home\dev\OpenRead\web
npm test
```

## Hackathon Materials

- [Technical design writeup](docs/openread-technical-writeup.md)
- Cinematic HTML/CSS demo: `http://localhost:5173/demo/openread-cinematic.html` after starting Vite
- If Vite is running on port 5174, use `http://localhost:5174/demo/openread-cinematic.html`

## Open Source Acknowledgements

OpenRead depends on major open-source projects including FastAPI, Vue, Vite, PaddleOCR, PaddlePaddle, Kokoro, Misaki, PyTorch, Pillow, NumPy, and eSpeak NG, plus the Google GenAI SDK and Gemma API/model terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for project-level acknowledgements and license notes.

## Production Notes

- The app must run behind HTTPS for iPhone Safari camera access.
- The backend serves the built `web/dist` directory in production for same-origin camera upload and audio playback.
- Build the web bundle before running the backend directly in production, or use the Docker image, which builds and copies `web/dist` automatically.
- Uploaded images are validated and normalized entirely in memory; they are not persisted to disk.
- Story compilation requires `GEMINI_API_KEY`; text-only TTS requests still work without it.
- Audio files and their JSON metadata are cached under `backend/var/media` on local disk with a TTL, a background cleanup loop, and an overall disk budget guard.
- In production, OCR/TTS models are preloaded at startup so the first user request does not pay the cold-start download and initialization cost.
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
STORY_COMPILER_MODE=gemma_vision
STORY_COMPILER_TIMEOUT_SECONDS=90
PRELOAD_MODELS=1
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
