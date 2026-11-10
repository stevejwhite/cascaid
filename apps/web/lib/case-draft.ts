import type { components } from "./api.generated";

type Schemas = components["schemas"];
export type Fact = Schemas["Fact"];
export type Task = Schemas["Task"];
export type Persona = Schemas["Persona"];
export type AffectStage = Schemas["AffectStage"];
export type CharacterQuestion = Schemas["CharacterQuestion"];
export type Problem = Schemas["Problem"];

type DeepPartial<T> = T extends (infer U)[] ? DeepPartial<U>[] : T extends object ? { [K in keyof T]?: DeepPartial<T[K]> } : T;

/** A draft case: the shape of a case file, possibly incomplete. Unset optional fields are absent. */
export type DraftCase = DeepPartial<Schemas["Case"]>;
export type Path = (string | number)[];

/** A copy of `value` with `path` set; `undefined` removes the key (so defaults stay unwritten). */
export function setIn<T>(value: T, path: Path, next: unknown): T {
  if (path.length === 0) return next as T;
  const [head, ...rest] = path;
  if (Array.isArray(value)) {
    const copy = [...value];
    copy[head as number] = setIn(copy[head as number], rest, next);
    return copy as T;
  }
  const source = (value ?? {}) as Record<string, unknown>;
  const child = setIn(source[head as string], rest, next);
  const copy = { ...source };
  if (child === undefined) delete copy[head as string];
  else copy[head as string] = child;
  return copy as T;
}

export function getIn(value: unknown, path: Path): unknown {
  return path.reduce<unknown>((node, key) => (node == null ? undefined : (node as Record<string | number, unknown>)[key]), value);
}

/** The control ID for a case path, so a check error can link to its field. */
export const fieldId = (path: Path) => `field-${path.join("-")}`;

export function errorsAt(errors: readonly Problem[], path: Path): string[] {
  const key = JSON.stringify(path);
  return errors.filter((e) => JSON.stringify(e.loc) === key).map((e) => e.message);
}

/** A collision-checked ID from text; matches the server's slug rules. */
export function slug(text: string, taken: Iterable<string>, limit = 60): string {
  const used = new Set(taken);
  const base = text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, limit).replace(/-+$/, "") || "item";
  let candidate = base;
  for (let n = 2; used.has(candidate); n++) {
    const suffix = `-${n}`;
    candidate = base.slice(0, limit - suffix.length).replace(/-+$/, "") + suffix;
  }
  return candidate;
}

/** Fact, task and question IDs share one namespace within a case. */
export function itemIds(draft: DraftCase): string[] {
  return [...(draft.facts ?? []), ...(draft.tasks ?? []), ...(draft.questions ?? [])]
    .map((item) => item?.id).filter((id): id is string => Boolean(id));
}

export function addFact(draft: DraftCase, firstLabel: string): DraftCase {
  const fact = { id: slug(firstLabel, itemIds(draft)), content: "", disclosure: "on_direct_question" as const,
    asked_about: [firstLabel.trim()], domain: "" };
  return { ...draft, facts: [...(draft.facts ?? []), fact] };
}

export function duplicateFact(draft: DraftCase, index: number): DraftCase {
  const facts = [...(draft.facts ?? [])];
  const original = facts[index];
  const copy = { ...original, id: slug(`${original?.id ?? "fact"}-copy`, itemIds(draft)) };
  facts.splice(index + 1, 0, copy);
  return { ...draft, facts };
}

export function move<K extends "facts" | "tasks" | "questions" | "affect_stages">(draft: DraftCase, key: K, index: number, offset: -1 | 1): DraftCase {
  const items = [...((draft[key] ?? []) as unknown[])];
  const target = index + offset;
  if (target < 0 || target >= items.length) return draft;
  [items[index], items[target]] = [items[target], items[index]];
  return { ...draft, [key]: items };
}

export interface FactLinks { tasks: string[]; questions: string[] }

/** Tasks and character questions that depend on a fact. */
export function linksTo(draft: DraftCase, factId: string): FactLinks {
  return {
    tasks: (draft.tasks ?? []).filter((t) => t?.evidence_fact === factId).map((t) => t?.id ?? ""),
    questions: (draft.questions ?? []).filter((q) => q?.after_fact === factId).map((q) => q?.id ?? ""),
  };
}

/** Remove a fact. Linked tasks become self-review; linked questions are removed. */
export function removeFact(draft: DraftCase, factId: string): DraftCase {
  return {
    ...draft,
    facts: (draft.facts ?? []).filter((f) => f?.id !== factId),
    tasks: (draft.tasks ?? []).map((t) => (t?.evidence_fact === factId ? setIn(t, ["evidence_fact"], undefined) : t)),
    questions: (draft.questions ?? []).filter((q) => q?.after_fact !== factId),
  };
}

export function addTask(draft: DraftCase, description: string): DraftCase {
  const task = { id: slug(description, itemIds(draft)), description: description.trim(), domain: "" };
  return { ...draft, tasks: [...(draft.tasks ?? []), task] };
}

export function addQuestion(draft: DraftCase, text: string): DraftCase {
  const question = { id: slug(text, itemIds(draft)), text: text.trim(), after_seconds: 240 };
  return { ...draft, questions: [...(draft.questions ?? []), question] };
}

export function addStage(draft: DraftCase, affect: string): DraftCase {
  const stages = draft.affect_stages ?? [];
  const stage = { id: slug(affect, stages.map((s) => s?.id ?? "")), affect: affect.trim(),
    ...(stages.length ? { rapport_at_least: 1 as const } : {}) };
  return { ...draft, affect_stages: [...stages, stage] };
}

/** One entry per line, blank lines dropped. */
export const lines = (text: string) => text.split("\n").map((line) => line.trim()).filter(Boolean);
