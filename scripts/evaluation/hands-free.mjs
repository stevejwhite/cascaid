// Measure hands-free conversation in Chromium with a synthetic microphone.
// Usage: npm run eval:hands-free -- [--out artifacts/eval/hands-free.json]
// Needs the dev web app and API (SPEECH_BACKEND=local, TTS_BACKEND=local), npm run models:start,
// speech:start and tts:start; macOS `say` makes the trainee's voice (no real person is recorded).
// For each case: Begin, then the microphone plays question 1 after 10 s and question 2 six
// seconds after it ends (timed to land while the character answers). Latencies come from the
// page's performance marks (hands-free:*, voice:*).
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "@playwright/test";
import { root } from "../models/files.mjs";

const flag = process.argv.indexOf("--out");
const outFile = flag >= 0 ? path.resolve(process.argv[flag + 1]) : null;
const work = path.join(root, "artifacts/eval/hands-free-audio");
const CASES = ["alcohol-history", "clozapine-explanation-relative", "elevated-mood-history", "memory-collateral-history", "overdose-risk-assessment"];
const QUESTIONS = ["Can you tell me a bit about what's been happening?", "Sorry to stop you there. How long has this been going on?"];
const LEAD = 10, GAP = 6, RATE = 48000;

async function wav(file) { // 16-bit mono PCM: [samples buffer, seconds]
  const out = file.replace(/\.aiff$/, ".wav");
  execFileSync("afconvert", ["-f", "WAVE", "-d", `LEI16@${RATE}`, "-c", "1", file, out]);
  const data = await readFile(out);
  const at = data.indexOf("data");
  const size = data.readUInt32LE(at + 4);
  const pcm = data.subarray(at + 8, at + 8 + size);
  return [pcm, pcm.length / 2 / RATE];
}

await mkdir(work, { recursive: true });
const said = [];
for (const [i, q] of QUESTIONS.entries()) {
  const aiff = path.join(work, `q${i + 1}.aiff`);
  execFileSync("say", ["-v", "Daniel", "-o", aiff, q]);
  said.push(await wav(aiff));
}
const silence = (s) => Buffer.alloc(Math.round(s * RATE) * 2);
const pcm = Buffer.concat([silence(LEAD), said[0][0], silence(GAP), said[1][0], silence(60)]);
const header = Buffer.alloc(44);
header.write("RIFF", 0); header.writeUInt32LE(36 + pcm.length, 4); header.write("WAVEfmt ", 8);
header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22);
header.writeUInt32LE(RATE, 24); header.writeUInt32LE(RATE * 2, 28); header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34);
header.write("data", 36); header.writeUInt32LE(pcm.length, 40);
const mic = path.join(work, "microphone.wav");
await writeFile(mic, Buffer.concat([header, pcm]));
const durations = said.map(([, seconds]) => seconds);

const browser = await chromium.launch({ headless: true, args: ["--use-angle=metal", "--enable-gpu", "--autoplay-policy=no-user-gesture-required",
  "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${mic}`] });
const rows = [];
for (const caseId of CASES) {
  const context = await browser.newContext({ permissions: ["microphone"], viewport: { width: 1280, height: 860 } });
  const page = await context.newPage();
  await page.addInitScript(() => {
    for (const key of ["casc.speakReplies", "casc.showAvatar", "casc.handsFree"]) localStorage.setItem(key, "true");
  });
  const interruptions = [];
  page.on("request", (r) => { if (r.url().endsWith("/interruptions")) interruptions.push(JSON.parse(r.postData())); });
  await page.goto("http://127.0.0.1:3105/");
  await page.locator(`article.station-card[aria-labelledby=station-${caseId}]`).getByRole("button", { name: "Start station" }).click();
  await page.getByRole("button", { name: "Begin interview now" }).click();
  await page.waitForTimeout(42000);
  const marks = await page.evaluate(() => performance.getEntriesByType("mark")
    .filter((m) => /^(hands-free|voice):/.test(m.name)).map((m) => ({ name: m.name, at: m.startTime })));
  const sent = (await page.locator(".transcript li.candidate p").allTextContents());
  await context.close();
  // Pair each utterance's marks: speech-start .. transcribed, then the next first audio.
  const all = (name) => marks.filter((m) => m.name === name).map((m) => m.at);
  const starts = all("hands-free:speech-start"), ends = all("hands-free:speech-end"), heard = all("hands-free:transcribed");
  const confirmed = all("hands-free:speech-confirmed"), ducked = all("voice:ducked"), stopped = all("voice:stopped"), audio = all("voice:first-audio");
  const near = (list, at, within = 50) => list.find((t) => t >= at && t - at <= within);
  // Each end of speech belongs to the last start before it (earlier starts were false starts).
  const utterances = ends.slice(0, 2).map((end, i) => {
    const start = starts.filter((t) => t < end).at(-1), transcribed = heard.find((t) => t > end);
    const confirm = confirmed.find((t) => t >= start);
    const reply = audio.find((t) => t > transcribed);
    return {
      question: i + 1,
      sent: sent[i] ?? null,
      // The VAD's start lags the true onset by a frame or two, so end detection is a bound.
      end_detection_ms: Math.round(end - start - durations[i] * 1000),
      transcription_ms: transcribed ? Math.round(transcribed - end) : null,
      reply_audible_after_end_ms: reply ? Math.round(reply - end) : null,
      interrupted: near(stopped, confirm) !== undefined,
      duck_ms: near(ducked, start) !== undefined ? Math.round(near(ducked, start) - start) : null,
      stop_ms: near(stopped, confirm) !== undefined ? Math.round(near(stopped, confirm) - start) : null,
    };
  });
  rows.push({ case_id: caseId, interruptions, utterances });
  console.log(caseId, JSON.stringify(utterances.map(({ sent: _, ...u }) => u)));
}
await browser.close();

const flat = rows.flatMap((r) => r.utterances);
const median = (xs) => { const v = xs.filter((x) => x !== null).sort((a, b) => a - b); return v.length ? v[Math.floor((v.length - 1) / 2)] : null; };
const summary = {
  utterances: flat.length,
  sent_verbatim: flat.filter((u, i) => u.sent === QUESTIONS[i % 2]).length,
  end_detection_ms_median: median(flat.map((u) => u.end_detection_ms)),
  transcription_ms_median: median(flat.map((u) => u.transcription_ms)),
  reply_audible_after_end_ms_median: median(flat.map((u) => u.reply_audible_after_end_ms)),
  interruptions: flat.filter((u) => u.interrupted).length,
  duck_ms_median: median(flat.filter((u) => u.interrupted).map((u) => u.duck_ms)),
  stop_ms_median: median(flat.filter((u) => u.interrupted).map((u) => u.stop_ms)),
};
console.log(JSON.stringify(summary, null, 2));
if (outFile) {
  await mkdir(path.dirname(outFile), { recursive: true });
  await writeFile(outFile, JSON.stringify({ measured_at: new Date().toISOString(), questions: QUESTIONS, durations_s: durations,
    summary, cases: rows }, null, 2) + "\n");
}
