import { rm } from "node:fs/promises";
import path from "node:path";

// The online API admits the supervisor's warm-up only with its per-start secret, and only
// on the API's loopback port: the web proxy refuses to forward that header.
const internal = (token) => (token ? { "X-CascAid-Internal": token } : {});

export async function request(base, route, body, signal, token) {
  const response = await fetch(base + route, { method: body === undefined ? "GET" : "POST",
    headers: { ...internal(token), ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.any([AbortSignal.timeout(180000), ...(signal ? [signal] : [])]) });
  if (!response.ok) throw new Error(`Production smoke failed: ${route} (${response.status})`);
  return response.json();
}

export async function smoke(c, base = `http://127.0.0.1:${c.apiPort}`, token = c.internalToken) {
  const call = (route, body) => request(base, route, body, c.abortSignal, token);
  // Original synthetic cases only. Never print model output or retain warm-up sessions.
  const cases = await call("/api/cases");
  const station = cases.find((item) => item.id === "depression-history") || cases[0];
  if (!station) throw new Error("No cases available for production warm-up");
  let id;
  try {
    const started = await call("/api/sessions", { case_id: station.id });
    id = started.session_id;
    if (!/^[a-f0-9]{32}$/.test(id)) throw new Error("Invalid smoke session ID");
    await call(`/api/sessions/${id}/begin`, {});
    const session = await call(`/api/sessions/${id}/turns`, {
      text: "Hello, I am the doctor. Could you tell me what has brought you here today?",
    });
    const reply = session.transcript.filter((line) => line.speaker === "character").at(-1)?.text;
    if (!reply) throw new Error("Warm-up returned no character reply");
    // Voice ID is a public station property; fall back to the installed default.
    const audio = await call(`/api/sessions/${id}/speech`, {
      text: reply, voice: station.voice?.speaker || c.tts.voices[0].name,
    });
    if (!audio.audio_wav_base64) throw new Error("Speech warm-up returned no audio");
    // ASR accepts 16kHz mono WAV. Silence is sufficient to exercise the recognizer
    // without storing any user's voice or depending on a TTS sample rate.
    const wav = Buffer.alloc(44 + 32000);
    wav.write("RIFF"); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
    wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
    wav.writeUInt32LE(16000, 24); wav.writeUInt32LE(32000, 28);
    wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(32000, 40);
    const asr = await fetch(`${base}/api/sessions/${id}/transcriptions`, {
      method: "POST", headers: { ...internal(token), "Content-Type": "audio/wav" }, body: wav,
      signal: AbortSignal.any([AbortSignal.timeout(60000), ...(c.abortSignal ? [c.abortSignal] : [])]),
    });
    if (!asr.ok) throw new Error(`ASR warm-up failed (${asr.status})`);
    const ended = await call(`/api/sessions/${id}/end`, {});
    if (!ended.feedback || ended.session.phase !== "ended") throw new Error("Feedback warm-up failed");
    await call(`/api/sessions/${id}/debrief`);
    return { status: "passed", checks: ["case", "interview", "local-generation", "speech", "transcription", "feedback"] };
  } finally {
    if (id && /^[a-f0-9]{32}$/.test(id)) await rm(path.join(c.env.SESSIONS_PATH, `${id}.jsonl`), { force: true });
  }
}
