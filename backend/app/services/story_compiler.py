from __future__ import annotations

import io
from typing import Protocol

from PIL import Image
from pydantic import ValidationError

from app.models import CompilerMode, StoryCompilation
from app.services.ocr_service import RecognizedPage


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
    ) -> StoryCompilation:
        """Compile a picture-book page image into a structured read-aloud story."""


class GemmaStoryCompilerService:
    def __init__(self, *, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def compile_page(
        self,
        *,
        image: Image.Image,
        mode: CompilerMode,
        lang_hint: str | None = None,
        ocr_page: RecognizedPage | None = None,
    ) -> StoryCompilation:
        if not self._api_key:
            raise StoryCompilerError("GEMINI_API_KEY is required for OpenRead story compilation.")

        image_bytes = _image_to_jpeg_bytes(image)
        prompt = _build_prompt(mode=mode, lang_hint=lang_hint, ocr_page=ocr_page)
        last_error: Exception | None = None

        for attempt in range(2):
            repair_note = ""
            if last_error is not None:
                repair_note = (
                    "\n\nYour previous response did not validate. Return only corrected JSON that matches "
                    f"the schema. Validation error: {last_error}"
                )
            raw = self._generate(image_bytes=image_bytes, prompt=f"{prompt}{repair_note}")
            try:
                compiled = StoryCompilation.model_validate_json(raw)
                return _validated_compilation(compiled, expected_mode=mode)
            except (ValidationError, ValueError) as exc:
                last_error = exc
                if attempt == 1:
                    raise StoryCompilerError(f"Gemma returned invalid story JSON: {exc}") from exc

        raise StoryCompilerError("Gemma did not return a valid story compilation.")

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
    return StoryCompilation(
        title=None,
        spoken_script=cleaned,
        beats=[
            {
                "beat_id": "text-1",
                "kind": "text",
                "narration": cleaned,
                "source_text": cleaned,
                "layout_region": None,
                "confidence": 1.0,
            }
        ],
        caregiver_cues=[],
        diagnostics={
            "mode": mode,
            "layout_notes": "Text input bypassed image story compilation.",
            "ocr_used": False,
            "warnings": [],
        },
    )


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
