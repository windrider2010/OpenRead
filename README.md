# Book Voice Web App

An iPhone-first mobile web app for reading printed book pages aloud:

- Safari opens a thin web UI.
- The UI shows the rear camera preview, captures one frame, uploads it.
- FastAPI runs OCR with PaddleOCR.
- FastAPI turns the recognized text into speech with Kokoro.
- The phone starts a background read job, polls for completion, and then plays the generated audio.

## Repo Layout

```text
book-voice-webapp/
  backend/   FastAPI API, OCR/TTS services, tests
  web/       Vue 3 + Vite mobile web app
```

## Runtime Requirements

- Python 3.12 managed with `uv`.
- Node 22 or another current Node release compatible with Vite 7.
- Local, non-Docker TTS requires eSpeak NG because Kokoro uses phonemizer for English text. Linux hosts can install the `espeak-ng` package. On Windows, install eSpeak NG and set `ESPEAK_NG_PATH` to the install directory, the library file, or the `espeak-ng-data` directory if it is not auto-detected.
- Docker builds install eSpeak NG and the Linux shared libraries required by PaddleOCR/OpenCV and Kokoro.

## Local Development

Create local environment settings first:

```powershell
cd C:\home\dev\book-voice-webapp
Copy-Item .env.example .env
```

### Backend

```powershell
cd C:\home\dev\book-voice-webapp
uv sync --project backend
uv run --directory backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The first real OCR/TTS request may download model assets required by PaddleOCR and Kokoro.

### Frontend

```powershell
cd C:\home\dev\book-voice-webapp\web
npm ci
npm run dev
```

Vite proxies `/api`, `/media`, and `/healthz` to `http://localhost:8000`.

## API Flow

- The mobile UI captures a JPEG from the visible camera crop and submits it to `POST /api/read/jobs` with `lang_hint=bilingual`.
- `POST /api/read/jobs` accepts either `image` or `text`, never both, and returns `202` with a `request_id`.
- The UI polls `GET /api/read/jobs/{request_id}` every 1.5 seconds. Job statuses are `queued`, `processing`, `completed`, and `failed`; stages are `queued`, `ocr`, `tts`, `completed`, and `failed`.
- Completed jobs return the recognized text plus `/media/audio/{request_id}`. Audio is WAV at 24 kHz and expires according to `MEDIA_TTL_SECONDS`.
- `POST /api/read` is still available for synchronous API use. It supports JSON metadata responses by default and `response_mode=stream` for direct WAV streaming.
- OCR language hinting maps `en` to PaddleOCR English. All other hints, including `bilingual` and `zh`, use PaddleOCR Chinese, which supports mixed Chinese/English pages better for the target use case.

## Configuration Notes

Important environment variables from `.env.example`:

- `ALLOW_ORIGINS` controls browser CORS during split frontend/backend development.
- `MAX_UPLOAD_BYTES` and `IMAGE_MAX_SIDE` bound uploaded camera frames before OCR.
- `MAX_TEXT_CHARS` bounds direct text input and OCR output sent to TTS.
- `MAX_ACTIVE_READS` controls async read-job worker count and synchronous `/api/read` concurrency.
- `PRELOAD_MODELS=1` warms PaddleOCR and Kokoro at startup; this improves first-request latency but makes startup slower and may download model assets.
- `MEDIA_TTL_SECONDS`, `MEDIA_CLEANUP_INTERVAL_SECONDS`, and `MEDIA_MAX_BYTES` control generated-audio retention.
- `DEFAULT_ZH_VOICE`, `DEFAULT_EN_VOICE`, `KOKORO_SPEED`, `KOKORO_DEVICE`, and `ESPEAK_NG_PATH` control Kokoro synthesis.
- `PADDLE_USE_GPU`, `PADDLE_ENABLE_MKLDNN`, `PADDLE_ENABLE_HPI`, and `PADDLE_CPU_THREADS` control PaddleOCR runtime behavior.

## Test

### Backend

```powershell
cd C:\home\dev\book-voice-webapp
uv run --directory backend pytest
```

### Frontend

```powershell
cd C:\home\dev\book-voice-webapp\web
npm test
```

## Production Notes

- The app must run behind HTTPS for iPhone Safari camera access.
- The backend serves the built `web/dist` directory in production for same-origin camera upload and audio playback.
- Build the web bundle before running the backend directly in production, or use the Docker image, which builds and copies `web/dist` automatically.
- Uploaded images are validated and normalized entirely in memory; they are not persisted to disk.
- Audio files and their JSON metadata are cached under `backend/var/media` on local disk with a TTL, a background cleanup loop, and an overall disk budget guard.
- In production, OCR/TTS models are preloaded at startup so the first user request does not pay the cold-start download and initialization cost.
- `MAX_ACTIVE_READS=1` limits concurrent OCR+TTS jobs on CPU-first deployments.
- The Docker image is aligned for Oracle Ubuntu hosts running Linux containers: Node builds the Vue bundle in a separate stage, Python 3.12 runs the API, and the runtime image includes the Linux shared libraries commonly required by PaddleOCR/OpenCV and Kokoro/eSpeak.
- This stack is aligned for Oracle Ubuntu `arm64` and `x86_64` CPU hosts. `paddlepaddle` is resolved from Paddle's official CPU wheel index instead of PyPI so Linux `aarch64` builds can install the official ARM wheel in Docker.
- The provided Nginx config sets `client_max_body_size 12m`, matching the default `MAX_UPLOAD_BYTES=10485760`, and 600-second proxy timeouts for slow CPU OCR/TTS requests.

## Docker On Oracle Ubuntu

Build:

```bash
docker build -t book-voice-webapp:latest .
```

Run:

```bash
docker run --rm -p 8000:8000 --env-file .env book-voice-webapp:latest
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
- `deploy/nginx/book-voice-webapp.conf` is a host-level Nginx reverse-proxy config that terminates HTTPS and forwards traffic to the local Docker app.
- `deploy/systemd/book-voice-webapp.service` manages the Docker Compose stack under `systemd`.

Suggested server layout:

```bash
sudo mkdir -p /opt/book-voice-webapp
sudo chown $USER:$USER /opt/book-voice-webapp
```

Copy this repo to `/opt/book-voice-webapp`, then create `/opt/book-voice-webapp/.env` from `.env.example` and set at least:

```dotenv
APP_ENV=production
ALLOW_ORIGINS=https://your-domain.example
MAX_ACTIVE_READS=1
MAX_TEXT_CHARS=10000
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
cd /opt/book-voice-webapp
docker compose build
docker compose up -d
docker compose ps
curl http://127.0.0.1:8001/healthz
```

Install Nginx:

```bash
sudo cp deploy/nginx/book-voice-webapp.conf /etc/nginx/sites-available/book-voice-webapp.conf
sudo ln -s /etc/nginx/sites-available/book-voice-webapp.conf /etc/nginx/sites-enabled/book-voice-webapp.conf
sudo nginx -t
sudo systemctl reload nginx
```

Update the placeholder domain and certificate paths in the Nginx config before enabling it.

Install the `systemd` unit:

```bash
sudo cp deploy/systemd/book-voice-webapp.service /etc/systemd/system/book-voice-webapp.service
sudo systemctl daemon-reload
sudo systemctl enable --now book-voice-webapp.service
sudo systemctl status book-voice-webapp.service
```
