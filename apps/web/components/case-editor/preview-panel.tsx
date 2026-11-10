"use client";

import { useState } from "react";
import { authoring, type Preview, type PreviewTurn } from "../../lib/authoring";
import type { DraftCase } from "../../lib/case-draft";

const STATE_LABEL = { available: "Available", held_back: "Not shared yet", partial: "Partial (vague)", released: "Released" } as const;
/** Matches the server's per-turn limit (PreviewTurn.asked). */
const MAX_ASKED = 4;
const RESULT_LABEL = { available: "Available", released: "Released", partial: "Partial", held_back: "Held back", already_released: "Already released" } as const;

/** What a candidate sees: instructions and the opening only. Built from the visible fields. */
function CandidateView({ draft }: { draft: DraftCase }) {
  const reading = draft.timing?.reading_seconds;
  return <div className="candidate-view" aria-label="Candidate view">
    <p className="eyebrow">Candidate view</p>
    <h3>{draft.title || "Untitled case"}</h3>
    <p className="muted">Reading time {reading ? (reading >= 120 ? `${reading / 60} minutes` : `${reading} seconds`) : "not set"} · interview 7 minutes</p>
    <p>{draft.candidate_instructions || <em>No candidate instructions yet.</em>}</p>
    <p className="muted">Opening, from {draft.persona?.name || "the character"}:</p>
    <blockquote>{draft.persona?.opening_statement || <em>No opening statement yet.</em>}</blockquote>
    <p className="muted">Facts, disclosure rules and tasks are not shown to candidates.</p>
  </div>;
}

export function PreviewPanel({ draftId, draft }: { draftId: string; draft: DraftCase }) {
  const [view, setView] = useState<"candidate" | "rules">("rules");
  const [turns, setTurns] = useState<PreviewTurn[]>([]);
  const [next, setNext] = useState<PreviewTurn>({ asked: [], empathy: 0, confrontational: false });
  const [result, setResult] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const facts = draft.facts ?? [];

  const run = async (sequence: PreviewTurn[], added = false) => {
    setBusy(true); setError(null);
    try {
      setResult(await authoring.preview(draftId, draft, sequence)); setTurns(sequence);
      // Clear the ticks so the next line starts fresh; tone settings carry over.
      if (added) setNext((n) => ({ ...n, asked: [] }));
    }
    catch (e) { setError(e instanceof Error ? e.message : "Preview failed"); }
    finally { setBusy(false); }
  };
  const last = result?.steps.at(-1);
  const states = last?.facts ?? result?.initial ?? [];

  return <aside className="preview-panel" aria-labelledby="preview-heading">
    <h2 id="preview-heading">Preview</h2>
    <div role="tablist" aria-label="Preview view" className="preview-tabs">
      <button role="tab" aria-selected={view === "candidate"} onClick={() => setView("candidate")}>Candidate view</button>
      <button role="tab" aria-selected={view === "rules"} onClick={() => setView("rules")}>Rule preview</button>
    </div>
    {view === "candidate" ? <CandidateView draft={draft} /> : <div role="tabpanel" aria-label="Rule preview">
      <p className="preview-label"><strong>Rule preview</strong>: question recognition and generated replies are not tested. You choose what each line asked about, standing in for the interpreter; the production disclosure rules decide the rest.</p>
      <fieldset className="turn-builder">
        <legend>Next candidate line</legend>
        <p className="field-hint">Asks about (up to {MAX_ASKED} per line, as one candidate question would; {next.asked?.length ?? 0} chosen):</p>
        <div className="turn-facts">
          {facts.map((fact) => {
            const id = fact?.id ?? "";
            const checked = next.asked?.includes(id) ?? false;
            return <label key={id}><input type="checkbox" checked={checked} disabled={!checked && (next.asked?.length ?? 0) >= MAX_ASKED}
              onChange={(e) => setNext({ ...next, asked: e.target.checked ? [...(next.asked ?? []), id] : (next.asked ?? []).filter((a) => a !== id) })} />
              {fact?.asked_about?.[0] ?? id}</label>;
          })}
        </div>
        <label>Empathy <select value={next.empathy} onChange={(e) => setNext({ ...next, empathy: Number(e.target.value) as 0 | 1 | 2 })}>
          <option value={0}>None</option><option value={1}>Brief or generic</option><option value={2}>Specific</option>
        </select></label>
        <label><input type="checkbox" checked={next.confrontational ?? false} onChange={(e) => setNext({ ...next, confrontational: e.target.checked })} /> Confrontational</label>
        <div className="turn-actions">
          <button type="button" className="refresh" disabled={busy || turns.length >= 40} onClick={() => run([...turns, next], true)}>Add turn</button>
          <button type="button" className="refresh" disabled={busy} onClick={() => run(turns)}>Refresh with current edits</button>
          <button type="button" className="refresh" disabled={busy || !turns.length} onClick={() => { setTurns([]); void run([]); }}>Reset</button>
        </div>
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      {result && <>
        <h3>Facts after {turns.length ? `turn ${turns.length}` : "the opening"}</h3>
        <ul className="fact-states">
          {states.map((f) => <li key={f.fact_id}><span className={`state state-${f.state}`}>{STATE_LABEL[f.state]}</span> {f.fact_id}</li>)}
        </ul>
        {last && <p className="muted">Rapport {last.rapport.toFixed(2)}{last.affect ? ` · affect: ${last.affect}` : ""}</p>}
        <ol className="preview-steps">
          {result.steps.map((step) => <li key={step.turn}>
            <p><strong>Turn {step.turn}</strong>: rapport {step.rapport.toFixed(2)}{step.affect_stage ? ` · stage ${step.affect_stage}` : ""}</p>
            {step.outcomes.length === 0 && <p className="muted">No fact asked about.</p>}
            <ul>{step.outcomes.map((o) => <li key={o.fact_id}><span className={`state state-${o.result}`}>{RESULT_LABEL[o.result]}</span> {o.fact_id}: {o.reason}</li>)}</ul>
            {step.ignored.length > 0 && <p className="muted">Not a fact in this case: {step.ignored.join(", ")}</p>}
            {step.character_question && <p className="muted">Character asks: “{step.character_question}”</p>}
          </li>)}
        </ol>
        <details>
          <summary>Author-only inspector: wording the character may use now</summary>
          <ul>{states.filter((f) => f.permitted_text).map((f) => <li key={f.fact_id}><code>{f.fact_id}</code>: {f.permitted_text}</li>)}</ul>
        </details>
        <p className="muted">{result.note}</p>
      </>}
      {!result && !error && <button type="button" className="refresh" onClick={() => run([])}>Start rule preview</button>}
    </div>}
  </aside>;
}
