"""Version linkage between cases, trained models and evaluation sets."""

import json
import shutil

import yaml

from psychiatry_api.case_versions import case_manifest, drift, write_manifest
from psychiatry_api.cases import CASES_PATH, load_cases
from psychiatry_api.config import ROOT


def test_drift_names_changed_and_added_cases(tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    for name in ("alcohol-history", "memory-collateral-history"):
        shutil.copy(CASES_PATH / f"{name}.yaml", cases)
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    write_manifest(cases, manifests / "student-x.json")
    assert drift(cases, "student-x", manifests) is None
    edited = cases / "alcohol-history.yaml"
    edited.write_text(edited.read_text().replace("title:", "# edited\ntitle:", 1))
    shutil.copy(CASES_PATH / "overdose-risk-assessment.yaml", cases)
    note = drift(cases, "student-x", manifests)
    assert "1 changed since training (alcohol-history)" in note
    assert "1 added since training (overdose-risk-assessment)" in note
    assert "not recorded" in drift(cases, "student-y", manifests)


def test_manifest_records_versions_and_hashes():
    manifest = case_manifest(CASES_PATH)
    case = next(iter(load_cases()))
    assert manifest[case.id]["version"] == case.version
    assert len(manifest[case.id]["sha256"]) == 64
    json.dumps(manifest)


def test_evaluation_sets_name_the_case_version_they_were_written_for():
    cases = {case.id: case for case in load_cases()}
    folders = ("data/evaluation/interpreter", "data/evaluation/scripts")
    for path in sorted(p for f in folders for p in (ROOT / f).glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        assert data["case_version"] == cases[data["case_id"]].version, path.name
