"use client";

import { useState, type ReactNode } from "react";
import type { Choice } from "../../lib/authoring";
import { errorsAt, fieldId, lines, type Path, type Problem } from "../../lib/case-draft";

interface Common {
  label: string;
  path: Path;
  errors: readonly Problem[];
  hint?: ReactNode;
}

function Messages({ id, hint, errors }: { id: string; hint?: ReactNode; errors: string[] }) {
  return <>
    {hint && <span className="field-hint" id={`${id}-hint`}>{hint}</span>}
    {errors.map((message) => <span key={message} className="field-error" id={`${id}-error`}><strong>Error:</strong> {message}</span>)}
  </>;
}

function described(id: string, hint: unknown, errors: string[]) {
  return [hint ? `${id}-hint` : "", errors.length ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
}

export function TextField({ label, path, errors, hint, value, onChange, multiline, type = "text", list }: Common & {
  value: string | number | null | undefined;
  onChange: (value: string | undefined) => void;
  multiline?: boolean;
  type?: "text" | "number";
  list?: string;
}) {
  const id = fieldId(path), found = errorsAt(errors, path);
  const props = {
    id, value: value ?? "", "aria-invalid": found.length > 0 || undefined,
    "aria-describedby": described(id, hint, found),
    onChange: (e: { target: { value: string } }) => onChange(e.target.value === "" ? undefined : e.target.value),
  };
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    {multiline ? <textarea rows={3} {...props} /> : <input type={type} list={list} {...props} />}
    <Messages id={id} hint={hint} errors={found} />
  </div>;
}

/** A list edited one entry per line. Keeps the raw text while typing. */
export function LinesField({ label, path, errors, hint, value, onChange }: Common & {
  value: readonly (string | undefined)[] | undefined;
  onChange: (value: string[]) => void;
}) {
  const id = fieldId(path), found = errorsAt(errors, path);
  const joined = (value ?? []).join("\n");
  const [editing, setEditing] = useState(false);
  const [local, setLocal] = useState({ text: joined, base: joined });
  // Follow outside changes (such as a reload) except while the author is typing.
  if (!editing && local.base !== joined) setLocal({ text: joined, base: joined });
  const text = local.text;
  const setText = (next: string) => setLocal({ text: next, base: lines(next).join("\n") });
  const itemErrors = errors.filter((e) => JSON.stringify(e.loc.slice(0, path.length)) === JSON.stringify(path) && e.loc.length > path.length);
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    <textarea id={id} rows={Math.max(2, Math.min(6, (value?.length ?? 0) + 1))} value={text}
      aria-invalid={found.length + itemErrors.length > 0 || undefined}
      aria-describedby={described(id, hint, [...found, ...itemErrors.map((e) => e.message)])}
      onFocus={() => setEditing(true)}
      onBlur={() => { setEditing(false); onChange(lines(text)); }}
      onChange={(e) => { setText(e.target.value); onChange(lines(e.target.value)); }} />
    <Messages id={id} hint={hint} errors={[...found, ...itemErrors.map((e) => e.message)]} />
  </div>;
}

export function SelectField({ label, path, errors, hint, value, choices, onChange, blank }: Common & {
  value: string | number | null | undefined;
  choices: readonly Choice[];
  onChange: (value: string | undefined) => void;
  blank?: string;
}) {
  const id = fieldId(path), found = errorsAt(errors, path);
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    <select id={id} value={value ?? ""} aria-invalid={found.length > 0 || undefined}
      aria-describedby={described(id, hint, found)}
      onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}>
      {blank !== undefined && <option value="">{blank}</option>}
      {choices.map((choice) => <option key={String(choice.value)} value={String(choice.value)}>{choice.label}</option>)}
    </select>
    <Messages id={id} hint={hint} errors={found} />
  </div>;
}

export function CheckField({ label, path, errors, hint, checked, onChange }: Common & {
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const id = fieldId(path), found = errorsAt(errors, path);
  return <div className="field field-check">
    <input id={id} type="checkbox" checked={checked} aria-describedby={described(id, hint, found)}
      onChange={(e) => onChange(e.target.checked)} />
    <label htmlFor={id}>{label}</label>
    <Messages id={id} hint={hint} errors={found} />
  </div>;
}
