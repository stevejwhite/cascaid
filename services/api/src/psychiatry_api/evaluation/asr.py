"""Speech-recognition evaluation: word error rate and its effect on interpretation.

Usage:
  npm run eval:asr -- [--voices Daniel,Samantha] [--interpret] [--out artifacts/eval/asr.json]
  npm run eval:asr -- --manifest recordings.yaml   # real recordings (Phase 4)

By default the labelled interpreter utterances are synthesised with on-device macOS voices
(`say`). Synthetic speech is clean and unhurried, so it gives a lower bound on error, not
a substitute for human recordings. A manifest lists real recordings instead:
  items: [{audio: path/to/16k-mono.wav, reference: "text", case_id: optional}]
"""

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml

from psychiatry_api.cases import load_cases
from psychiatry_api.config import ROOT, Settings
from psychiatry_api.domain import Contract
from psychiatry_api.evaluation.interpreter import speech_labels
from psychiatry_api.models.selection import language_model, verify_service
from psychiatry_api.roleplay.disclosure import DisclosureState
from psychiatry_api.roleplay.interpret import STOPWORDS, ModelInterpreter
from psychiatry_api.sources import UniqueKeyLoader
from psychiatry_api.speech import (
    SpeechError,
    WhisperCppRecognizer,
    running_model,
    validate_wav,
    vocabulary_prompt,
)

VOICES = ("Daniel", "Samantha", "Karen", "Moira", "Rishi", "Tessa")
AUDIO_CACHE = ROOT / "artifacts/eval/asr-audio"


class Recording(Contract):
    audio: str
    reference: str
    case_id: str | None = None
    voice: str | None = None


# Whisper tends to write American spellings; standard ASR scoring treats them as equal.
SPELLING = {
    "favourite": "favorite",
    "summarise": "summarize",
    "summarised": "summarized",
    "recognise": "recognize",
    "realise": "realize",
    "realised": "realized",
    "organise": "organize",
    "apologise": "apologize",
    "behaviour": "behavior",
    "behaviours": "behaviors",
    "colour": "color",
    "centre": "center",
    "programme": "program",
    "paediatric": "pediatric",
    "anaesthetic": "anesthetic",
    "haematology": "hematology",
    "oesophagus": "esophagus",
    "counselling": "counseling",
    "travelled": "traveled",
}


def normalise(text: str, spelling: bool = True) -> list[str]:
    text = text.casefold().replace("’", "'").replace("-", " ")
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)
    return [SPELLING.get(w, w) for w in words] if spelling else words


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, word in enumerate(reference, 1):
        current = [i]
        for j, heard in enumerate(hypothesis, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (word != heard))
            )
        previous = current
    return previous[-1]


def content_words(words: list[str]) -> set[str]:
    return {w for w in words if len(w) >= 4 and w not in STOPWORDS}


def synthesise(text: str, voice: str) -> Path:
    path = AUDIO_CACHE / voice / f"{hashlib.sha1(text.encode()).hexdigest()[:16]}.wav"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "say",
                "-v",
                voice,
                "-o",
                str(path),
                "--file-format=WAVE",
                "--data-format=LEI16@16000",
                text,
            ],
            check=True,
        )
    return path


def labelled_recordings(voices: tuple[str, ...]) -> list[tuple[Recording, dict]]:
    rows = []
    for label_set in speech_labels():
        for item in label_set.items:
            for voice in voices:
                recording = Recording(
                    audio=str(synthesise(item.utterance, voice)),
                    reference=item.utterance,
                    case_id=label_set.case_id,
                    voice=voice,
                )
                rows.append(
                    (recording, {"expected": sorted(item.expected), "split": label_set.split})
                )
    return rows


def summarise(rows: list[dict]) -> dict:
    ref_words = sum(r["reference_words"] for r in rows)
    content = sum(r["content_words"] for r in rows)
    audio = sum(r["audio_ms"] for r in rows)
    summary = {
        "items": len(rows),
        "wer": sum(r["errors"] for r in rows) / ref_words if ref_words else 0.0,
        "wer_without_spelling_normalisation": (
            sum(r.get("raw_errors", r["errors"]) for r in rows) / ref_words if ref_words else 0.0
        ),
        "exact_transcripts": sum(r["errors"] == 0 for r in rows) / len(rows),
        "content_word_recall": sum(r["content_found"] for r in rows) / content if content else 1.0,
        "mean_asr_ms": round(sum(r["asr_ms"] for r in rows) / len(rows)),
        "mean_audio_ms": round(audio / len(rows)),
        "real_time_factor": sum(r["asr_ms"] for r in rows) / audio if audio else 0.0,
    }
    interpreted = [r for r in rows if "selected_from_speech" in r]
    if interpreted:
        summary |= {
            "interpreted": len(interpreted),
            "typed_exact_match": sum(r["selected_from_text"] == r["expected"] for r in interpreted)
            / len(interpreted),
            "speech_exact_match": sum(
                r["selected_from_speech"] == r["expected"] for r in interpreted
            )
            / len(interpreted),
            "speech_agrees_with_typed": sum(
                r["selected_from_speech"] == r["selected_from_text"] for r in interpreted
            )
            / len(interpreted),
        }
    return summary


async def evaluate(settings: Settings, recordings, interpret: bool) -> dict:
    model = running_model(settings.speech_state_file)
    if model is None:
        raise SystemExit("Start speech recognition first: npm run speech:start")
    asr = WhisperCppRecognizer(settings.asr_base_url, model, settings.model_timeout_seconds)
    cases = {case.id: case for case in load_cases(settings.cases_path)}
    interpreter = None
    if interpret:
        await verify_service(settings)
        interpreter = ModelInterpreter(
            language_model(settings), int(settings.model_timeout_seconds * 1000)
        )
    rows, typed_cache = [], {}
    for recording, labels in recordings:
        case = cases.get(recording.case_id) if recording.case_id else None
        prompt = vocabulary_prompt(case.persona.name) if case else None
        audio = validate_wav(Path(recording.audio).read_bytes())
        try:
            heard = await asr.transcribe(audio, prompt)
        except SpeechError as error:
            raise SystemExit(f"Speech recognition failed: {error}") from error
        reference, hypothesis = normalise(recording.reference), normalise(heard.text)
        raw_errors = edit_distance(
            normalise(recording.reference, spelling=False), normalise(heard.text, spelling=False)
        )
        wanted = content_words(reference)
        row = {
            "voice": recording.voice,
            "case_id": recording.case_id,
            "reference": recording.reference,
            "transcript": heard.text,
            "reference_words": len(reference),
            "errors": edit_distance(reference, hypothesis),
            "raw_errors": raw_errors,
            "content_words": len(wanted),
            "content_found": len(wanted & set(hypothesis)),
            "audio_ms": audio.duration_ms,
            "asr_ms": heard.asr_ms,
            **labels,
        }
        if interpreter and case and "expected" in labels:
            key = (case.id, recording.reference)
            if key not in typed_cache:
                typed, _, _ = await interpreter.interpret(
                    case, DisclosureState(), [], recording.reference
                )
                typed_cache[key] = sorted(typed.asked)
            spoken, _, _ = await interpreter.interpret(case, DisclosureState(), [], heard.text)
            row |= {
                "selected_from_text": typed_cache[key],
                "selected_from_speech": sorted(spoken.asked),
            }
        rows.append(row)
        if row["errors"]:
            print(f"[{recording.voice}] {recording.reference!r}\n      heard {heard.text!r}")
    voices = sorted({r["voice"] for r in rows if r["voice"]})
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "recognizer": asr.id,
        "prompt": "vocabulary_prompt(character name)",
        "audio": "synthetic macOS voices" if voices else "manifest recordings",
        "summary": summarise(rows),
        "by_voice": {v: summarise([r for r in rows if r["voice"] == v]) for v in voices},
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--voices", default=",".join(VOICES))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--interpret", action="store_true", help="also run the local interpreter")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.manifest:
        data = yaml.load(args.manifest.read_text(), Loader=UniqueKeyLoader)
        recordings = [(Recording.model_validate(item), {}) for item in data["items"]]
    else:
        recordings = labelled_recordings(tuple(v for v in args.voices.split(",") if v))
    report = asyncio.run(evaluate(Settings(), recordings, args.interpret))
    print(
        json.dumps(
            {
                "recognizer": report["recognizer"],
                "summary": report["summary"],
                "by_voice": report["by_voice"],
            },
            indent=2,
        )
    )
    if args.out:
        out = args.out if args.out.is_absolute() else ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
