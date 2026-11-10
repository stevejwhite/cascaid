"use client";

import { useState } from "react";
import type { Choice } from "../../lib/authoring";
import { addQuestion, addStage, addTask, move, type DraftCase } from "../../lib/case-draft";
import { LinesField, SelectField, TextField } from "./fields";
import type { SectionProps } from "./station-section";

type Replace = { replace: (next: (d: DraftCase) => DraftCase) => void };

export function TasksSection({ draft, options, errors, update, replace }: SectionProps & Replace) {
  const [description, setDescription] = useState("");
  const tasks = draft.tasks ?? [];
  const facts: Choice[] = (draft.facts ?? []).map((f) => ({ value: f?.id ?? "", label: `${f?.asked_about?.[0] ?? f?.id} (${f?.id})` }));
  return <section aria-labelledby="tasks-heading" className="editor-section">
    <h2 id="tasks-heading">4. Feedback tasks</h2>
    <p className="field-hint">Each task has one source of evidence. Keep subjective judgements, such as overall empathy or professionalism, as self-review. Feedback is descriptive; there is no pass mark.</p>
    {tasks.map((task, index) => {
      const base = ["tasks", index];
      const evidence = task?.evidence_fact ? "fact" : task?.evidence_indicator ? "indicator" : "self";
      return <article key={task?.id ?? index} className="fact-card" aria-label={`Task ${index + 1}`}>
        <header className="fact-card-head">
          <h3>Task {index + 1}</h3>
          <div className="fact-actions">
            <button type="button" className="refresh" disabled={index === 0} onClick={() => replace((d) => move(d, "tasks", index, -1))} aria-label={`Move task ${index + 1} up`}>↑ Up</button>
            <button type="button" className="refresh" disabled={index === tasks.length - 1} onClick={() => replace((d) => move(d, "tasks", index, 1))} aria-label={`Move task ${index + 1} down`}>↓ Down</button>
            <button type="button" className="refresh danger" onClick={() => replace((d) => ({ ...d, tasks: (d.tasks ?? []).filter((_, i) => i !== index) }))}>Delete</button>
          </div>
        </header>
        <TextField label="Task" path={[...base, "description"]} errors={errors} value={task?.description} onChange={(v) => update([...base, "description"], v)} />
        <div className="field-row">
          <TextField label="Feedback area" path={[...base, "domain"]} errors={errors} value={task?.domain} list="domains" onChange={(v) => update([...base, "domain"], v)} />
          <SelectField label="Evidence" path={[...base, "evidence"]} errors={[]} value={evidence}
            choices={[{ value: "fact", label: "A fact elicited" }, { value: "indicator", label: "A communication indicator" }, { value: "self", label: "Self-review" }]}
            onChange={(v) => {
              update([...base, "evidence_fact"], v === "fact" ? facts[0]?.value : undefined);
              update([...base, "evidence_indicator"], v === "indicator" ? options.indicators[0]?.value : undefined);
            }} />
          {evidence === "fact" && <SelectField label="Fact" path={[...base, "evidence_fact"]} errors={errors} value={task?.evidence_fact} choices={facts} onChange={(v) => update([...base, "evidence_fact"], v)} />}
          {evidence === "indicator" && <SelectField label="Indicator" path={[...base, "evidence_indicator"]} errors={errors} value={task?.evidence_indicator}
            choices={options.indicators} onChange={(v) => update([...base, "evidence_indicator"], v)} hint="Descriptive indicators, not CASC marks." />}
        </div>
        <p className="field-hint">ID <code>{task?.id}</code></p>
      </article>;
    })}
    <form className="add-row" onSubmit={(e) => { e.preventDefault(); if (description.trim()) { replace((d) => addTask(d, description)); setDescription(""); } }}>
      <label htmlFor="new-task">New task</label>
      <input id="new-task" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="for example: Asks about withdrawal seizures" />
      <button type="submit" className="refresh" disabled={!description.trim()}>Add task</button>
    </form>
  </section>;
}

export function BehaviourSection({ draft, options, errors, update, replace }: SectionProps & Replace) {
  const [stage, setStage] = useState("");
  const [question, setQuestion] = useState("");
  const stages = draft.affect_stages ?? [];
  const questions = draft.questions ?? [];
  const facts: Choice[] = (draft.facts ?? []).map((f) => ({ value: f?.id ?? "", label: `${f?.asked_about?.[0] ?? f?.id} (${f?.id})` }));
  const triggers: Choice[] = [{ value: "rapport-1", label: "Rapport level 1" }, { value: "rapport-2", label: "Rapport level 2" }, { value: "confrontation", label: "After a confrontational line" }];
  return <details className="editor-section editor-details">
    <summary><h2 id="behaviour-heading">Character behaviour (optional)</h2></summary>
    <p className="field-hint">These use only the engine’s existing conditions: rapport levels, confrontation, a revealed fact or a time. They are not a validated model of emotion or cognition.</p>
    <LinesField label="Other ways to deflect questions outside the case (one per line)" path={["deflections"]} errors={errors}
      value={draft.deflections} onChange={(v) => update(["deflections"], v.length ? v : undefined)} />
    <h3>Affect stages</h3>
    {stages.map((item, index) => {
      const base = ["affect_stages", index];
      const trigger = item?.on_confrontation ? "confrontation" : item?.rapport_at_least ? `rapport-${item.rapport_at_least}` : "start";
      return <article key={item?.id ?? index} className="fact-card" aria-label={`Affect stage ${index + 1}`}>
        <div className="field-row">
          <TextField label="Affect" path={[...base, "affect"]} errors={errors} value={item?.affect} onChange={(v) => update([...base, "affect"], v)} />
          {index === 0 ? <div className="field"><span className="field-label">Applies</span><span>From the start</span></div>
            : <SelectField label="Applies" path={[...base, "trigger"]} errors={[]} value={trigger} choices={triggers} onChange={(v) => {
              update([...base, "on_confrontation"], v === "confrontation" || undefined);
              update([...base, "rapport_at_least"], v === "rapport-1" ? 1 : v === "rapport-2" ? 2 : undefined);
            }} />}
          <SelectField label="Expression" path={[...base, "expression"]} errors={errors} value={item?.expression ?? "neutral"} choices={options.expressions}
            onChange={(v) => update([...base, "expression"], v === "neutral" ? undefined : v)} />
        </div>
        <LinesField label="Hesitations (up to four, one per line)" path={[...base, "hesitations"]} errors={errors} value={item?.hesitations}
          onChange={(v) => update([...base, "hesitations"], v.length ? v : undefined)} />
        <button type="button" className="refresh danger" onClick={() => replace((d) => ({ ...d, affect_stages: (d.affect_stages ?? []).filter((_, i) => i !== index) }))}>Delete stage</button>
      </article>;
    })}
    <form className="add-row" onSubmit={(e) => { e.preventDefault(); if (stage.trim()) { replace((d) => addStage(d, stage)); setStage(""); } }}>
      <label htmlFor="new-stage">New affect stage</label>
      <input id="new-stage" value={stage} onChange={(e) => setStage(e.target.value)} placeholder="for example: Relieved and more open" />
      <button type="submit" className="refresh" disabled={!stage.trim()}>Add stage</button>
    </form>
    <h3>Character questions</h3>
    <p className="field-hint">Appended to a reply once due. Make sure a question reveals nothing the candidate has not yet elicited.</p>
    {questions.map((item, index) => {
      const base = ["questions", index];
      const byFact = item?.after_fact != null;
      return <article key={item?.id ?? index} className="fact-card" aria-label={`Character question ${index + 1}`}>
        <TextField label="Question" path={[...base, "text"]} errors={errors} value={item?.text} onChange={(v) => update([...base, "text"], v)} />
        <div className="field-row">
          <SelectField label="Asked" path={[...base, "trigger"]} errors={[]} value={byFact ? "fact" : "time"}
            choices={[{ value: "fact", label: "After a fact is revealed" }, { value: "time", label: "After a time" }]}
            onChange={(v) => {
              update([...base, "after_fact"], v === "fact" ? facts[0]?.value : undefined);
              update([...base, "after_seconds"], v === "time" ? 240 : undefined);
            }} />
          {byFact ? <SelectField label="Fact" path={[...base, "after_fact"]} errors={errors} value={item?.after_fact} choices={facts} onChange={(v) => update([...base, "after_fact"], v)} />
            : <TextField label="Seconds into the interview" type="number" path={[...base, "after_seconds"]} errors={errors} value={item?.after_seconds}
              onChange={(v) => update([...base, "after_seconds"], v === undefined ? undefined : Number(v))} />}
        </div>
        <button type="button" className="refresh danger" onClick={() => replace((d) => ({ ...d, questions: (d.questions ?? []).filter((_, i) => i !== index) }))}>Delete question</button>
      </article>;
    })}
    <form className="add-row" onSubmit={(e) => { e.preventDefault(); if (question.trim()) { replace((d) => addQuestion(d, question)); setQuestion(""); } }}>
      <label htmlFor="new-question">New character question</label>
      <input id="new-question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="for example: Will I lose my licence?" />
      <button type="submit" className="refresh" disabled={!question.trim()}>Add question</button>
    </form>
  </details>;
}
