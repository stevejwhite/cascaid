"""Draft checks: blocking errors from the runtime Case schema, and review prompts.

Errors come from the same validation the learner case loader applies. Prompts are simple
text checks that ask the author to look again; each says exactly what it checked. Neither
is a judgement of clinical accuracy or safety.
"""

import re
from typing import Any

from pydantic import ValidationError

from psychiatry_api.cases import Case
from psychiatry_api.domain import Contract

Loc = tuple[str | int, ...]


class Problem(Contract):
    loc: Loc
    message: str


class Prompt(Contract):
    loc: Loc
    message: str
    checked: str


class CheckResult(Contract):
    valid: bool
    errors: tuple[Problem, ...]
    prompts: tuple[Prompt, ...]


def clean(value: Any) -> Any:
    """Form state to case data: unset optional values (None, blank text or an emptied group
    such as a cleared voice) are omitted, so defaults stay unwritten."""
    if isinstance(value, dict):
        cleaned = {key: clean(item) for key, item in value.items()}
        return {
            key: item
            for key, item in cleaned.items()
            if item is not None
            and not (isinstance(item, str) and not item.strip())
            and not (isinstance(item, dict) and not item)
        }
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def validate(
    case: dict, *, taken_ids: set[str], source_version: str | None, revision: bool
) -> tuple[Case | None, tuple[Problem, ...]]:
    errors: list[Problem] = []
    data = clean(case)
    parsed = None
    try:
        parsed = Case.model_validate(data)
    except ValidationError as error:
        for item in error.errors():
            message = str(item["msg"]).removeprefix("Value error, ")
            errors.append(Problem(loc=tuple(item["loc"]), message=message))
    if not revision and data.get("id") in taken_ids:
        errors.append(Problem(loc=("id",), message="Another case already uses this ID"))
    if revision and source_version and re.fullmatch(r"\d+\.\d+\.\d+", str(data.get("version"))):
        if version_tuple(data["version"]) <= version_tuple(source_version):
            errors.append(
                Problem(
                    loc=("version",), message=f"A revision needs a version above {source_version}"
                )
            )
    return (parsed if not errors else None), tuple(errors)


STOP = frozenset(
    "about after again always because before being could doctor every going having their "
    "there these thing think those though through today whether which while would really "
    "never other people little since still where years months weeks first".split()
)


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 5 and w not in STOP}


def prompts(case: Case) -> tuple[Prompt, ...]:
    found: list[Prompt] = []
    shown = {
        ("persona", "opening_statement"): case.persona.opening_statement,
        ("persona", "description"): case.persona.description,
        ("candidate_instructions",): case.candidate_instructions,
    }
    for index, fact in enumerate(case.facts):
        if fact.disclosure == "volunteered":
            continue
        distinctive = words(fact.content)
        for loc, text in shown.items():
            shared = sorted(distinctive & words(text))
            # Three shared words, or every distinctive word of a short fact (at least two).
            if len(shared) >= max(2, min(3, len(distinctive))):
                found.append(
                    Prompt(
                        loc=loc,
                        message=f"May reveal the withheld fact “{fact.id}” from the start "
                        f"(shared words: {', '.join(shared[:5])}).",
                        checked="Words of five or more letters shared between a withheld "
                        "fact and text available from the start (three, or all of a short "
                        "fact's).",
                    )
                )
        if len(fact.asked_about) == 1:
            found.append(
                Prompt(
                    loc=("facts", index, "asked_about"),
                    message=f"“{fact.id}” has one question label; add a few other ways a "
                    "candidate might ask.",
                    checked="Number of question labels on the fact.",
                )
            )
        if fact.vague and fact.vague.strip().lower() == fact.content.strip().lower():
            found.append(
                Prompt(
                    loc=("facts", index, "vague"),
                    message=f"The vague answer for “{fact.id}” repeats the full answer.",
                    checked="Vague and full answers compared as text.",
                )
            )
    labels: dict[str, str] = {}
    for index, fact in enumerate(case.facts):
        for label in fact.asked_about:
            key = " ".join(label.lower().split())
            if key in labels and labels[key] != fact.id:
                found.append(
                    Prompt(
                        loc=("facts", index, "asked_about"),
                        message=f"The label “{label}” is also used by “{labels[key]}”; keep "
                        "labels distinct between facts.",
                        checked="Question labels compared across facts, ignoring case.",
                    )
                )
            labels.setdefault(key, fact.id)
    withheld = {f.id: f for f in case.facts if f.disclosure != "volunteered"}
    for index, question in enumerate(case.questions):
        for fact in withheld.values():
            if fact.id == question.after_fact:
                continue
            shared = sorted(words(fact.content) & words(question.text))
            if len(shared) >= 3:
                found.append(
                    Prompt(
                        loc=("questions", index, "text"),
                        message=f"This question may reveal “{fact.id}” before it is elicited "
                        f"(shared words: {', '.join(shared[:5])}).",
                        checked="Words of five or more letters shared between a character "
                        "question and other withheld facts.",
                    )
                )
    if case.persona.age is not None:
        for loc, text in shown.items():
            for match in re.finditer(r"\baged (\d{1,3})\b|\b(\d{1,3})-year-old\b", text):
                stated = int(match.group(1) or match.group(2))
                if stated != case.persona.age:
                    found.append(
                        Prompt(
                            loc=loc,
                            message=f"States age {stated}; the character's age is "
                            f"{case.persona.age}.",
                            checked="“aged N” and “N-year-old” compared with the age field.",
                        )
                    )
    if not case.tasks:
        found.append(
            Prompt(
                loc=("tasks",),
                message="No feedback tasks: the debrief will show the information checklist only.",
                checked="Number of tasks.",
            )
        )
    return tuple(found)


def check(
    case: dict, *, taken_ids: set[str], source_version: str | None, revision: bool
) -> CheckResult:
    parsed, errors = validate(
        case, taken_ids=taken_ids, source_version=source_version, revision=revision
    )
    return CheckResult(
        valid=parsed is not None, errors=errors, prompts=prompts(parsed) if parsed else ()
    )
