from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
DEFAULT_FIXTURE_DIR = BACKEND_DIR / "tests" / "fixtures" / "word_explorer"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.image_pipeline import crop_center_region, normalize_uploaded_image
from app.services.word_explorer import GemmaWordExplorerService


class CaptureDiagnosticsRecorder:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def record(self, payload: dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "unknown")
        self.records[request_id] = payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Gemma 4 Word Explorer latency over real page photos.")
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help=f"Directory containing photos. Defaults to {DEFAULT_FIXTURE_DIR.relative_to(REPO_DIR)}.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        action="append",
        default=None,
        help="Individual image fixture. Can be passed more than once.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=None,
        help="Gemma model ID. Can be passed more than once.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to backend/var/diagnostics/word-explorer-benchmark/<timestamp>.",
    )
    parser.add_argument("--lang-hint", default="auto", help="Language hint passed to Gemma.")
    parser.add_argument("--image-max-side", type=int, default=None, help="Maximum normalized image side in pixels.")
    parser.add_argument(
        "--crop-fraction",
        type=float,
        default=None,
        help="Centered crop fraction. Defaults to WORD_EXPLORER_CROP_FRACTION.",
    )
    parser.add_argument(
        "--no-center-crop",
        action="store_true",
        help="Send the full normalized image instead of the production center crop.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required for the Word Explorer benchmark.")

    fixtures = _resolve_fixtures(args.fixture_dir, args.fixture)
    models = _dedupe(args.model or [settings.gemma_model, settings.word_explorer_model])
    image_max_side = args.image_max_side or settings.image_max_side
    crop_fraction = args.crop_fraction if args.crop_fraction is not None else settings.word_explorer_crop_fraction
    if not 0 < crop_fraction <= 1:
        raise SystemExit("--crop-fraction must be greater than 0 and at most 1.")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (args.output_dir or BACKEND_DIR / "var" / "diagnostics" / "word-explorer-benchmark" / timestamp)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    for fixture_path in fixtures:
        raw_bytes = fixture_path.read_bytes()
        normalization_started = perf_counter()
        normalized = normalize_uploaded_image(
            raw_bytes,
            content_type=_content_type_for_path(fixture_path),
            max_upload_bytes=settings.max_upload_bytes,
            image_max_side=image_max_side,
        )
        normalization_ms = _elapsed_ms(normalization_started)
        crop_started = perf_counter()
        model_input = (
            normalized
            if args.no_center_crop
            else crop_center_region(normalized.image, fraction=crop_fraction)
        )
        crop_ms = _elapsed_ms(crop_started)
        original_width, original_height = _image_size(fixture_path)

        for model in models:
            recorder = CaptureDiagnosticsRecorder()
            explorer = GemmaWordExplorerService(
                api_key=settings.gemini_api_key,
                model=model,
                diagnostics_recorder=recorder,
            )
            request_id = f"benchmark-{fixture_path.stem}-{_model_slug(model)}"
            run_started = perf_counter()
            result = None
            error = None
            try:
                result = explorer.explore_word(
                    image=model_input.image.copy(),
                    lang_hint=args.lang_hint,
                    request_id=request_id,
                    client_ip=None,
                )
            except Exception as exc:
                error = str(exc)
            total_ms = _elapsed_ms(run_started)
            diagnostic = recorder.records.get(request_id, {})
            timings = diagnostic.get("timings") if isinstance(diagnostic.get("timings"), dict) else {}
            run = {
                "fixture": fixture_path.name,
                "fixture_path": _report_path(fixture_path),
                "original_bytes": len(raw_bytes),
                "original_width": original_width,
                "original_height": original_height,
                "normalized_width": normalized.width,
                "normalized_height": normalized.height,
                "model_input_width": model_input.width,
                "model_input_height": model_input.height,
                "image_max_side": image_max_side,
                "normalization_ms": normalization_ms,
                "center_crop_fraction": None if args.no_center_crop else crop_fraction,
                "crop_ms": crop_ms,
                "model": model,
                "status": "completed" if result is not None else "failed",
                "selected_word": result.selected_word if result is not None else None,
                "kid_explanation": result.kid_explanation if result is not None else None,
                "confidence": result.confidence if result is not None else None,
                "spoken_script": result.spoken_script if result is not None else None,
                "warnings": result.diagnostics.warnings if result is not None else [],
                "error": error,
                "benchmark_total_ms": total_ms,
                "timings": timings,
                "raw_gemma_outputs": diagnostic.get("raw_gemma_outputs", []),
                "validation_errors": diagnostic.get("validation_errors", []),
            }
            runs.append(run)
            print(_run_line(run), flush=True)

    aggregates = [_aggregate_model(model, runs) for model in models]
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "fixture_count": len(fixtures),
        "models": models,
        "image_max_side": image_max_side,
        "center_crop_fraction": None if args.no_center_crop else crop_fraction,
        "runs": runs,
        "aggregates": aggregates,
    }
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "summary.json").write_text(
        json.dumps(aggregates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(output_dir / "runs.csv", runs)
    print(f"output_dir={output_dir}")
    for aggregate in aggregates:
        print(
            f"{aggregate['model']}: {aggregate['success_count']}/{aggregate['run_count']} succeeded, "
            f"median={aggregate['median_service_total_ms']}ms, mean={aggregate['mean_service_total_ms']}ms"
        )
    return 0


def _resolve_fixtures(fixture_dir: Path | None, explicit: list[Path] | None) -> list[Path]:
    fixtures = [path.resolve() for path in explicit or []]
    if fixture_dir is not None:
        directory = fixture_dir.resolve()
        if not directory.is_dir():
            raise FileNotFoundError(f"Fixture directory not found: {directory}")
        fixtures.extend(
            sorted(
                path.resolve()
                for path in directory.iterdir()
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            )
        )
    fixtures = list(dict.fromkeys(fixtures))
    if not fixtures:
        raise ValueError("Provide --fixture-dir or at least one --fixture.")
    missing = [path for path in fixtures if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Fixture image not found: {missing[0]}")
    return fixtures


def _aggregate_model(model: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    model_runs = [run for run in runs if run["model"] == model]
    successful = [run for run in model_runs if run["status"] == "completed"]
    latencies = [float(run["timings"].get("service_total_ms", run["benchmark_total_ms"])) for run in successful]
    generation_latencies = [
        sum(float(attempt.get("generation_ms", 0.0)) for attempt in run["timings"].get("attempts", []))
        for run in successful
    ]
    return {
        "model": model,
        "run_count": len(model_runs),
        "success_count": len(successful),
        "failure_count": len(model_runs) - len(successful),
        "mean_service_total_ms": _mean_or_none(latencies),
        "median_service_total_ms": _median_or_none(latencies),
        "min_service_total_ms": round(min(latencies), 3) if latencies else None,
        "max_service_total_ms": round(max(latencies), 3) if latencies else None,
        "mean_generation_ms": _mean_or_none(generation_latencies),
        "total_attempts": sum(len(run["timings"].get("attempts", [])) for run in model_runs),
        "fallback_count": sum(1 for run in successful if run["warnings"]),
        "selected_words": {run["fixture"]: run["selected_word"] for run in model_runs},
        "errors": {run["fixture"]: run["error"] for run in model_runs if run["error"]},
    }


def _write_csv(path: Path, runs: list[dict[str, Any]]) -> None:
    fieldnames = [
        "fixture",
        "model",
        "status",
        "selected_word",
        "confidence",
        "original_width",
        "original_height",
        "original_bytes",
        "normalized_width",
        "normalized_height",
        "model_input_width",
        "model_input_height",
        "normalization_ms",
        "center_crop_fraction",
        "crop_ms",
        "image_encode_ms",
        "generation_ms",
        "parse_validation_ms",
        "service_total_ms",
        "attempt_count",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            attempts = run["timings"].get("attempts", [])
            writer.writerow(
                {
                    "fixture": run["fixture"],
                    "model": run["model"],
                    "status": run["status"],
                    "selected_word": run["selected_word"],
                    "confidence": run["confidence"],
                    "original_width": run["original_width"],
                    "original_height": run["original_height"],
                    "original_bytes": run["original_bytes"],
                    "normalized_width": run["normalized_width"],
                    "normalized_height": run["normalized_height"],
                    "model_input_width": run["model_input_width"],
                    "model_input_height": run["model_input_height"],
                    "normalization_ms": run["normalization_ms"],
                    "center_crop_fraction": run["center_crop_fraction"],
                    "crop_ms": run["crop_ms"],
                    "image_encode_ms": run["timings"].get("image_encode_ms"),
                    "generation_ms": round(sum(float(item.get("generation_ms", 0.0)) for item in attempts), 3),
                    "parse_validation_ms": round(
                        sum(float(item.get("parse_validation_ms", 0.0)) for item in attempts),
                        3,
                    ),
                    "service_total_ms": run["timings"].get("service_total_ms"),
                    "attempt_count": len(attempts),
                    "error": run["error"],
                }
            )


def _run_line(run: dict[str, Any]) -> str:
    service_ms = run["timings"].get("service_total_ms", run["benchmark_total_ms"])
    return (
        f"{run['fixture']} {run['model']}: {run['status']} "
        f"word={run['selected_word']!r} confidence={run['confidence']} total={service_ms}ms"
    )


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def _model_slug(model: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in model).strip("-")


def _report_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_DIR).as_posix()
    except ValueError:
        return str(path)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def _mean_or_none(values: list[float]) -> float | None:
    return round(statistics.mean(values), 3) if values else None


def _median_or_none(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


if __name__ == "__main__":
    raise SystemExit(main())
