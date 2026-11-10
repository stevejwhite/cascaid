import type { components } from "./api.generated";

export type Readiness = components["schemas"]["Readiness"];
export type ServiceCheck = components["schemas"]["ServiceCheck"];
export type CaseSummary = components["schemas"]["CaseSummary"];
export type BlueprintMatrix = components["schemas"]["BlueprintMatrix"];
export type MatrixStation = components["schemas"]["MatrixStation"];
export type SessionView = components["schemas"]["SessionView"];
export type Debrief = components["schemas"]["Debrief"];
export type Feedback = components["schemas"]["Feedback"];
export type FactResult = components["schemas"]["FactResult"];
export type TaskResult = components["schemas"]["TaskResult"];
export type AffectChange = components["schemas"]["AffectChange"];
export type QuestionResult = components["schemas"]["QuestionResult"];
export type Utterance = components["schemas"]["Utterance"];
export type TranscriptionView = components["schemas"]["TranscriptionView"];
export type SpeechView = components["schemas"]["SpeechView"];

export async function readApi<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/backend${path}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("The local API could not complete this request.");
  return response.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/backend${path}`, {
    method: "POST", signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().then((b) => b.detail).catch(() => undefined);
    throw new ApiError(typeof detail === "string" ? detail : "The local API could not complete this request.", response.status);
  }
  return response.json() as Promise<T>;
}

export const startSession = (caseId: string) => post<SessionView>("/api/sessions", { case_id: caseId });
export const beginInterview = (id: string) => post<SessionView>(`/api/sessions/${id}/begin`);
export const sendTurn = (id: string, text: string, transcriptionId?: string | null, signal?: AbortSignal) =>
  post<SessionView>(`/api/sessions/${id}/turns`,
    transcriptionId ? { text, transcription_id: transcriptionId } : { text }, signal);

type StreamEvent =
  | { type: "pace"; slow: boolean }
  | { type: "sentence"; text: string }
  | { type: "done"; session: SessionView }
  | { type: "error"; status: number; detail: string };

/** Send a turn and receive the reply sentence by sentence (newline-delimited JSON). */
export async function sendTurnStream(id: string, text: string, transcriptionId: string | null | undefined,
  onSentence: (sentence: string, index: number) => void, signal?: AbortSignal,
  /** Whether the turn will wait for the language model (sent before any sentence). */
  onPace?: (slow: boolean) => void): Promise<SessionView> {
  const response = await fetch(`/backend/api/sessions/${id}/turns/stream`, {
    method: "POST", signal, headers: { "Content-Type": "application/json" },
    body: JSON.stringify(transcriptionId ? { text, transcription_id: transcriptionId } : { text }),
  });
  if (!response.ok || !response.body) {
    const detail = await response.json().then((b) => b.detail).catch(() => undefined);
    throw new ApiError(typeof detail === "string" ? detail : "The local API could not complete this request.", response.status);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let count = 0;
  for (;;) {
    const { value, done } = await reader.read();
    buffer += value ?? "";
    const lines = buffer.split("\n");
    buffer = done ? "" : lines.pop()!;
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as StreamEvent;
      if (event.type === "pace") onPace?.(event.slow);
      else if (event.type === "sentence") onSentence(event.text, count++);
      else if (event.type === "done") return event.session;
      else throw new ApiError(event.detail, event.status);
    }
    if (done) throw new ApiError("The reply ended unexpectedly.", 503);
  }
}

export async function transcribe(id: string, audio: Blob): Promise<TranscriptionView> {
  const response = await fetch(`/backend/api/sessions/${id}/transcriptions`, {
    method: "POST", headers: { "Content-Type": "audio/wav" }, body: audio,
  });
  if (!response.ok) {
    const detail = await response.json().then((b) => b.detail).catch(() => undefined);
    throw new ApiError(typeof detail === "string" ? detail : "Speech could not be transcribed.", response.status);
  }
  return response.json() as Promise<TranscriptionView>;
}
/** The character's voice for one sentence it has said: WAV audio with viseme timings. */
export const synthesize = (id: string, text: string, voice: string, signal?: AbortSignal) =>
  post<SpeechView>(`/api/sessions/${id}/speech`, { text, voice }, signal);

/** Record that the trainee spoke over the character (hands-free conversation). */
export async function recordInterruption(id: string, during: "speaking" | "thinking", heardMs: number): Promise<void> {
  try {
    await fetch(`/backend/api/sessions/${id}/interruptions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ during, heard_ms: Math.max(0, Math.round(heardMs)) }),
    });
  } catch { /* best effort: a missed log entry must not interrupt the conversation */ }
}

export const endSession = (id: string) => post<Debrief>(`/api/sessions/${id}/end`);

export type RecordingPrompts = components["schemas"]["RecordingPrompts"];
export type Saved = components["schemas"]["Saved"];

export async function saveRecording(speaker: string, item: number, audio: Blob): Promise<Saved> {
  const query = new URLSearchParams({ speaker, item: String(item), consent: "true" });
  const response = await fetch(`/backend/api/recordings?${query}`, {
    method: "POST", headers: { "Content-Type": "audio/wav" }, body: audio,
  });
  if (!response.ok) {
    const detail = await response.json().then((b) => b.detail).catch(() => undefined);
    throw new ApiError(typeof detail === "string" ? detail : "The recording could not be saved.", response.status);
  }
  return response.json() as Promise<Saved>;
}
