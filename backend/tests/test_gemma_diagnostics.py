from __future__ import annotations

import json
from pathlib import Path

from app.services.gemma_diagnostics import GemmaDiagnosticsStore


def test_gemma_diagnostics_store_records_json_without_images(tmp_path: Path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800)

    path = store.record(
        {
            "request_id": "abc123",
            "client_ip": "203.0.113.10",
            "status": "completed",
            "raw_gemma_outputs": [{"attempt": 1, "output": '{"spoken_script":"hello"}'}],
        }
    )

    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["request_id"] == "abc123"
    assert payload["client_ip"] == "203.0.113.10"
    assert payload["raw_gemma_outputs"][0]["output"] == '{"spoken_script":"hello"}'
    assert "image" not in payload
    assert "expires_at" in payload


def test_gemma_diagnostics_store_respects_logging_flags(tmp_path: Path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800, log_successes=False, log_failures=True)

    assert store.record({"request_id": "success", "status": "completed"}) is None
    assert store.record({"request_id": "failed", "status": "failed"}) is not None
    assert not (tmp_path / "gemma" / "success.json").exists()
    assert (tmp_path / "gemma" / "failed.json").exists()


def test_gemma_diagnostics_store_merges_pipeline_timings(tmp_path: Path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800)
    path = store.record(
        {
            "request_id": "timed",
            "status": "completed",
            "timings": {"service_total_ms": 1250.0},
        }
    )
    assert path is not None

    updated = store.update(
        "timed",
        {
            "pipeline_status": "completed",
            "timings": {"pipeline": {"tts_ms": 400.0, "total_ms": 1800.0}},
        },
    )

    assert updated == path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["timings"]["service_total_ms"] == 1250.0
    assert payload["timings"]["pipeline"]["tts_ms"] == 400.0
    assert payload["timings"]["pipeline"]["total_ms"] == 1800.0
    assert payload["pipeline_status"] == "completed"
    assert "updated_at" in payload


def test_gemma_diagnostics_store_creates_record_for_pipeline_failure(tmp_path: Path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800)

    updated = store.update(
        "timed-out",
        {
            "pipeline_status": "failed",
            "pipeline_error": "OpenRead story compilation timed out.",
            "timings": {"pipeline": {"total_ms": 90000.0}},
        },
    )

    assert updated == tmp_path / "gemma" / "timed-out.json"
    payload = json.loads(updated.read_text(encoding="utf-8"))
    assert payload["request_id"] == "timed-out"
    assert payload["status"] == "failed"
    assert payload["pipeline_status"] == "failed"
    assert payload["pipeline_error"] == "OpenRead story compilation timed out."


def test_gemma_diagnostics_store_preserves_failed_pipeline_when_gemma_finishes_late(tmp_path: Path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800)
    store.update(
        "late-result",
        {
            "pipeline_status": "failed",
            "pipeline_error": "OpenRead story compilation timed out.",
            "timings": {"pipeline": {"total_ms": 90000.0}},
        },
    )

    path = store.record(
        {
            "request_id": "late-result",
            "status": "completed",
            "timings": {"service_total_ms": 938000.0},
            "raw_gemma_outputs": [{"attempt": 1, "output": "{}"}],
        }
    )

    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["late_gemma_status"] == "completed"
    assert payload["pipeline_status"] == "failed"
    assert payload["pipeline_error"] == "OpenRead story compilation timed out."
    assert payload["timings"]["pipeline"]["total_ms"] == 90000.0
    assert payload["timings"]["service_total_ms"] == 938000.0


def test_gemma_diagnostics_store_cleans_expired_records(tmp_path: Path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=60)
    path = store.record({"request_id": "old", "status": "completed"})
    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expires_at"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(payload), encoding="utf-8")

    removed = store.cleanup_expired()

    assert removed == 1
    assert not path.exists()
