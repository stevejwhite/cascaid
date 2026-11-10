"""The station catalogue (data/catalogue/stations.yaml): definitions of a full set of
stations in the CASC blueprint's proportions, from which detailed cases are written.

Usage: npm run catalogue:doc   # regenerates docs/STATION-CATALOGUE.md
"""

from collections import Counter
from pathlib import Path

import yaml

from psychiatry_api.config import ROOT

CATALOGUE = ROOT / "data/catalogue/stations.yaml"
DOC = ROOT / "docs/STATION-CATALOGUE.md"

LABELS = {
    "history": "History",
    "examination": "Examination",
    "management": "Management",
    "presenting_complaint_and_psychiatric_history": "Presenting complaint and psychiatric history",
    "physical_health_history": "Physical health history",
    "developmental_history": "Developmental history",
    "personal_and_social_history": "Personal and social history",
    "collateral_history": "Collateral history",
    "mental_state_cognitive": "Mental state (cognitive)",
    "mental_state_psychotic": "Mental state (psychotic)",
    "mental_state_non_psychotic": "Mental state (non-psychotic)",
    "capacity_assessment": "Capacity assessment",
    "physical_examination": "Physical examination",
    "risk_assessment": "Risk assessment",
    "formulation": "Formulation",
    "management_biological": "Management (biological)",
    "management_psychological": "Management (psychological)",
    "holistic_management_plan": "Holistic management plan",
    "safety_planning": "Safety planning",
    "legal_and_ethical_management": "Legal and ethical management",
    "general": "General",
    "child_and_adolescent": "Child and adolescent",
    "intellectual_disability": "Intellectual disability",
    "old_age": "Old age",
    "forensic": "Forensic",
    "medical_psychotherapy": "Medical psychotherapy",
    "addiction": "Addiction",
    "personalisation_and_respect": "Personalisation and respect",
    "recognising_and_responding_to_cues": "Cues",
    "empathy": "Empathy",
    "providing_clear_and_accurate_information": "Clear information",
}


def load(path: Path = CATALOGUE) -> dict:
    return yaml.safe_load(path.read_text())


def running_orders(catalogue: dict) -> dict[str, list[dict]]:
    orders: dict[str, list[dict]] = {}
    for station in catalogue["stations"]:
        orders.setdefault(station["code"][0], []).append(station)
    return orders


def label(value: str) -> str:
    return LABELS.get(value, value.replace("_", " "))


def render(catalogue: dict) -> str:
    """docs/STATION-CATALOGUE.md, generated from the catalogue."""
    orders = running_orders(catalogue)
    blueprint = catalogue["blueprint"]
    stations = catalogue["stations"]
    lines = [
        "# Station catalogue",
        "",
        "<!-- Generated from data/catalogue/stations.yaml by `npm run catalogue:doc`; edit the",
        "YAML, not this file. -->",
        "",
        "Definitions for a full set of practice stations, from which detailed case files will be",
        "written ([NEW-STATION-PROCESS.md](NEW-STATION-PROCESS.md)). All are original fiction and",
        "not clinically validated. The set follows the pinned MRCPsych CASC Syllabus and Blueprint",
        f"(March 2023): **{len(orders)} complete running orders of 16 stations** "
        f"({len(stations)} stations). Each running order is valid on its own, with the exam's",
        "proportions; together they meet every minimum frequency in the blueprint matrix.",
        "`services/api/tests/test_station_catalogue.py` checks every rule below.",
        "",
        "## How the set follows the blueprint",
        "",
        "Every running order has 5 history, 5 examination and 6 management stations: in the",
        "morning session 6 management, 1 history and 1 examination station (4 minutes' reading);",
        "in the afternoon 4 history and 4 examination stations (90 seconds' reading). Each has",
        "at least four general psychiatry stations and at least one in each other specialty;",
        "at least one station of risk assessment or safety planning, of cognition or capacity,",
        "and of physical health history or physical examination; and each communication",
        "subdivision as the emphasis of at least one station.",
        "",
        "### Skill subdivisions: running orders that test each, against the blueprint minimum",
        "",
        "| Skill | Subdivision | Running orders | Stations | Minimum |",
        "|---|---|---|---|---|",
    ]
    for skill, count in blueprint["stations_per_running_order"].items():
        subs = [
            s
            for s, _ in blueprint["minimum_percentage"].items()
            if any(st["skill"] == skill and st["subdivision"] == s for st in stations)
        ]
        for sub in subs:
            present = sum(any(st["subdivision"] == sub for st in o) for o in orders.values())
            total = sum(st["subdivision"] == sub for st in stations)
            pct = 100 * present // len(orders)
            lines.append(
                f"| {label(skill)} ({count} per order) | {label(sub)} | "
                f"{present} of {len(orders)} ({pct}%) | {total} | "
                f"{blueprint['minimum_percentage'][sub]}% |"
            )
    lines += [
        "",
        "### Specialties per running order",
        "",
        "| Running order | " + " | ".join(label(s) for s in blueprint["minimum_specialty"]) + " |",
        "|---|" + "---|" * len(blueprint["minimum_specialty"]),
    ]
    for code, order in orders.items():
        counts = Counter(st["specialty"] for st in order)
        lines.append(
            f"| {code} | "
            + " | ".join(str(counts[s]) for s in blueprint["minimum_specialty"])
            + " |"
        )
    lines.append(
        "| Minimum | " + " | ".join(str(v) for v in blueprint["minimum_specialty"].values()) + " |"
    )
    coverage = catalogue["coverage"]
    conditions = Counter(st["condition"] for st in stations)
    lines += [
        "",
        "### Range of clinical scenarios",
        "",
        "Every disorder group the syllabus lists appears at least once:",
        "",
        "| Condition group | Stations |",
        "|---|---|",
    ]
    for key, name in coverage["condition_groups"].items():
        codes = ", ".join(st["code"] for st in stations if st["condition"] == key)
        lines.append(f"| {name} | {codes} ({conditions[key]}) |")
    sources = {
        "Settings": lambda st: st["setting"],
        "Patients' age bands": lambda st: st.get("patient_age_band") or st["meets"]["age_band"],
        "Who the candidate meets": lambda st: st["meets"]["role"],
    }
    for title, source in sources.items():
        counts = Counter(source(st) for st in stations)
        lines += [
            "",
            f"**{title}:** " + "; ".join(f"{k.replace('_', ' ')} {counts[k]}" for k in counts),
        ]
    physical = [st["code"] for st in stations if st.get("simulator") == "physical_examination"]
    existing = [
        f"{st['code']} ({st['existing_case']})" for st in stations if st.get("existing_case")
    ]
    lines += [
        "",
        "**Already written as cases:** " + ", ".join(existing) + ".",
        "",
        "**Need a new simulator mechanism:** "
        + ", ".join(physical)
        + " (physical examination: the candidate examines and asks for findings, which the",
        "current voice simulator cannot yet provide).",
        "",
    ]
    for code, order in orders.items():
        lines += [
            f"## Running order {code}",
            "",
            "| Code | Session | Skill: subdivision | Specialty | Emphasis | Setting | Meets "
            "| Scenario | Task |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for st in order:
            meets = f"{st['meets']['who']} ({st['meets']['role']})"
            mark = " ✱" if st.get("existing_case") else ""
            slot = f"{label(st['skill'])}: {label(st['subdivision'])}"
            setting = st["setting"].replace("_", " ")
            cells = [
                f"{st['code']}{mark}",
                st["session"],
                slot,
                label(st["specialty"]),
                label(st["communication"]),
                setting,
                meets,
                st["scenario"],
                st["task"],
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines += ["", "✱ already written as a case.", ""]
    return "\n".join(lines)


def main() -> None:
    DOC.write_text(render(load()))
    print(f"Wrote {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
