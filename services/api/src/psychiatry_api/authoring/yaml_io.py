"""Case YAML for authoring: edits merged into the original file so its comments survive.

A draft's case is plain JSON. On export it is merged into the source file's round-trip
tree: unchanged values keep their comments and styles, edited values are replaced in
place and lists of items with IDs are matched by ID. Any comment that cannot survive
(for example one attached to a deleted fact) is reported, never dropped silently.
"""

import io
import re
from collections import Counter
from typing import Any

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import FoldedScalarString, LiteralScalarString

from psychiatry_api.sources import UniqueKeyLoader

NEW_HEADER = (
    "Original fictional case for the CascAid CASC proof of concept (CC-BY-4.0).\n"
    "Author draft (case editor). Not clinically validated."
)
# Long prose is written as a folded block, as in the hand-written cases.
FOLD_AT = 100


def _yaml() -> YAML:
    y = YAML(typ="rt")
    y.indent(mapping=2, sequence=4, offset=2)
    # No re-wrapping: folded blocks keep their author's line breaks.
    y.width = 4096
    y.preserve_quotes = True
    return y


def plain(text: str) -> Any:
    """The data of a case file, parsed safely (no tags, no duplicate keys)."""
    return yaml.load(text, Loader=UniqueKeyLoader)


def _folded(text: str, width: int = 96) -> FoldedScalarString:
    """A folded block broken at spaces so no line exceeds `width` characters."""
    folded = FoldedScalarString(text)
    positions, start = [], 0
    while len(text) - start > width:
        space = text.rfind(" ", start, start + width)
        if space <= start or text[space - 1] == " " or text[space + 1 : space + 2] == " ":
            break
        positions.append(space)
        start = space + 1
    folded.fold_pos = positions
    return folded


def _styled(old: Any, new: Any) -> Any:
    if not isinstance(new, str):
        return new
    if "\n" in new:
        return LiteralScalarString(new)
    if isinstance(old, FoldedScalarString) or len(new) > FOLD_AT:
        return _folded(new)
    return new


def _build(value: Any) -> Any:
    if isinstance(value, dict):
        node = CommentedMap()
        for key, item in value.items():
            node[key] = _build(item)
        return node
    if isinstance(value, list):
        node = CommentedSeq(_build(item) for item in value)
        if all(isinstance(item, str | int | float | bool) for item in value) and value:
            node.fa.set_flow_style()
        return node
    return _styled(None, value)


def _same(old: Any, new: Any) -> bool:
    return _unstyle(old) == new


def _unstyle(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _unstyle(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unstyle(item) for item in value]
    return str(value) if isinstance(value, str) else value


def _merge_map(target: CommentedMap, new: dict) -> None:
    for key in [k for k in target if k not in new]:
        del target[key]
    for key, value in new.items():
        if key not in target:
            target[key] = _build(value)
        else:
            target[key] = _merge(target[key], value)


def _merge_seq(target: CommentedSeq, new: list) -> CommentedSeq:
    by_id = {item["id"]: item for item in target if isinstance(item, CommentedMap) and "id" in item}
    if by_id and all(isinstance(item, dict) and "id" in item for item in new):
        if [item["id"] for item in target] == [item["id"] for item in new]:
            for index, item in enumerate(new):
                target[index] = _merge(target[index], item)
            return target
        rebuilt = CommentedSeq()
        for item in new:
            existing = by_id.get(item["id"])
            rebuilt.append(_merge(existing, item) if existing is not None else _build(item))
        if target.fa.flow_style():
            rebuilt.fa.set_flow_style()
        return rebuilt
    if _same(target, new):
        return target
    rebuilt = _build(new)
    if isinstance(rebuilt, CommentedSeq) and target.fa.flow_style():
        rebuilt.fa.set_flow_style()
    return rebuilt


def _merge(target: Any, new: Any) -> Any:
    if isinstance(target, CommentedMap) and isinstance(new, dict):
        _merge_map(target, new)
        return target
    if isinstance(target, CommentedSeq) and isinstance(new, list):
        return _merge_seq(target, new)
    if _same(target, new):
        return target
    return _styled(target, new) if isinstance(new, str) else _build(new)


def _real_comments(text: str) -> set[str]:
    """Comment texts the YAML scanner recognises (not '#' inside quoted or block text)."""
    found = set()
    for token in _yaml().scan(text):
        for part in _comment_parts(getattr(token, "comment", None)):
            found |= {line.strip() for line in part.splitlines() if line.strip().startswith("#")}
    return found


def _anchor(line: str) -> str:
    """What a comment describes: the item ID or key on the line it precedes or ends."""
    text = line.strip()
    if text.startswith("- id:"):
        return text
    return text.removeprefix("- ").split(":", 1)[0]


def comments(text: str) -> Counter:
    """Every comment with the item or key it sits beside. A comment that ends up beside a
    different item counts as not kept, as well as one that disappears."""
    real = _real_comments(text)
    lines = text.splitlines()
    found: Counter = Counter()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            if stripped in real:
                following = next(
                    (n for n in lines[index + 1 :] if n.strip() and not n.strip().startswith("#")),
                    "",
                )
                found[(stripped, _anchor(following))] += 1
        elif " #" in line:
            inline = line[line.index(" #") + 1 :].strip()
            if inline in real:
                found[(inline, _anchor(line))] += 1
    return found


def _comment_parts(comment: Any) -> list[str]:
    if comment is None:
        return []
    if isinstance(comment, str):
        return [comment]
    if hasattr(comment, "value"):
        return [comment.value]
    if isinstance(comment, list | tuple):
        return [text for part in comment for text in _comment_parts(part)]
    return []


def render(case: dict, source_text: str | None) -> tuple[str, list[str]]:
    """The case as YAML, and any source comments the edits could not keep."""
    y = _yaml()
    if source_text:
        tree = y.load(source_text)
        tree = _merge(tree, case)
    else:
        tree = _build(case)
        tree.yaml_set_start_comment(NEW_HEADER)
    out = io.StringIO()
    y.dump(tree, out)
    text = out.getvalue()
    if plain(text) != case:
        raise ValueError("The rendered YAML does not match the draft")
    dropped = comments(source_text) - comments(text) if source_text else Counter()
    return text, sorted(comment for comment, _ in dropped.elements())


SLUG_PART = re.compile(r"[^a-z0-9]+")


def slug(text: str, taken: set[str], limit: int = 60) -> str:
    """A stable, collision-checked ID from text: lower-case words joined by hyphens."""
    base = SLUG_PART.sub("-", text.lower()).strip("-")[:limit].strip("-") or "item"
    candidate, number = base, 2
    while candidate in taken:
        suffix = f"-{number}"
        candidate = base[: limit - len(suffix)].strip("-") + suffix
        number += 1
    return candidate
