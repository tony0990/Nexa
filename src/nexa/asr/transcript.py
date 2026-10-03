"""Helpers for building/merging Transcript objects."""
from __future__ import annotations

import re
from collections.abc import Iterable

from ..contracts.transcription import Transcript, TranscriptSegment

_ARABIC = re.compile("[؀-ۿݐ-ݿ]")
_LATIN = re.compile("[A-Za-z]")


def language_hint(text: str) -> str | None:
    """Rough script-based hint: 'ar', 'en', or 'mixed'. Informational only."""
    ar, en = len(_ARABIC.findall(text)), len(_LATIN.findall(text))
    total = ar + en
    if total == 0:
        return None
    if ar / total >= 0.85:
        return "ar"
    if en / total >= 0.85:
        return "en"
    return "mixed"


def build_transcript(
    raw_segments: Iterable[tuple[float, float, str]],
    model_name: str,
    duration_ms: int = 0,
) -> Transcript:
    """Build a Transcript from (start_seconds, end_seconds, text) tuples."""
    segments = []
    for i, (start, end, text) in enumerate(raw_segments):
        text = text.strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                segment_index=len(segments),
                start_ms=int(round(start * 1000)),
                end_ms=int(round(end * 1000)),
                raw_text=text,
                language_hint=language_hint(text),
            )
        )
    end_ms = segments[-1].end_ms if segments else 0
    return _transcript(segments, model_name, duration_ms or end_ms)


def merge_transcripts(parts: list[tuple[int, Transcript]]) -> Transcript:
    """Merge chunk transcripts. Each part is (chunk_start_offset_ms, transcript)."""
    segments: list[TranscriptSegment] = []
    total = 0
    model = ""
    for offset_ms, transcript in parts:
        model = model or transcript.model_name
        for seg in transcript.segments:
            segments.append(
                TranscriptSegment(
                    segment_index=len(segments),
                    start_ms=seg.start_ms + offset_ms,
                    end_ms=seg.end_ms + offset_ms,
                    raw_text=seg.raw_text,
                    confirmed_text=seg.confirmed_text,
                    language_hint=seg.language_hint,
                )
            )
        total = max(total, offset_ms + transcript.duration_ms)
    return _transcript(segments, model, total)


def _transcript(segments: list[TranscriptSegment], model_name: str, duration_ms: int) -> Transcript:
    text = " ".join(s.raw_text for s in segments)
    return Transcript(
        segments=tuple(segments),
        language_hint=language_hint(text),
        model_name=model_name,
        duration_ms=duration_ms,
    )
