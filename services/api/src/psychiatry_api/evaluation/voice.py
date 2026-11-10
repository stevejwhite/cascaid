"""Measure how soon the character is heard, against the running local stack.

Usage: npm run eval:voice -- [--api http://127.0.0.1:8105] [--out artifacts/eval/voice.json]

Needs the API (TTS_BACKEND=local, QA_BACKEND=local), the models (npm run models:start) and
speech synthesis (npm run tts:start). For each case it begins a station and asks the same
generic questions, doing what the browser does: each released sentence is sent for
synthesis as soon as it arrives, and sentences play in order. Reported per turn:

- first_audio_ms: from sending the turn to the first sentence's audio being ready to play
  (the leading silence the player skips is not counted as waiting);
- stall_ms: total silence between sentences while a later one was still being synthesised;
- synthesis_ms and audio_ms per sentence, and their real-time factor.
"""

import argparse
import asyncio
import base64
import io
import json
import statistics
import wave
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx

from psychiatry_api.cases import load_cases
from psychiatry_api.config import Settings

# Generic openers any station could hear; not taken from the evaluation label sets.
QUESTIONS = (
    "Can you tell me a bit about what's been happening?",
    "How have things been for you over the last few weeks?",
    "What worries you most about all this?",
)
VOICE = {"female": "af_bella", "male": "am_michael"}
LEAD_IN_MS = 120  # as apps/web/lib/neural-voice.ts


def audible_ms(speech: dict) -> int:
    with wave.open(io.BytesIO(base64.b64decode(speech["audio_wav_base64"]))) as audio:
        total = audio.getnframes() * 1000 / audio.getframerate()
    skipped = max(0, (speech["word_times_ms"] or [0])[0] - LEAD_IN_MS)
    return round(total - skipped)


async def turn(client: httpx.AsyncClient, sid: str, text: str, voice: str) -> dict:
    started = perf_counter()
    elapsed = lambda: (perf_counter() - started) * 1000  # noqa: E731
    jobs: list[asyncio.Task] = []

    async def synthesise(sentence: str) -> tuple[dict, float]:
        response = await client.post(
            f"/api/sessions/{sid}/speech", json={"text": sentence, "voice": voice}
        )
        response.raise_for_status()
        return response.json(), elapsed()

    first_sentence_ms = None
    async with client.stream(
        "POST", f"/api/sessions/{sid}/turns/stream", json={"text": text}
    ) as response:
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event["type"] == "sentence":
                first_sentence_ms = first_sentence_ms or elapsed()
                jobs.append(asyncio.create_task(synthesise(event["text"])))
            elif event["type"] == "error":
                raise RuntimeError(event["detail"])
    results = [await job for job in jobs]
    # Play in order: each sentence starts when it is ready and the previous one has finished.
    clock, stall, sentences = None, 0.0, []
    for speech, ready in results:
        if clock is None:
            clock = ready
        else:
            stall += max(0.0, ready - clock)
            clock = max(clock, ready)
        clock += audible_ms(speech)
        sentences.append({"synthesis_ms": speech["synthesis_ms"], "audio_ms": audible_ms(speech)})
    return {
        "question": text,
        "sentences": len(results),
        "first_sentence_ms": round(first_sentence_ms) if first_sentence_ms else None,
        "first_audio_ms": round(results[0][1]) if results else None,
        "stall_ms": round(stall),
        "per_sentence": sentences,
    }


def summary(turns: list[dict]) -> dict:
    first = [t["first_audio_ms"] for t in turns if t["first_audio_ms"] is not None]
    sentences = [s for t in turns for s in t["per_sentence"]]
    return {
        "turns": len(turns),
        "first_audio_ms_median": statistics.median(first),
        "first_audio_ms_max": max(first),
        "first_sentence_ms_median": statistics.median(
            t["first_sentence_ms"] for t in turns if t["first_sentence_ms"]
        ),
        "synthesis_ms_median": statistics.median(s["synthesis_ms"] for s in sentences),
        "real_time_factor": sum(s["synthesis_ms"] for s in sentences)
        / max(1, sum(s["audio_ms"] for s in sentences)),
        "turns_with_stalls": sum(1 for t in turns if t["stall_ms"] > 0),
        "stall_ms_max": max(t["stall_ms"] for t in turns),
    }


async def run(api: str) -> dict:
    settings = Settings()
    rows = []
    async with httpx.AsyncClient(base_url=api, timeout=180, trust_env=False) as client:
        status = (await client.get("/api/status")).json()
        if status["voice"]["status"] != "ready" or status["generation"]["status"] != "ready":
            raise SystemExit("Start the models, speech synthesis and the API (TTS_BACKEND=local)")
        for case in load_cases(settings.cases_path):
            sex = case.persona.voice.sex or "female"
            started = await client.post("/api/sessions", json={"case_id": case.id})
            sid = started.json()["session_id"]
            await client.post(f"/api/sessions/{sid}/begin")
            for question in QUESTIONS:
                row = await turn(client, sid, question, VOICE[sex])
                rows.append({"case_id": case.id, **row})
                print(
                    f"{case.id:32} first audio {row['first_audio_ms']:>5} ms"
                    f"  sentences {row['sentences']}  stall {row['stall_ms']} ms"
                )
    return {
        "measured_at": datetime.now(UTC).isoformat(),
        "api": api,
        "tts_backend": settings.tts_backend,
        "summary": summary(rows),
        "turns": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8105")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.api))
    print(json.dumps(result["summary"], indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
