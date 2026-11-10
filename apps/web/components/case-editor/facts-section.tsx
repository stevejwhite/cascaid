"use client";

import { useState } from "react";
import { addFact, duplicateFact, linksTo, move, removeFact, type DraftCase } from "../../lib/case-draft";
import { CheckField, LinesField, SelectField, TextField } from "./fields";
import type { SectionProps } from "./station-section";

export function FactsSection({ draft, options, errors, update, replace }: SectionProps & { replace: (next: (d: DraftCase) => DraftCase) => void }) {
  const [label, setLabel] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const facts = draft.facts ?? [];
  return <section aria-labelledby="facts-heading" className="editor-section">
    <h2 id="facts-heading">3. Facts and disclosure</h2>
    <p className="field-hint">One independently askable topic per fact. Question labels help the interpreter recognise questions; they are not exact phrases a candidate must use.</p>
    <datalist id="domains">{options.domains.map((d) => <option key={d} value={d} />)}</datalist>
    {facts.map((fact, index) => {
      const id = fact?.id ?? "";
      const base = ["facts", index];
      const links = linksTo(draft, id);
      const linked = links.tasks.length + links.questions.length;
      const volunteered = fact?.disclosure === "volunteered";
      return <article key={id || index} className="fact-card" aria-label={`Fact ${index + 1}: ${fact?.asked_about?.[0] ?? id}`}>
        <header className="fact-card-head">
          <h3>Fact {index + 1}: {fact?.asked_about?.[0] || id}</h3>
          <span className={`tag fact-disclosure-${fact?.disclosure ?? "unset"}`}>{options.disclosures.find((d) => d.value === fact?.disclosure)?.label ?? "Disclosure not set"}</span>
          <div className="fact-actions">
            <button type="button" className="refresh" onClick={() => replace((d) => move(d, "facts", index, -1))} disabled={index === 0} aria-label={`Move fact ${index + 1} up`}>↑ Up</button>
            <button type="button" className="refresh" onClick={() => replace((d) => move(d, "facts", index, 1))} disabled={index === facts.length - 1} aria-label={`Move fact ${index + 1} down`}>↓ Down</button>
            <button type="button" className="refresh" onClick={() => replace((d) => duplicateFact(d, index))}>Duplicate</button>
            <button type="button" className="refresh danger" onClick={() => linked ? setConfirming(id) : replace((d) => removeFact(d, id))}>Delete</button>
          </div>
        </header>
        {confirming === id && <div className="confirm" role="alertdialog" aria-label="Confirm deleting a linked fact">
          <p>This fact is linked to {links.tasks.length ? `task${links.tasks.length > 1 ? "s" : ""} ${links.tasks.join(", ")} (they will become self-review)` : ""}{links.tasks.length && links.questions.length ? " and " : ""}{links.questions.length ? `character question${links.questions.length > 1 ? "s" : ""} ${links.questions.join(", ")} (they will be removed)` : ""}.</p>
          <button type="button" className="refresh danger" onClick={() => { replace((d) => removeFact(d, id)); setConfirming(null); }}>Delete fact and update links</button>
          <button type="button" className="refresh" onClick={() => setConfirming(null)}>Keep fact</button>
        </div>}
        <TextField label="What the character says" path={[...base, "content"]} errors={errors} multiline value={fact?.content}
          onChange={(v) => update([...base, "content"], v)} hint="The full answer, in the character's own words." />
        <LinesField label="Questions about this fact (one per line)" path={[...base, "asked_about"]} errors={errors}
          value={fact?.asked_about} onChange={(v) => update([...base, "asked_about"], v)}
          hint="Their order matters to the interpreter; keep the first label stable." />
        <div className="field-row">
          <SelectField label="When it may be shared" path={[...base, "disclosure"]} errors={errors} value={fact?.disclosure}
            choices={options.disclosures} onChange={(v) => {
              update([...base, "disclosure"], v);
              if (v !== "after_rapport") update([...base, "rapport_needed"], undefined);
              if (v === "volunteered") update([...base, "vague"], undefined);
            }} />
          {fact?.disclosure === "after_rapport" && <SelectField label="Rapport needed" path={[...base, "rapport_needed"]} errors={errors}
            value={fact?.rapport_needed ?? 1} choices={options.rapport_levels}
            onChange={(v) => update([...base, "rapport_needed"], v === "2" ? 2 : undefined)}
            hint="Simulation settings, not a validated model of trust." />}
          <TextField label="Feedback area" path={[...base, "domain"]} errors={errors} value={fact?.domain}
            onChange={(v) => update([...base, "domain"], v)} list="domains" hint="A short slug, for example alcohol or risk." />
        </div>
        <CheckField label="Include in information checklist" path={[...base, "key"]} errors={errors} checked={Boolean(fact?.key)}
          onChange={(on) => update([...base, "key"], on || undefined)}
          hint={volunteered ? "Volunteered facts are excluded from the elicitation total." : undefined} />
        {!volunteered && <TextField label="Optional initial vague answer" path={[...base, "vague"]} errors={errors} multiline value={fact?.vague}
          onChange={(v) => update([...base, "vague"], v)} hint="Given the first time; asking again gets the full answer." />}
        <p className="field-hint">ID <code>{id}</code>{linked ? ` · linked to ${linked} item${linked > 1 ? "s" : ""}` : ""}</p>
      </article>;
    })}
    <form className="add-row" onSubmit={(e) => { e.preventDefault(); if (label.trim()) { replace((d) => addFact(d, label)); setLabel(""); } }}>
      <label htmlFor="new-fact-label">New fact: its main question label</label>
      <input id="new-fact-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="for example: morning drinking" />
      <button type="submit" className="refresh" disabled={!label.trim()}>Add fact</button>
    </form>
  </section>;
}
