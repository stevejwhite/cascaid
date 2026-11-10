"""Versioned CASC-style station cases with a hidden structured state.

A case is the source of truth for a simulated interview. The role-player model is
shown only the persona and the facts its disclosure rules currently allow, so it
cannot reveal what it was never given. Station structure follows the pinned CASC
blueprint (March 2023); cases are original fiction and are not clinically validated.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import AfterValidator, Field, ValidationError, model_validator

from psychiatry_api.config import ROOT
from psychiatry_api.domain import Contract, NonEmpty
from psychiatry_api.sources import UniqueKeyLoader

CASES_PATH = ROOT / "data/cases"
BLUEPRINT_SOURCE_ID = "mrcpsych_casc"
BLUEPRINT_VERSION = (
    "March 2023 | sha256:ae1eac93e556b3701a4aae70f1f9e784ad47ecd51ff69a0ae70631a703062a99"
)
# Blueprint: every station is seven minutes; reading time is four minutes in the
# morning session and 90 seconds in the afternoon session.
INTERVIEW_SECONDS = 420
READING_SECONDS = frozenset({90, 240})

Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$", max_length=60)]


class Skill(StrEnum):
    HISTORY = "history"
    EXAMINATION = "examination"
    MANAGEMENT = "management"


SUBDIVISIONS: dict[Skill, frozenset[str]] = {
    Skill.HISTORY: frozenset(
        {
            "presenting_complaint_and_psychiatric_history",
            "physical_health_history",
            "developmental_history",
            "personal_and_social_history",
            "collateral_history",
        }
    ),
    Skill.EXAMINATION: frozenset(
        {
            "mental_state_cognitive",
            "mental_state_psychotic",
            "mental_state_non_psychotic",
            "capacity_assessment",
            "physical_examination",
            "risk_assessment",
        }
    ),
    Skill.MANAGEMENT: frozenset(
        {
            "formulation",
            "management_biological",
            "management_psychological",
            "holistic_management_plan",
            "safety_planning",
            "legal_and_ethical_management",
        }
    ),
}

Specialty = Literal[
    "general",
    "child_and_adolescent",
    "old_age",
    "intellectual_disability",
    "forensic",
    "medical_psychotherapy",
    "addiction",
]
CommunicationFocus = Literal[
    "personalisation_and_respect",
    "recognising_and_responding_to_cues",
    "empathy",
    "providing_clear_and_accurate_information",
]


class Blueprint(Contract):
    source_id: Literal["mrcpsych_casc"] = BLUEPRINT_SOURCE_ID
    version: NonEmpty = BLUEPRINT_VERSION
    skill: Skill
    subdivision: NonEmpty
    specialty: Specialty
    communication_focus: tuple[CommunicationFocus, ...] = ()

    @model_validator(mode="after")
    def known_subdivision(self) -> Self:
        if self.version != BLUEPRINT_VERSION:
            raise ValueError("Cases must target the pinned CASC blueprint version")
        if self.subdivision not in SUBDIVISIONS[self.skill]:
            raise ValueError(f"{self.subdivision} is not a {self.skill} subdivision")
        return self


class Timing(Contract):
    reading_seconds: int
    interview_seconds: int = INTERVIEW_SECONDS

    @model_validator(mode="after")
    def blueprint_timing(self) -> Self:
        if self.reading_seconds not in READING_SECONDS:
            raise ValueError("Reading time must be 90 or 240 seconds")
        if self.interview_seconds != INTERVIEW_SECONDS:
            raise ValueError("Stations last seven minutes")
        return self


class VoiceHint(Contract):
    """How the character should sound when replies are read aloud; not a hidden fact."""

    sex: Literal["female", "male"] | None = None
    age: Literal["young", "adult", "older"] = "adult"
    # A BCP 47 English accent tag, such as en-GB or en-IE.
    accent: Annotated[str, Field(pattern=r"^en-[A-Z]{2}$")] = "en-GB"
    # The neural voice to use when local speech synthesis is installed (config/tts-runtime.json).
    speaker: Annotated[str, Field(pattern=r"^[a-z]{2}_[a-z]{2,20}$")] | None = None


class Persona(Contract):
    role: Literal["patient", "relative", "carer", "colleague"]
    name: NonEmpty
    age: int | None = Field(default=None, ge=0, le=120)
    description: NonEmpty
    speech_style: NonEmpty
    affect: NonEmpty
    opening_statement: NonEmpty
    voice: VoiceHint = Field(default_factory=VoiceHint)
    # The 3D character who plays this persona (config/avatar-register.json); presentation only.
    avatar: Slug | None = None


class Fact(Contract):
    """Something the role-player knows, and when it may be revealed.

    volunteered: may be offered unprompted. on_direct_question: only once the
    candidate asks about one of ``asked_about``. after_rapport: as for a direct
    question, but only after the candidate has shown empathy or acknowledgement.
    ``asked_about`` labels are what the interpreter matches questions against, so even
    volunteered facts need them; keep labels distinctive between facts.
    """

    id: Slug
    content: NonEmpty
    disclosure: Literal["volunteered", "on_direct_question", "after_rapport"]
    asked_about: tuple[NonEmpty, ...] = Field(min_length=1)
    domain: Slug
    key: bool = False
    # after_rapport only: the rapport level needed (1: brief empathy; 2: specific empathy
    # or repeated empathy). Defaults to 1.
    rapport_needed: Literal[1, 2] | None = None
    # A less specific version given the first time the fact is asked about; asking again
    # gets the full content. Feedback reports a fact revealed only vaguely as touched on.
    vague: NonEmpty | None = None

    @model_validator(mode="after")
    def gated_options(self) -> Self:
        if self.rapport_needed and self.disclosure != "after_rapport":
            raise ValueError(f"Fact {self.id}: rapport_needed applies only to after_rapport facts")
        if self.vague and self.disclosure == "volunteered":
            raise ValueError(f"Fact {self.id}: a volunteered fact cannot have a vague version")
        return self


class Task(Contract):
    """A candidate action. Feedback marks it met from a linked communication indicator or
    an elicited fact; tasks with neither are left for the candidate's self-review."""

    id: Slug
    description: NonEmpty
    domain: Slug
    evidence_indicator: (
        Literal["summary", "check_understanding", "empathy", "open_question"] | None
    ) = None
    evidence_fact: Slug | None = None

    @model_validator(mode="after")
    def one_kind_of_evidence(self) -> Self:
        if self.evidence_indicator and self.evidence_fact:
            raise ValueError(f"Task {self.id} links both an indicator and a fact")
        return self


# How the 3D character's face shows an affect stage.
Expression = Literal[
    "neutral", "warm", "cheerful", "sad", "tearful", "anxious", "tense", "irritable", "flat"
]
# Thinking sounds a character may voice during a long wait, from a closed list so they can
# carry no fact, number or name, and are not the start of a sentence: "Hmmm.", "Mm.",
# "OK.", "Right.", or two joined ("Mm, OK.").
FILLERS = frozenset({"mm", "hmmm", "um", "ok", "okay", "right"})


def _filler(text: str) -> str:
    parts = [part.strip(" .…").lower() for part in text.split(",")]
    if not text.strip() or not all(part in FILLERS for part in parts):
        raise ValueError(f"Hesitations must be thinking sounds such as 'Hmmm.', not {text!r}")
    return text


Hesitation = Annotated[str, Field(max_length=20), AfterValidator(_filler)]


class AffectStage(Contract):
    """How the character feels at one point in the interview.

    The first stage applies from the start. A stage with rapport_at_least applies once the
    running rapport reaches that level; an on_confrontation stage applies for the turn of a
    confrontational line and the turn after, and takes precedence.

    expression and hesitations are presentation only: how the 3D character looks, and
    fillers it may voice while thinking. Neither changes what it knows or reveals.
    """

    id: Slug
    affect: NonEmpty
    rapport_at_least: Literal[1, 2] | None = None
    on_confrontation: bool = False
    expression: Expression = "neutral"
    hesitations: tuple[Hesitation, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def one_trigger(self) -> Self:
        if self.rapport_at_least and self.on_confrontation:
            raise ValueError(f"Affect stage {self.id} has two triggers")
        return self


class CharacterQuestion(Contract):
    """A question the character asks, appended verbatim to its reply once due.

    after_fact: on the turn that fact is first revealed (or the next free turn after).
    after_seconds: on the first turn this far into the interview. Authors must make sure
    a question reveals nothing the candidate has not yet elicited.
    """

    id: Slug
    text: NonEmpty
    after_fact: Slug | None = None
    after_seconds: int | None = Field(default=None, ge=0, le=INTERVIEW_SECONDS)

    @model_validator(mode="after")
    def one_trigger(self) -> Self:
        if (self.after_fact is None) == (self.after_seconds is None):
            raise ValueError(f"Question {self.id} needs exactly one of after_fact, after_seconds")
        return self


class Authorship(Contract):
    author: NonEmpty
    status: Literal["author_draft", "author_reviewed"]
    # Explicit so every export and screen can state it; the POC has no clinician review.
    clinically_validated: Literal[False] = False


class Case(Contract):
    id: Slug
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    title: NonEmpty
    blueprint: Blueprint
    timing: Timing
    authorship: Authorship
    candidate_instructions: NonEmpty
    persona: Persona
    facts: tuple[Fact, ...] = Field(min_length=1)
    tasks: tuple[Task, ...] = ()
    unscripted_response: NonEmpty
    # Alternative in-character deflections, rotated so the character does not repeat itself.
    deflections: tuple[NonEmpty, ...] = ()
    affect_stages: tuple[AffectStage, ...] = ()
    questions: tuple[CharacterQuestion, ...] = ()

    def deflection(self, seed: int) -> str:
        options = (self.unscripted_response, *self.deflections)
        return options[seed % len(options)]

    @model_validator(mode="after")
    def consistent_ids(self) -> Self:
        ids = [fact.id for fact in self.facts] + [task.id for task in self.tasks]
        ids += [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Fact, task and question IDs must be unique within a case")
        if not any(fact.key for fact in self.facts):
            raise ValueError("A case needs at least one key fact for marking")
        facts = {fact.id for fact in self.facts}
        for task in self.tasks:
            if task.evidence_fact and task.evidence_fact not in facts:
                raise ValueError(f"Task {task.id} links unknown fact {task.evidence_fact}")
        for question in self.questions:
            if question.after_fact and question.after_fact not in facts:
                raise ValueError(
                    f"Question {question.id} follows unknown fact {question.after_fact}"
                )
        stages = self.affect_stages
        if stages:
            if len({stage.id for stage in stages}) != len(stages):
                raise ValueError("Affect stage IDs must be unique")
            if stages[0].rapport_at_least or stages[0].on_confrontation:
                raise ValueError("The first affect stage is the starting one and has no trigger")
            if sum(stage.on_confrontation for stage in stages) > 1:
                raise ValueError("Only one affect stage can follow confrontation")
        return self


class CaseSummary(Contract):
    """What a candidate may see before and during a station; never the hidden facts."""

    id: str
    version: str
    title: str
    skill: Skill
    subdivision: str
    specialty: Specialty
    reading_seconds: int
    interview_seconds: int
    role: str
    candidate_instructions: str
    authorship_status: str
    clinically_validated: bool
    voice: VoiceHint
    avatar: str | None

    @classmethod
    def of(cls, case: Case) -> "CaseSummary":
        return cls(
            id=case.id,
            version=case.version,
            title=case.title,
            skill=case.blueprint.skill,
            subdivision=case.blueprint.subdivision,
            specialty=case.blueprint.specialty,
            reading_seconds=case.timing.reading_seconds,
            interview_seconds=case.timing.interview_seconds,
            role=case.persona.role,
            candidate_instructions=case.candidate_instructions,
            authorship_status=case.authorship.status,
            clinically_validated=case.authorship.clinically_validated,
            voice=case.persona.voice,
            avatar=case.persona.avatar,
        )


def load_case(path: Path) -> Case:
    try:
        case = _parse_case(path.read_text())
    except ValidationError as error:
        # Name the file and field, never the offending value.
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "case"
        raise ValueError(f"{path.name}: {where}: {first['msg']}") from error
    if case.id != path.stem:
        raise ValueError(f"Case file {path.name} must be named after its ID")
    return case


@lru_cache(maxsize=64)
def _parse_case(contents: str) -> Case:
    return Case.model_validate(yaml.load(contents, Loader=UniqueKeyLoader))


def load_cases(root: Path = CASES_PATH) -> tuple[Case, ...]:
    cases = tuple(load_case(path) for path in sorted(root.glob("*.yaml")))
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate case ID")
    return cases
