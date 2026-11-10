"""Python implementation of the same registry policy as packages/sources."""

from datetime import date
from enum import StrEnum
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import Field, StrictBool, model_validator

from psychiatry_api.domain import Contract, NonEmpty, Provenance


class SourceStatus(StrEnum):
    APPROVED = "approved"
    IN_PRINCIPLE = "approved_in_principle"
    CONDITIONAL = "approved_with_conditions"
    PER_ITEM = "per_item_check"
    PENDING_PERMISSION = "pending_permission"
    PENDING_REUSE = "pending_reuse_check"
    BLOCKED = "blocked_until_licensed"


PERMITTED = {SourceStatus.APPROVED, SourceStatus.CONDITIONAL, SourceStatus.PER_ITEM}


class ReuseReview(Contract):
    basis: NonEmpty
    reviewed_by: NonEmpty
    reviewed_at: date
    permitted_uses: tuple[str, ...]


class ApprovedItem(Contract):
    identifier: NonEmpty
    version: NonEmpty
    licence: NonEmpty


class ReferenceAccess(Contract):
    enabled: StrictBool
    basis: NonEmpty
    recorded_by: NonEmpty
    recorded_at: date
    permitted_uses: tuple[Literal["link", "metadata", "exam_facts"], ...]


class Source(Contract):
    id: NonEmpty
    name: NonEmpty
    status: SourceStatus
    category: NonEmpty
    jurisdiction: NonEmpty
    ingestion_enabled: StrictBool
    licence: NonEmpty
    reuse_review: ReuseReview | None = None
    approved_items: tuple[ApprovedItem, ...] = ()
    reference_urls: tuple[NonEmpty, ...] = ()
    review_notes: NonEmpty | None = None
    reference_access: ReferenceAccess | None = None

    @cached_property
    def approved_scope(self) -> frozenset[tuple[str, str, str]]:
        return frozenset((i.identifier, i.version, i.licence) for i in self.approved_items)

    def model_copy(self, *, update=None, deep=False):
        copied = super().model_copy(update=update, deep=deep)
        copied.__dict__.pop("approved_scope", None)
        return copied

    @model_validator(mode="after")
    def enforce_enabled_policy(self) -> Self:
        if self.reference_access and self.reference_access.enabled:
            if self.status not in PERMITTED or not {"link", "metadata"}.issubset(
                self.reference_access.permitted_uses
            ):
                raise ValueError("Reference access requires a permitted status and metadata scope")
        if not self.ingestion_enabled:
            return self
        if self.status not in PERMITTED:
            raise ValueError(f"Source {self.id} cannot be enabled with status {self.status}")
        if not self.reuse_review or not {"index", "retrieve"}.issubset(
            self.reuse_review.permitted_uses
        ):
            raise ValueError("Enabled sources require an indexing/retrieval reuse review")
        if self.category != "fixture" and not self.approved_items:
            raise ValueError("Enabled external sources require approved items")
        return self


class SourceNotPermittedError(ValueError):
    code = "source_not_permitted"


class SourceRegistry(Contract):
    sources: tuple[Source, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("Duplicate source ID")
        return self

    def assert_evidence_allowed(self, evidence: Provenance) -> None:
        source = next((row for row in self.sources if row.id == evidence.source_id), None)
        if not source or not source.ingestion_enabled or source.status not in PERMITTED:
            raise SourceNotPermittedError("Source is not enabled for ingestion/retrieval")
        if source.category == "fixture":
            if not (
                evidence.source_url_or_identifier.startswith("fixture:")
                and evidence.source_type.startswith("synthetic_")
                and evidence.licence == "CC-BY-4.0"
            ):
                raise SourceNotPermittedError("Fixture approval covers only original fixtures")
        elif (
            evidence.source_url_or_identifier,
            evidence.version,
            evidence.licence,
        ) not in source.approved_scope:
            raise SourceNotPermittedError("Evidence is outside recorded approval scope")


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicates just as the Node YAML parser does."""


def unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_registry(path: Path) -> SourceRegistry:
    # Re-read for each operation so a revocation never requires an API restart.
    return _parse_registry(path.read_text())


@lru_cache(maxsize=4)
def _parse_registry(contents: str) -> SourceRegistry:
    return SourceRegistry.model_validate(yaml.load(contents, Loader=UniqueKeyLoader))
