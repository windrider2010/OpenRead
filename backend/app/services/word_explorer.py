from __future__ import annotations

import logging
from base64 import b64encode
from time import perf_counter
from typing import Any, Protocol

import httpx
from PIL import Image
from pydantic import ValidationError

from app.models import CompilerProvider, TtsSegment, WordExplorerResult
from app.services.story_compiler import (
    StoryCompilerError,
    _extract_text_like_output,
    _image_to_jpeg_bytes,
    _json_candidates,
    _repair_json_text,
    _strict_json_schema,
)

logger = logging.getLogger(__name__)


class WordExplorerError(RuntimeError):
    """Raised when the centered word cannot be explained."""


class WordExplorerService(Protocol):
    def explore_word(
        self,
        *,
        image: Image.Image,
        lang_hint: str | None = None,
        request_id: str | None = None,
        client_ip: str | None = None,
    ) -> WordExplorerResult:
        """Find the word nearest the image center and explain it for a child."""


class GemmaDiagnosticsRecorder(Protocol):
    def record(self, payload: dict[str, Any]) -> object | None:
        """Persist one Gemma diagnostic payload."""


class GemmaWordExplorerService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        provider: CompilerProvider = "google_genai",
        diagnostics_recorder: GemmaDiagnosticsRecorder | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._provider = provider
        self._missing_api_key_message = "GEMINI_API_KEY is required for OpenRead word exploration."
        self._diagnostics_recorder = diagnostics_recorder

    def explore_word(
        self,
        *,
        image: Image.Image,
        lang_hint: str | None = None,
        request_id: str | None = None,
        client_ip: str | None = None,
    ) -> WordExplorerResult:
        if not self._api_key:
            raise WordExplorerError(self._missing_api_key_message)

        service_started = perf_counter()
        image_encode_started = perf_counter()
        image_bytes = _image_to_jpeg_bytes(image)
        timings: dict[str, Any] = {
            "input_width": image.width,
            "input_height": image.height,
            "encoded_image_bytes": len(image_bytes),
            "image_encode_ms": _elapsed_ms(image_encode_started),
            "attempts": [],
        }
        prompt = _build_word_prompt(lang_hint=lang_hint)
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
            attempt_timing: dict[str, Any] = {"attempt": attempt + 1}
            generation_started = perf_counter()
            try:
                raw = self._generate(image_bytes=image_bytes, prompt=f"{prompt}{repair_note}")
            except Exception as exc:
                attempt_timing["generation_ms"] = _elapsed_ms(generation_started)
                attempt_timing["error"] = str(exc)
                timings["attempts"].append(attempt_timing)
                timings["service_total_ms"] = _elapsed_ms(service_started)
                self._record_diagnostic(
                    request_id=request_id,
                    client_ip=client_ip,
                    lang_hint=lang_hint,
                    status="failed",
                    raw_outputs=raw_outputs,
                    validation_errors=validation_errors,
                    final_result=None,
                    fallback_used=False,
                    error=str(exc),
                    timings=timings,
                )
                raise
            attempt_timing["generation_ms"] = _elapsed_ms(generation_started)
            attempt_timing["output_chars"] = len(raw)
            raw_outputs.append({"attempt": attempt + 1, "output": raw})
            parse_started = perf_counter()
            try:
                result = _parse_word_json(raw)
                result = _validated_word_result(result)
                attempt_timing["parse_validation_ms"] = _elapsed_ms(parse_started)
                timings["attempts"].append(attempt_timing)
                timings["service_total_ms"] = _elapsed_ms(service_started)
                self._record_diagnostic(
                    request_id=request_id,
                    client_ip=client_ip,
                    lang_hint=lang_hint,
                    status="completed",
                    raw_outputs=raw_outputs,
                    validation_errors=validation_errors,
                    final_result=result,
                    fallback_used=False,
                    error=None,
                    timings=timings,
                )
                return result
            except (ValidationError, ValueError) as exc:
                attempt_timing["parse_validation_ms"] = _elapsed_ms(parse_started)
                attempt_timing["validation_error"] = str(exc)
                timings["attempts"].append(attempt_timing)
                last_error = exc
                validation_errors.append(str(exc))
                if attempt == 1:
                    fallback = None if _is_unclear_word_error(exc) else _word_result_from_text_like_output(raw)
                    if fallback is not None:
                        timings["service_total_ms"] = _elapsed_ms(service_started)
                        self._record_diagnostic(
                            request_id=request_id,
                            client_ip=client_ip,
                            lang_hint=lang_hint,
                            status="completed_with_fallback",
                            raw_outputs=raw_outputs,
                            validation_errors=validation_errors,
                            final_result=fallback,
                            fallback_used=True,
                            error=str(exc),
                            timings=timings,
                        )
                        return fallback
                    timings["service_total_ms"] = _elapsed_ms(service_started)
                    self._record_diagnostic(
                        request_id=request_id,
                        client_ip=client_ip,
                        lang_hint=lang_hint,
                        status="failed",
                        raw_outputs=raw_outputs,
                        validation_errors=validation_errors,
                        final_result=None,
                        fallback_used=False,
                        error=str(exc),
                        timings=timings,
                    )
                    raise WordExplorerError(
                        "OpenRead could not identify the word in the center. Move closer and try again."
                    ) from exc
            except StoryCompilerError as exc:
                raise WordExplorerError(str(exc)) from exc

        raise WordExplorerError("Gemma did not return a valid word explanation.")

    def _record_diagnostic(
        self,
        *,
        request_id: str | None,
        client_ip: str | None,
        lang_hint: str | None,
        status: str,
        raw_outputs: list[dict[str, object]],
        validation_errors: list[str],
        final_result: WordExplorerResult | None,
        fallback_used: bool,
        error: str | None,
        timings: dict[str, Any],
    ) -> None:
        if self._diagnostics_recorder is None or request_id is None:
            return
        payload: dict[str, Any] = {
            "request_id": request_id,
            "client_ip": client_ip,
            "task": "word_explorer",
            "compiler_provider": self._provider,
            "model": self._model,
            "compiler_mode": "gemma_vision",
            "lang_hint": lang_hint,
            "status": status,
            "fallback_used": fallback_used,
            "raw_gemma_outputs": raw_outputs,
            "validation_errors": validation_errors,
            "error": error,
            "timings": timings,
            "final_spoken_script": final_result.spoken_script if final_result is not None else None,
            "word_result": final_result.model_dump() if final_result is not None else None,
        }
        try:
            self._diagnostics_recorder.record(payload)
        except Exception:
            logger.exception("Failed to record Word Explorer diagnostics for request %s", request_id)

    def _generate(self, *, image_bytes: bytes, prompt: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise WordExplorerError(
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
                response_json_schema=WordExplorerResult.model_json_schema(),
            ),
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise WordExplorerError("Gemma returned an empty word explanation response.")
        return text


class CerebrasWordExplorerService(GemmaWordExplorerService):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gemma-4-31b",
        base_url: str = "https://api.cerebras.ai/v1",
        timeout_seconds: int = 90,
        diagnostics_recorder: GemmaDiagnosticsRecorder | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            provider="cerebras",
            diagnostics_recorder=diagnostics_recorder,
        )
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = max(1, timeout_seconds)
        self._missing_api_key_message = "CEREBRAS_API_KEY is required for OpenRead fast word exploration."

    def _generate(self, *, image_bytes: bytes, prompt: str) -> str:
        image_data_url = f"data:image/jpeg;base64,{b64encode(image_bytes).decode('ascii')}"
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "openread_word_explorer",
                    "strict": True,
                    "schema": _strict_json_schema(WordExplorerResult.model_json_schema()),
                },
            },
            "max_tokens": 2048,
            "temperature": 0.1,
            "reasoning_effort": "none",
            "stream": False,
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=httpx.Timeout(self._timeout_seconds),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise WordExplorerError(f"Cerebras word exploration failed ({exc.response.status_code}): {detail}") from exc
        except httpx.HTTPError as exc:
            raise WordExplorerError(f"Cerebras word exploration failed: {exc}") from exc

        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WordExplorerError("Cerebras returned an unexpected word explanation response.") from exc
        if not isinstance(text, str) or not text.strip():
            raise WordExplorerError("Cerebras returned an empty word explanation response.")
        return text


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def _parse_word_json(raw: str) -> WordExplorerResult:
    candidates = _json_candidates(raw)
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return WordExplorerResult.model_validate_json(candidate)
        except (ValidationError, ValueError) as exc:
            last_error = exc
            repaired = _repair_json_text(candidate)
            if repaired == candidate:
                continue
            try:
                return WordExplorerResult.model_validate_json(repaired)
            except (ValidationError, ValueError) as repaired_exc:
                last_error = repaired_exc
    if last_error is not None:
        raise last_error
    raise ValueError("Gemma did not return a JSON object.")


def _validated_word_result(result: WordExplorerResult) -> WordExplorerResult:
    selected_word = result.selected_word.strip()
    kid_explanation = result.kid_explanation.strip()
    if not selected_word:
        raise ValueError("selected_word is required.")
    if selected_word.lower() in {"unknown", "unclear", "not sure", "n/a"}:
        raise ValueError("selected_word must identify the pointed printed word.")
    if not kid_explanation:
        raise ValueError("kid_explanation is required.")
    tts_segments = _word_tts_segments(result, selected_word=selected_word, kid_explanation=kid_explanation)
    spoken_script = _join_word_tts_segments(tts_segments)
    if not spoken_script:
        raise ValueError("spoken_script is required.")
    return result.model_copy(
        update={
            "selected_word": selected_word,
            "kid_explanation": kid_explanation,
            "spoken_script": spoken_script,
            "tts_segments": tts_segments,
        }
    )


def _word_tts_segments(
    result: WordExplorerResult,
    *,
    selected_word: str,
    kid_explanation: str,
) -> list[TtsSegment]:
    segments = [
        TtsSegment(segment_id="word", text=selected_word, kind="word", after_beat_id=None),
        TtsSegment(segment_id="meaning", text=kid_explanation, kind="meaning", after_beat_id=None),
    ]
    example_sentence = (result.example_sentence or "").strip()
    if example_sentence:
        segments.append(TtsSegment(segment_id="example", text=example_sentence, kind="example", after_beat_id=None))
    return segments


def _join_word_tts_segments(segments: list[TtsSegment]) -> str:
    parts: list[str] = []
    for index, segment in enumerate(segments):
        text = segment.text.strip()
        if not text:
            continue
        if index == 0 and segment.kind == "word" and text[-1] not in ".!?。！？":
            text = f"{text}."
        parts.append(text)
    return " ".join(parts).strip()


def _is_unclear_word_error(exc: Exception) -> bool:
    message = str(exc)
    return "selected_word is required" in message or "selected_word must identify" in message


def _word_result_from_text_like_output(raw: str) -> WordExplorerResult | None:
    text = _extract_text_like_output(raw)
    if text is None:
        return None
    segments = [
        TtsSegment(
            segment_id="meaning",
            text=text,
            kind="meaning",
            after_beat_id=None,
        )
    ]
    return WordExplorerResult(
        selected_word="center word",
        normalized_word=None,
        language=None,
        part_of_speech=None,
        pronunciation_hint=None,
        kid_explanation=text,
        example_sentence=None,
        page_context=None,
        spoken_script=text,
        tts_segments=segments,
        confidence=0.3,
        diagnostics={
            "mode": "gemma_vision",
            "pointing_evidence": "Gemma returned malformed JSON; OpenRead used a plain-text explanation fallback.",
            "layout_region": None,
            "warnings": ["Gemma returned malformed JSON. Used plain-text fallback for TTS."],
        },
    )


def _build_word_prompt(*, lang_hint: str | None) -> str:
    return f"""
You are OpenRead Word Explorer, a gentle child-friendly vocabulary guide for picture books.

Task:
- Analyze this center crop from a picture-book page.
- Identify the single printed word nearest the exact center of the image.
- If the center falls inside a word or between its letters, select that whole word.
- Do not require or search for a pen, finger, pencil, or other physical pointer.
- Explain that word in simple language a young child can understand.
- Use nearby text and illustration context only to disambiguate the centered word and make the explanation clearer.
- Do not explain the whole page or tell a new story.
- Return only JSON matching the provided schema.
- Preserve apostrophes, quotation marks, curly quotes, dashes, ellipses, CJK punctuation, and symbols as valid JSON string content.
- Escape every double quote inside string values so the response remains parseable JSON.
- Do not wrap JSON in markdown fences, commentary, or explanatory text.

Language hint: {lang_hint or "auto"}

Output rules:
- `selected_word` is the exact visible printed word nearest the image center. If the centered word is unclear, return an empty string so validation can fail.
- `normalized_word` is a dictionary-style form when useful, otherwise null.
- `language` should name the detected language when you can tell.
- `part_of_speech` should be child-friendly, such as "noun", "verb", "describing word", or null if unsure.
- `pronunciation_hint` is optional and should be short.
- `kid_explanation` should be one or two simple sentences.
- `example_sentence` should be short and use the word naturally when useful.
- `page_context` should briefly say how the word appears on this page when useful.
- `spoken_script` should say the word, then the kid-friendly meaning, and may include the example sentence.
- `tts_segments` may be returned, but OpenRead will normalize it to predictable audio chunks: word first, meaning second, example third.
- `confidence` must be 0 to 1.
- `diagnostics.mode` must be "gemma_vision".
- `diagnostics.pointing_evidence` should briefly describe why you chose that word, such as "the word crosses the exact center of the crop".
""".strip()
