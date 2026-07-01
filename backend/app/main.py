from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.config import get_settings
from app.models import (
    CompilerMode,
    CompilerProvider,
    HealthResponse,
    OcrBlock,
    OcrResponse,
    ReadJobAcceptedResponse,
    ReadJobStatusResponse,
    ReadResponse,
    StoryCompilation,
    WordExplorerResult,
    WordJobAcceptedResponse,
    WordJobStatusResponse,
)
from app.services.gemma_diagnostics import GemmaDiagnosticsStore
from app.services.image_pipeline import ImageValidationError, crop_center_region, normalize_uploaded_image
from app.services.media_store import MediaStore
from app.services.ocr_service import OcrService, PaddleOcrService
from app.services.story_compiler import (
    CerebrasStoryCompilerService,
    GemmaStoryCompilerService,
    StoryCompilerError,
    StoryCompilerService,
    normalize_compiler_mode,
    normalize_compiler_provider,
    story_from_text,
)
from app.services.tts_service import KokoroTtsService, TtsService, synthesize_text_in_paragraphs
from app.services.word_explorer import (
    CerebrasWordExplorerService,
    GemmaWordExplorerService,
    WordExplorerError,
    WordExplorerService,
)

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
    compiler_provider: CompilerProvider = "cerebras"
    client_ip: str | None = None
    text: str | None = None
    story: StoryCompilation | None = None
    mime_type: str | None = None
    expires_at: str | None = None
    paragraphs_total: int = 0
    paragraphs_completed: int = 0
    error: str | None = None
    request_started_perf: float = field(default_factory=perf_counter, repr=False)
    enqueued_perf: float = field(default_factory=perf_counter, repr=False)
    timings: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class WordJob:
    request_id: str
    status: str
    stage: str
    created_at: datetime
    updated_at: datetime
    image: object | None = None
    lang_hint: str | None = None
    client_ip: str | None = None
    word: WordExplorerResult | None = None
    text: str | None = None
    mime_type: str | None = None
    expires_at: str | None = None
    paragraphs_total: int = 0
    paragraphs_completed: int = 0
    error: str | None = None
    request_started_perf: float = field(default_factory=perf_counter, repr=False)
    enqueued_perf: float = field(default_factory=perf_counter, repr=False)
    timings: dict[str, float] = field(default_factory=dict)


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
        compiler_provider: CompilerProvider,
        client_ip: str | None,
        request_started_perf: float | None = None,
        normalization_ms: float = 0.0,
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
            compiler_provider=compiler_provider,
            client_ip=client_ip,
            request_started_perf=request_started_perf or perf_counter(),
            enqueued_perf=perf_counter(),
            timings={"image_normalize_ms": round(normalization_ms, 3)},
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
        processing_started = perf_counter()
        with self._lock:
            job = self._jobs.get(request_id)
            if job is None:
                return
            job.timings["queue_wait_ms"] = round((processing_started - job.enqueued_perf) * 1000, 3)
            job.status = "processing"
            job.stage = "ocr"
            job.updated_at = datetime.now(UTC)
            image = job.image
            input_text = job.input_text
            lang_hint = job.lang_hint
            compiler_mode = job.compiler_mode
            compiler_provider = job.compiler_provider
            client_ip = job.client_ip
            request_started_perf = job.request_started_perf

        try:
            story_started = perf_counter()
            if image is not None:
                with self._lock:
                    compiling_job = self._jobs.get(request_id)
                    if compiling_job is not None:
                        compiling_job.stage = "story_compile"
                        compiling_job.updated_at = datetime.now(UTC)
                story = await _compile_story_for_image(
                    app,
                    image,
                    compiler_mode,
                    compiler_provider,
                    lang_hint,
                    request_id,
                    client_ip,
                )
                source_text = story.spoken_script
                story_timing_key = "gemma_pipeline_ms"
            else:
                story = story_from_text(input_text or "", mode=compiler_mode)
                source_text = story.spoken_script
                story_timing_key = "text_prepare_ms"
            with self._lock:
                timing_job = self._jobs.get(request_id)
                if timing_job is not None:
                    timing_job.timings[story_timing_key] = _elapsed_ms(story_started)

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

            tts_started = perf_counter()
            audio = await asyncio.to_thread(
                synthesize_text_in_paragraphs,
                app.state.tts_service,
                source_text,
                lang_hint,
                progress_callback=on_tts_progress,
            )
            with self._lock:
                timing_job = self._jobs.get(request_id)
                if timing_job is not None:
                    timing_job.timings["tts_ms"] = _elapsed_ms(tts_started)
            media_store_started = perf_counter()
            asset = app.state.media_store.store_audio(
                request_id=request_id,
                audio_bytes=audio.audio_bytes,
                mime_type=audio.mime_type,
                text=source_text,
            )
            with self._lock:
                timing_job = self._jobs.get(request_id)
                if timing_job is not None:
                    timing_job.timings["media_store_ms"] = _elapsed_ms(media_store_started)
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
                    failed_job.timings["total_ms"] = round((perf_counter() - request_started_perf) * 1000, 3)
                    failed_timings = dict(failed_job.timings)
                else:
                    failed_timings = {}
            _update_pipeline_diagnostics(
                app,
                request_id=request_id,
                status="failed",
                timings=failed_timings,
                error=str(exc),
            )
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
            completed_job.timings["total_ms"] = round((perf_counter() - request_started_perf) * 1000, 3)
            completed_timings = dict(completed_job.timings)
        _update_pipeline_diagnostics(
            app,
            request_id=request_id,
            status="completed",
            timings=completed_timings,
            error=None,
        )


class WordJobManager:
    def __init__(self, *, max_workers: int, ttl_seconds: int) -> None:
        self._max_workers = max(1, max_workers)
        self._ttl_seconds = max(60, ttl_seconds)
        self._jobs: dict[str, WordJob] = {}
        self._lock = threading.Lock()
        self._queue: asyncio.Queue[str] | None = None
        self._workers: list[asyncio.Task[None]] = []

    def create_job(
        self,
        *,
        image: object,
        lang_hint: str | None,
        client_ip: str | None,
        request_started_perf: float | None = None,
        normalization_ms: float = 0.0,
        crop_ms: float = 0.0,
    ) -> WordJob:
        now = datetime.now(UTC)
        job = WordJob(
            request_id=uuid.uuid4().hex,
            status="queued",
            stage="queued",
            created_at=now,
            updated_at=now,
            image=image,
            lang_hint=lang_hint,
            client_ip=client_ip,
            request_started_perf=request_started_perf or perf_counter(),
            enqueued_perf=perf_counter(),
            timings={
                "image_normalize_ms": round(normalization_ms, 3),
                "image_crop_ms": round(crop_ms, 3),
            },
        )
        with self._lock:
            self._jobs[job.request_id] = job
        return job

    async def start(self, app: FastAPI) -> None:
        if self._queue is not None:
            return
        self._queue = asyncio.Queue()
        self._workers = [
            asyncio.create_task(self._worker(app), name=f"word-job-worker-{index}")
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
            raise RuntimeError("Word job manager has not been started.")
        await self._queue.put(request_id)

    def get_job(self, request_id: str) -> WordJob | None:
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
        processing_started = perf_counter()
        with self._lock:
            job = self._jobs.get(request_id)
            if job is None:
                return
            job.timings["queue_wait_ms"] = round((processing_started - job.enqueued_perf) * 1000, 3)
            job.status = "processing"
            job.stage = "word_detect"
            job.updated_at = datetime.now(UTC)
            image = job.image
            lang_hint = job.lang_hint
            client_ip = job.client_ip
            request_started_perf = job.request_started_perf

        try:
            if image is None:
                raise ValueError("Word Explorer requires an image.")
            gemma_started = perf_counter()
            word = await _explore_word_for_image(app, image, lang_hint, request_id, client_ip)
            with self._lock:
                timing_job = self._jobs.get(request_id)
                if timing_job is not None:
                    timing_job.timings["gemma_pipeline_ms"] = _elapsed_ms(gemma_started)
            source_text = word.spoken_script
            if not source_text:
                raise ValueError("No word explanation was produced from the submitted input.")
            max_text_chars = app.state.settings.max_text_chars
            if len(source_text) > max_text_chars:
                raise ValueError(f"Text exceeds the {max_text_chars} character limit.")

            with self._lock:
                tts_job = self._jobs.get(request_id)
                if tts_job is not None:
                    tts_job.word = word
                    tts_job.text = source_text
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

            tts_started = perf_counter()
            audio = await asyncio.to_thread(
                synthesize_text_in_paragraphs,
                app.state.tts_service,
                source_text,
                lang_hint,
                progress_callback=on_tts_progress,
            )
            with self._lock:
                timing_job = self._jobs.get(request_id)
                if timing_job is not None:
                    timing_job.timings["tts_ms"] = _elapsed_ms(tts_started)
            media_store_started = perf_counter()
            asset = app.state.media_store.store_audio(
                request_id=request_id,
                audio_bytes=audio.audio_bytes,
                mime_type=audio.mime_type,
                text=source_text,
            )
            with self._lock:
                timing_job = self._jobs.get(request_id)
                if timing_job is not None:
                    timing_job.timings["media_store_ms"] = _elapsed_ms(media_store_started)
        except Exception as exc:
            logger.exception("Word job %s failed", request_id)
            with self._lock:
                failed_job = self._jobs.get(request_id)
                if failed_job is not None:
                    failed_job.status = "failed"
                    failed_job.stage = "failed"
                    failed_job.error = str(exc)
                    failed_job.updated_at = datetime.now(UTC)
                    failed_job.image = None
                    failed_job.timings["total_ms"] = round((perf_counter() - request_started_perf) * 1000, 3)
                    failed_timings = dict(failed_job.timings)
                else:
                    failed_timings = {}
            _update_pipeline_diagnostics(
                app,
                request_id=request_id,
                status="failed",
                timings=failed_timings,
                error=str(exc),
            )
            return

        with self._lock:
            completed_job = self._jobs.get(request_id)
            if completed_job is None:
                return
            completed_job.status = "completed"
            completed_job.stage = "completed"
            completed_job.updated_at = datetime.now(UTC)
            completed_job.word = word
            completed_job.text = source_text
            completed_job.mime_type = audio.mime_type
            completed_job.expires_at = asset.expires_at
            completed_job.image = None
            completed_job.timings["total_ms"] = round((perf_counter() - request_started_perf) * 1000, 3)
            completed_timings = dict(completed_job.timings)
        _update_pipeline_diagnostics(
            app,
            request_id=request_id,
            status="completed",
            timings=completed_timings,
            error=None,
        )


def create_app(
    *,
    settings=None,
    ocr_service: OcrService | None = None,
    story_compiler_service: StoryCompilerService | None = None,
    cerebras_story_compiler_service: StoryCompilerService | None = None,
    word_explorer_service: WordExplorerService | None = None,
    tts_service: TtsService | None = None,
    media_store: MediaStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.media_store.cleanup_expired()
        app.state.media_store.cleanup_to_size_limit()
        app.state.gemma_diagnostics_store.cleanup_expired()
        app.state.read_job_manager.cleanup_expired()
        app.state.word_job_manager.cleanup_expired()
        await app.state.read_job_manager.start(app)
        await app.state.word_job_manager.start(app)
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
            await app.state.word_job_manager.stop()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.ocr_service = ocr_service or PaddleOcrService(
        use_gpu=settings.paddle_use_gpu,
        enable_mkldnn=settings.paddle_enable_mkldnn,
        enable_hpi=settings.paddle_enable_hpi,
        cpu_threads=settings.paddle_cpu_threads,
    )
    app.state.gemma_diagnostics_store = GemmaDiagnosticsStore(
        settings.gemma_diagnostics_root,
        ttl_seconds=settings.openread_gemma_log_ttl_seconds,
        log_failures=settings.openread_log_gemma_failures,
        log_successes=settings.openread_log_gemma_successes,
    )
    app.state.story_compiler_service = story_compiler_service or GemmaStoryCompilerService(
        api_key=settings.gemini_api_key,
        model=settings.gemma_model,
        max_output_tokens=settings.story_compiler_max_output_tokens,
        temperature=settings.story_compiler_temperature,
        diagnostics_recorder=app.state.gemma_diagnostics_store,
    )
    app.state.cerebras_story_compiler_service = (
        cerebras_story_compiler_service
        or (
            story_compiler_service
            if story_compiler_service is not None
            else CerebrasStoryCompilerService(
                api_key=settings.cerebras_api_key,
                model=settings.cerebras_gemma_model,
                base_url=settings.cerebras_base_url,
                max_output_tokens=settings.story_compiler_max_output_tokens,
                temperature=settings.story_compiler_temperature,
                timeout_seconds=settings.story_compiler_timeout_seconds,
                diagnostics_recorder=app.state.gemma_diagnostics_store,
            )
        )
    )
    resolved_word_provider = normalize_compiler_provider(None, settings.word_explorer_provider)
    if word_explorer_service is not None:
        app.state.word_explorer_service = word_explorer_service
    elif resolved_word_provider == "cerebras":
        app.state.word_explorer_service = CerebrasWordExplorerService(
            api_key=settings.cerebras_api_key,
            model=settings.cerebras_word_explorer_model,
            base_url=settings.cerebras_base_url,
            timeout_seconds=settings.story_compiler_timeout_seconds,
            diagnostics_recorder=app.state.gemma_diagnostics_store,
        )
    else:
        app.state.word_explorer_service = GemmaWordExplorerService(
            api_key=settings.gemini_api_key,
            model=settings.word_explorer_model,
            diagnostics_recorder=app.state.gemma_diagnostics_store,
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
    app.state.word_job_manager = WordJobManager(
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
        compiler_provider: str | None = Form(None),
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
            resolved_compiler_provider = normalize_compiler_provider(
                compiler_provider,
                settings.story_compiler_provider,
            )
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
            client_ip = _client_ip(request)
            story = None
            if image is not None:
                normalized = await _read_and_normalize_upload(image, app)
                story = await _compile_story_for_image(
                    app,
                    normalized.image,
                    resolved_compiler_mode,
                    resolved_compiler_provider,
                    lang_hint,
                    request_id,
                    client_ip,
                )
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
        request: Request,
        image: UploadFile | None = File(None),
        text: str | None = Form(None),
        lang_hint: str | None = Form(None),
        compiler_mode: str | None = Form(None),
        compiler_provider: str | None = Form(None),
    ) -> ReadJobAcceptedResponse:
        request_started_perf = perf_counter()
        if image is None and not (text or "").strip():
            raise HTTPException(status_code=422, detail="Provide either `image` or `text`.")
        if image is not None and (text or "").strip():
            raise HTTPException(status_code=422, detail="Provide only one of `image` or `text`, not both.")
        try:
            resolved_compiler_mode = normalize_compiler_mode(compiler_mode, settings.story_compiler_mode)
            resolved_compiler_provider = normalize_compiler_provider(
                compiler_provider,
                settings.story_compiler_provider,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        normalized_image = None
        input_text = None
        normalization_ms = 0.0
        if image is not None:
            normalization_started = perf_counter()
            normalized = await _read_and_normalize_upload(image, app)
            normalization_ms = _elapsed_ms(normalization_started)
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
            compiler_provider=resolved_compiler_provider,
            client_ip=_client_ip(request),
            request_started_perf=request_started_perf,
            normalization_ms=normalization_ms,
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
            timings=job.timings,
        )

    @app.post("/api/word/jobs", response_model=WordJobAcceptedResponse, status_code=202)
    async def start_word_job(
        request: Request,
        image: UploadFile = File(...),
        lang_hint: str | None = Form(None),
    ) -> WordJobAcceptedResponse:
        request_started_perf = perf_counter()
        normalization_started = perf_counter()
        normalized = await _read_and_normalize_upload(image, app)
        normalization_ms = _elapsed_ms(normalization_started)
        crop_started = perf_counter()
        cropped = crop_center_region(
            normalized.image,
            fraction=settings.word_explorer_crop_fraction,
        )
        crop_ms = _elapsed_ms(crop_started)
        job = app.state.word_job_manager.create_job(
            image=cropped.image,
            lang_hint=lang_hint,
            client_ip=_client_ip(request),
            request_started_perf=request_started_perf,
            normalization_ms=normalization_ms,
            crop_ms=crop_ms,
        )
        await app.state.word_job_manager.enqueue(job.request_id)
        return WordJobAcceptedResponse(request_id=job.request_id, status=job.status)

    @app.get("/api/word/jobs/{request_id}", response_model=WordJobStatusResponse)
    async def get_word_job(request: Request, request_id: str) -> WordJobStatusResponse:
        job = app.state.word_job_manager.get_job(request_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Word job not found or expired.")
        audio_url = None
        if job.status == "completed":
            audio_url = str(request.url_for("get_audio_asset", request_id=request_id))
        return WordJobStatusResponse(
            request_id=job.request_id,
            status=job.status,  # type: ignore[arg-type]
            stage=job.stage,  # type: ignore[arg-type]
            word=job.word,
            text=job.text,
            audio_url=audio_url,
            mime_type=job.mime_type,
            expires_at=job.expires_at,
            paragraphs_total=job.paragraphs_total,
            paragraphs_completed=job.paragraphs_completed,
            error=job.error,
            timings=job.timings,
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
    compiler_provider: CompilerProvider,
    lang_hint: str | None,
    request_id: str,
    client_ip: str | None,
) -> StoryCompilation:
    ocr_page = None
    if compiler_mode == "ocr_assisted":
        ocr_page = await asyncio.to_thread(app.state.ocr_service.recognize, image, lang_hint)
    compiler_service = (
        app.state.cerebras_story_compiler_service
        if compiler_provider == "cerebras"
        else app.state.story_compiler_service
    )
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                compiler_service.compile_page,
                image=image,
                mode=compiler_mode,
                lang_hint=lang_hint,
                ocr_page=ocr_page,
                request_id=request_id,
                client_ip=client_ip,
            ),
            timeout=app.state.settings.story_compiler_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise StoryCompilerError("OpenRead story compilation timed out. Try a clearer page photo.") from exc


async def _explore_word_for_image(
    app: FastAPI,
    image: object,
    lang_hint: str | None,
    request_id: str,
    client_ip: str | None,
) -> WordExplorerResult:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                app.state.word_explorer_service.explore_word,
                image=image,
                lang_hint=lang_hint,
                request_id=request_id,
                client_ip=client_ip,
            ),
            timeout=app.state.settings.story_compiler_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise WordExplorerError("OpenRead word exploration timed out. Try a closer photo.") from exc


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


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip() or None
    if request.client is not None:
        return request.client.host
    return None


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def _update_pipeline_diagnostics(
    app: FastAPI,
    *,
    request_id: str,
    status: str,
    timings: dict[str, float],
    error: str | None,
) -> None:
    try:
        app.state.gemma_diagnostics_store.update(
            request_id,
            {
                "pipeline_status": status,
                "pipeline_error": error,
                "timings": {"pipeline": timings},
            },
        )
    except Exception:
        logger.exception("Failed to update pipeline diagnostics for request %s", request_id)


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
            app.state.gemma_diagnostics_store.cleanup_expired()
            app.state.read_job_manager.cleanup_expired()
            app.state.word_job_manager.cleanup_expired()
        except Exception:
            logger.exception("Background media cleanup failed")


def _preload_runtime_dependencies(app: FastAPI) -> None:
    settings = app.state.settings
    if settings.preload_ocr:
        ocr_service = app.state.ocr_service
        preload_ocr = getattr(ocr_service, "preload", None)
        if callable(preload_ocr):
            preload_ocr()

    if settings.preload_tts:
        tts_service = app.state.tts_service
        preload_tts = getattr(tts_service, "preload", None)
        if callable(preload_tts):
            preload_tts()


app = create_app()
