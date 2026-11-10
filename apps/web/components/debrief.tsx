"use client";

import type { AffectChange, Debrief, FactResult, QuestionResult, TaskResult, Utterance } from "../lib/api";
import { label } from "./stations";

export function minutes(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

const percent = (value: number) => `${Math.round(value * 100)}%`;

// Status always pairs colour with an icon and words, never colour alone.
const FACT_STATUS: Record<FactResult["status"], { icon: string; text: string; tone: string }> = {
  elicited: { icon: "✓", text: "Elicited", tone: "good" },
  touched_on: { icon: "◐", text: "Touched on — a follow-up question would have drawn out the detail", tone: "warning" },
  volunteered: { icon: "○", text: "Offered unprompted", tone: "neutral" },
  held_back: { icon: "⏸", text: "Held back — needed more rapport when asked", tone: "warning" },
  missed: { icon: "✕", text: "Not elicited", tone: "critical" },
};
const TASK_STATUS: Record<TaskResult["status"], { icon: string; text: string; tone: string }> = {
  met: { icon: "✓", text: "Detected", tone: "good" },
  not_detected: { icon: "✕", text: "Not detected", tone: "critical" },
  self_review: { icon: "?", text: "Review yourself", tone: "neutral" },
};

const CAUSE: Record<AffectChange["cause"], string> = {
  start: "At the start",
  rapport: "After empathy",
  confrontation: "After a confrontational remark",
  settled: "Settling again",
  rapport_fell: "As rapport faded",
};

function answerStatus(q: QuestionResult) {
  if (q.answered === null || q.answered === undefined) return { icon: "–", text: "Station ended before you replied", tone: "neutral" };
  return q.answered ? { icon: "✓", text: "Responded to", tone: "good" } : { icon: "✕", text: "Not responded to", tone: "critical" };
}

function Status({ icon, text, tone }: { icon: string; text: string; tone: string }) {
  return <span className={`status tone-${tone}`}><span aria-hidden="true">{icon}</span> {text}</span>;
}

function Tile({ label: name, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="tile"><span>{name}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

function Meter({ name, value, total, caption }: { name: string; value: number; total: number; caption: string }) {
  const share = total ? value / total : 0;
  return <div className="meter-row" title={`${name}: ${caption}`}>
    <span className="meter-label">{name}</span>
    <span className="meter" role="meter" aria-label={name} aria-valuemin={0} aria-valuemax={total} aria-valuenow={value}
      aria-valuetext={caption}><span style={{ width: `${share * 100}%` }} /></span>
    <span className="meter-value">{caption}</span>
  </div>;
}

function tags(u: Utterance): string[] {
  return [
    u.question_type === "open" ? "Open question" : u.question_type === "closed" ? "Closed question" : "",
    u.questions > 1 ? `${u.questions} questions at once` : "",
    u.empathy ? "Empathy" : "",
    u.summary ? "Summary" : "",
    u.check_understanding ? "Checks understanding" : "",
    ...u.jargon.map((term) => `Term: ${term}`),
    u.input === "speech" ? (u.edited ? "Spoken, edited" : "Spoken") : "",
  ].filter(Boolean);
}

export function DebriefView({ debrief, onExit }: { debrief: Debrief; onExit: () => void }) {
  const { feedback, session } = debrief;
  const { information: info, communication: comm } = feedback;
  const keyFacts = info.facts.filter((f) => f.key && f.status !== "volunteered");
  const otherFacts = info.facts.filter((f) => !f.key || f.status === "volunteered");
  const asked = comm.open_questions + comm.closed_questions;
  let candidateLine = 0;

  return <section className="debrief" aria-labelledby="debrief-heading">
    <p className="eyebrow">
      {session.station.title} · {feedback.ended_reason === "time_up" ? "time up" : "ended by you"} · {minutes(feedback.duration_seconds)}
    </p>
    {feedback.ended_reason === "time_up" && <p className="cue" role="status">Time is up. The station has ended.</p>}
    <h1 id="debrief-heading">Feedback</h1>
    <p className="notice">{feedback.note}</p>

    <div className="tiles" role="list" aria-label="Summary">
      <div role="listitem"><Tile label="Key information elicited" value={`${info.key_elicited} of ${info.key_total}`}
        detail={info.key_touched ? `${info.key_touched} more touched on` : undefined} /></div>
      <div role="listitem"><Tile label="Questions asked" value={String(asked)}
        detail={asked ? `${comm.open_questions} open · ${comm.closed_questions} closed` : undefined} /></div>
      <div role="listitem"><Tile label="Empathic statements" value={String(comm.empathy)} /></div>
      <div role="listitem"><Tile label="Summaries · checks" value={`${comm.summaries} · ${comm.checks_of_understanding}`} /></div>
    </div>

    <h2>Information gathering</h2>
    <div className="meters">
      {info.domains.map((d) => <Meter key={d.domain} name={label(d.domain)} value={d.elicited} total={d.total}
        caption={`${d.elicited} of ${d.total}`} />)}
    </div>
    <table className="facts">
      <caption className="sr-only">Key case information and whether your questions elicited it</caption>
      <thead><tr><th>Key information</th><th>Domain</th><th>Result</th></tr></thead>
      <tbody>{keyFacts.map((f) => <tr key={f.id}>
        <td>{f.content}</td><td>{label(f.domain)}</td>
        <td><Status {...FACT_STATUS[f.status]} />
          {f.question !== null && f.question !== undefined && <small className="when">Question {f.question} · {minutes(f.seconds ?? 0)}</small>}</td>
      </tr>)}</tbody>
    </table>
    {otherFacts.length > 0 && <details className="more"><summary>Other case information ({otherFacts.length})</summary>
      <ul>{otherFacts.map((f) => <li key={f.id}><Status {...FACT_STATUS[f.status]} /> {f.content}</li>)}</ul>
    </details>}

    {feedback.journey.length > 0 && <>
      <h2>How {session.character_name} felt</h2>
      <p className="muted">Stages written by the case author; changes follow the rapport and tone the local model detected.</p>
      <ol className="journey">{feedback.journey.map((c, i) => <li key={i}>
        <strong>{CAUSE[c.cause]}{c.question > 0 ? ` (question ${c.question})` : ""}:</strong> {c.affect}
      </li>)}</ol>
    </>}

    {feedback.questions.length > 0 && <>
      <h2>{session.character_name}&apos;s questions</h2>
      <p className="muted">Whether you responded is judged by the local model and can be wrong.</p>
      <ul className="tasks">{feedback.questions.map((q) => <li key={q.id}>
        <Status {...answerStatus(q)} /> <strong>“{q.text}”</strong> <small className="when">after your question {q.asked_after}</small>
        {q.response && <q>{q.response}</q>}
      </li>)}</ul>
    </>}

    {feedback.tasks.length > 0 && <>
      <h2>Station tasks</h2>
      <ul className="tasks">{feedback.tasks.map((t) => <li key={t.id}>
        <Status {...TASK_STATUS[t.status]} /> <strong>{t.description}</strong>
        {t.evidence && <q>{t.evidence}</q>}
      </li>)}</ul>
    </>}

    <h2>How you asked</h2>
    <p className="muted">Descriptive indicators, not marks. Question types, summaries, checks and technical terms come
      from rules ({comm.rules_version}); empathy comes from the {comm.empathy_source === "model" ? "local model" : "keyword matcher"} and can be wrong.</p>
    <div className="meters">
      {asked > 0 && <Meter name="Open questions" value={comm.open_questions} total={asked}
        caption={`${percent(comm.open_share ?? 0)} of questions`} />}
      {comm.candidate_word_share !== null && comm.candidate_word_share !== undefined &&
        <Meter name="Your share of words" value={Math.round(comm.candidate_word_share * 100)} total={100}
          caption={percent(comm.candidate_word_share)} />}
    </div>
    <ul className="observations">
      <li>{comm.stacked === 0 ? "No turns asked several questions at once." : `${comm.stacked} turn${comm.stacked === 1 ? "" : "s"} asked several questions at once.`}</li>
      <li>{comm.jargon.length ? `Technical terms to check you explained: ${comm.jargon.join(", ")}.` : "No listed technical terms were used."}</li>
      {comm.spoken > 0 && <li>{comm.spoken} turn{comm.spoken === 1 ? " was" : "s were"} spoken; {comm.spoken_edited} edited before sending.</li>}
      {comm.interruptions > 0 && <li>You spoke over {debrief.session.character_name} {comm.interruptions} time{comm.interruptions === 1 ? "" : "s"}.</li>}
    </ul>

    <details className="debrief-transcript" open>
      <summary>Annotated transcript</summary>
      <ol className="transcript">
        {session.transcript.map((line, index) => {
          const u = line.speaker === "candidate" ? feedback.utterances[candidateLine++] : undefined;
          return <li key={index} className={line.speaker}>
            <strong>{line.speaker === "candidate" ? `You · question ${u?.question ?? ""}` : session.character_name}</strong>
            <p>{line.text}</p>
            {u && <span className="chips">{tags(u).map((t) => <span key={t} className="chip">{t}</span>)}</span>}
          </li>;
        })}
      </ol>
    </details>
    <button className="start" type="button" onClick={onExit}>Back to stations</button>
  </section>;
}
