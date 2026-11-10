"""Which case versions a trained model saw, so a newer case is reported, never assumed covered.

A manifest maps each case ID to its version and file hash. The fine-tune export writes one
beside its training data; when a model is pinned in config/finetune.json, its manifest is
copied to config/model-cases/<model name>.json and committed with the registry entry.
"""

import hashlib
import json
from pathlib import Path

from psychiatry_api.cases import load_cases
from psychiatry_api.config import ROOT

MANIFESTS = ROOT / "config/model-cases"


def case_manifest(cases_path: Path) -> dict[str, dict[str, str]]:
    return {
        case.id: {
            "version": case.version,
            "sha256": hashlib.sha256((cases_path / f"{case.id}.yaml").read_bytes()).hexdigest(),
        }
        for case in load_cases(cases_path)
    }


def write_manifest(cases_path: Path, file: Path) -> None:
    file.write_text(json.dumps(case_manifest(cases_path), indent=2, sort_keys=True) + "\n")


def drift(cases_path: Path, model: str, manifests: Path = MANIFESTS) -> str | None:
    """A sentence naming cases the model was not trained on, or None if it saw them all."""
    file = manifests / f"{model}.json"
    if not file.exists():
        return f"The case set {model} was trained on is not recorded."
    trained = json.loads(file.read_text())
    current = case_manifest(cases_path)
    changed = sorted(i for i in current if i in trained and trained[i] != current[i])
    added = sorted(i for i in current if i not in trained)
    if not changed and not added:
        return None
    parts = []
    if changed:
        parts.append(f"{len(changed)} changed since training ({', '.join(changed[:3])})")
    if added:
        parts.append(f"{len(added)} added since training ({', '.join(added[:3])})")
    return f"{model}: " + "; ".join(parts) + "."
