from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.models import CompilerMode
from app.services.image_pipeline import normalize_uploaded_image
from app.services.ocr_service import PaddleOcrService
from app.services.story_compiler import GemmaStoryCompilerService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark OpenRead story compiler modes over page fixtures.")
    parser.add_argument(
        "--fixture",
        type=Path,
        action="append",
        default=None,
        help="Image fixture to benchmark. Can be passed more than once.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_DIR / "var" / "diagnostics" / "openread",
        help="Directory where benchmark JSON reports are written.",
    )
    parser.add_argument("--lang-hint", default="bilingual", help="Language hint passed to OCR and Gemma.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    fixtures = args.fixture or [BACKEND_DIR / "tests" / "ocr_voice_test.png"]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    compiler = GemmaStoryCompilerService(api_key=settings.gemini_api_key, model=settings.gemma_model)
    ocr_service = PaddleOcrService(
        use_gpu=settings.paddle_use_gpu,
        enable_mkldnn=settings.paddle_enable_mkldnn,
        enable_hpi=settings.paddle_enable_hpi,
        cpu_threads=settings.paddle_cpu_threads,
    )

    reports = []
    for fixture in fixtures:
        fixture_path = fixture.resolve()
        if not fixture_path.is_file():
            raise FileNotFoundError(f"Fixture image not found: {fixture_path}")
        normalized = normalize_uploaded_image(
            fixture_path.read_bytes(),
            content_type=_content_type_for_path(fixture_path),
            max_upload_bytes=settings.max_upload_bytes,
            image_max_side=settings.image_max_side,
        )
        for mode in ("gemma_vision", "ocr_assisted"):
            report = _run_mode(
                compiler=compiler,
                ocr_service=ocr_service,
                fixture_path=fixture_path,
                image=normalized.image,
                mode=mode,
                lang_hint=args.lang_hint,
            )
            reports.append(report)
            output_path = output_dir / f"{fixture_path.stem}-{mode}.json"
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{fixture_path.name} {mode}: {report['latency_seconds']}s, {report['beat_count']} beats")

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary_path={summary_path}")
    return 0


def _run_mode(
    *,
    compiler: GemmaStoryCompilerService,
    ocr_service: PaddleOcrService,
    fixture_path: Path,
    image,
    mode: CompilerMode,
    lang_hint: str,
) -> dict:
    started = perf_counter()
    ocr_page = None
    if mode == "ocr_assisted":
        ocr_page = ocr_service.recognize(image, lang_hint)
    story = compiler.compile_page(image=image, mode=mode, lang_hint=lang_hint, ocr_page=ocr_page)
    latency_seconds = perf_counter() - started
    return {
        "fixture_path": str(fixture_path),
        "compiler_mode": mode,
        "spoken_script": story.spoken_script,
        "beat_count": len(story.beats),
        "caregiver_cue_count": len(story.caregiver_cues),
        "warnings": story.diagnostics.warnings,
        "latency_seconds": round(latency_seconds, 3),
        "ocr_used": story.diagnostics.ocr_used,
        "ocr_text_chars": len(ocr_page.text) if ocr_page is not None else 0,
        "ocr_contributed_useful_text": bool(ocr_page and story.diagnostics.ocr_used and ocr_page.text.strip()),
        "story": story.model_dump(mode="json"),
    }


def _content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


if __name__ == "__main__":
    raise SystemExit(main())
