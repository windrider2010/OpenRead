from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from app.models import StoryCompilation
from app.services.gemma_diagnostics import GemmaDiagnosticsStore
from app.services.story_compiler import GemmaStoryCompilerService, StoryCompilerError, normalize_compiler_mode


class FakeGemmaCompiler(GemmaStoryCompilerService):
    def __init__(self, responses: list[str], diagnostics_recorder=None) -> None:
        super().__init__(api_key="test-key", model="gemma-test", diagnostics_recorder=diagnostics_recorder)
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


def _special_story_json() -> str:
    story = StoryCompilation(
        title="Balloon Page",
        spoken_script='The bear looked up. “Where did my balloon go?” 树上有一个红气球… ✨',
        beats=[
            {
                "beat_id": "illustration-1",
                "kind": "illustration",
                "narration": "The bear looked up at a red balloon caught in the tree.",
                "source_text": None,
                "layout_region": "center",
                "confidence": 0.86,
            },
            {
                "beat_id": "text-1",
                "kind": "text",
                "narration": "“Where did my balloon go?”",
                "source_text": "“Where did my balloon go?”",
                "layout_region": "speech-bubble-right",
                "confidence": 0.91,
            },
            {
                "beat_id": "text-2",
                "kind": "text",
                "narration": "树上有一个红气球… ✨",
                "source_text": "树上有一个红气球… ✨",
                "layout_region": "bottom-left",
                "confidence": 0.9,
            },
        ],
        caregiver_cues=[
            {
                "cue_id": "cue-1",
                "after_beat_id": "text-1",
                "cue": "Ask, “How does the bear feel?”",
                "purpose": "emotion",
            }
        ],
        diagnostics={
            "mode": "gemma_vision",
            "layout_notes": "Read the picture clue before the speech bubble.",
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


def test_gemma_story_compiler_extracts_json_wrapped_in_text() -> None:
    compiler = FakeGemmaCompiler([f"Here is the JSON:\n```json\n{_story_json()}\n```"])

    story = compiler.compile_page(
        image=Image.new("RGB", (20, 20), color="white"),
        mode="gemma_vision",
    )

    assert story.spoken_script == "Hello world."
    assert len(compiler.prompts) == 1


def test_gemma_story_compiler_repairs_invalid_trailing_commas() -> None:
    raw = """
    {
      "title": null,
      "spoken_script": "The bear looked up.",
      "beats": [
        {
          "beat_id": "text-1",
          "kind": "text",
          "narration": "The bear looked up.",
          "source_text": "The bear looked up.",
          "layout_region": "center",
          "confidence": 0.94,
        },
      ],
      "caregiver_cues": [],
      "diagnostics": {
        "mode": "gemma_vision",
        "layout_notes": "Single fixed page.",
        "ocr_used": false,
        "warnings": [],
      },
    }
    """
    compiler = FakeGemmaCompiler([raw])

    story = compiler.compile_page(
        image=Image.new("RGB", (20, 20), color="white"),
        mode="gemma_vision",
    )

    assert story.spoken_script == "The bear looked up."
    assert story.beats[0].layout_region == "center"


def test_gemma_story_compiler_preserves_special_characters_in_valid_json() -> None:
    compiler = FakeGemmaCompiler([_special_story_json()])

    story = compiler.compile_page(
        image=Image.new("RGB", (20, 20), color="white"),
        mode="gemma_vision",
    )

    assert story.spoken_script == 'The bear looked up. “Where did my balloon go?” 树上有一个红气球… ✨'
    assert story.beats[1].source_text == "“Where did my balloon go?”"
    assert story.caregiver_cues[0].cue == "Ask, “How does the bear feel?”"


def test_gemma_story_compiler_records_success_diagnostics(tmp_path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800)
    compiler = FakeGemmaCompiler([_special_story_json()], diagnostics_recorder=store)

    story = compiler.compile_page(
        image=Image.new("RGB", (20, 20), color="white"),
        mode="gemma_vision",
        request_id="request-1",
        client_ip="203.0.113.99",
    )

    path = tmp_path / "gemma" / "request-1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert story.spoken_script in payload["final_spoken_script"]
    assert payload["client_ip"] == "203.0.113.99"
    assert payload["model"] == "gemma-test"
    assert payload["status"] == "completed"
    assert payload["fallback_used"] is False
    assert payload["raw_gemma_outputs"][0]["output"] == _special_story_json()
    assert payload["timings"]["image_encode_ms"] >= 0
    assert payload["timings"]["attempts"][0]["generation_ms"] >= 0
    assert payload["timings"]["attempts"][0]["parse_validation_ms"] >= 0
    assert payload["timings"]["service_total_ms"] >= 0
    assert "image" not in payload


def test_gemma_story_compiler_falls_back_to_text_like_output_after_retry() -> None:
    compiler = FakeGemmaCompiler(
        [
            json.dumps({"spoken_script": ""}),
            "The bear looked up.\nA red balloon is caught in the tree.\n“Where did my balloon go?”",
        ]
    )

    story = compiler.compile_page(
        image=Image.new("RGB", (20, 20), color="white"),
        mode="gemma_vision",
    )

    assert story.spoken_script == "The bear looked up. A red balloon is caught in the tree. “Where did my balloon go?”"
    assert story.beats[0].narration == story.spoken_script
    assert story.diagnostics.warnings == ["Gemma returned malformed JSON. Used plain-text fallback for TTS."]


def test_gemma_story_compiler_records_fallback_diagnostics(tmp_path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800)
    compiler = FakeGemmaCompiler(
        [
            json.dumps({"spoken_script": ""}),
            "The bear looked up.\n“Where did my balloon go?”",
        ],
        diagnostics_recorder=store,
    )

    compiler.compile_page(
        image=Image.new("RGB", (20, 20), color="white"),
        mode="gemma_vision",
        request_id="fallback-request",
        client_ip="203.0.113.88",
    )

    payload = json.loads((tmp_path / "gemma" / "fallback-request.json").read_text(encoding="utf-8"))
    assert payload["status"] == "completed_with_fallback"
    assert payload["fallback_used"] is True
    assert len(payload["raw_gemma_outputs"]) == 2
    assert payload["validation_errors"]


def test_gemma_story_compiler_falls_back_to_nested_text_field_after_retry() -> None:
    compiler = FakeGemmaCompiler(
        [
            json.dumps({"spoken_script": ""}),
            '{"message": {"text": "It floated away."}}',
        ]
    )

    story = compiler.compile_page(
        image=Image.new("RGB", (20, 20), color="white"),
        mode="gemma_vision",
    )

    assert story.spoken_script == "It floated away."


def test_gemma_story_compiler_fails_after_second_invalid_output() -> None:
    compiler = FakeGemmaCompiler([json.dumps({"spoken_script": ""}), json.dumps({"spoken_script": ""})])

    with pytest.raises(StoryCompilerError):
        compiler.compile_page(
            image=Image.new("RGB", (20, 20), color="white"),
            mode="gemma_vision",
        )


def test_gemma_story_compiler_records_failure_diagnostics(tmp_path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800)
    compiler = FakeGemmaCompiler(
        [json.dumps({"spoken_script": ""}), json.dumps({"spoken_script": ""})],
        diagnostics_recorder=store,
    )

    with pytest.raises(StoryCompilerError):
        compiler.compile_page(
            image=Image.new("RGB", (20, 20), color="white"),
            mode="gemma_vision",
            request_id="failed-request",
            client_ip="203.0.113.77",
        )

    payload = json.loads((tmp_path / "gemma" / "failed-request.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["error"]
    assert len(payload["raw_gemma_outputs"]) == 2


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
