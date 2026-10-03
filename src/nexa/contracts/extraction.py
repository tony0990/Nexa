"""Shared extraction contracts (implemented by Member 3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional, Protocol, Sequence, runtime_checkable

from .transcription import Transcript


@dataclass(frozen=True)
class ActionCandidate:
    """AI output before human approval. Never persisted as final truth."""

    task: str = ""
    owner_text: Optional[str] = None
    raw_date_phrase: Optional[str] = None
    resolved_date: Optional[date] = None
    resolved_time: Optional[time] = None
    source_text: str = ""
    confidence: float = 0.0
    duplicate_of: Optional[int] = None


@runtime_checkable
class ExtractionService(Protocol):
    def extract(
        self, transcript: Transcript, reference_datetime: datetime
    ) -> Sequence[ActionCandidate]: ...
