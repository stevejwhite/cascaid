import pytest
from pydantic import ValidationError

from psychiatry_api.sources import SourceNotPermittedError, SourceRegistry, load_registry


def test_same_fixture_provenance_is_allowed_and_external_sources_are_denied(settings, provenance):
    registry = load_registry(settings.source_registry_path)
    registry.assert_evidence_allowed(provenance)
    for source_id in ["unknown", "nice", "bnf", "dsm5tr", "mrcpsych_casc"]:
        with pytest.raises(SourceNotPermittedError):
            registry.assert_evidence_allowed(provenance.model_copy(update={"source_id": source_id}))
    with pytest.raises(SourceNotPermittedError):
        registry.assert_evidence_allowed(
            provenance.model_copy(
                update={"source_url_or_identifier": "https://example.invalid/content"}
            )
        )


def test_permission_change_takes_effect_without_process_restart(settings, provenance, tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(settings.source_registry_path.read_text())
    load_registry(path).assert_evidence_allowed(provenance)
    path.write_text(path.read_text().replace("ingestion_enabled: true", "ingestion_enabled: false"))
    with pytest.raises(SourceNotPermittedError):
        load_registry(path).assert_evidence_allowed(provenance)


def test_invalid_registry_states_and_duplicate_yaml_fail(settings, tmp_path):
    registry = load_registry(settings.source_registry_path).model_dump(mode="json")
    registry["sources"][1]["ingestion_enabled"] = True
    registry["sources"][1]["status"] = "pending_permission"
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(registry)
    path = tmp_path / "duplicate.yaml"
    path.write_text("sources: []\nsources: []\n")
    with pytest.raises(ValueError, match="Duplicate"):
        load_registry(path)


def test_external_permission_is_scoped_to_item_version_licence(provenance):
    from psychiatry_api.sources import Source

    source = Source.model_validate(
        {
            "id": "external_fixture",
            "name": "Test",
            "status": "approved",
            "category": "guidance",
            "jurisdiction": "Testland",
            "ingestion_enabled": True,
            "licence": "CC-BY-4.0",
            "reuse_review": {
                "basis": "Original test data",
                "reviewed_by": "test",
                "reviewed_at": "2026-09-26",
                "permitted_uses": ["index", "retrieve"],
            },
            "approved_items": [
                {
                    "identifier": "https://example.invalid/fixture",
                    "version": "1",
                    "licence": "CC-BY-4.0",
                }
            ],
        }
    )
    registry = SourceRegistry(sources=(source,))
    item = provenance.model_copy(
        update={
            "source_id": source.id,
            "source_url_or_identifier": "https://example.invalid/fixture",
            "version": "1",
        }
    )
    registry.assert_evidence_allowed(item)
    for change in [
        {"version": "2"},
        {"licence": "proprietary"},
        {"source_url_or_identifier": "https://example.invalid/other"},
    ]:
        with pytest.raises(SourceNotPermittedError):
            registry.assert_evidence_allowed(item.model_copy(update=change))
