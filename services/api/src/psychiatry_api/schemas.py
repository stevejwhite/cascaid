from typing import Literal

from pydantic import AwareDatetime

from psychiatry_api.domain import Contract
from psychiatry_api.sources import Source


class ServiceCheck(Contract):
    status: Literal["ready", "unavailable", "empty", "invalid", "disabled"]
    detail: str


class Health(Contract):
    status: Literal["ok"] = "ok"
    service: Literal["psychiatry-edu-api"] = "psychiatry-edu-api"
    version: Literal["0.2.0"] = "0.2.0"


class Readiness(Contract):
    """Text role-play needs valid cases and registry; local mode also needs generation.

    Speech is optional: typed input works whether or not speech recognition is ready, and
    replies can be read in a browser voice when the character's voice is not.
    """

    status: Literal["ready", "not_ready"]
    model_backend: Literal["fake", "local"]
    speech_backend: Literal["off", "fake", "local"]
    tts_backend: Literal["off", "fake", "local"]
    checked_at: AwareDatetime
    registry: ServiceCheck
    cases: ServiceCheck
    generation: ServiceCheck
    speech: ServiceCheck
    voice: ServiceCheck


class SourceSummary(Contract):
    source: Source
    access_state: Literal["in_use", "blocked", "awaiting_permission", "not_used"]
    detail: str


class SourceCatalogue(Contract):
    sources: tuple[SourceSummary, ...]


class ErrorResponse(Contract):
    detail: str
