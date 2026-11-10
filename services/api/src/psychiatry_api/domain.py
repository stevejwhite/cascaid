"""Shared immutable contract base and source provenance."""

from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

NonEmpty = Annotated[str, Field(min_length=1, pattern=r"\S")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Provenance(Contract):
    source_id: NonEmpty
    publisher: NonEmpty
    source_type: NonEmpty
    title: NonEmpty
    source_url_or_identifier: NonEmpty
    version: NonEmpty
    jurisdiction: NonEmpty
    licence: NonEmpty
    publication_date: date | None = None
    update_date: date | None = None
    effective_date: date | None = None
    retrieved_at: AwareDatetime
    attribution: str | None = None
    licence_url: str | None = None
    usage_note: str | None = None
