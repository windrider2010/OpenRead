from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from app.models import StoryCompilation
from app.services.story_compiler import GemmaStoryCompilerService, StoryCompilerError, normalize_compiler_mode


class FakeGemmaCompiler(GemmaStoryCompilerService):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(api_key="test-key", model="gemma-test")
        self.responses = responses
        self.prompts: list[str] = []

    def _generate(self, *, image_bytes: bytes, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def _story_json() -> str:
    story = StoryCompilation(
        title="Moon Page",
        spoken_script="Hello world.",
        beats=[
            {
                "beat_id": "text-1",
                "kind": "text",
                "narration": "Hello world.",
                "source_text": "Hello world.",
                "layout_region": "top-left",
                "confidence": 0.95,
            }
        ],
        caregiver_cues=[
            {
                "cue_id": "cue-1",
                "after_beat_id": "text-1",
                "cue": "Ask what might happen next.",
                "purpose": "prediction",
            }
        ],
        diagnostics={
            "mode": "gemma_vision",
            "layout_notes": "Single text block.",
            "ocr_used": False,
            "warnings": [],
        },
    )
    return story.model_dump_json()


def test_gemma_story_compiler_retries_invalid_structured_output() -> None:
    compiler = FakeGemmaCompiler([json.dumps({"spoken_script": ""}), _story_json()])

    story = compiler.compile_page(
        image=Image.new("RGB", (20, 20), color="white"),
        mode="gemma_vision",
    )

    assert story.spoken_script == "Hello world."
    assert len(compiler.prompts) == 2
    assert "Validation error" in compiler.prompts[1]


def test_gemma_story_compiler_fails_after_second_invalid_output() -> None:
    compiler = FakeGemmaCompiler([json.dumps({"spoken_script": ""}), json.dumps({"spoken_script": ""})])

    with pytest.raises(StoryCompilerError):
        compiler.compile_page(
            image=Image.new("RGB", (20, 20), color="white"),
            mode="gemma_vision",
        )


def test_gemma_story_compiler_requires_api_key() -> None:
    compiler = GemmaStoryCompilerService(api_key=None, model="gemma-test")

    with pytest.raises(StoryCompilerError, match="GEMINI_API_KEY"):
        compiler.compile_page(
            image=Image.new("RGB", (20, 20), color="white"),
            mode="gemma_vision",
        )


def test_gemma_story_compiler_uses_current_genai_structured_output_config(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePart:
        @staticmethod
        def from_bytes(*, data: bytes, mime_type: str) -> dict[str, object]:
            return {"data": data, "mime_type": mime_type}

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs) -> None:
            captured["config_kwargs"] = kwargs

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=_story_json())

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setitem(
        sys.modules,
        "google.genai",
        SimpleNamespace(Client=FakeClient, types=SimpleNamespace(Part=FakePart, GenerateContentConfig=FakeGenerateContentConfig)),
    )
    monkeypatch.setitem(
        sys.modules,
        "google",
        SimpleNamespace(genai=sys.modules["google.genai"]),
    )

    compiler = GemmaStoryCompilerService(api_key="test-key", model="gemma-test")
    story = compiler.compile_page(image=Image.new("RGB", (20, 20), color="white"), mode="gemma_vision")

    assert story.spoken_script == "Hello world."
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gemma-test"
    config_kwargs = captured["config_kwargs"]
    assert config_kwargs["response_mime_type"] == "application/json"
    assert "response_json_schema" in config_kwargs
    assert "response_format" not in config_kwargs


def test_normalize_compiler_mode_accepts_supported_modes() -> None:
    assert normalize_compiler_mode(None, "gemma_vision") == "gemma_vision"
    assert normalize_compiler_mode("ocr_assisted", "gemma_vision") == "ocr_assisted"
    with pytest.raises(ValueError):
        normalize_compiler_mode("ocr", "gemma_vision")
