import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

// WebGL is not available in jsdom; the 3D view is replaced by a stand-in that shows its props.
vi.mock("../components/avatar-view", () => ({
  default: (p: { avatarId: string; state: string; mood?: string; label: string }) =>
    <div data-testid="avatar" data-avatar={p.avatarId} data-state={p.state} data-mood={p.mood} aria-label={p.label} />,
}));
import { avatarFor, avatarState, clock, presentedSex, StationRunner } from "../components/station";
import { characterVoice } from "../lib/neural-voice";
import { emitSpeech } from "../lib/avatar/speech";
import type { ListenerEvents } from "../lib/hands-free";
import type { CaseSummary, Debrief, SessionView } from "../lib/api";

const station: CaseSummary = {
  id: "alcohol-history", version: "0.1.0", title: "Alcohol use — history",
  skill: "history", subdivision: "presenting_complaint_and_psychiatric_history", specialty: "addiction",
  reading_seconds: 90, interview_seconds: 420, role: "patient",
  candidate_instructions: "Take a history of Chris's alcohol use.",
  authorship_status: "author_draft", clinically_validated: false, voice: { age: "adult", accent: "en-GB" }, avatar: null,
};
const base: SessionView = {
  session_id: "a".repeat(32), station, character_name: "Chris", phase: "reading",
  created_at: "2026-10-07T12:00:00Z", interview_deadline: null, transcript: [],
  presentation: { expression: "neutral", hesitations: [] },
};
const opening = { speaker: "character" as const, text: "My GP said my liver tests were off." };

function stream(...events: object[]): Response {
  return new Response(events.map((e) => JSON.stringify(e) + "\n").join(""), { headers: { "Content-Type": "application/x-ndjson" } });
}

function mockApi(overrides: Record<string, () => Response> = {}) {
  const deadline = new Date(Date.now() + 420_000).toISOString();
  const interview: SessionView = { ...base, phase: "interview", interview_deadline: deadline, transcript: [opening] };
  const answered: SessionView = { ...interview, transcript: [opening,
    { speaker: "candidate", text: "How much do you drink?" },
    { speaker: "character", text: "About a litre of vodka a day." }] };
  const debrief: Debrief = {
    session: { ...answered, phase: "ended" },
    feedback: {
      note: "Automated feedback for practice; not a CASC mark.",
      ended_reason: "candidate_ended", duration_seconds: 95,
      information: {
        key_elicited: 1, key_touched: 1, key_total: 4,
        facts: [
          { id: "quantity", domain: "alcohol", content: "About a litre of vodka a day.", key: true, status: "elicited", question: 1, seconds: 40 },
          { id: "withdrawal", domain: "alcohol", content: "Shakes and sweats.", key: true, status: "missed", question: null, seconds: null },
          { id: "motivation", domain: "perspective", content: "My grandson.", key: true, status: "held_back", question: null, seconds: null },
          { id: "quantity", domain: "alcohol", content: "Every day, more than I should.", key: true, status: "touched_on", question: 2, seconds: 70 },
          { id: "tolerance", domain: "alcohol", content: "Needs more now.", key: false, status: "missed", question: null, seconds: null },
        ],
        domains: [{ domain: "alcohol", elicited: 1, total: 2 }, { domain: "perspective", elicited: 0, total: 1 }],
      },
      communication: {
        utterances: 1, open_questions: 0, closed_questions: 1, open_share: 0, stacked: 0, empathy: 0,
        summaries: 0, checks_of_understanding: 0, jargon: ["neutropenia"], candidate_word_share: 0.25,
        spoken: 0, spoken_edited: 0, interruptions: 0, rules_version: "indicators-v1", empathy_source: "model",
      },
      tasks: [{ id: "non-judgemental", description: "Takes the history non-judgementally.", status: "self_review", evidence: null }],
      utterances: [{ question: 1, seconds: 40, text: "How much do you drink?", input: "typed", edited: null,
        question_type: "closed", questions: 1, summary: false, check_understanding: false, empathy: false, jargon: [] }],
      journey: [
        { question: 0, stage: "minimising", affect: "Defensive and minimising.", cause: "start" },
        { question: 1, stage: "irritable", affect: "Irritable and closed off.", cause: "confrontation" },
      ],
      questions: [{ id: "tell-gp", text: "Is all of this going back to my GP?", asked_after: 1, answered: false, response: "Do you smoke?" }],
    },
  };
  const routes: Record<string, () => Response> = {
    "/backend/api/sessions": () => Response.json(base),
    [`/backend/api/sessions/${base.session_id}/begin`]: () => Response.json(interview),
    [`/backend/api/sessions/${base.session_id}/turns/stream`]: () =>
      stream({ type: "sentence", text: "About a litre of vodka a day." }, { type: "done", session: answered }),
    [`/backend/api/sessions/${base.session_id}/end`]: () => Response.json(debrief),
    [`/backend/api/sessions/${base.session_id}/transcriptions`]: () =>
      Response.json({ transcription_id: "b".repeat(32), text: "How much do you drink?", audio_ms: 1800, asr_ms: 900 }),
    ...overrides,
  };
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => routes[url]());
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => { vi.useRealTimers(); window.localStorage.clear(); });

const fakeRecorder = () => vi.fn(async () => ({
  stop: async () => new Blob([new Uint8Array(44)], { type: "audio/wav" }),
  cancel: vi.fn(),
}));

async function beginSpeaking(record: ReturnType<typeof fakeRecorder>) {
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} speech record={record} />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  await user.click(await screen.findByRole("button", { name: "Speak to Chris" }));
  await user.click(await screen.findByRole("button", { name: /Stop and transcribe/ }));
  return user;
}

test("speech is transcribed into the box for review, then sent with its transcription ID", async () => {
  const fetch = mockApi();
  const record = fakeRecorder();
  const user = await beginSpeaking(record);
  const box = screen.getByLabelText("What you say to Chris");
  await waitFor(() => expect(box).toHaveValue("How much do you drink?"));
  const upload = fetch.mock.calls.find(([url]) => url.endsWith("/transcriptions"))!;
  expect(upload[1]?.headers).toEqual({ "Content-Type": "audio/wav" });
  await user.type(box, " today{Enter}");
  expect(await screen.findByText("About a litre of vodka a day.")).toBeInTheDocument();
  const turn = fetch.mock.calls.find(([url]) => url.endsWith("/turns/stream"))!;
  expect(JSON.parse(String(turn[1]?.body))).toEqual({ text: "How much do you drink? today", transcription_id: "b".repeat(32) });
});

test("auto-send posts recognised speech straight away", async () => {
  window.localStorage.setItem("casc.autoSend", "true");
  const fetch = mockApi();
  await beginSpeaking(fakeRecorder());
  expect(await screen.findByText("About a litre of vodka a day.")).toBeInTheDocument();
  const turn = fetch.mock.calls.find(([url]) => url.endsWith("/turns/stream"))!;
  expect(JSON.parse(String(turn[1]?.body)).transcription_id).toBe("b".repeat(32));
});

test("a refused microphone is reported and typing still works", async () => {
  mockApi();
  const user = userEvent.setup();
  const denied = vi.fn(async () => { throw new DOMException("denied", "NotAllowedError"); });
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} speech record={denied} />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  await user.click(await screen.findByRole("button", { name: "Speak to Chris" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("microphone permission");
  expect(screen.getByLabelText("What you say to Chris")).toBeEnabled();
});

test("without speech there is no microphone button", async () => {
  mockApi();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  await userEvent.click(await screen.findByRole("button", { name: "Begin interview now" }));
  await screen.findByLabelText("What you say to Chris");
  expect(screen.queryByRole("button", { name: /Speak to/ })).not.toBeInTheDocument();
});

test("runs reading, interview and debrief against the session API", async () => {
  const fetch = mockApi();
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  expect(await screen.findByText("Take a history of Chris's alcohol use.")).toBeInTheDocument();
  expect(screen.getByRole("timer", { name: "Reading time remaining" })).toHaveTextContent("1:30");
  await user.click(screen.getByRole("button", { name: "Begin interview now" }));
  expect(await screen.findByText("My GP said my liver tests were off.")).toBeInTheDocument();
  await user.type(screen.getByLabelText("What you say to Chris"), "How much do you drink?{Enter}");
  expect(await screen.findByText("About a litre of vodka a day.")).toBeInTheDocument();
  expect(JSON.parse(String(fetch.mock.calls[2]?.[1]?.body))).toEqual({ text: "How much do you drink?" });
  await user.click(screen.getByRole("button", { name: "End station" }));
  expect(await screen.findByRole("heading", { name: "Feedback" })).toBeInTheDocument();
  const tile = screen.getByText("Key information elicited").closest(".tile")!;
  expect(within(tile as HTMLElement).getByText("1 of 4")).toBeInTheDocument();
  expect(within(tile as HTMLElement).getByText("1 more touched on")).toBeInTheDocument();
  expect(screen.getByText(/a follow-up question would have drawn out the detail/)).toBeInTheDocument();
  expect(screen.getByText(/After a confrontational remark \(question 1\):/)).toBeInTheDocument();
  const asked = screen.getByText("“Is all of this going back to my GP?”").closest("li")!;
  expect(within(asked).getByText("Not responded to")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: "Alcohol" })).toHaveAttribute("aria-valuetext", "1 of 2");
  const missed = screen.getByText("Shakes and sweats.").closest("tr")!;
  expect(within(missed).getByText("Not elicited")).toBeInTheDocument();
  const held = screen.getByText("My grandson.").closest("tr")!;
  expect(within(held).getByText(/Held back/)).toBeInTheDocument();
  expect(screen.getByText("Review yourself")).toBeInTheDocument();
  expect(screen.getByText(/Technical terms to check you explained: neutropenia/)).toBeInTheDocument();
  expect(screen.getByText("Closed question")).toBeInTheDocument();
});

test("keeps the draft and reports a model failure", async () => {
  mockApi({ [`/backend/api/sessions/${base.session_id}/turns/stream`]: () =>
    stream({ type: "error", status: 503, detail: "The simulated character could not reply." }) });
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  const box = await screen.findByLabelText("What you say to Chris");
  await user.type(box, "Hello?{Enter}");
  expect(await screen.findByRole("alert")).toHaveTextContent("could not reply");
  expect(box).toHaveValue("Hello?");
});

test("reading time running out begins the interview automatically", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  mockApi();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  await screen.findByText("Take a history of Chris's alcohol use.");
  await act(async () => { vi.advanceTimersByTime(91_000); });
  expect(await screen.findByText("My GP said my liver tests were off.")).toBeInTheDocument();
});

test("formats countdowns", () => {
  expect(clock(420)).toBe("7:00");
  expect(clock(59.2)).toBe("1:00");
  expect(clock(-3)).toBe("0:00");
});

test("read-aloud becomes available when on-device voices finish loading", async () => {
  mockApi();
  const listeners: (() => void)[] = [];
  let voices: Partial<SpeechSynthesisVoice>[] = [];
  vi.stubGlobal("speechSynthesis", {
    getVoices: () => voices, cancel: vi.fn(), speak: vi.fn(),
    addEventListener: (_: string, cb: () => void) => listeners.push(cb), removeEventListener: vi.fn(),
  });
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  await userEvent.click(await screen.findByRole("button", { name: "Begin interview now" }));
  const box = await screen.findByRole("checkbox", { name: /Read replies aloud/ });
  expect(box).toBeDisabled();
  voices = [{ name: "Moira", localService: true, lang: "en-IE" }, { name: "Google US English", localService: false, lang: "en-US" }];
  act(() => listeners.forEach((cb) => cb()));
  expect(box).toBeEnabled();
});

test("streamed sentences are read aloud as they arrive and not repeated at the end", async () => {
  window.localStorage.setItem("casc.speakReplies", "true");
  const said: string[] = [];
  vi.stubGlobal("SpeechSynthesisUtterance", class { voice = null; lang = ""; constructor(readonly text: string) {} });
  const speech = { getVoices: () => [{ name: "Daniel", localService: true, lang: "en-GB" }], cancel: vi.fn(),
    speak: vi.fn((u: { text: string }) => said.push(u.text)), addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.stubGlobal("speechSynthesis", speech);
  const fetch = mockApi();
  const interview = await (await fetch.getMockImplementation()!(`/backend/api/sessions/${base.session_id}/begin`)).json();
  const reply = "I drink a bit. Maybe more than I should.";
  fetch.mockImplementation(async (url) => url.endsWith("/turns/stream")
    ? stream({ type: "sentence", text: "I drink a bit." }, { type: "sentence", text: "Maybe more than I should." },
      { type: "done", session: { ...interview, transcript: [...interview.transcript,
        { speaker: "candidate", text: "Do you drink?" }, { speaker: "character", text: reply }] } })
    : url.endsWith("/begin") ? Response.json(interview) : Response.json(base));
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  await screen.findByText("My GP said my liver tests were off.");
  said.length = 0;
  await user.type(screen.getByLabelText("What you say to Chris"), "Do you drink?{Enter}");
  expect(await screen.findByText(reply)).toBeInTheDocument();
  await act(async () => {});
  expect(said).toEqual(["I drink a bit.", "Maybe more than I should."]);
});

test("warns at one minute remaining and announces it when cues are spoken", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.localStorage.setItem("casc.spokenCues", "true");
  const said: string[] = [];
  vi.stubGlobal("SpeechSynthesisUtterance", class { voice = null; lang = ""; constructor(readonly text: string) {} });
  vi.stubGlobal("speechSynthesis", { getVoices: () => [{ name: "Daniel", localService: true, lang: "en-GB" }],
    cancel: vi.fn(), speak: vi.fn((u: { text: string }) => said.push(u.text)), addEventListener: vi.fn(), removeEventListener: vi.fn() });
  mockApi();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  await userEvent.click(await screen.findByRole("button", { name: "Begin interview now" }));
  await screen.findByText("My GP said my liver tests were off.");
  expect(screen.queryByText("One minute remaining.")).not.toBeInTheDocument();
  await act(async () => { vi.advanceTimersByTime(361_000); });
  expect(screen.getByRole("status")).toHaveTextContent("One minute remaining.");
  expect(said).toEqual(["You have one minute remaining."]);
  await act(async () => { vi.advanceTimersByTime(60_000); });
  expect(said).toContain("Time is up.");
  expect(await screen.findByRole("heading", { name: "Feedback" })).toBeInTheDocument();
});

test("the character listens, thinks and idles with the station", () => {
  expect(avatarState(undefined, "idle", "")).toBe("idle");
  expect(avatarState(undefined, "recording", "")).toBe("listening");
  expect(avatarState(undefined, "idle", "How much")).toBe("listening");
  expect(avatarState(undefined, "transcribing", "")).toBe("thinking");
  expect(avatarState("How much do you drink?", "idle", "")).toBe("thinking");
  expect(avatarFor("x", "female")).toBe("female-adult-01");
  expect(avatarFor("x", "male")).toBe("male-adult-08");
  expect(avatarFor("alcohol-history", null)).toBe(avatarFor("alcohol-history", undefined));
});

test("the character is shown by default; hiding it is remembered", async () => {
  mockApi();
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  const avatar = await screen.findByTestId("avatar");
  expect(avatar).toHaveAttribute("data-state", "idle");
  expect(avatar).toHaveAccessibleName("Chris, the simulated patient");
  await user.type(screen.getByLabelText("What you say to Chris"), "How much");
  expect(screen.getByTestId("avatar")).toHaveAttribute("data-state", "listening");
  await user.click(screen.getByRole("checkbox", { name: /Show the character/ }));
  expect(screen.queryByTestId("avatar")).not.toBeInTheDocument();
  expect(window.localStorage.getItem("casc.showAvatar")).toBe("false");
});

test("with the character's voice, each streamed sentence is synthesised and played, not spoken by the browser", async () => {
  window.localStorage.setItem("casc.speakReplies", "true");
  const browser = { getVoices: () => [{ name: "Daniel", localService: true, lang: "en-GB" }], cancel: vi.fn(),
    speak: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.stubGlobal("speechSynthesis", browser);
  const started: number[] = [];
  vi.stubGlobal("AudioContext", class {
    state = "running"; destination = {}; currentTime = 0; resume = vi.fn(); close = vi.fn(async () => {});
    createGain() { return { gain: { value: 1, setTargetAtTime: vi.fn() }, connect: (to: unknown) => to }; }
    decodeAudioData = async () => ({ duration: 2 });
    createBufferSource() {
      const source = { buffer: null, onended: null as null | (() => void), connect: (to: unknown) => to, stop: vi.fn(),
        start: vi.fn((_: number, offset: number) => { started.push(offset); setTimeout(() => source.onended?.(), 0); }) };
      return source;
    }
  });
  const fetch = mockApi();
  const routes = fetch.getMockImplementation()!;
  const asked: { text: string; voice: string }[] = [];
  fetch.mockImplementation(async (url, init) => {
    if (!url.endsWith("/speech")) return routes(url, init);
    asked.push(JSON.parse(init!.body as string));
    return Response.json({ audio_wav_base64: btoa("RIFF"), words: ["About"], word_times_ms: [460], word_durations_ms: [200],
      visemes: ["aa"], viseme_times_ms: [460], viseme_durations_ms: [120], voice: "x", model: "kokoro", synthesis_ms: 300 });
  });
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} neural />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  await screen.findByText("My GP said my liver tests were off.");
  expect(screen.getByRole("checkbox", { name: "Read replies aloud (character voice)" })).toBeChecked();
  await user.type(screen.getByLabelText("What you say to Chris"), "How much do you drink?{Enter}");
  await screen.findByText(/Reply audible after .* s/);
  const voice = characterVoice(presentedSex("alcohol-history", undefined), "adult");
  expect(asked).toEqual([{ text: "My GP said my liver tests were off.", voice }, { text: "About a litre of vodka a day.", voice }]);
  expect(started.every((offset) => Math.abs(offset - 0.34) < 1e-9)).toBe(true);
  expect(browser.speak).not.toHaveBeenCalled();
});

/** A fake WebAudio that records what each played buffer said (the test's base64 is plain text). */
function fakeAudio() {
  const played: string[] = [];
  vi.stubGlobal("AudioContext", class {
    state = "running"; destination = {}; currentTime = 0; resume = vi.fn(); close = vi.fn(async () => {});
    createGain() { return { gain: { value: 1, setTargetAtTime: vi.fn() }, connect: (to: unknown) => to }; }
    decodeAudioData = async (wav: ArrayBuffer) => ({ duration: 2, text: new TextDecoder().decode(wav) });
    createBufferSource() {
      const source = { buffer: null as null | { text: string }, onended: null as null | (() => void), connect: (to: unknown) => to, stop: vi.fn(),
        start: vi.fn(() => { played.push(source.buffer!.text); setTimeout(() => source.onended?.(), 0); }) };
      return source;
    }
  });
  return played;
}

const spoken = (text: string) => Response.json({ audio_wav_base64: btoa(text), words: [text], word_times_ms: [460],
  word_durations_ms: [200], visemes: ["aa"], viseme_times_ms: [460], viseme_durations_ms: [120], voice: "x", model: "kokoro", synthesis_ms: 300 });

test("the case's own character shows the affect stage's expression and speaks in the case's voice", async () => {
  window.localStorage.setItem("casc.showAvatar", "true");
  window.localStorage.setItem("casc.speakReplies", "true");
  vi.stubGlobal("speechSynthesis", { getVoices: () => [], cancel: vi.fn(), speak: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() });
  fakeAudio();
  const own = { ...station, avatar: "male-adult-12", voice: { ...station.voice, sex: "male" as const, speaker: "am_michael" } };
  const fetch = mockApi();
  const routes = fetch.getMockImplementation()!;
  const voices: string[] = [];
  fetch.mockImplementation(async (url, init) => {
    if (url.endsWith("/speech")) { voices.push(JSON.parse(init!.body as string).voice); return spoken("x"); }
    const body = await (await routes(url, init)).json();
    return Response.json(url.endsWith("/begin")
      ? { ...body, station: own, presentation: { expression: "tense", hesitations: [] } } : { ...body, station: own });
  });
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} neural />);
  await userEvent.click(await screen.findByRole("button", { name: "Begin interview now" }));
  const avatar = await screen.findByTestId("avatar");
  expect(avatar).toHaveAttribute("data-avatar", "male-adult-12");
  expect(avatar).toHaveAttribute("data-mood", "tense");
  await waitFor(() => expect(voices).toContain("am_michael"));
});

test("a slow turn has a hesitation midway, synthesised in advance and played quieter", async () => {
  window.localStorage.setItem("casc.speakReplies", "true");
  vi.stubGlobal("speechSynthesis", { getVoices: () => [], cancel: vi.fn(), speak: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() });
  const played = fakeAudio();
  const fetch = mockApi();
  const routes = fetch.getMockImplementation()!;
  const asked: string[] = [];
  fetch.mockImplementation(async (url, init) => {
    if (url.endsWith("/speech")) { const { text } = JSON.parse(init!.body as string); asked.push(text); return spoken(text); }
    const response = await routes(url, init);
    if (url.endsWith("/turns/stream")) {
      // The API says the turn is slow, then the reply arrives after the hesitation is due.
      const events = await response.text();
      const bytes = (text: string) => new TextEncoder().encode(text);
      return new Response(new ReadableStream({ start(stream) {
        stream.enqueue(bytes(JSON.stringify({ type: "pace", slow: true }) + "\n"));
        setTimeout(() => { stream.enqueue(bytes(events)); stream.close(); }, 2200);
      } }));
    }
    if (!url.endsWith("/begin")) return response;
    return Response.json({ ...(await response.json()), presentation: { expression: "tense", hesitations: ["Hmmm."] } });
  });
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} neural />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  await waitFor(() => expect(asked).toContain("Hmmm."));
  played.length = 0;
  await user.type(screen.getByLabelText("What you say to Chris"), "How much do you drink?{Enter}");
  await waitFor(() => expect(played).toEqual(["Hmmm.", "About a litre of vodka a day."]), { timeout: 4000 });
  expect(asked.filter((t) => t === "Hmmm.")).toHaveLength(1); // prepared once, not on the turn
});

/** A stand-in for voice-activity detection that the test drives. */
function fakeListening() {
  let events: ListenerEvents | null = null;
  const listener = { start: vi.fn(async () => {}), pause: vi.fn(async () => {}), destroy: vi.fn(async () => {}), setGuarded: vi.fn() };
  const listen = vi.fn(async (e: ListenerEvents) => { events = e; return listener; });
  const say = async () => {
    await act(async () => { events!.onSpeechStart(); events!.onSpeechConfirmed(); });
    await act(async () => { events!.onSpeechEnd(new Float32Array(16000)); });
  };
  return { listen, listener, events: () => events!, say };
}

async function beginHandsFree(listening: ReturnType<typeof fakeListening>) {
  window.localStorage.setItem("casc.handsFree", "true");
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} speech listen={listening.listen} />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  await screen.findByText(/Listening — just speak to Chris/);
  return user;
}

test("hands-free: speech is transcribed and sent without clicking", async () => {
  const fetch = mockApi();
  const listening = fakeListening();
  await beginHandsFree(listening);
  expect(screen.queryByRole("button", { name: "Speak to Chris" })).not.toBeInTheDocument();
  await listening.say();
  expect(await screen.findByText("About a litre of vodka a day.")).toBeInTheDocument();
  const sent = fetch.mock.calls.find(([url]) => url.endsWith("/turns/stream"))!;
  expect(JSON.parse(sent[1]!.body as string)).toEqual({ text: "How much do you drink?", transcription_id: "b".repeat(32) });
});

test("hands-free: talking over the character stops its voice and records the interruption", async () => {
  const fetch = mockApi({ [`/backend/api/sessions/${base.session_id}/interruptions`]: () => new Response(null, { status: 204 }) });
  const cancel = vi.fn();
  vi.stubGlobal("speechSynthesis", { getVoices: () => [], cancel, speak: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() });
  const listening = fakeListening();
  await beginHandsFree(listening);
  act(() => emitSpeech({ type: "start", text: "My GP said my liver tests were off." }));
  await waitFor(() => expect(listening.listener.setGuarded).toHaveBeenLastCalledWith(true));
  await act(async () => { listening.events().onSpeechStart(); listening.events().onSpeechConfirmed(); });
  expect(cancel).toHaveBeenCalled();
  const cut = fetch.mock.calls.find(([url]) => url.endsWith("/interruptions"))!;
  expect(JSON.parse(cut[1]!.body as string)).toMatchObject({ during: "speaking" });
  await waitFor(() => expect(listening.listener.setGuarded).toHaveBeenLastCalledWith(false));
});

test("hands-free: speaking while the reply is prepared silences it and sends the new words after", async () => {
  window.localStorage.setItem("casc.speakReplies", "true");
  const said: string[] = [];
  vi.stubGlobal("SpeechSynthesisUtterance", class { voice = null; lang = ""; constructor(readonly text: string) {} });
  vi.stubGlobal("speechSynthesis", { getVoices: () => [{ name: "Daniel", localService: true, lang: "en-GB" }], cancel: vi.fn(),
    speak: vi.fn((u: { text: string }) => said.push(u.text)), addEventListener: vi.fn(), removeEventListener: vi.fn() });
  let release = () => {};
  const fetch = mockApi({ [`/backend/api/sessions/${base.session_id}/interruptions`]: () => new Response(null, { status: 204 }) });
  const routes = fetch.getMockImplementation()!;
  fetch.mockImplementation(async (url, init) => {
    const response = await routes(url, init);
    if (url.endsWith("/turns/stream")) await new Promise<void>((r) => { release = r; });
    return response;
  });
  const listening = fakeListening();
  await beginHandsFree(listening);
  said.length = 0;
  await listening.say(); // first question: the reply is now being prepared
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.endsWith("/turns/stream"))).toBe(true));
  await listening.say(); // speaks again before the reply arrives
  const cut = fetch.mock.calls.find(([url]) => url.endsWith("/interruptions"))!;
  expect(JSON.parse(cut[1]!.body as string)).toEqual({ during: "thinking", heard_ms: 0 });
  await act(async () => release());
  await waitFor(() => expect(fetch.mock.calls.filter(([url]) => url.endsWith("/turns/stream"))).toHaveLength(2));
  expect(said).not.toContain("About a litre of vodka a day.");
  await act(async () => release());
});

test("hands-free: the character's own voice heard by the microphone is not sent", async () => {
  const fetch = mockApi({ [`/backend/api/sessions/${base.session_id}/transcriptions`]: () =>
    Response.json({ transcription_id: "c".repeat(32), text: "my GP said my liver tests were off", audio_ms: 1500, asr_ms: 600 }),
  [`/backend/api/sessions/${base.session_id}/interruptions`]: () => new Response(null, { status: 204 }) });
  vi.stubGlobal("speechSynthesis", { getVoices: () => [], cancel: vi.fn(), speak: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() });
  const listening = fakeListening();
  await beginHandsFree(listening);
  act(() => emitSpeech({ type: "start", text: "My GP said my liver tests were off." }));
  await listening.say();
  await act(async () => {});
  expect(fetch.mock.calls.some(([url]) => url.endsWith("/turns/stream"))).toBe(false);
  act(() => emitSpeech({ type: "end" }));
});

/** jsdom does no layout: give the transcript a fixed size so scrolling can be checked. */
function sized(list: HTMLElement, contentHeight: () => number) {
  Object.defineProperty(list, "clientHeight", { configurable: true, get: () => 300 });
  Object.defineProperty(list, "scrollHeight", { configurable: true, get: contentHeight });
}

test("the transcript follows new lines, unless the trainee scrolls up to reread", async () => {
  let content = 1000;
  const fetch = mockApi();
  const routes = fetch.getMockImplementation()!;
  const interview = await (await routes(`/backend/api/sessions/${base.session_id}/begin`)).json();
  let turn = 0;
  let release = () => {};
  const bytes = (event: object) => new TextEncoder().encode(JSON.stringify(event) + "\n");
  fetch.mockImplementation(async (url, init) => {
    if (!url.endsWith("/turns/stream")) return routes(url, init);
    const n = ++turn;
    const transcript = [...interview.transcript];
    for (let i = 1; i <= n; i++) transcript.push({ speaker: "candidate", text: `Question ${i}?` }, { speaker: "character", text: `Answer ${i}. More.` });
    // The reply arrives in two parts; the second waits for the test.
    return new Response(new ReadableStream({ async start(out) {
      content += 300;
      out.enqueue(bytes({ type: "sentence", text: `Answer ${n}.` }));
      await new Promise<void>((r) => { release = r; });
      content += 300;
      out.enqueue(bytes({ type: "sentence", text: "More." }));
      out.enqueue(bytes({ type: "done", session: { ...interview, transcript } }));
      out.close();
    } }));
  });
  const user = userEvent.setup();
  render(<StationRunner caseId="alcohol-history" onExit={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Begin interview now" }));
  const list = await screen.findByRole("list", { name: "Transcript" });
  sized(list, () => content);

  // Sending follows the conversation to the newest line, as the reply streams in.
  await user.type(screen.getByLabelText("What you say to Chris"), "Question 1?{Enter}");
  await screen.findByText("Answer 1.");
  await waitFor(() => expect(list.scrollTop).toBe(content));
  await act(async () => release());
  await screen.findByText("Answer 1. More.");
  await waitFor(() => expect(list.scrollTop).toBe(content));

  // Scrolled up to reread while the next reply streams in: it does not pull them down.
  await user.type(screen.getByLabelText("What you say to Chris"), "Question 2?{Enter}");
  await screen.findByText("Answer 2.");
  list.scrollTop = 100;
  act(() => { list.dispatchEvent(new Event("scroll")); });
  await act(async () => release());
  await screen.findByText("Answer 2. More.");
  expect(list.scrollTop).toBe(100);

  // Sending again resumes following.
  await user.type(screen.getByLabelText("What you say to Chris"), "Question 3?{Enter}");
  await screen.findByText("Answer 3.");
  await waitFor(() => expect(list.scrollTop).toBe(content));
  await act(async () => release());
});
