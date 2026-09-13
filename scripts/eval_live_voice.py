"""Bounded synthetic provider evaluation. Default invocation makes no paid requests."""

import argparse
import asyncio
import io
import json
import os
import re
import struct
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from lunaris_live.voice.protocols.provider import IVoiceProvider
from lunaris_live.voice.providers.elevenlabs import ElevenLabsVoiceProvider
from lunaris_live.voice.read_audio import read_audio
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.metering.cost_scope import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostSubjectType
from structlog.contextvars import bound_contextvars

_TEXTS = (
    "HIPAA protects patient privacy. An EHR is an electronic health record.",
    "When voltage stays constant, doubling resistance halves the electric current.",
)
_MAX_PCM_BYTES = 24000 * 2 * 30
_CLEANUP_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class _Run:
    provider: IVoiceProvider
    output: Path
    scope: CostScope
    report: dict[str, Any]


async def run_evaluation(provider: IVoiceProvider, output: Path) -> None:
    """At most two syntheses and one transcription; fail immediately without retry."""
    await asyncio.to_thread(_claim_output, output)
    run_id = uuid4().hex
    scope = CostScope(
        run_id=run_id,
        subject_type=CostSubjectType.LIVE_SESSION,
        subject_id="synthetic-voice-evaluation",
        price_book=PriceBook.current(),
    )
    run = _Run(provider, output, scope, _manifest(scope))
    await asyncio.to_thread(_write_report, run)
    with cost_scope(scope), bound_contextvars(run_id=run_id, request_id=run_id):
        try:
            first_pcm = await _speech(run, _TEXTS[0], 1)
            await _speech(run, _TEXTS[1], 2)
            await _transcribe(run, first_pcm)
            run.report["status"] = "completed"
        except BaseException as exc:
            run.report.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            await asyncio.to_thread(_write_report, run)


def _claim_output(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if (output / "report.json").exists():
        raise FileExistsError("Choose a new output directory; previous attempts cannot be retried.")
    # The exclusive marker survives crashes before a report is written. Never remove/reclaim it.
    with (output / "attempt.claim").open("x") as claim:
        claim.write("This evaluation output is claimed; do not retry paid work here.\n")


def _manifest(scope: CostScope) -> dict[str, Any]:
    return {
        "run_id": scope.run_id,
        "status": "running",
        "synthetic_input_only": True,
        "call_cap": {"tts": 2, "stt": 1},
        "calls_started": {"tts": 0, "stt": 0},
        "speech": [],
        "billed_cost_usd": None,
        "cost_note": "Usage is measured. Billed account cost is unknown, not zero.",
        "intelligibility": {"human_rating": None, "assessment": "requires_listening"},
        "price_book_version": scope.price_book.version,
    }


async def _speech(run: _Run, text: str, number: int) -> bytes:
    run.report["calls_started"]["tts"] += 1
    await asyncio.to_thread(_write_report, run)
    started = perf_counter()
    first_ms = None
    pcm = bytearray()
    stream = run.provider.speak(text, run_id=run.scope.run_id)
    try:
        async with asyncio.timeout(30):
            async for chunk in stream:
                if not chunk:
                    continue
                if first_ms is None:
                    first_ms = (perf_counter() - started) * 1000
                if len(pcm) + len(chunk) > _MAX_PCM_BYTES:
                    raise ValueError("Speech exceeds the fixed evaluation duration cap")
                pcm.extend(chunk)
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            async with asyncio.timeout(_CLEANUP_TIMEOUT_S):
                await close()
    if not pcm or len(pcm) % 2:
        raise ValueError("Speech did not contain complete PCM samples")
    wav_name = f"speech-{number}.wav"
    await asyncio.to_thread((run.output / wav_name).write_bytes, _wav(bytes(pcm), 24000))
    run.report["speech"].append(
        {
            "canonical_text": text,
            "audio_file": wav_name,
            "first_pcm_ms": first_ms,
            "total_ms": (perf_counter() - started) * 1000,
            "audio_seconds": len(pcm) / 48000,
            "voice_id": "JBFqnCBsd6RMkjVDRZzb",
            "voice_name": "George",
            "sample_rate": 24000,
        }
    )
    await asyncio.to_thread(_write_report, run)
    return bytes(pcm)


async def _transcribe(run: _Run, pcm: bytes) -> None:
    # Downsample 24kHz PCM to the same mono 16kHz WAV accepted from browsers.
    samples = [sample[0] for sample in struct.iter_unpack("<h", pcm)]
    converted = bytearray()
    for index in range(len(samples) * 2 // 3):
        start = index * 3 // 2
        left, right = samples[start], samples[min(start + 1, len(samples) - 1)]
        sample = round((left + 2 * right) / 3 if index % 2 else (2 * left + right) / 3)
        converted.extend(struct.pack("<h", sample))
    audio = read_audio(_wav(bytes(converted), 16000))
    await asyncio.to_thread((run.output / "transcription-input.wav").write_bytes, audio.data)
    run.report["calls_started"]["stt"] += 1
    await asyncio.to_thread(_write_report, run)
    started = perf_counter()
    async with asyncio.timeout(30):
        result = await run.provider.transcribe(audio, run_id=run.scope.run_id)
    run.report["transcription"] = {
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "latency_ms": (perf_counter() - started) * 1000,
        "audio_seconds": audio.duration_s,
    }
    run.report["intelligibility"].update(
        word_error_rate=_word_error_rate(_TEXTS[0], result.text),
        method="Word edit distance on synthetic loopback; this is not a human listening rating.",
    )


def _word_error_rate(expected: str, actual: str) -> float:
    reference, hypothesis = re.findall(r"\w+", expected.lower()), re.findall(r"\w+", actual.lower())
    previous = list(range(len(hypothesis) + 1))
    for row, word in enumerate(reference, 1):
        current = [row]
        for column, candidate in enumerate(hypothesis, 1):
            current.append(
                min(
                    previous[column] + 1,
                    current[-1] + 1,
                    previous[column - 1] + (word != candidate),
                )
            )
        previous = current
    return previous[-1] / len(reference)


def _wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(pcm)
    return buffer.getvalue()


def _write_report(run: _Run) -> None:
    run.report["metered_usage"] = [asdict(entry) for entry in run.scope.entries]
    path = run.output / "report.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(run.report, indent=2) + "\n")
    temporary.replace(path)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-paid", action="store_true", help="Allow at most 2 TTS + 1 STT calls"
    )
    parser.add_argument("--output", type=Path, default=Path(".eval/live-voice") / uuid4().hex)
    args = parser.parse_args()
    if not args.allow_paid:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "plan.json").write_text(json.dumps(_plan(), indent=2) + "\n")
        return 0
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        parser.error("ELEVENLABS_API_KEY is required; no provider call was made.")
    with run_credentials({"ELEVENLABS_API_KEY": key}):
        try:
            asyncio.run(
                run_evaluation(
                    ElevenLabsVoiceProvider(timeout_s=25, max_audio_bytes=_MAX_PCM_BYTES),
                    args.output,
                )
            )
        except Exception:
            return 1
    return 0


def _plan() -> dict[str, Any]:
    return {
        "status": "not_run",
        "texts": _TEXTS,
        "call_cap": {"tts": 2, "stt": 1},
        "maximum_audio_seconds_per_tts": 30,
        "provider_timeout_seconds": 25,
        "stream_cleanup_timeout_seconds": _CLEANUP_TIMEOUT_S,
        "instruction": "Set ELEVENLABS_API_KEY securely and rerun with --allow-paid.",
    }


if __name__ == "__main__":
    raise SystemExit(_main())
