"""Pydantic request and response models mirroring ARCHITECTURE.md section 9.

Wire fields are camelCase; Python attributes stay snake_case. Range checks
that must produce a specific error code (for example OUT_OF_RANGE with
``{field, min, max, value}``) are performed by the routes so the envelope is
exact; these models only pin the shape and basic types.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

GenerationState = Literal["queued", "running", "cancelling", "succeeded", "failed", "cancelled"]
SourceType = Literal["text", "file"]


class ContractModel(BaseModel):
    """Base model that accepts snake_case and emits camelCase."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# -- Errors (section 9.1) ---------------------------------------------------


class ErrorInfo(ContractModel):
    code: str
    message: str
    details: dict[str, object] | None = None


class ErrorEnvelope(ContractModel):
    error: ErrorInfo


# -- Health ----------------------------------------------------------------


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
    version: str
    voices_installed: int
    default_voice_id: str


# -- Voices ----------------------------------------------------------------


class Voice(ContractModel):
    id: str
    name: str
    language: str
    gender: str | None = None
    sample_rate: int


class VoiceList(ContractModel):
    items: list[Voice]
    total: int
    default_voice_id: str


class VoicePreviewRequest(ContractModel):
    voice_id: str


# -- Timings and cues ------------------------------------------------------


class WordTimingSchema(ContractModel):
    text: str
    start_ms: int
    end_ms: int
    aligned: bool


class CueSchema(ContractModel):
    index: int
    start_ms: int
    end_ms: int
    text: str


# -- Generations -----------------------------------------------------------


class GenerationStatus(ContractModel):
    generation_id: str
    status: GenerationState


class GenerationProgress(GenerationStatus):
    sentence_index: int
    sentence_count: int


class GenerationSucceeded(GenerationStatus):
    duration_seconds: float


class GenerationError(ContractModel):
    code: str
    message: str


class GenerationFailed(GenerationStatus):
    error: GenerationError


class GenerationCancelled(GenerationStatus):
    pass


class GenerationCreateRequest(ContractModel):
    # Optional here so the route can return EMPTY_INPUT for missing text
    # instead of a generic schema-validation error (section 9.2).
    text: str | None = None
    voice_id: str | None = None
    rate: float | None = None
    volume: float | None = None


class GenerationSummary(ContractModel):
    generation_id: str
    status: GenerationState
    created_at: str
    source_type: SourceType
    input_preview: str
    input_filename: str | None = None
    voice_id: str
    voice_name: str
    rate: float
    volume: float
    duration_seconds: float | None = None
    error: GenerationError | None = None


class GenerationDetail(GenerationSummary):
    text: str | None = None
    sample_rate: int | None = None
    aligned_word_ratio: float | None = None
    word_timings: list[WordTimingSchema] | None = None
    cues: list[CueSchema] | None = None


class GenerationList(ContractModel):
    items: list[GenerationSummary]
    total: int


# -- Uploads ---------------------------------------------------------------


class UploadResponse(ContractModel):
    text: str
    filename: str
    size_bytes: int


# -- Settings --------------------------------------------------------------


class SettingsResponse(ContractModel):
    default_voice_id: str
    rate: float
    volume: float


class SettingsPatch(ContractModel):
    default_voice_id: str | None = None
    rate: float | None = None
    volume: float | None = None
