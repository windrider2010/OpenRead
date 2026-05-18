from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CompilerMode = Literal["gemma_vision", "ocr_assisted"]
ReadJobStage = Literal["queued", "story_compile", "ocr", "tts", "completed", "failed"]


class OcrBlock(BaseModel):
    text: str
    confidence: float | None = None
    box: list[list[float]] = Field(default_factory=list)


class OcrResponse(BaseModel):
    request_id: str
    text: str
    blocks: list[OcrBlock]
    detected_scripts: list[str]


class ReadResponse(BaseModel):
    request_id: str
    text: str
    audio_url: str
    mime_type: str = "audio/wav"
    expires_at: str
    story: "StoryCompilation | None" = None


class ReadJobAcceptedResponse(BaseModel):
    request_id: str
    status: Literal["queued", "processing", "completed", "failed"]


class ReadJobStatusResponse(BaseModel):
    request_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    stage: ReadJobStage
    text: str | None = None
    audio_url: str | None = None
    mime_type: str | None = None
    expires_at: str | None = None
    paragraphs_total: int = 0
    paragraphs_completed: int = 0
    error: str | None = None
    story: "StoryCompilation | None" = None


class StoryBeat(BaseModel):
    beat_id: str
    kind: Literal["text", "illustration"]
    narration: str
    source_text: str | None = None
    layout_region: str | None = None
    confidence: float = Field(ge=0, le=1)


class CaregiverCue(BaseModel):
    cue_id: str
    after_beat_id: str
    cue: str
    purpose: Literal["prediction", "emotion", "vocabulary", "engagement"]


class StoryDiagnostics(BaseModel):
    mode: CompilerMode
    layout_notes: str
    ocr_used: bool
    warnings: list[str] = Field(default_factory=list)


class StoryCompilation(BaseModel):
    title: str | None = None
    spoken_script: str
    beats: list[StoryBeat] = Field(default_factory=list)
    caregiver_cues: list[CaregiverCue] = Field(default_factory=list)
    diagnostics: StoryDiagnostics


class HealthResponse(BaseModel):
    status: Literal["ok"]
