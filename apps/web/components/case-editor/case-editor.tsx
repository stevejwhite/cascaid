"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { authoring, AuthoringError, type AuthoringOptions, type CheckResult, type Draft, type Export } from "../../lib/authoring";
import { fieldId, setIn, type DraftCase, type Path } from "../../lib/case-draft";
import { FactsSection } from "./facts-section";
import { PreviewPanel } from "./preview-panel";
import { CharacterSection, StationSection } from "./station-section";
import { BehaviourSection, TasksSection } from "./tasks-section";

type SaveState = "saved" | "dirty" | "saving" | "error";
const SAVE_LABEL: Record<SaveState, string> = { saved: "Draft saved", dirty: "Unsaved changes", saving: "Saving…", error: "Not saved" };

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  link.click();
  URL.revokeObjectURL(url);
}

function locLabel(loc: readonly (string | number)[]) {
  return loc.map((part) => typeof part === "number" ? `#${part + 1}` : part.replaceAll("_", " ")).join(" › ") || "case";
}

export function CaseEditor({ draftId }: { draftId: string }) {
  const [options, setOptions] = useState<AuthoringOptions | null>(null);
  const [saved, setSaved] = useState<Draft | null>(null);
  const [draft, setDraft] = useState<DraftCase>({});
  const [notes, setNotes] = useState({ notes: "", objectives: "" });
  const [state, setState] = useState<SaveState>("saved");
  const [message, setMessage] = useState<string | null>(null);
  const [check, setCheck] = useState<CheckResult | null>(null);
  const [exported, setExported] = useState<Export | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const loaded = useRef(false);

  useEffect(() => {
    Promise.all([authoring.options(), authoring.load(draftId)]).then(([o, d]) => {
      setOptions(o); setSaved(d); setDraft(d.case); setNotes({ notes: d.notes, objectives: d.objectives });
      loaded.current = true;
      authoring.check(draftId, d.case).then(setCheck, () => setCheck(null));
    }, (e) => setLoadError(e instanceof Error ? e.message : "The draft could not be loaded."));
  }, [draftId]);

  useEffect(() => {
    if (state !== "dirty" && state !== "error") return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [state]);

  const edit = useCallback((change: (d: DraftCase) => DraftCase) => {
    setDraft(change); setState("dirty"); setExported(null);
  }, []);
  const update = useCallback((path: Path, value: unknown) => edit((d) => setIn(d, path, value)), [edit]);

  const runCheck = async (current: DraftCase) => {
    try { setCheck(await authoring.check(draftId, current)); } catch { setCheck(null); }
  };

  const save = async () => {
    if (!saved) return;
    setState("saving"); setMessage(null);
    try {
      const next = await authoring.save(draftId, saved.revision, { case: draft, ...notes });
      setSaved(next); setState("saved");
      await runCheck(draft);
    } catch (e) {
      setState("error");
      setMessage(e instanceof AuthoringError && e.status === 409
        ? `${e.message} Your edits are still on this page; copy anything you need before reloading.`
        : e instanceof Error ? e.message : "Saving failed.");
    }
  };

  const runExport = async () => {
    if (!saved) return;
    setMessage(null);
    try { setExported(await authoring.export(draftId, saved.revision)); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Export failed."); }
  };

  if (loadError) return <div className="error" role="alert">{loadError} <Link href="/authoring">Back to drafts</Link></div>;
  if (!options || !saved) return <p aria-live="polite">Loading the draft…</p>;

  const errors = check?.errors ?? [];
  const props = { draft, options, errors, update };
  const schemaPassed = check?.valid === true && state === "saved";

  return <div className="case-editor">
    <div className="editor-bar">
      <div>
        <p className="eyebrow">Case editor · {saved.kind === "revision" ? `revision of ${saved.source?.case_id} ${saved.source?.version}` : saved.source ? `new case copied from ${saved.source.case_id}` : "new case"}</p>
        <h1>{draft.title || "Untitled case"}</h1>
        <p className="validation-banner">Not clinically validated. Original fictional cases only.</p>
      </div>
      <div className="editor-bar-actions">
        <span className={`save-state save-${state}`} role="status" aria-live="polite">{SAVE_LABEL[state]}</span>
        <button type="button" className="refresh primary" onClick={save} disabled={state === "saving" || state === "saved"}>Save changes</button>
      </div>
    </div>
    {message && <p className="error" role="alert">{message}</p>}
    <nav aria-label="Editor sections" className="editor-nav">
      <a href="#station-heading">1. Station</a><a href="#character-heading">2. Character</a>
      <a href="#facts-heading">3. Facts</a><a href="#tasks-heading">4. Tasks</a><a href="#export-heading">5. Check and export</a>
    </nav>
    <div className="editor-layout">
      <div className="editor-main">
        <StationSection {...props} kind={saved.kind} />
        <CharacterSection {...props} />
        <FactsSection {...props} replace={edit} />
        <TasksSection {...props} replace={edit} />
        <BehaviourSection {...props} replace={edit} />
        <section aria-labelledby="notes-heading" className="editor-section">
          <h2 id="notes-heading">Author notes</h2>
          <p className="field-hint">Kept with the draft and on the review sheet; never given to the role-player.</p>
          <div className="field"><label htmlFor="objectives">Intended learning objectives</label>
            <textarea id="objectives" rows={3} value={notes.objectives} onChange={(e) => { setNotes({ ...notes, objectives: e.target.value }); setState("dirty"); }} /></div>
          <div className="field"><label htmlFor="notes">Working notes and clinical assumptions</label>
            <textarea id="notes" rows={4} value={notes.notes} onChange={(e) => { setNotes({ ...notes, notes: e.target.value }); setState("dirty"); }} /></div>
        </section>
        <section aria-labelledby="export-heading" className="editor-section">
          <h2 id="export-heading">5. Check and export</h2>
          <ul className="milestones" aria-label="Draft status">
            <li className={state === "saved" ? "done" : ""}>{state === "saved" ? "✓" : "○"} Saved</li>
            <li className={schemaPassed ? "done" : ""}>{schemaPassed ? "✓" : "○"} Schema checks passed</li>
            <li>○ Author reviewed <span className="muted">(recorded during integration)</span></li>
            <li>○ Integrated for practice <span className="muted">(developer workflow after export)</span></li>
          </ul>
          <button type="button" className="refresh" onClick={() => runCheck(draft)}>Check now</button>
          {check && <div aria-live="polite">
            {check.valid ? <p className="good-note">The case passes the runtime schema checks.</p>
              : <><h3>{check.errors.length} error{check.errors.length === 1 ? "" : "s"} to fix</h3>
                <ul className="error-summary">{check.errors.map((e, i) => <li key={i}>
                  <a href={`#${fieldId(e.loc as Path)}`} onClick={() => document.getElementById(fieldId(e.loc as Path))?.focus()}>{locLabel(e.loc)}</a>: {e.message}
                </li>)}</ul></>}
            {check.prompts.length > 0 && <><h3>Review prompts</h3>
              <p className="field-hint">Simple text checks to look at again; not a judgement of clinical accuracy or safety.</p>
              <ul>{check.prompts.map((p, i) => <li key={i}>{p.message} <span className="muted">Checked: {p.checked}</span></li>)}</ul></>}
          </div>}
          <p className="field-hint">Export writes the case file and a review sheet for a developer to integrate. It never changes the active station.</p>
          <button type="button" className="refresh primary" onClick={runExport} disabled={!schemaPassed}>Export case</button>
          {!schemaPassed && <p className="field-hint">Save the draft and pass the checks to export.</p>}
          {exported && <div className="export-result" aria-live="polite">
            <p className="good-note">Exported {exported.file_name} (version {exported.case.version}, author draft).</p>
            {exported.source_changed && <p className="error">The active source case changed since this draft was created; compare both before integrating.</p>}
            {exported.dropped_comments.length > 0 && <><p><strong>Comments not kept</strong> (attached to removed or rewritten items):</p>
              <ul>{exported.dropped_comments.map((c) => <li key={c}><code>{c}</code></li>)}</ul></>}
            <button type="button" className="refresh" onClick={() => download(exported.file_name, exported.case_yaml, "text/yaml")}>Download case YAML</button>
            <button type="button" className="refresh" onClick={() => download(`${exported.case.id}-REVIEW.md`, exported.review_markdown, "text/markdown")}>Download review sheet</button>
            <p className="muted">Also saved on the server in {exported.saved_to}.</p>
            <details><summary>Review sheet</summary><pre className="review-sheet">{exported.review_markdown}</pre></details>
          </div>}
        </section>
      </div>
      <PreviewPanel draftId={draftId} draft={draft} />
    </div>
  </div>;
}
