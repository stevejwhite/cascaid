"""Candidate-visible blueprint matrix, without author guidance or hidden case facts."""

from pathlib import Path
from typing import Literal

from psychiatry_api import catalogue
from psychiatry_api.cases import (
    BLUEPRINT_SOURCE_ID,
    BLUEPRINT_VERSION,
    SUBDIVISIONS,
    Skill,
    Specialty,
    load_cases,
)
from psychiatry_api.domain import Contract


class MatrixSubdivision(Contract):
    skill: Skill
    id: str
    label: str
    minimum_percentage: int


class MatrixStation(Contract):
    code: str
    running_order: str
    session: Literal["morning", "afternoon"]
    skill: Skill
    subdivision: str
    specialty: Specialty
    title: str
    case_id: str | None
    unavailable_reason: str | None
    clinically_validated: bool


class BlueprintMatrix(Contract):
    source_id: str
    version: str
    stations_per_running_order: dict[Skill, int]
    minimum_specialty: dict[Specialty, int]
    reading_seconds: dict[str, int]
    subdivisions: tuple[MatrixSubdivision, ...]
    stations: tuple[MatrixStation, ...]


def matrix(cases_path: Path) -> BlueprintMatrix:
    data = catalogue.load()
    blueprint = data["blueprint"]
    if (blueprint["source_id"], blueprint["version"]) != (
        BLUEPRINT_SOURCE_ID,
        BLUEPRINT_VERSION,
    ):
        raise ValueError("Catalogue must use the pinned blueprint")
    cases = {case.id: case for case in load_cases(cases_path)}
    subdivisions = tuple(
        MatrixSubdivision(
            skill=skill,
            id=subdivision,
            label=catalogue.label(subdivision),
            minimum_percentage=minimum,
        )
        for skill in Skill
        for subdivision, minimum in blueprint["minimum_percentage"].items()
        if subdivision in SUBDIVISIONS[skill]
    )
    stations = []
    for entry in data["stations"]:
        case = cases.get(entry.get("existing_case"))
        reason = None
        if entry.get("simulator") == "physical_examination":
            reason = "Physical examination is not supported by the simulator."
        elif case is None:
            reason = "No runnable case is available yet."
        if case is not None and any(
            getattr(case.blueprint, key) != entry[key]
            for key in ("skill", "subdivision", "specialty")
        ):
            raise ValueError("Catalogue and case blueprint disagree")
        stations.append(
            MatrixStation(
                code=entry["code"],
                running_order=entry["code"][0],
                session=entry["session"],
                skill=entry["skill"],
                subdivision=entry["subdivision"],
                specialty=entry["specialty"],
                title=case.title if case is not None else entry["task"],
                case_id=case.id if case is not None and reason is None else None,
                unavailable_reason=reason,
                clinically_validated=case.authorship.clinically_validated if case else False,
            )
        )
    return BlueprintMatrix(
        source_id=blueprint["source_id"],
        version=blueprint["version"],
        stations_per_running_order=blueprint["stations_per_running_order"],
        minimum_specialty=blueprint["minimum_specialty"],
        reading_seconds={
            key: value["reading_seconds"] for key, value in blueprint["sessions"].items()
        },
        subdivisions=subdivisions,
        stations=tuple(stations),
    )
