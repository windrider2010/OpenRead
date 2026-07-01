from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
WEB_DIST_DIR = REPO_DIR / "web" / "dist"

load_dotenv(REPO_DIR / ".env", override=False)


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    items = [item.strip() for item in raw.split(",")]
    cleaned = [item for item in items if item]
    return tuple(cleaned or ["*"])


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "OpenRead API")
    app_env: str = os.getenv("APP_ENV", "development")
    allow_origins: tuple[str, ...] = _csv_env("ALLOW_ORIGINS", "*")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    max_text_chars: int = int(os.getenv("MAX_TEXT_CHARS", "10000"))
    preload_models: bool = _bool_env(
        "PRELOAD_MODELS",
        os.getenv("APP_ENV", "development").strip().lower() == "production",
    )
    preload_ocr: bool = _bool_env("PRELOAD_OCR", False)
    preload_tts: bool = _bool_env("PRELOAD_TTS", True)
    image_max_side: int = int(os.getenv("IMAGE_MAX_SIDE", "2200"))
    media_ttl_seconds: int = int(os.getenv("MEDIA_TTL_SECONDS", "3600"))
    media_cleanup_interval_seconds: int = int(os.getenv("MEDIA_CLEANUP_INTERVAL_SECONDS", "300"))
    media_max_bytes: int = int(os.getenv("MEDIA_MAX_BYTES", str(512 * 1024 * 1024)))
    max_active_reads: int = max(1, int(os.getenv("MAX_ACTIVE_READS", "1")))
    default_zh_voice: str = os.getenv("DEFAULT_ZH_VOICE", "zf_xiaobei")
    default_en_voice: str = os.getenv("DEFAULT_EN_VOICE", "af_heart")
    kokoro_speed: float = float(os.getenv("KOKORO_SPEED", "1.0"))
    kokoro_device: str = os.getenv("KOKORO_DEVICE", "cpu")
    paddle_use_gpu: bool = _bool_env("PADDLE_USE_GPU", False)
    paddle_enable_mkldnn: bool = _bool_env("PADDLE_ENABLE_MKLDNN", False)
    paddle_enable_hpi: bool = _bool_env("PADDLE_ENABLE_HPI", False)
    paddle_cpu_threads: int = max(1, int(os.getenv("PADDLE_CPU_THREADS", "4")))
    espeak_ng_path: str | None = os.getenv("ESPEAK_NG_PATH") or None
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemma_model: str = os.getenv("GEMMA_MODEL", "gemma-4-31b-it")
    cerebras_api_key: str | None = os.getenv("CEREBRAS_API_KEY") or None
    cerebras_base_url: str = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1").rstrip("/")
    cerebras_gemma_model: str = os.getenv("CEREBRAS_GEMMA_MODEL", "gemma-4-31b")
    word_explorer_model: str = os.getenv("WORD_EXPLORER_MODEL", "gemma-4-26b-a4b-it")
    cerebras_word_explorer_model: str = os.getenv("CEREBRAS_WORD_EXPLORER_MODEL", "gemma-4-31b")
    word_explorer_provider: str = os.getenv("WORD_EXPLORER_PROVIDER", "cerebras")
    word_explorer_crop_fraction: float = min(
        1.0,
        max(0.2, float(os.getenv("WORD_EXPLORER_CROP_FRACTION", "0.62"))),
    )
    story_compiler_provider: str = os.getenv("STORY_COMPILER_PROVIDER", "cerebras")
    story_compiler_mode: str = os.getenv("STORY_COMPILER_MODE", "gemma_vision")
    story_compiler_timeout_seconds: int = max(1, int(os.getenv("STORY_COMPILER_TIMEOUT_SECONDS", "90")))
    story_compiler_max_output_tokens: int = max(256, int(os.getenv("STORY_COMPILER_MAX_OUTPUT_TOKENS", "4096")))
    story_compiler_temperature: float = float(os.getenv("STORY_COMPILER_TEMPERATURE", "0.1"))
    openread_log_gemma_failures: bool = _bool_env("OPENREAD_LOG_GEMMA_FAILURES", True)
    openread_log_gemma_successes: bool = _bool_env("OPENREAD_LOG_GEMMA_SUCCESSES", True)
    openread_gemma_log_ttl_seconds: int = max(60, int(os.getenv("OPENREAD_GEMMA_LOG_TTL_SECONDS", "604800")))
    backend_dir: Path = BACKEND_DIR
    repo_dir: Path = REPO_DIR
    web_dist_dir: Path = WEB_DIST_DIR
    media_root: Path = BACKEND_DIR / "var" / "media"
    gemma_diagnostics_root: Path = BACKEND_DIR / "var" / "diagnostics" / "gemma"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.media_root.mkdir(parents=True, exist_ok=True)
    settings.gemma_diagnostics_root.mkdir(parents=True, exist_ok=True)
    return settings
