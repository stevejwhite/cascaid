import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { CaseEditor } from "../components/case-editor/case-editor";

const options = {
  blueprint_version: "March 2023 | sha256:x", interview_seconds: 420,
  skills: [{ value: "history", label: "History" }],
  subdivisions: { history: [{ value: "presenting_complaint_and_psychiatric_history", label: "Presenting complaint" }] },
  specialties: [{ value: "addiction", label: "Addiction" }], communication_focus: [],
  reading_seconds: [{ value: 90, label: "90 seconds" }, { value: 240, label: "4 minutes" }],
  roles: [{ value: "patient", label: "Patient" }],
  disclosures: [{ value: "volunteered", label: "Can be volunteered" }, { value: "on_direct_question", label: "Share when asked" }, { value: "after_rapport", label: "Share when asked after rapport" }],
  rapport_levels: [{ value: 1, label: "Level 1" }, { value: 2, label: "Level 2" }],
  indicators: [{ value: "summary", label: "Summary" }], expressions: [{ value: "neutral", label: "Neutral" }],
  voice_sexes: [], voice_ages: [{ value: "adult", label: "Adult" }], speakers: [], avatars: [], domains: ["alcohol"],
};
const draftCase = {
  id: "alcohol-history", version: "0.5.0", title: "Alcohol use — history",
  blueprint: { skill: "history", subdivision: "presenting_complaint_and_psychiatric_history", specialty: "addiction" },
  timing: { reading_seconds: 90 }, authorship: { author: "Dr A", status: "author_draft" },
  candidate_instructions: "Take a history.", unscripted_response: "Not sure.",
  persona: { role: "patient", name: "Chris", description: "Lives alone.", speech_style: "Brief.", affect: "Guarded.", opening_statement: "Hello." },
  facts: [{ id: "withdrawal", content: "I get the shakes.", disclosure: "on_direct_question", asked_about: ["withdrawal"], domain: "alcohol", key: true }],
  tasks: [{ id: "ask-withdrawal", description: "Ask about withdrawal", domain: "alcohol", evidence_fact: "withdrawal" }],
};
const draft = { draft_id: "a".repeat(32), revision: 1, kind: "revision", author: "Dr A", notes: "", objectives: "",
  source: { case_id: "alcohol-history", version: "0.4.0", sha256: "x" }, created_at: "2026-11-10T10:00:00Z", updated_at: "2026-11-10T10:00:00Z", case: draftCase };
const valid = { valid: true, errors: [], prompts: [] };

function server(overrides: Record<string, (init?: RequestInit) => Response> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const key = `${init?.method ?? "GET"} ${url.replace("/backend/api/authoring", "")}`;
    for (const [pattern, reply] of Object.entries(overrides)) if (key.startsWith(pattern)) return reply(init);
    if (key === "GET /options") return json(options);
    if (key.startsWith("GET /drafts/")) return json(draft);
    if (key.startsWith("POST /drafts/") && key.endsWith("/check")) return json(valid);
    if (key.startsWith("PUT /drafts/")) return json({ ...draft, revision: 2, case: JSON.parse(String(init?.body)).case });
    return json({ detail: "unexpected" }, 500);
  }));
  return calls;
}

test("edits a fact's answer, saves it with the edited revision and reports the state", async () => {
  const calls = server();
  render(<CaseEditor draftId={"a".repeat(32)} />);
  const card = await screen.findByRole("article", { name: /Fact 1: withdrawal/ });
  expect(screen.getByText("Not clinically validated. Original fictional cases only.")).toBeInTheDocument();
  await userEvent.clear(within(card).getByLabelText("What the character says"));
  await userEvent.type(within(card).getByLabelText("What the character says"), "I shake by lunchtime.");
  expect(screen.getByRole("status")).toHaveTextContent("Unsaved changes");
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Draft saved"));
  const put = calls.find((c) => c.init?.method === "PUT")!;
  const sent = JSON.parse(String(put.init?.body));
  expect(sent.revision).toBe(1);
  expect(sent.case.facts[0].content).toBe("I shake by lunchtime.");
  expect(sent.case.facts[0].key).toBe(true);
});

test("a stale save is reported and the edits stay on the page", async () => {
  server({ "PUT /drafts/": () => new Response(JSON.stringify({ detail: "This draft was saved elsewhere (revision 3)." }), { status: 409 }) });
  render(<CaseEditor draftId={"a".repeat(32)} />);
  const field = await screen.findByLabelText("Title");
  await userEvent.type(field, " (edited)");
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/saved elsewhere.*still on this page/);
  expect(screen.getByRole("status")).toHaveTextContent("Not saved");
  expect(screen.getByLabelText("Title")).toHaveValue("Alcohol use — history (edited)");
});

test("deleting a fact linked to a task asks first and explains the repair", async () => {
  server();
  render(<CaseEditor draftId={"a".repeat(32)} />);
  const card = await screen.findByRole("article", { name: /Fact 1/ });
  await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
  const dialog = screen.getByRole("alertdialog");
  expect(dialog).toHaveTextContent("ask-withdrawal (they will become self-review)");
  await userEvent.click(within(dialog).getByRole("button", { name: "Delete fact and update links" }));
  expect(screen.queryByRole("article", { name: /Fact 1/ })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Evidence", { selector: "select" })).toHaveValue("self");
});

test("check errors link to their field and block export", async () => {
  server({ "POST /drafts/": (init) => new Response(JSON.stringify(String(init?.body).includes("turns") ? {} : {
    valid: false, errors: [{ loc: ["persona", "name"], message: "Field required" }], prompts: [] })) });
  render(<CaseEditor draftId={"a".repeat(32)} />);
  const link = await screen.findByRole("link", { name: "persona › name" });
  expect(link).toHaveAttribute("href", "#field-persona-name");
  expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByRole("button", { name: "Export case" })).toBeDisabled();
  fireEvent.click(link);
  expect(screen.getByLabelText("Name")).toHaveFocus();
});

test("the rule preview is labelled as not testing recognition or replies", async () => {
  server({ "POST /drafts/a": (init) => new Response(JSON.stringify(String(init?.body).includes("turns") ? {
    label: "", groups: [], note: "Time-based character questions are not simulated.",
    initial: [{ fact_id: "withdrawal", state: "held_back", permitted_text: null }],
    steps: [{ turn: 1, rapport: 0, affect_stage: null, affect: null, ignored: [], character_question: null,
      outcomes: [{ fact_id: "withdrawal", result: "released", reason: "Asked directly: released." }],
      facts: [{ fact_id: "withdrawal", state: "released", permitted_text: "I get the shakes." }] }],
  } : valid)) });
  render(<CaseEditor draftId={"a".repeat(32)} />);
  expect(await screen.findByText(/question recognition and generated replies are not tested/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Start rule preview" }));
  await userEvent.click(await screen.findByRole("checkbox", { name: "withdrawal" }));
  await userEvent.click(screen.getByRole("button", { name: "Add turn" }));
  expect(await screen.findByText(/Asked directly: released./)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Candidate view" }));
  expect(screen.getByText("Facts, disclosure rules and tasks are not shown to candidates.")).toBeInTheDocument();
  expect(screen.queryByText("I get the shakes.", { selector: ".candidate-view *" })).not.toBeInTheDocument();
});
