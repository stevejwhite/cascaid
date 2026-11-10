"use client";

import type { AuthoringOptions } from "../../lib/authoring";
import type { DraftCase, Path, Problem } from "../../lib/case-draft";
import { CheckField, SelectField, TextField } from "./fields";

export interface SectionProps {
  draft: DraftCase;
  options: AuthoringOptions;
  errors: readonly Problem[];
  update: (path: Path, value: unknown) => void;
}

export function StationSection({ draft, options, errors, update, kind }: SectionProps & { kind: "new" | "revision" }) {
  const blueprint = draft.blueprint ?? {};
  const skill = String(blueprint.skill ?? "history");
  const focus = new Set(blueprint.communication_focus ?? []);
  return <section aria-labelledby="station-heading" className="editor-section">
    <h2 id="station-heading">1. Station</h2>
    <p className="field-hint">
      Case ID <code>{draft.id}</code> · version <code>{draft.version}</code>
      {kind === "revision" ? " (revision: the ID stays the same)" : " (new case: the ID was fixed when the draft was created)"}
    </p>
    <TextField label="Title" path={["title"]} errors={errors} value={draft.title} onChange={(v) => update(["title"], v)}
      hint="Changing the title does not change the case ID." />
    {kind === "revision" && <TextField label="Version for export" path={["version"]} errors={errors} value={draft.version}
      onChange={(v) => update(["version"], v)} hint="Must be higher than the active case's version." />}
    <TextField label="Candidate instructions" path={["candidate_instructions"]} errors={errors} multiline
      value={draft.candidate_instructions} onChange={(v) => update(["candidate_instructions"], v)}
      hint="A bounded task: who the candidate is, who they are meeting and what to do (and not do)." />
    <div className="field-row">
      <SelectField label="Skill" path={["blueprint", "skill"]} errors={errors} value={skill} choices={options.skills}
        onChange={(v) => { update(["blueprint", "skill"], v); update(["blueprint", "subdivision"], options.subdivisions[v ?? "history"]?.[0]?.value); }} />
      <SelectField label="Subdivision" path={["blueprint", "subdivision"]} errors={errors} value={blueprint.subdivision}
        choices={options.subdivisions[skill] ?? []} onChange={(v) => update(["blueprint", "subdivision"], v)} />
      <SelectField label="Specialty" path={["blueprint", "specialty"]} errors={errors} value={blueprint.specialty}
        choices={options.specialties} onChange={(v) => update(["blueprint", "specialty"], v)} />
    </div>
    <fieldset className="field">
      <legend>Communication focus</legend>
      {options.communication_focus.map((choice) => <CheckField key={String(choice.value)} label={choice.label}
        path={["blueprint", "communication_focus", String(choice.value)]} errors={[]}
        checked={focus.has(choice.value as never)}
        onChange={(on) => {
          const next = options.communication_focus.map((c) => String(c.value))
            .filter((value) => value === choice.value ? on : focus.has(value as never));
          update(["blueprint", "communication_focus"], next.length ? next : undefined);
        }} />)}
    </fieldset>
    <div className="field-row">
      <SelectField label="Reading time" path={["timing", "reading_seconds"]} errors={errors}
        value={draft.timing?.reading_seconds} choices={options.reading_seconds}
        onChange={(v) => update(["timing", "reading_seconds"], v === undefined ? undefined : Number(v))} />
      <div className="field"><span className="field-label">Interview time</span><span>{options.interview_seconds / 60} minutes (fixed by the blueprint)</span></div>
    </div>
    <TextField label="Author name" path={["authorship", "author"]} errors={errors} value={draft.authorship?.author}
      onChange={(v) => update(["authorship", "author"], v)} />
    <p className="field-hint">Blueprint: {options.blueprint_version.split(" | ")[0]} (pinned, read-only). Exported cases are always author drafts and not clinically validated.</p>
  </section>;
}

export function CharacterSection({ draft, options, errors, update }: SectionProps) {
  const persona = draft.persona ?? {};
  const voice = persona.voice ?? {};
  const setVoice = (key: string, value: unknown) => update(["persona", "voice", key], value);
  return <section aria-labelledby="character-heading" className="editor-section">
    <h2 id="character-heading">2. Character</h2>
    <p className="field-hint">Facts the candidate must elicit belong on fact cards, not in the background or opening, which the character can use from the start.</p>
    <div className="field-row">
      <SelectField label="Role" path={["persona", "role"]} errors={errors} value={persona.role} choices={options.roles}
        onChange={(v) => update(["persona", "role"], v)} />
      <TextField label="Name" path={["persona", "name"]} errors={errors} value={persona.name} onChange={(v) => update(["persona", "name"], v)} />
      <TextField label="Age" type="number" path={["persona", "age"]} errors={errors} value={persona.age}
        onChange={(v) => update(["persona", "age"], v === undefined ? undefined : Number(v))} />
    </div>
    <TextField label="Background" path={["persona", "description"]} errors={errors} multiline value={persona.description}
      onChange={(v) => update(["persona", "description"], v)} />
    <TextField label="Speech style" path={["persona", "speech_style"]} errors={errors} value={persona.speech_style}
      onChange={(v) => update(["persona", "speech_style"], v)} />
    <TextField label="Initial affect" path={["persona", "affect"]} errors={errors} value={persona.affect}
      onChange={(v) => update(["persona", "affect"], v)} />
    <TextField label="Opening statement" path={["persona", "opening_statement"]} errors={errors} multiline
      value={persona.opening_statement} onChange={(v) => update(["persona", "opening_statement"], v)} />
    <TextField label="Response to questions outside the case" path={["unscripted_response"]} errors={errors}
      value={draft.unscripted_response} onChange={(v) => update(["unscripted_response"], v)}
      hint="Said in character when asked about something the case does not cover." />
    <details className="editor-details">
      <summary>Presentation (optional): voice and avatar</summary>
      <div className="field-row">
        <SelectField label="Voice sex" path={["persona", "voice", "sex"]} errors={errors} value={voice.sex} blank="Not set"
          choices={options.voice_sexes} onChange={(v) => setVoice("sex", v)} />
        <SelectField label="Voice age" path={["persona", "voice", "age"]} errors={errors} value={voice.age ?? "adult"}
          choices={options.voice_ages} onChange={(v) => setVoice("age", v === "adult" ? undefined : v)} />
        <TextField label="Accent" path={["persona", "voice", "accent"]} errors={errors} value={voice.accent}
          onChange={(v) => setVoice("accent", v)} hint="For example en-GB (the default) or en-IE." />
      </div>
      <div className="field-row">
        <SelectField label="Neural voice" path={["persona", "voice", "speaker"]} errors={errors} value={voice.speaker} blank="Not set"
          choices={options.speakers} onChange={(v) => setVoice("speaker", v)} />
        <SelectField label="Avatar" path={["persona", "avatar"]} errors={errors} value={persona.avatar} blank="Not set"
          choices={options.avatars} onChange={(v) => update(["persona", "avatar"], v)} />
      </div>
      <p className="field-hint">Integration checks voice and avatar constraints for the station catalogue.</p>
    </details>
  </section>;
}
