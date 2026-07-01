from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from app.models import WordExplorerResult
from app.services.gemma_diagnostics import GemmaDiagnosticsStore
from app.services.word_explorer import CerebrasWordExplorerService, GemmaWordExplorerService, WordExplorerError


class FakeGemmaWordExplorer(GemmaWordExplorerService):
    def __init__(self, responses: list[str], diagnostics_recorder=None) -> None:
        super().__init__(api_key="test-key", model="gemma-test", diagnostics_recorder=diagnostics_recorder)
        self.responses = responses
        self.prompts: list[str] = []

    def _generate(self, *, image_bytes: bytes, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def _word_json() -> str:
    result = WordExplorerResult(
        selected_word="brave",
        normalized_word="brave",
        language="English",
        part_of_speech="describing word",
        pronunciation_hint="brayv",
        kid_explanation="Brave means you try even when something feels a little scary.",
        example_sentence="The brave rabbit hopped across the bridge.",
        page_context="The word is centered in a sentence near the rabbit.",
        spoken_script=(
            "The word is brave. Brave means you try even when something feels a little scary. "
            "The brave rabbit hopped across the bridge."
        ),
        confidence=0.93,
        diagnostics={
            "mode": "gemma_vision",
            "pointing_evidence": "The word brave crosses the center of the crop.",
            "layout_region": "center",
            "warnings": [],
        },
    )
    return result.model_dump_json()


def test_gemma_word_explorer_retries_invalid_structured_output() -> None:
    explorer = FakeGemmaWordExplorer([json.dumps({"selected_word": ""}), _word_json()])

    result = explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))

    assert result.selected_word == "brave"
    assert result.spoken_script == (
        "brave. Brave means you try even when something feels a little scary. "
        "The brave rabbit hopped across the bridge."
    )
    assert [segment.text for segment in result.tts_segments] == [
        "brave",
        "Brave means you try even when something feels a little scary.",
        "The brave rabbit hopped across the bridge.",
    ]
    assert len(explorer.prompts) == 2
    assert "Validation error" in explorer.prompts[1]


def test_gemma_word_explorer_repairs_invalid_trailing_commas() -> None:
    raw = """
    {
      "selected_word": "moon",
      "normalized_word": "moon",
      "language": "English",
      "part_of_speech": "noun",
      "pronunciation_hint": "moon",
      "kid_explanation": "A moon is a bright round thing we see in the night sky.",
      "example_sentence": "The moon shines at bedtime.",
      "page_context": "Moon is centered near the top of the page.",
      "spoken_script": "The word is moon. A moon is a bright round thing we see in the night sky.",
      "confidence": 0.88,
      "diagnostics": {
        "mode": "gemma_vision",
        "pointing_evidence": "Moon is nearest the center of the crop.",
        "layout_region": "top",
        "warnings": [],
      },
    }
    """
    explorer = FakeGemmaWordExplorer([raw])

    result = explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))

    assert result.selected_word == "moon"
    assert result.kid_explanation.startswith("A moon")
    assert [segment.text for segment in result.tts_segments] == [
        "moon",
        "A moon is a bright round thing we see in the night sky.",
        "The moon shines at bedtime.",
    ]


def test_gemma_word_explorer_falls_back_to_text_like_output_after_retry() -> None:
    explorer = FakeGemmaWordExplorer(
        [
            json.dumps({"selected_word": ""}),
            "The word means a little home for a bird.",
        ]
    )

    result = explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))

    assert result.selected_word == "center word"
    assert result.spoken_script == "The word means a little home for a bird."
    assert result.diagnostics.warnings == ["Gemma returned malformed JSON. Used plain-text fallback for TTS."]


def test_gemma_word_explorer_fails_when_centered_word_is_unclear() -> None:
    payload = WordExplorerResult(
        selected_word="unknown",
        normalized_word=None,
        language=None,
        part_of_speech=None,
        pronunciation_hint=None,
        kid_explanation="I cannot tell which word is centered.",
        example_sentence=None,
        page_context=None,
        spoken_script="I cannot tell which word is centered.",
        confidence=0.1,
        diagnostics={
            "mode": "gemma_vision",
            "pointing_evidence": "The image center falls between several blurred words.",
            "layout_region": None,
            "warnings": ["Centered word is unclear."],
        },
    )
    explorer = FakeGemmaWordExplorer([payload.model_dump_json(), payload.model_dump_json()])

    with pytest.raises(WordExplorerError, match="could not identify the word"):
        explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))


def test_gemma_word_explorer_prompt_selects_center_without_physical_pointer() -> None:
    explorer = FakeGemmaWordExplorer([_word_json()])

    explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))

    assert "nearest the exact center" in explorer.prompts[0]
    assert "Do not require or search for a pen" in explorer.prompts[0]
    assert "Find the pen" not in explorer.prompts[0]


def test_gemma_word_explorer_records_success_diagnostics(tmp_path) -> None:
    store = GemmaDiagnosticsStore(tmp_path / "gemma", ttl_seconds=604800)
    explorer = FakeGemmaWordExplorer([_word_json()], diagnostics_recorder=store)

    explorer.explore_word(
        image=Image.new("RGB", (20, 20), color="white"),
        request_id="word-request",
        client_ip="203.0.113.55",
    )

    payload = json.loads((tmp_path / "gemma" / "word-request.json").read_text(encoding="utf-8"))
    assert payload["task"] == "word_explorer"
    assert payload["client_ip"] == "203.0.113.55"
    assert payload["status"] == "completed"
    assert payload["word_result"]["selected_word"] == "brave"
    assert payload["timings"]["encoded_image_bytes"] > 0
    assert payload["timings"]["attempts"][0]["generation_ms"] >= 0
    assert payload["timings"]["attempts"][0]["parse_validation_ms"] >= 0
    assert payload["timings"]["service_total_ms"] >= 0
    assert "image" not in payload


def test_gemma_word_explorer_requires_api_key() -> None:
    explorer = GemmaWordExplorerService(api_key=None, model="gemma-test")

    with pytest.raises(WordExplorerError, match="GEMINI_API_KEY"):
        explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))


def test_cerebras_word_explorer_requires_cerebras_api_key() -> None:
    explorer = CerebrasWordExplorerService(api_key=None)

    with pytest.raises(WordExplorerError, match="CEREBRAS_API_KEY"):
        explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))


def test_cerebras_word_explorer_uses_chat_completions_with_strict_schema(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": _word_json()}}]}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.services.word_explorer.httpx.post", fake_post)

    explorer = CerebrasWordExplorerService(
        api_key="cerebras-key",
        model="gemma-4-31b",
        base_url="https://api.cerebras.ai/v1",
        timeout_seconds=12,
    )
    result = explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))

    assert result.selected_word == "brave"
    assert captured["url"] == "https://api.cerebras.ai/v1/chat/completions"
    payload = captured["json"]
    assert payload["model"] == "gemma-4-31b"
    assert payload["max_tokens"] == 2048
    assert payload["temperature"] == 0.1
    assert payload["reasoning_effort"] == "none"
    assert payload["response_format"]["type"] == "json_schema"
    json_schema = payload["response_format"]["json_schema"]
    assert json_schema["strict"] is True
    assert json_schema["schema"]["additionalProperties"] is False
    assert "selected_word" in json_schema["schema"]["required"]
    content = payload["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert captured["headers"]["Authorization"] == "Bearer cerebras-key"


def test_gemma_word_explorer_uses_current_genai_structured_output_config(monkeypatch) -> None:
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
            return SimpleNamespace(text=_word_json())

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setitem(
        sys.modules,
        "google.genai",
        SimpleNamespace(
            Client=FakeClient,
            types=SimpleNamespace(Part=FakePart, GenerateContentConfig=FakeGenerateContentConfig),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "google",
        SimpleNamespace(genai=sys.modules["google.genai"]),
    )

    explorer = GemmaWordExplorerService(api_key="test-key", model="gemma-test")
    result = explorer.explore_word(image=Image.new("RGB", (20, 20), color="white"))

    assert result.selected_word == "brave"
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gemma-test"
    config_kwargs = captured["config_kwargs"]
    assert config_kwargs["response_mime_type"] == "application/json"
    assert "response_json_schema" in config_kwargs
    assert "response_format" not in config_kwargs
