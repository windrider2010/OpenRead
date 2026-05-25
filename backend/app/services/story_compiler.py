from __future__ import annotations

import io
import json
import logging
import re
from typing import Any, Protocol

from PIL import Image
from pydantic import ValidationError

from app.models import CompilerMode, StoryCompilation
from app.services.ocr_service import RecognizedPage

logger = logging.getLogger(__name__)


class StoryCompilerError(RuntimeError):
    """Raised when a page cannot be compiled into a read-aloud story."""


class StoryCompilerService(Protocol):
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
        """Compile a picture-book page image into a structured read-aloud story."""


class GemmaDiagnosticsRecorder(Protocol):
    def record(self, payload: dict[str, Any]) -> object | None:
        """Persist one Gemma diagnostic payload."""


class GemmaStoryCompilerService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        diagnostics_recorder: GemmaDiagnosticsRecorder | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._diagnostics_recorder = diagnostics_recorder

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
        if not self._api_key:
            raise StoryCompilerError("GEMINI_API_KEY is required for OpenRead story compilation.")

        image_bytes = _image_to_jpeg_bytes(image)
        prompt = _build_prompt(mode=mode, lang_hint=lang_hint, ocr_page=ocr_page)
        last_error: Exception | None = None
        raw_outputs: list[dict[str, object]] = []
        validation_errors: list[str] = []

        for attempt in range(2):
            repair_note = ""
            if last_error is not None:
                repair_note = (
                    "\n\nYour previous response did not validate. Return only corrected JSON that matches "
                    f"the schema. Validation error: {last_error}"
                )
            raw = self._generate(image_bytes=image_bytes, prompt=f"{prompt}{repair_note}")
            raw_outputs.append({"attempt": attempt + 1, "output": raw})
            try:
                compiled = _parse_story_json(raw)
                story = _validated_compilation(compiled, expected_mode=mode)
                self._record_diagnostic(
                    request_id=request_id,
                    client_ip=client_ip,
                    mode=mode,
                    lang_hint=lang_hint,
                    status="completed",
                    raw_outputs=raw_outputs,
                    validation_errors=validation_errors,
                    final_story=story,
                    fallback_used=False,
                    error=None,
                )
                return story
            except (ValidationError, ValueError) as exc:
                last_error = exc
                validation_errors.append(str(exc))
                if attempt == 1:
                    fallback = _story_from_text_like_output(raw, mode=mode)
                    if fallback is not None:
                        self._record_diagnostic(
                            request_id=request_id,
                            client_ip=client_ip,
                            mode=mode,
                            lang_hint=lang_hint,
                            status="completed_with_fallback",
                            raw_outputs=raw_outputs,
                            validation_errors=validation_errors,
                            final_story=fallback,
                            fallback_used=True,
                            error=str(exc),
                        )
                        return fallback
                    self._record_diagnostic(
                        request_id=request_id,
                        client_ip=client_ip,
                        mode=mode,
                        lang_hint=lang_hint,
                        status="failed",
                        raw_outputs=raw_outputs,
                        validation_errors=validation_errors,
                        final_story=None,
                        fallback_used=False,
                        error=str(exc),
                    )
                    raise StoryCompilerError(f"Gemma returned invalid story JSON: {exc}") from exc

        raise StoryCompilerError("Gemma did not return a valid story compilation.")

    def _record_diagnostic(
        self,
        *,
        request_id: str | None,
        client_ip: str | None,
        mode: CompilerMode,
        lang_hint: str | None,
        status: str,
        raw_outputs: list[dict[str, object]],
        validation_errors: list[str],
        final_story: StoryCompilation | None,
        fallback_used: bool,
        error: str | None,
    ) -> None:
        if self._diagnostics_recorder is None or request_id is None:
            return
        payload: dict[str, Any] = {
            "request_id": request_id,
            "client_ip": client_ip,
            "model": self._model,
            "compiler_mode": mode,
            "lang_hint": lang_hint,
            "status": status,
            "fallback_used": fallback_used,
            "raw_gemma_outputs": raw_outputs,
            "validation_errors": validation_errors,
            "error": error,
            "final_spoken_script": final_story.spoken_script if final_story is not None else None,
            "story_diagnostics": final_story.diagnostics.model_dump() if final_story is not None else None,
        }
        try:
            self._diagnostics_recorder.record(payload)
        except Exception:
            logger.exception("Failed to record Gemma diagnostics for request %s", request_id)

    def _generate(self, *, image_bytes: bytes, prompt: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise StoryCompilerError(
                "google-genai is unavailable. Run `uv sync --project backend` to install Gemma dependencies."
            ) from exc

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=StoryCompilation.model_json_schema(),
            ),
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise StoryCompilerError("Gemma returned an empty story response.")
        return text


def normalize_compiler_mode(raw_mode: str | None, default_mode: str) -> CompilerMode:
    mode = (raw_mode or default_mode or "gemma_vision").strip().lower()
    if mode in {"gemma_vision", "ocr_assisted"}:
        return mode  # type: ignore[return-value]
    raise ValueError("compiler_mode must be either `gemma_vision` or `ocr_assisted`.")


def story_from_text(text: str, *, mode: CompilerMode = "gemma_vision") -> StoryCompilation:
    cleaned = text.strip()
    if not cleaned:
        raise StoryCompilerError("No readable text was produced from the submitted input.")
    return _story_from_plain_text(
        cleaned,
        mode=mode,
        layout_notes="Text input bypassed image story compilation.",
        warnings=[],
    )


def _story_from_plain_text(
    text: str,
    *,
    mode: CompilerMode,
    layout_notes: str,
    warnings: list[str],
) -> StoryCompilation:
    return StoryCompilation(
        title=None,
        spoken_script=text,
        beats=[
            {
                "beat_id": "text-1",
                "kind": "text",
                "narration": text,
                "source_text": text,
                "layout_region": None,
                "confidence": 1.0,
            }
        ],
        caregiver_cues=[],
        diagnostics={
            "mode": mode,
            "layout_notes": layout_notes,
            "ocr_used": False,
            "warnings": warnings,
        },
    )


def _parse_story_json(raw: str) -> StoryCompilation:
    candidates = _json_candidates(raw)
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return StoryCompilation.model_validate_json(candidate)
        except (ValidationError, ValueError) as exc:
            last_error = exc
            repaired = _repair_json_text(candidate)
            if repaired == candidate:
                continue
            try:
                return StoryCompilation.model_validate_json(repaired)
            except (ValidationError, ValueError) as repaired_exc:
                last_error = repaired_exc
    if last_error is not None:
        raise last_error
    raise ValueError("Gemma did not return a JSON object.")


def _json_candidates(raw: str) -> list[str]:
    cleaned = raw.strip()
    if not cleaned:
        return []

    candidates = [cleaned]

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())

    extracted = _extract_json_object(cleaned)
    if extracted is not None:
        candidates.append(extracted)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None

    in_string = False
    escaped = False
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1].strip()
    return None


def _repair_json_text(raw: str) -> str:
    repaired = raw.strip()
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = repaired.replace("\ufeff", "")
    return repaired


def _story_from_text_like_output(raw: str, *, mode: CompilerMode) -> StoryCompilation | None:
    text = _extract_text_like_output(raw)
    if text is None:
        return None
    return _story_from_plain_text(
        text,
        mode=mode,
        layout_notes="Gemma returned malformed JSON; OpenRead used a deterministic plain-text fallback.",
        warnings=["Gemma returned malformed JSON. Used plain-text fallback for TTS."],
    )


def _extract_text_like_output(raw: str) -> str | None:
    cleaned = raw.strip()
    if not cleaned:
        return None

    for candidate in _json_candidates(cleaned):
        repaired = _repair_json_text(candidate)
        try:
            payload = json.loads(repaired)
        except json.JSONDecodeError:
            continue
        text = _find_text_value(payload)
        if text:
            return text

    if "{" in cleaned or "}" in cleaned:
        return None
    lines = [_clean_text_line(line) for line in cleaned.splitlines()]
    text = " ".join(line for line in lines if line)
    if not text:
        return None
    return text[:4000]


def _clean_text_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^(?:[-•]\s*|\d+[.)]\s*)", "", cleaned)
    return cleaned.strip()


def _find_text_value(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("spoken_script", "narration", "source_text", "text", "content"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        for item in value.values():
            found = _find_text_value(item)
            if found:
                return found
    elif isinstance(value, list):
        parts = [_find_text_value(item) for item in value]
        joined = " ".join(part for part in parts if part)
        if joined:
            return joined.strip()
    elif isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _validated_compilation(compiled: StoryCompilation, *, expected_mode: CompilerMode) -> StoryCompilation:
    spoken_script = compiled.spoken_script.strip()
    if not spoken_script:
        raise ValueError("spoken_script is required.")
    if not compiled.beats:
        raise ValueError("At least one story beat is required.")
    diagnostics = compiled.diagnostics.model_copy(update={"mode": expected_mode})
    return compiled.model_copy(update={"spoken_script": spoken_script, "diagnostics": diagnostics})


def _image_to_jpeg_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def _build_prompt(*, mode: CompilerMode, lang_hint: str | None, ocr_page: RecognizedPage | None) -> str:
    ocr_context = ""
    if mode == "ocr_assisted" and ocr_page is not None:
        ocr_blocks = [
            {
                "text": block.text,
                "confidence": block.confidence,
                "box": block.box,
            }
            for block in ocr_page.blocks
        ]
        ocr_context = (
            "\n\nPaddleOCR context is provided to help you recover exact printed words. "
            "Use the image to determine layout and story order; use OCR only when it agrees with the page.\n"
            f"OCR text:\n{ocr_page.text}\n"
            f"OCR detected scripts: {ocr_page.detected_scripts}\n"
            f"OCR blocks: {ocr_blocks}\n"
        )

    return f"""
You are OpenRead, a careful children picture-book story reader.

Task:
- Analyze the page photo.
- Reconstruct the natural story order even when text is arranged in speech bubbles, sidebars, curves, or non-top-down layouts.
- Read visible printed text faithfully. Correct obvious OCR/layout ordering issues, but do not invent missing printed text.
- Briefly narrate meaningful illustrations only when they help a child understand the page.
- Keep caregiver co-reading cues separate from the child-facing spoken script.
- Return only JSON matching the provided schema.
- Preserve apostrophes, quotation marks, curly quotes, dashes, ellipses, CJK punctuation, and symbols as valid JSON string content.
- Escape every double quote inside `spoken_script`, `narration`, `source_text`, and `cue` values so the response remains parseable JSON.
- Do not wrap JSON in markdown fences, commentary, or explanatory text.

Mode: {mode}
Language hint: {lang_hint or "bilingual"}

Output rules:
- `spoken_script` is the exact child-facing text that will be sent to text-to-speech.
- `beats` must be in the order they should be read aloud.
- `kind=text` beats should preserve visible page wording in `source_text`.
- `kind=illustration` beats should be short, concrete, and based only on visible illustration details.
- `caregiver_cues` are for the adult UI only and must not be included in `spoken_script`.
- `diagnostics.mode` must be "{mode}".
- `diagnostics.ocr_used` must be true only when OCR materially influenced the answer.
- If the page has no readable or narratable content, return an empty `spoken_script` so validation can fail.
{ocr_context}
""".strip()
