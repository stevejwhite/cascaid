import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { duration, label, Stations } from "../components/stations";
import type { CaseSummary, Readiness } from "../lib/api";

const status: Readiness = {
  status: "ready", model_backend: "fake", speech_backend: "off", tts_backend: "off", checked_at: "2026-10-07T12:00:00Z",
  registry: { status: "ready", detail: "7 sources registered." },
  cases: { status: "ready", detail: "1 station case available." },
  generation: { status: "unavailable", detail: "Local model service is not ready." },
  speech: { status: "disabled", detail: "Speech input is off; typing works." },
  voice: { status: "disabled", detail: "Character voice is off; browser voices work." },
};
const station: CaseSummary = {
  id: "elevated-mood-history", version: "0.1.0", title: "Elevated mood — history",
  skill: "history", subdivision: "presenting_complaint_and_psychiatric_history", specialty: "general",
  reading_seconds: 90, interview_seconds: 420, role: "patient",
  candidate_instructions: "Take a history to establish the nature of the current problem.",
  authorship_status: "author_draft", clinically_validated: false, voice: { age: "adult", accent: "en-GB" }, avatar: null,
};

function mockApi(cases: CaseSummary[] | Response = [station]) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) =>
    url.endsWith("/cases") && cases instanceof Response ? cases
      : new Response(JSON.stringify(url.endsWith("/status") ? status : cases))));
}

test("lists stations with blueprint timing and an explicit validation warning", async () => {
  mockApi();
  render(<Stations />);
  const card = await screen.findByRole("article", { name: "Elevated mood — history" });
  expect(within(card).getByText("History")).toBeInTheDocument();
  expect(within(card).getByText("General")).toBeInTheDocument();
  expect(within(card).getByText("Reading 90 s")).toBeInTheDocument();
  expect(within(card).getByText("Station 7 min")).toBeInTheDocument();
  expect(within(card).getByText("Not clinically validated")).toBeInTheDocument();
  expect(within(card).getByRole("button", { name: /start station/i })).toBeEnabled();
  await userEvent.click(within(card).getByText("Candidate instructions"));
  expect(within(card).getByText(/Take a history/)).toBeVisible();
  expect(screen.queryByRole("region", { name: "Service status" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Status" })).toHaveAttribute("href", "/status");
});

test("reports an API failure instead of an empty station list", async () => {
  mockApi(new Response("{}", { status: 503 }));
  render(<Stations />);
  expect(await screen.findByRole("alert")).toHaveTextContent("local API is unavailable");
  expect(screen.queryByRole("article", { name: /Elevated mood/ })).not.toBeInTheDocument();
});

test("formats blueprint vocabulary and durations", () => {
  expect(label("mental_state_non_psychotic")).toBe("Mental state non psychotic");
  expect(duration(240)).toBe("4 min");
  expect(duration(90)).toBe("90 s");
});

test("stations still start with an older API missing speech fields", async () => {
  // A pre-speech API omits speech fields; the page must not crash or claim it is still waiting.
  const old: Partial<Readiness> = { ...status };
  delete old.speech;
  delete old.speech_backend;
  vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/api/sessions")
    ? new Promise<Response>(() => {}) // keep the new session pending; only the render matters
    : Promise.resolve(new Response(JSON.stringify(url.endsWith("/status") ? old : [station])))));
  render(<Stations />);
  await userEvent.click(await screen.findByRole("button", { name: /start station/i }));
  expect(await screen.findByText("Preparing station…")).toBeInTheDocument();
});

test("station browsing does not wait for service status checks", async () => {
  vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/status")
    ? new Promise<Response>(() => {})
    : Promise.resolve(new Response(JSON.stringify([station])))));
  render(<Stations />);
  expect(await screen.findByRole("article", { name: station.title })).toBeInTheDocument();
  expect(screen.getByRole("searchbox")).toBeEnabled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

const otherStations: CaseSummary[] = [station, {
  ...station, id: "capacity", title: "Capacity discussion", skill: "examination",
  subdivision: "capacity_assessment", specialty: "old_age", role: "patient",
  candidate_instructions: "Assess a decision about surgery.",
}, {
  ...station, id: "medication-discussion", title: "Medication discussion", skill: "management",
  subdivision: "management_biological", specialty: "general", role: "relative",
  candidate_instructions: "Discuss clozapine with a relative.",
}];

test("combines search with category filters and clears an empty result", async () => {
  mockApi(otherStations);
  render(<Stations />);
  await screen.findByText("Showing 3 of 3 stations");
  await userEvent.type(screen.getByRole("searchbox"), "  CLOZAPINE  ");
  await userEvent.selectOptions(screen.getByLabelText("Role"), "relative");
  expect(screen.getByText("Showing 1 of 3 stations")).toBeInTheDocument();
  expect(screen.getByRole("article", { name: "Medication discussion" })).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Specialty"), "old_age");
  expect(screen.getByText(/No stations match these filters/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByText("Showing 3 of 3 stations")).toBeInTheDocument();
  expect(screen.getByRole("searchbox")).toHaveValue("");
});

test("changing skill clears an incompatible subdivision", async () => {
  mockApi(otherStations);
  render(<Stations />);
  await screen.findByText("Showing 3 of 3 stations");
  await userEvent.selectOptions(screen.getByLabelText("Skill"), "examination");
  await userEvent.selectOptions(screen.getByLabelText("Subdivision"), "capacity_assessment");
  expect(screen.getByRole("article", { name: "Capacity discussion" })).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Skill"), "management");
  expect(screen.getByLabelText("Subdivision")).toHaveValue("");
  expect(screen.queryByRole("option", { name: "Capacity assessment" })).not.toBeInTheDocument();
  expect(screen.getByRole("article", { name: "Medication discussion" })).toBeInTheDocument();
});

test("a matrix selection starts the chosen case only after checking availability", async () => {
  const fetcher = vi.fn((url: string) => url.endsWith("/api/sessions")
    ? new Promise<Response>(() => {})
    : Promise.resolve(new Response(JSON.stringify(url.endsWith("/status") ? status : otherStations))));
  vi.stubGlobal("fetch", fetcher);
  render(<Stations initialCaseId="capacity" />);
  await screen.findByText("Preparing station…");
  expect(fetcher).toHaveBeenCalledWith("/backend/api/sessions", expect.objectContaining({
    method: "POST", body: JSON.stringify({ case_id: "capacity" }),
  }));
});

test("an invalid station link never creates a session and leaves the list usable", async () => {
  mockApi(otherStations);
  render(<Stations initialCaseId="missing-case" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("selected station is unavailable");
  expect(screen.getByRole("article", { name: "Capacity discussion" })).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalledWith("/backend/api/sessions", expect.anything());
});
