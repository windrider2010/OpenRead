from __future__ import annotations

import io
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.models import CompilerMode, CompilerProvider, StoryCompilation, WordExplorerResult
from app.services.media_store import MediaStore
from app.services.ocr_service import RecognizedBlock, RecognizedPage
from app.services.tts_service import SynthesizedAudio
from app.services.word_explorer import WordExplorerError


class FakeOcrService:
    def __init__(self) -> None:
        self.calls = 0

    def recognize(self, image: Image.Image, lang_hint: str | None = None) -> RecognizedPage:
        self.calls += 1
        return RecognizedPage(
            text="hello world",
            blocks=[
                RecognizedBlock(text="hello", confidence=0.99, box=[[0, 0], [1, 0], [1, 1], [0, 1]]),
                RecognizedBlock(text="world", confidence=0.98, box=[[2, 2], [3, 2], [3, 3], [2, 3]]),
            ],
            detected_scripts=["latin"],
        )


class FakeTtsService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize_text(self, text: str, lang_hint: str | None = None) -> SynthesizedAudio:
        self.calls.append(text)
        return SynthesizedAudio(audio_bytes=b"RIFFfakewav", mime_type="audio/wav", sample_rate=24000)

    def preload(self) -> None:
        self.preloaded = True


class FakePreloadOcrService(FakeOcrService):
    def __init__(self) -> None:
        super().__init__()
        self.preloaded = False

    def preload(self) -> None:
        self.preloaded = True


class FakePreloadTtsService(FakeTtsService):
    def __init__(self) -> None:
        super().__init__()
        self.preloaded = False

    def preload(self) -> None:
        self.preloaded = True


class BlockingTtsService(FakeTtsService):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def synthesize_text(self, text: str, lang_hint: str | None = None) -> SynthesizedAudio:
        self.started.set()
        self.release.wait(timeout=1)
        return super().synthesize_text(text, lang_hint)


class FakeStoryCompilerService:
    def __init__(self, *, provider: CompilerProvider = "google_genai") -> None:
        self.provider = provider
        self.calls: list[CompilerMode] = []
        self.ocr_pages: list[RecognizedPage | None] = []
        self.request_ids: list[str | None] = []
        self.client_ips: list[str | None] = []

    def compile_page(
        self,
        *,
        image: Image.Image,
        mode: CompilerMode,
        lang_hint: str | None = None,
        ocr_page: RecognizedPage | None = None,
        request_id: str | None = None,
        client_ip: str | None = None,
    ) -> StoryCompilation:
        self.calls.append(mode)
        self.ocr_pages.append(ocr_page)
        self.request_ids.append(request_id)
        self.client_ips.append(client_ip)
        return _sample_story(mode=mode, ocr_used=ocr_page is not None)


class FakeWordExplorerService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0
        self.request_ids: list[str | None] = []
        self.client_ips: list[str | None] = []
        self.image_sizes: list[tuple[int, int]] = []

    def explore_word(
        self,
        *,
        image: Image.Image,
        lang_hint: str | None = None,
        request_id: str | None = None,
        client_ip: str | None = None,
    ) -> WordExplorerResult:
        self.calls += 1
        self.image_sizes.append(image.size)
        self.request_ids.append(request_id)
        self.client_ips.append(client_ip)
        if self.error is not None:
            raise self.error
        return _sample_word()


def _sample_story(*, mode: CompilerMode = "gemma_vision", ocr_used: bool = False) -> StoryCompilation:
    return StoryCompilation(
        title="Moon Page",
        spoken_script="Hello world. The moon glows over the little boat.",
        beats=[
            {
                "beat_id": "text-1",
                "kind": "text",
                "narration": "Hello world.",
                "source_text": "Hello world.",
                "layout_region": "top-left",
                "confidence": 0.98,
            },
            {
                "beat_id": "illustration-1",
                "kind": "illustration",
                "narration": "The moon glows over the little boat.",
                "source_text": None,
                "layout_region": "center",
                "confidence": 0.84,
            },
        ],
        caregiver_cues=[
            {
                "cue_id": "cue-1",
                "after_beat_id": "illustration-1",
                "cue": "Ask what the child thinks will happen next.",
                "purpose": "prediction",
            }
        ],
        diagnostics={
            "mode": mode,
            "layout_notes": "Read top-left text before the central illustration.",
            "ocr_used": ocr_used,
            "warnings": [],
        },
    )


def _sample_word() -> WordExplorerResult:
    return WordExplorerResult(
        selected_word="brave",
        normalized_word="brave",
        language="English",
        part_of_speech="describing word",
        pronunciation_hint="brayv",
        kid_explanation="Brave means you try even when something feels a little scary.",
        example_sentence="The brave rabbit hopped across the bridge.",
        page_context="The word is centered in a sentence near the fox.",
        spoken_script=(
            "The word is brave. Brave means you try even when something feels a little scary. "
            "The brave rabbit hopped across the bridge."
        ),
        confidence=0.92,
        diagnostics={
            "mode": "gemma_vision",
            "pointing_evidence": "The word brave crosses the center of the crop.",
            "layout_region": "center",
            "warnings": [],
        },
    )


def _make_client(tmp_path: Path, *, settings: Settings | None = None) -> TestClient:
    app = create_app(
        settings=settings,
        ocr_service=FakeOcrService(),
        story_compiler_service=FakeStoryCompilerService(),
        word_explorer_service=FakeWordExplorerService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    return TestClient(app)


def _sample_image_bytes() -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (120, 60), color=(255, 255, 255))
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _wait_for_job_completion(client: TestClient, request_id: str) -> dict:
    for _ in range(50):
        response = client.get(f"/api/read/jobs/{request_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for read job {request_id}")


def _wait_for_word_job_completion(client: TestClient, request_id: str) -> dict:
    for _ in range(50):
        response = client.get(f"/api/word/jobs/{request_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for word job {request_id}")


def test_ocr_endpoint_returns_text_and_blocks(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/ocr",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        data={"lang_hint": "bilingual"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "hello world"
    assert payload["detected_scripts"] == ["latin"]
    assert len(payload["blocks"]) == 2


def test_read_endpoint_rejects_image_and_text_together(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/read",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        data={"text": "hello"},
    )
    assert response.status_code == 422
    assert "only one" in response.json()["detail"]


def test_read_endpoint_json_mode_returns_audio_url_text_and_story(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/read",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        data={"lang_hint": "bilingual"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "Hello world. The moon glows over the little boat."
    assert payload["mime_type"] == "audio/wav"
    assert payload["audio_url"].endswith(f'/media/audio/{payload["request_id"]}')
    assert payload["story"]["beats"][1]["kind"] == "illustration"
    assert payload["story"]["caregiver_cues"][0]["purpose"] == "prediction"


def test_read_endpoint_passes_request_id_and_forwarded_ip_to_compiler(tmp_path: Path) -> None:
    compiler = FakeStoryCompilerService()
    app = create_app(
        ocr_service=FakeOcrService(),
        story_compiler_service=compiler,
        word_explorer_service=FakeWordExplorerService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    client = TestClient(app)

    response = client.post(
        "/api/read",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        headers={"x-forwarded-for": "203.0.113.42, 10.0.0.1"},
    )

    assert response.status_code == 200
    assert compiler.request_ids == [response.json()["request_id"]]
    assert compiler.client_ips == ["203.0.113.42"]


def test_read_endpoint_sends_only_spoken_script_to_tts(tmp_path: Path) -> None:
    tts = FakeTtsService()
    app = create_app(
        ocr_service=FakeOcrService(),
        story_compiler_service=FakeStoryCompilerService(),
        word_explorer_service=FakeWordExplorerService(),
        tts_service=tts,
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    client = TestClient(app)

    response = client.post(
        "/api/read",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        data={"lang_hint": "bilingual"},
    )

    assert response.status_code == 200
    assert tts.calls == ["Hello world. The moon glows over the little boat."]
    assert "Ask what the child thinks" not in tts.calls[0]


def test_read_endpoint_stream_mode_returns_audio_and_link(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/read",
        data={"text": "hello", "response_mode": "stream"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["link"].startswith("<http://testserver/media/audio/")
    assert response.content == b"RIFFfakewav"


def test_read_job_endpoint_returns_completed_status_audio_url_and_story(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        start_response = client.post(
            "/api/read/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
            data={"lang_hint": "bilingual"},
        )
        assert start_response.status_code == 202
        request_id = start_response.json()["request_id"]

        payload = _wait_for_job_completion(client, request_id)
        assert payload["status"] == "completed"
        assert payload["stage"] == "completed"
        assert "moon glows" in payload["text"]
        assert payload["mime_type"] == "audio/wav"
        assert payload["audio_url"].endswith(f"/media/audio/{request_id}")
        assert payload["story"]["title"] == "Moon Page"
        assert payload["story"]["caregiver_cues"][0]["cue"].startswith("Ask what")
        assert payload["paragraphs_total"] >= 1
        assert payload["paragraphs_completed"] == payload["paragraphs_total"]
        assert payload["timings"]["image_normalize_ms"] >= 0
        assert payload["timings"]["gemma_pipeline_ms"] >= 0
        assert payload["timings"]["tts_ms"] >= 0
        assert payload["timings"]["total_ms"] >= payload["timings"]["tts_ms"]


def test_read_job_endpoint_surfaces_story_before_audio_completion(tmp_path: Path) -> None:
    blocking_tts = BlockingTtsService()
    app = create_app(
        ocr_service=FakeOcrService(),
        story_compiler_service=FakeStoryCompilerService(),
        word_explorer_service=FakeWordExplorerService(),
        tts_service=blocking_tts,
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )

    with TestClient(app) as client:
        start_response = client.post(
            "/api/read/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
            data={"lang_hint": "bilingual"},
        )
        assert start_response.status_code == 202
        request_id = start_response.json()["request_id"]
        assert blocking_tts.started.wait(timeout=1)

        status_response = client.get(f"/api/read/jobs/{request_id}")
        assert status_response.status_code == 200
        payload = status_response.json()
        assert payload["status"] == "processing"
        assert payload["stage"] == "tts"
        assert "moon glows" in payload["text"]
        assert payload["story"]["beats"][0]["layout_region"] == "top-left"
        assert payload["paragraphs_total"] == 1
        assert payload["paragraphs_completed"] == 0

        blocking_tts.release.set()
        completed = _wait_for_job_completion(client, request_id)
        assert completed["status"] == "completed"


def test_read_job_endpoint_ocr_assisted_mode_invokes_ocr_before_compiler(tmp_path: Path) -> None:
    ocr = FakeOcrService()
    compiler = FakeStoryCompilerService()
    app = create_app(
        ocr_service=ocr,
        story_compiler_service=compiler,
        word_explorer_service=FakeWordExplorerService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )

    with TestClient(app) as client:
        start_response = client.post(
            "/api/read/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
            data={"compiler_mode": "ocr_assisted"},
        )
        assert start_response.status_code == 202
        completed = _wait_for_job_completion(client, start_response.json()["request_id"])

    assert completed["status"] == "completed"
    assert ocr.calls == 1
    assert compiler.calls == ["ocr_assisted"]
    assert compiler.ocr_pages[0] is not None
    assert completed["story"]["diagnostics"]["ocr_used"] is True


def test_read_job_endpoint_defaults_to_cerebras_provider(tmp_path: Path) -> None:
    google_compiler = FakeStoryCompilerService(provider="google_genai")
    cerebras_compiler = FakeStoryCompilerService(provider="cerebras")
    app = create_app(
        ocr_service=FakeOcrService(),
        story_compiler_service=google_compiler,
        cerebras_story_compiler_service=cerebras_compiler,
        word_explorer_service=FakeWordExplorerService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )

    with TestClient(app) as client:
        start_response = client.post(
            "/api/read/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        )
        assert start_response.status_code == 202
        completed = _wait_for_job_completion(client, start_response.json()["request_id"])

    assert completed["status"] == "completed"
    assert google_compiler.calls == []
    assert cerebras_compiler.calls == ["gemma_vision"]


def test_read_job_endpoint_google_provider_can_be_selected_by_env(tmp_path: Path) -> None:
    google_compiler = FakeStoryCompilerService(provider="google_genai")
    cerebras_compiler = FakeStoryCompilerService(provider="cerebras")
    settings = Settings(story_compiler_provider="google_genai")
    app = create_app(
        settings=settings,
        ocr_service=FakeOcrService(),
        story_compiler_service=google_compiler,
        cerebras_story_compiler_service=cerebras_compiler,
        word_explorer_service=FakeWordExplorerService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )

    with TestClient(app) as client:
        start_response = client.post(
            "/api/read/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        )
        assert start_response.status_code == 202
        completed = _wait_for_job_completion(client, start_response.json()["request_id"])

    assert completed["status"] == "completed"
    assert google_compiler.calls == ["gemma_vision"]
    assert cerebras_compiler.calls == []


def test_read_job_endpoint_request_can_override_compiler_provider(tmp_path: Path) -> None:
    google_compiler = FakeStoryCompilerService(provider="google_genai")
    cerebras_compiler = FakeStoryCompilerService(provider="cerebras")
    settings = Settings(story_compiler_provider="google_genai")
    app = create_app(
        settings=settings,
        ocr_service=FakeOcrService(),
        story_compiler_service=google_compiler,
        cerebras_story_compiler_service=cerebras_compiler,
        word_explorer_service=FakeWordExplorerService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )

    with TestClient(app) as client:
        start_response = client.post(
            "/api/read/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
            data={"compiler_provider": "cerebras"},
        )
        assert start_response.status_code == 202
        completed = _wait_for_job_completion(client, start_response.json()["request_id"])

    assert completed["status"] == "completed"
    assert google_compiler.calls == []
    assert cerebras_compiler.calls == ["gemma_vision"]


def test_read_endpoint_rejects_invalid_compiler_provider(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/read",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        data={"compiler_provider": "bad-provider"},
    )
    assert response.status_code == 422
    assert "compiler_provider" in response.json()["detail"]


def test_read_job_endpoint_rejects_empty_input(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    start_response = client.post("/api/read/jobs", data={"text": "   "})
    assert start_response.status_code == 422


def test_read_job_endpoint_rejects_invalid_compiler_mode(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    start_response = client.post("/api/read/jobs", data={"text": "hello", "compiler_mode": "bad"})
    assert start_response.status_code == 422


def test_audio_asset_endpoint_serves_cached_wav(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    read_response = client.post("/api/read", data={"text": "hello"})
    request_id = read_response.json()["request_id"]
    response = client.get(f"/media/audio/{request_id}")
    assert response.status_code == 200
    assert response.content == b"RIFFfakewav"


def test_word_job_endpoint_returns_completed_status_audio_url_and_word(tmp_path: Path) -> None:
    word_service = FakeWordExplorerService()
    tts = FakeTtsService()
    settings = Settings(word_explorer_crop_fraction=0.5)
    app = create_app(
        settings=settings,
        ocr_service=FakeOcrService(),
        story_compiler_service=FakeStoryCompilerService(),
        word_explorer_service=word_service,
        tts_service=tts,
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )

    with TestClient(app) as client:
        start_response = client.post(
            "/api/word/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
            data={"lang_hint": "bilingual"},
            headers={"x-forwarded-for": "203.0.113.45, 10.0.0.1"},
        )
        assert start_response.status_code == 202
        request_id = start_response.json()["request_id"]
        payload = _wait_for_word_job_completion(client, request_id)

    assert payload["status"] == "completed"
    assert payload["stage"] == "completed"
    assert payload["audio_url"].endswith(f"/media/audio/{request_id}")
    assert payload["word"]["selected_word"] == "brave"
    assert payload["word"]["kid_explanation"].startswith("Brave means")
    assert payload["paragraphs_total"] >= 1
    assert payload["paragraphs_completed"] == payload["paragraphs_total"]
    assert payload["timings"]["image_normalize_ms"] >= 0
    assert payload["timings"]["image_crop_ms"] >= 0
    assert payload["timings"]["gemma_pipeline_ms"] >= 0
    assert payload["timings"]["tts_ms"] >= 0
    assert payload["timings"]["total_ms"] >= payload["timings"]["tts_ms"]
    assert tts.calls == [_sample_word().spoken_script]
    assert "pointing_evidence" not in tts.calls[0]
    assert word_service.request_ids == [request_id]
    assert word_service.client_ips == ["203.0.113.45"]
    assert word_service.image_sizes == [(60, 30)]
    assert app.state.word_job_manager.get_job(request_id).image is None


def test_word_job_endpoint_fails_cleanly_when_centered_word_is_unclear(tmp_path: Path) -> None:
    app = create_app(
        ocr_service=FakeOcrService(),
        story_compiler_service=FakeStoryCompilerService(),
        word_explorer_service=FakeWordExplorerService(
            error=WordExplorerError("OpenRead could not identify the word in the center.")
        ),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )

    with TestClient(app) as client:
        start_response = client.post(
            "/api/word/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        )
        assert start_response.status_code == 202
        payload = _wait_for_word_job_completion(client, start_response.json()["request_id"])

    assert payload["status"] == "failed"
    assert payload["stage"] == "failed"
    assert "could not identify the word" in payload["error"]


def test_read_endpoint_returns_busy_when_gate_is_full(tmp_path: Path) -> None:
    app = create_app(
        ocr_service=FakeOcrService(),
        story_compiler_service=FakeStoryCompilerService(),
        word_explorer_service=FakeWordExplorerService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    app.state.read_gate._active = 1
    client = TestClient(app)
    response = client.post("/api/read", data={"text": "hello"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_read_endpoint_rejects_overlong_text(tmp_path: Path) -> None:
    settings = Settings(max_text_chars=4)
    client = _make_client(tmp_path, settings=settings)
    response = client.post("/api/read", data={"text": "hello"})
    assert response.status_code == 422
    assert "character limit" in response.json()["detail"]


def test_app_preloads_only_tts_by_default_when_enabled(tmp_path: Path) -> None:
    ocr = FakePreloadOcrService()
    tts = FakePreloadTtsService()
    settings = Settings(preload_models=True)
    app = create_app(
        settings=settings,
        ocr_service=ocr,
        story_compiler_service=FakeStoryCompilerService(),
        word_explorer_service=FakeWordExplorerService(),
        tts_service=tts,
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    with TestClient(app):
        pass
    assert ocr.preloaded is False
    assert tts.preloaded is True


def test_app_can_preload_ocr_when_enabled(tmp_path: Path) -> None:
    ocr = FakePreloadOcrService()
    tts = FakePreloadTtsService()
    settings = Settings(preload_models=True, preload_ocr=True, preload_tts=False)
    app = create_app(
        settings=settings,
        ocr_service=ocr,
        story_compiler_service=FakeStoryCompilerService(),
        word_explorer_service=FakeWordExplorerService(),
        tts_service=tts,
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    with TestClient(app):
        pass
    assert ocr.preloaded is True
    assert tts.preloaded is False
