"""Shared transcription contracts (implemented by Member 2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from .meetings import TranscriptSegment


@dataclass(frozen=True)
class Transcript:
    segments: Tuple[TranscriptSegment, ...] = ()
    language_hint: Optional[str] = None
    model_name: Optional[str] = None

    @property
    def full_text(self) -> str:
        """Confirmed wording when present, otherwise the raw ASR wording."""
        return " ".join(
            (s.confirmed_text or s.raw_text).strip()
            for s in self.segments
            if (s.confirmed_text or s.raw_text)
        )


class TranscriptionService(Protocol):
    def transcribe(self, audio_path: str) -> Transcript: ...
