"""Shared audio capture contracts (implemented by Member 2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class RecordedAudio:
    path: str = ""
    duration_ms: int = 0
    source: str = "MICROPHONE"
    sample_rate: Optional[int] = None


class AudioRecordingService(Protocol):
    def start(self, source: str) -> str: ...

    def stop(self) -> RecordedAudio: ...
