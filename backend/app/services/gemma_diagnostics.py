from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class GemmaDiagnosticsStore:
    def __init__(
        self,
        root_dir: Path,
        *,
        ttl_seconds: int,
        log_failures: bool = True,
        log_successes: bool = True,
    ) -> None:
        self.root_dir = root_dir
        self.ttl_seconds = max(60, ttl_seconds)
        self.log_failures = log_failures
        self.log_successes = log_successes
        self._lock = threading.Lock()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def record(self, payload: dict[str, Any]) -> Path | None:
        status = str(payload.get("status") or "")
        is_failure = status == "failed"
        if is_failure and not self.log_failures:
            return None
        if not is_failure and not self.log_successes:
            return None

        request_id = str(payload.get("request_id") or "unknown")
        created_at = datetime.now(UTC)
        record = {
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(seconds=self.ttl_seconds)).isoformat(),
            **payload,
        }
        path = self.root_dir / f"{_safe_filename(request_id)}.json"
        with self._lock:
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def update(self, request_id: str, payload: dict[str, Any]) -> Path | None:
        path = self.root_dir / f"{_safe_filename(request_id)}.json"
        with self._lock:
            if not path.is_file():
                return None
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            _merge_dict(record, payload)
            record["updated_at"] = datetime.now(UTC).isoformat()
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def cleanup_expired(self) -> int:
        removed = 0
        for path in self.root_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if _is_expired(str(payload.get("expires_at") or "")):
                path.unlink(missing_ok=True)
                removed += 1
        return removed


def _safe_filename(raw: str) -> str:
    cleaned = "".join(char for char in raw if char.isalnum() or char in {"-", "_"})
    return cleaned[:128] or "unknown"


def _merge_dict(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        current = target.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            _merge_dict(current, value)
        else:
            target[key] = value


def _is_expired(expires_at: str) -> bool:
    if not expires_at:
        return True
    try:
        expires = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= datetime.now(UTC)
