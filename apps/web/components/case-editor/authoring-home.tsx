"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { authoring, type CaseChoice, type DraftSummary } from "../../lib/authoring";

const AUTHOR_KEY = "cascaid.author";

function rememberedAuthor() {
  try { return window.localStorage.getItem(AUTHOR_KEY) ?? ""; } catch { return ""; }
}

export function AuthoringHome() {
  const router = useRouter();
  const [drafts, setDrafts] = useState<DraftSummary[] | null>(null);
  const [cases, setCases] = useState<CaseChoice[]>([]);
  const [author, setAuthor] = useState("");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("");
  const [mode, setMode] = useState<"new" | "revision">("new");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([authoring.drafts(), authoring.cases()]).then(([d, c]) => {
      setDrafts(d); setCases(c); setSource(c[0]?.id ?? ""); setAuthor((name) => name || rememberedAuthor());
    },
      (e) => setError(e instanceof Error ? e.message : "The case editor is unavailable."));
  }, []);

  const create = async (request: Omit<Parameters<typeof authoring.create>[0], "author">) => {
    if (!author.trim()) { setError("Enter your name first; it is recorded on the draft."); return; }
    setBusy(true); setError(null);
    try {
      try { window.localStorage.setItem(AUTHOR_KEY, author.trim()); } catch { /* optional convenience */ }
      const draft = await authoring.create({ ...request, author: author.trim() });
      router.push(`/authoring/${draft.draft_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "The draft could not be created."); setBusy(false); }
  };

  return <div className="authoring-home">
    <div className="page-heading"><div>
      <p className="eyebrow">Case editor · local author tool</p>
      <h1>Case drafts</h1>
      <p className="intro">Create or revise an original fictional case without editing YAML. Drafts are stored separately from the active stations; exported cases are integrated by a developer. Not clinically validated.</p>
    </div></div>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="field"><label htmlFor="author">Your name (recorded on drafts)</label>
      <input id="author" value={author} onChange={(e) => setAuthor(e.target.value)} /></div>
    <div className="authoring-start">
      <form className="editor-section" onSubmit={(e) => { e.preventDefault(); void create({ kind: "new", title }); }}>
        <h2>Create a case</h2>
        <div className="field"><label htmlFor="new-title">Title</label>
          <input id="new-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="for example: Low mood after redundancy" /></div>
        <p className="field-hint">The case ID is made from this title and fixed; changing the title later does not change it.</p>
        <button type="submit" className="refresh primary" disabled={busy || !title.trim()}>Create draft</button>
      </form>
      <form className="editor-section" onSubmit={(e) => { e.preventDefault(); void create({ kind: mode, source_case_id: source }); }}>
        <h2>Start from an existing case</h2>
        <div className="field"><label htmlFor="source-case">Case</label>
          <select id="source-case" value={source} onChange={(e) => setSource(e.target.value)}>
            {cases.map((c) => <option key={c.id} value={c.id}>{c.title} ({c.version})</option>)}
          </select></div>
        <fieldset className="field"><legend>As</legend>
          <label><input type="radio" name="mode" checked={mode === "new"} onChange={() => setMode("new")} /> A copy: a new case with a new ID, starting at 0.1.0</label>
          <label><input type="radio" name="mode" checked={mode === "revision"} onChange={() => setMode("revision")} /> A revision: keeps the case ID and proposes the next version</label>
        </fieldset>
        <button type="submit" className="refresh primary" disabled={busy || !source}>Open a draft</button>
      </form>
    </div>
    <section className="editor-section" aria-labelledby="drafts-heading">
      <h2 id="drafts-heading">Continue a draft</h2>
      {drafts === null ? <p aria-live="polite">Loading drafts…</p> : drafts.length === 0 ? <p className="muted">No drafts yet.</p> :
        <table className="draft-table"><thead><tr><th>Title</th><th>Kind</th><th>Source</th><th>Last saved</th><th>Author</th></tr></thead>
          <tbody>{drafts.map((d) => <tr key={d.draft_id}>
            <td><Link href={`/authoring/${d.draft_id}`}>{d.title}</Link> <code>{d.case_id}</code></td>
            <td>{d.kind === "revision" ? "Revision" : "New case"}</td>
            <td>{d.source ? `${d.source.case_id} ${d.source.version}` : "—"}</td>
            <td>{new Date(d.updated_at).toLocaleString("en-GB")} (revision {d.revision})</td>
            <td>{d.author}</td>
          </tr>)}</tbody></table>}
    </section>
  </div>;
}
