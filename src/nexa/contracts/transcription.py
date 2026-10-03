"""Shared transcription contracts (implemented by Member 2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple, runtime_checkable

from .audio import RecordedAudio
from .meetings import TranscriptSegment


@dataclass(frozen=True)
class Transcript:
    segments: Tuple[TranscriptSegment, ...] = ()
    language_hint: Optional[str] = None
    model_name: Optional[str] = None
    duration_ms: int = 0  # length of the audio, not just the last segment's end

    @property
    def full_text(self) -> str:
        """Confirmed wording when present, otherwise the raw ASR wording."""
        return " ".join(
            (s.confirmed_text or s.raw_text).strip()
            for s in self.segments
            if (s.confirmed_text or s.raw_text)
        )


@runtime_checkable
class TranscriptionService(Protocol):
    def transcribe(self, audio_path: str) -> Transcript: ...

    def transcribe_chunks(self, audio: RecordedAudio) -> Transcript: ...
