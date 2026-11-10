import pytest

from psychiatry_api.config import ROOT, Settings
from psychiatry_api.domain import Provenance


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        model_backend="fake",
        source_registry_path=ROOT / "config/sources.yaml",
        cases_path=ROOT / "data/cases",
        readiness_timeout_seconds=0.1,
    )


@pytest.fixture
def provenance() -> Provenance:
    return Provenance(
        source_id="synthetic_fixtures",
        publisher="PsychiatryEduAI",
        source_type="synthetic_case",
        title="Original fictional case",
        source_url_or_identifier="fixture:elevated-mood-history",
        version="0.1.0",
        jurisdiction="synthetic",
        licence="CC-BY-4.0",
        retrieved_at="2026-10-07T00:00:00Z",
    )
