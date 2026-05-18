from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.config import get_settings
from app.models import (
    CompilerMode,
    HealthResponse,
    OcrBlock,
    OcrResponse,
    ReadJobAcceptedResponse,
    ReadJobStatusResponse,
    ReadResponse,
    StoryCompilation,
)
from app.services.image_pipeline import ImageValidationError, normalize_uploaded_image
from app.services.media_store import MediaStore
from app.services.ocr_service import OcrService, PaddleOcrService
from app.services.story_compiler import (
    GemmaStoryCompilerService,
    StoryCompilerError,
    StoryCompilerService,
    normalize_compiler_mode,
    story_from_text,
)
from app.services.tts_service import KokoroTtsService, TtsService, synthesize_text_in_paragraphs

logger = logging.getLogger(__name__)


class ReadConcurrencyGate:
    def __init__(self, max_active: int) -> None:
        self._max_active = max_active
        self._lock = threading.Lock()
        self._active = 0

    def try_acquire(self) -> bool:
        with self._lock:
            if self._active >= self._max_active:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


@dataclass(slots=True)
class ReadJob:
    request_id: str
    status: str
    stage: str
    created_at: datetime
    updated_at: datetime
    image: object | None = None
    input_text: str | None = None
    lang_hint: str | None = None
    compiler_mode: CompilerMode = "gemma_vision"
    text: str | None = None
    story: StoryCompilation | None = None
    mime_type: str | None = None
    expires_at: str | None = None
    paragraphs_total: int = 0
    paragraphs_completed: int = 0
    error: str | None = None


class ReadJobManager:
    def __init__(self, *, max_workers: int, ttl_seconds: int) -> None:
        self._max_workers = max(1, max_workers)
        self._ttl_seconds = max(60, ttl_seconds)
        self._jobs: dict[str, ReadJob] = {}
        self._lock = threading.Lock()
        self._queue: asyncio.Queue[str] | None = None
        self._workers: list[asyncio.Task[None]] = []

    def create_job(
        self,
        *,
        image: object | None,
        text: str | None,
        lang_hint: str | None,
        compiler_mode: CompilerMode,
    ) -> ReadJob:
        now = datetime.now(UTC)
        job = ReadJob(
            request_id=uuid.uuid4().hex,
            status="queued",
            stage="queued",
            created_at=now,
            updated_at=now,
            image=image,
            input_text=text,
            lang_hint=lang_hint,
            compiler_mode=compiler_mode,
        )
        with self._lock:
            self._jobs[job.request_id] = job
        return job

    async def start(self, app: FastAPI) -> None:
        if self._queue is not None:
            return
        self._queue = asyncio.Queue()
        self._workers = [
            asyncio.create_task(self._worker(app), name=f"read-job-worker-{index}")
            for index in range(self._max_workers)
        ]

    async def stop(self) -> None:
        workers = list(self._workers)
        self._workers.clear()
        queue = self._queue
        self._queue = None
        for worker in workers:
            worker.cancel()
        for worker in workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        if queue is not None:
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    break

    async def enqueue(self, request_id: str) -> None:
        if self._queue is None:
            raise RuntimeError("Read job manager has not been started.")
        await self._queue.put(request_id)

    def get_job(self, request_id: str) -> ReadJob | None:
        with self._lock:
            return self._jobs.get(request_id)

    def cleanup_expired(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)
        removed = 0
        with self._lock:
            expired_ids = [
                request_id
                for request_id, job in self._jobs.items()
                if job.status in {"completed", "failed"} and job.updated_at <= cutoff
            ]
            for request_id in expired_ids:
                self._jobs.pop(request_id, None)
                removed += 1
        return removed

    async def _worker(self, app: FastAPI) -> None:
        assert self._queue is not None
        while True:
            request_id = await self._queue.get()
            try:
                await self._process_job(app, request_id)
            finally:
                self._queue.task_done()

    async def _process_job(self, app: FastAPI, request_id: str) -> None:
        with self._lock:
            job = self._jobs.get(request_id)
            if job is None:
                return
            job.status = "processing"
            job.stage = "ocr"
            job.updated_at = datetime.now(UTC)
            image = job.image
            input_text = job.input_text
            lang_hint = job.lang_hint
            compiler_mode = job.compiler_mode

        try:
            if image is not None:
                with self._lock:
                    compiling_job = self._jobs.get(request_id)
                    if compiling_job is not None:
                        compiling_job.stage = "story_compile"
                        compiling_job.updated_at = datetime.now(UTC)
                story = await _compile_story_for_image(app, image, compiler_mode, lang_hint)
                source_text = story.spoken_script
            else:
                story = story_from_text(input_text or "", mode=compiler_mode)
                source_text = story.spoken_script

            if not source_text:
                raise ValueError("No readable text was produced from the submitted input.")
            max_text_chars = app.state.settings.max_text_chars
            if len(source_text) > max_text_chars:
                raise ValueError(f"Text exceeds the {max_text_chars} character limit.")

            with self._lock:
                tts_job = self._jobs.get(request_id)
                if tts_job is not None:
                    tts_job.text = source_text
                    tts_job.story = story
                    tts_job.stage = "tts"
                    tts_job.updated_at = datetime.now(UTC)

            def on_tts_progress(completed: int, total: int) -> None:
                with self._lock:
                    progress_job = self._jobs.get(request_id)
                    if progress_job is None:
                        return
                    progress_job.status = "processing"
                    progress_job.stage = "tts"
                    progress_job.paragraphs_total = total
                    progress_job.paragraphs_completed = completed
                    progress_job.updated_at = datetime.now(UTC)

            audio = await asyncio.to_thread(
                synthesize_text_in_paragraphs,
                app.state.tts_service,
                source_text,
                lang_hint,
                progress_callback=on_tts_progress,
            )
            asset = app.state.media_store.store_audio(
                request_id=request_id,
                audio_bytes=audio.audio_bytes,
                mime_type=audio.mime_type,
                text=source_text,
            )
        except Exception as exc:
            logger.exception("Read job %s failed", request_id)
            with self._lock:
                failed_job = self._jobs.get(request_id)
                if failed_job is not None:
                    failed_job.status = "failed"
                    failed_job.stage = "failed"
                    failed_job.error = str(exc)
                    failed_job.updated_at = datetime.now(UTC)
                    failed_job.image = None
                    failed_job.input_text = None
            return

        with self._lock:
            completed_job = self._jobs.get(request_id)
            if completed_job is None:
                return
            completed_job.status = "completed"
            completed_job.stage = "completed"
            completed_job.updated_at = datetime.now(UTC)
            completed_job.text = source_text
            completed_job.story = story
            completed_job.mime_type = audio.mime_type
            completed_job.expires_at = asset.expires_at
            completed_job.image = None
            completed_job.input_text = None


def create_app(
    *,
    settings=None,
    ocr_service: OcrService | None = None,
    story_compiler_service: StoryCompilerService | None = None,
    tts_service: TtsService | None = None,
    media_store: MediaStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.media_store.cleanup_expired()
        app.state.media_store.cleanup_to_size_limit()
        app.state.read_job_manager.cleanup_expired()
        await app.state.read_job_manager.start(app)
        if app.state.settings.preload_models:
            await asyncio.to_thread(_preload_runtime_dependencies, app)
        cleanup_task = asyncio.create_task(_media_cleanup_loop(app))
        try:
            yield
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            await app.state.read_job_manager.stop()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.ocr_service = ocr_service or PaddleOcrService(
        use_gpu=settings.paddle_use_gpu,
        enable_mkldnn=settings.paddle_enable_mkldnn,
        enable_hpi=settings.paddle_enable_hpi,
        cpu_threads=settings.paddle_cpu_threads,
    )
    app.state.story_compiler_service = story_compiler_service or GemmaStoryCompilerService(
        api_key=settings.gemini_api_key,
        model=settings.gemma_model,
    )
    app.state.tts_service = tts_service or KokoroTtsService(
        default_en_voice=settings.default_en_voice,
        default_zh_voice=settings.default_zh_voice,
        device=settings.kokoro_device,
        speed=settings.kokoro_speed,
        espeak_ng_path=settings.espeak_ng_path,
    )
    app.state.media_store = media_store or MediaStore(
        settings.media_root,
        ttl_seconds=settings.media_ttl_seconds,
        max_bytes=settings.media_max_bytes,
    )
    app.state.read_gate = ReadConcurrencyGate(settings.max_active_reads)
    app.state.read_job_manager = ReadJobManager(
        max_workers=settings.max_active_reads,
        ttl_seconds=settings.media_ttl_seconds,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allow_origins) if settings.allow_origins != ("*",) else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/api/ocr", response_model=OcrResponse)
    async def run_ocr(image: UploadFile = File(...), lang_hint: str | None = Form(None)) -> OcrResponse:
        request_id = uuid.uuid4().hex
        normalized = await _read_and_normalize_upload(image, app)
        result = await asyncio.to_thread(app.state.ocr_service.recognize, normalized.image, lang_hint)
        return OcrResponse(
            request_id=request_id,
            text=result.text,
            blocks=[OcrBlock(text=block.text, confidence=block.confidence, box=block.box) for block in result.blocks],
            detected_scripts=result.detected_scripts,
        )

    @app.post("/api/read", response_model=ReadResponse)
    async def read_page(
        request: Request,
        image: UploadFile | None = File(None),
        text: str | None = Form(None),
        lang_hint: str | None = Form(None),
        compiler_mode: str | None = Form(None),
        response_mode: str = Form("json"),
    ) -> ReadResponse | StreamingResponse:
        response_mode = response_mode.strip().lower()
        if response_mode not in {"json", "stream"}:
            raise HTTPException(status_code=422, detail="response_mode must be either `json` or `stream`.")
        if image is None and not (text or "").strip():
            raise HTTPException(status_code=422, detail="Provide either `image` or `text`.")
        if image is not None and (text or "").strip():
            raise HTTPException(status_code=422, detail="Provide only one of `image` or `text`, not both.")
        try:
            resolved_compiler_mode = normalize_compiler_mode(compiler_mode, settings.story_compiler_mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not app.state.read_gate.try_acquire():
            raise HTTPException(
                status_code=503,
                detail="The OCR/TTS worker is busy. Retry shortly.",
                headers={"Retry-After": "5"},
            )

        try:
            request_id = uuid.uuid4().hex
            story = None
            if image is not None:
                normalized = await _read_and_normalize_upload(image, app)
                story = await _compile_story_for_image(app, normalized.image, resolved_compiler_mode, lang_hint)
                source_text = story.spoken_script
            else:
                source_text = (text or "").strip()

            if not source_text:
                raise HTTPException(status_code=422, detail="No readable text was produced from the submitted input.")
            if len(source_text) > settings.max_text_chars:
                raise HTTPException(
                    status_code=422,
                    detail=f"Text exceeds the {settings.max_text_chars} character limit.",
                )

            audio = await asyncio.to_thread(
                synthesize_text_in_paragraphs,
                app.state.tts_service,
                source_text,
                lang_hint,
            )
            asset = app.state.media_store.store_audio(
                request_id=request_id,
                audio_bytes=audio.audio_bytes,
                mime_type=audio.mime_type,
                text=source_text,
            )
        except StoryCompilerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            app.state.read_gate.release()

        audio_url = str(request.url_for("get_audio_asset", request_id=request_id))
        if response_mode == "stream":
            return StreamingResponse(
                iter([audio.audio_bytes]),
                media_type=audio.mime_type,
                headers={"Link": f'<{audio_url}>; rel="alternate"'},
            )
        return ReadResponse(
            request_id=request_id,
            text=source_text,
            audio_url=audio_url,
            mime_type=audio.mime_type,
            expires_at=asset.expires_at,
            story=story,
        )

    @app.post("/api/read/jobs", response_model=ReadJobAcceptedResponse, status_code=202)
    async def start_read_job(
        image: UploadFile | None = File(None),
        text: str | None = Form(None),
        lang_hint: str | None = Form(None),
        compiler_mode: str | None = Form(None),
    ) -> ReadJobAcceptedResponse:
        if image is None and not (text or "").strip():
            raise HTTPException(status_code=422, detail="Provide either `image` or `text`.")
        if image is not None and (text or "").strip():
            raise HTTPException(status_code=422, detail="Provide only one of `image` or `text`, not both.")
        try:
            resolved_compiler_mode = normalize_compiler_mode(compiler_mode, settings.story_compiler_mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        normalized_image = None
        input_text = None
        if image is not None:
            normalized = await _read_and_normalize_upload(image, app)
            normalized_image = normalized.image
        else:
            input_text = (text or "").strip()
            if len(input_text) > settings.max_text_chars:
                raise HTTPException(
                    status_code=422,
                    detail=f"Text exceeds the {settings.max_text_chars} character limit.",
                )

        job = app.state.read_job_manager.create_job(
            image=normalized_image,
            text=input_text,
            lang_hint=lang_hint,
            compiler_mode=resolved_compiler_mode,
        )
        await app.state.read_job_manager.enqueue(job.request_id)
        return ReadJobAcceptedResponse(request_id=job.request_id, status=job.status)

    @app.get("/api/read/jobs/{request_id}", response_model=ReadJobStatusResponse)
    async def get_read_job(request: Request, request_id: str) -> ReadJobStatusResponse:
        job = app.state.read_job_manager.get_job(request_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Read job not found or expired.")
        audio_url = None
        if job.status == "completed":
            audio_url = str(request.url_for("get_audio_asset", request_id=request_id))
        return ReadJobStatusResponse(
            request_id=job.request_id,
            status=job.status,  # type: ignore[arg-type]
            stage=job.stage,  # type: ignore[arg-type]
            text=job.text,
            audio_url=audio_url,
            mime_type=job.mime_type,
            expires_at=job.expires_at,
            paragraphs_total=job.paragraphs_total,
            paragraphs_completed=job.paragraphs_completed,
            error=job.error,
            story=job.story,
        )

    @app.get("/media/audio/{request_id}", name="get_audio_asset")
    async def get_audio_asset(request_id: str) -> FileResponse:
        asset = app.state.media_store.get_asset(request_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Audio asset not found or expired.")
        return FileResponse(asset.audio_path, media_type=asset.mime_type, filename=f"{request_id}.wav")

    _register_spa_routes(app)
    return app


async def _compile_story_for_image(
    app: FastAPI,
    image: object,
    compiler_mode: CompilerMode,
    lang_hint: str | None,
) -> StoryCompilation:
    ocr_page = None
    if compiler_mode == "ocr_assisted":
        ocr_page = await asyncio.to_thread(app.state.ocr_service.recognize, image, lang_hint)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                app.state.story_compiler_service.compile_page,
                image=image,
                mode=compiler_mode,
                lang_hint=lang_hint,
                ocr_page=ocr_page,
            ),
            timeout=app.state.settings.story_compiler_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise StoryCompilerError("OpenRead story compilation timed out. Try a clearer page photo.") from exc


async def _read_and_normalize_upload(upload: UploadFile, app: FastAPI):
    settings = app.state.settings
    raw_bytes = await upload.read()
    try:
        return normalize_uploaded_image(
            raw_bytes,
            content_type=upload.content_type,
            max_upload_bytes=settings.max_upload_bytes,
            image_max_side=settings.image_max_side,
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _register_spa_routes(app: FastAPI) -> None:
    settings = app.state.settings
    index_path = settings.web_dist_dir / "index.html"

    @app.get("/", include_in_schema=False, response_model=None)
    async def root():
        if index_path.exists():
            return FileResponse(index_path)
        return JSONResponse({"message": "Frontend build not found. Build web/dist to serve the mobile app."})

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "media/", "healthz")):
            raise HTTPException(status_code=404)
        if not settings.web_dist_dir.exists():
            raise HTTPException(status_code=404, detail="Frontend build not found.")
        candidate = settings.web_dist_dir / Path(full_path)
        if candidate.is_file():
            return FileResponse(candidate)
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404)


async def _media_cleanup_loop(app: FastAPI) -> None:
    interval = app.state.settings.media_cleanup_interval_seconds
    if interval <= 0:
        return
    while True:
        await asyncio.sleep(interval)
        try:
            app.state.media_store.cleanup_expired()
            app.state.media_store.cleanup_to_size_limit()
            app.state.read_job_manager.cleanup_expired()
        except Exception:
            logger.exception("Background media cleanup failed")


def _preload_runtime_dependencies(app: FastAPI) -> None:
    ocr_service = app.state.ocr_service
    preload_ocr = getattr(ocr_service, "preload", None)
    if callable(preload_ocr):
        preload_ocr()

    tts_service = app.state.tts_service
    preload_tts = getattr(tts_service, "preload", None)
    if callable(preload_tts):
        preload_tts()


app = create_app()
