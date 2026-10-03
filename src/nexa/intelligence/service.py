"""`ExtractionService` — the public face of the intelligence layer (§23.2, §23.3).

Section 23.2 lists this file and Section 23.3 freezes its interface:

    ExtractionService.extract(transcript, reference_datetime) -> list[ActionCandidate]

It was missing, and that left the Member 2 → Member 3 seam unconnected. The two
halves did not meet in the middle:

* Member 2 produces a `Transcript` of `TranscriptSegment`s.
* Member 3's `Extractor.extract` takes **one segment's text** as a string and
  returns an `intelligence.schemas.ExtractionResult` of pydantic
  `ActionCandidate`s.
* The frozen contract expects a whole `Transcript` in and a sequence of
  `contracts.extraction.ActionCandidate` — a *different* class with the same
  name — out.

So nothing could go from audio to reviewable actions. This module is the join,
and it belongs here because the per-segment granularity is correct and worth
keeping: the LLM sees one segment at a time, and `evidence_span` offsets are
only meaningful relative to the segment they were extracted from.

What it does, in order, per segment:

1. extract candidates (Member 3's `Extractor`)
2. normalize each raw date phrase deterministically (`nexa.dates`)
3. score confidence and set review flags (`confidence.finalize_candidate`)
4. detect duplicates across the whole meeting (`nexa.dedup`)
5. map to the contract's `ActionCandidate`

Step 2 is what keeps the "code disposes" rule (§1.1) true end to end: the LLM
never sets `resolved_date`, and this service is the only thing that does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence

from ..contracts.extraction import ActionCandidate as ContractCandidate
from ..contracts.meetings import TranscriptSegment
from ..contracts.transcription import Transcript
from ..dates.normalizer import normalize_date_phrase
from .confidence import finalize_candidate
from .extractor import Extractor
from .llm_runtime import LLMRuntime
from .schemas import ActionCandidate, ExtractionResult

log = logging.getLogger("nexa.intelligence.service")


@dataclass
class SegmentExtraction:
    """One segment's candidates, kept with the segment that produced them.

    The review screen needs this pairing: it shows the original confirmed
    sentence next to what Nexa read from it (§2.2), and `evidence_span` offsets
    are relative to this segment, not to the whole transcript.
    """

    segment: TranscriptSegment
    result: ExtractionResult
    candidates: List[ActionCandidate] = field(default_factory=list)


class ExtractionService:
    """Transcript in, reviewable action candidates out.

    `duplicates` is optional so the service runs without the embedding model
    installed — `nexa.dedup` pulls in sentence-transformers, which lives in
    `requirements/ai.txt`. Without it, extraction still works and nothing is
    flagged as a duplicate.
    """

    def __init__(
        self,
        extractor: Optional[Extractor] = None,
        runtime: Optional[LLMRuntime] = None,
        duplicates: object = None,
        *,
        detect_duplicates: bool = True,
    ):
        if extractor is None:
            runtime = runtime or LLMRuntime(model_path="mock")
            if not runtime.is_ready():
                runtime.start()
            extractor = Extractor(runtime)
        self.extractor = extractor
        self.duplicates = duplicates
        self.detect_duplicates = detect_duplicates

    # ------------------------------------------------------------------ public
    def extract(
        self, transcript: Transcript, reference_datetime: datetime
    ) -> List[ContractCandidate]:
        """The frozen Section 23.3 interface."""
        return [
            self.to_contract(candidate, extraction.segment)
            for extraction in self.extract_detailed(transcript, reference_datetime)
            for candidate in extraction.candidates
        ]

    def extract_detailed(
        self, transcript: Transcript, reference_datetime: datetime
    ) -> List[SegmentExtraction]:
        """Same work, but keeping the segment pairing the review screen needs."""
        extractions: List[SegmentExtraction] = []

        for index, segment in enumerate(_segments_of(transcript)):
            text = _text_of(segment)
            if not text.strip():
                continue
            segment_id = _segment_id(segment, index)
            try:
                result = self.extractor.extract(text, segment_id, reference_datetime)
            except Exception:
                # One malformed segment must not lose a whole meeting's
                # extraction. The admin can still review the rest and add the
                # missing item by hand (§2.1 allows manual entry).
                log.exception("extraction failed for segment %s", segment_id)
                continue

            resolved = [
                self._resolve(candidate, reference_datetime) for candidate in result.items
            ]
            extractions.append(
                SegmentExtraction(segment=segment, result=result, candidates=resolved)
            )

        if self.detect_duplicates:
            self._flag_duplicates(extractions)
        return extractions

    # ----------------------------------------------------------------- stages
    def _resolve(
        self, candidate: ActionCandidate, reference_datetime: datetime
    ) -> ActionCandidate:
        """Normalize the date deterministically, then score the candidate.

        `raw_date_phrase` is left exactly as spoken (§2.2); only the computed
        `resolved_date` is written, and only from the deterministic layer.
        """
        temporal = normalize_date_phrase(candidate.raw_date_phrase, reference_datetime)
        return finalize_candidate(candidate, temporal, llm_confidence=candidate.confidence)

    def _flag_duplicates(self, extractions: Sequence[SegmentExtraction]) -> None:
        """Mark near-duplicate candidates across the whole meeting.

        Duplicates are *flagged*, never merged here: §7 and §24.1 both put the
        merge decision with the admin, and this service runs before review.
        """
        if self.duplicates is None:
            return
        seen: List[ActionCandidate] = []
        for extraction in extractions:
            for candidate in extraction.candidates:
                try:
                    decisions = self.duplicates.compare(candidate, seen)
                except Exception:
                    log.exception("duplicate detection failed; continuing")
                    seen.append(candidate)
                    continue
                for decision in decisions or ():
                    if decision.is_duplicate and decision.recommended_action != "keep_both":
                        candidate.needs_review = True
                        candidate.review_reason = (
                            candidate.review_reason or "conflicting_signals"
                        )
                seen.append(candidate)

    # ----------------------------------------------------------------- mapping
    @staticmethod
    def to_contract(
        candidate: ActionCandidate, segment: Optional[TranscriptSegment] = None
    ) -> ContractCandidate:
        """Map Member 3's pydantic candidate onto the shared dataclass.

        Two `ActionCandidate` classes exist — this one and
        `contracts.extraction.ActionCandidate` — and they are not
        interchangeable. The contract's is what leaves this package, so other
        members never import `intelligence.schemas`.

        `source_text` carries the evidence forward: the contract has no
        `evidence_text` field, and dropping it would break the §2.2 guarantee
        that the original wording survives to the review screen.
        """
        resolved = candidate.resolved_date
        return ContractCandidate(
            task=candidate.task or "",
            owner_text=candidate.owner_text,
            raw_date_phrase=candidate.raw_date_phrase,
            resolved_date=resolved.date() if resolved is not None else None,
            resolved_time=resolved.time() if resolved is not None else None,
            source_text=candidate.evidence_text
            or (segment.raw_text if segment is not None else ""),
            confidence=float(candidate.confidence or 0.0),
        )


def _segments_of(transcript: Transcript) -> Sequence[TranscriptSegment]:
    """Accept a `Transcript`, a bare sequence of segments, or plain text.

    Member 2 hands over a `Transcript`. The review screen and the fixtures
    sometimes have only the segments, and a demo may have only a string; being
    lenient here costs three lines and removes an adapter from every caller.
    """
    if isinstance(transcript, Transcript):
        return transcript.segments
    if isinstance(transcript, str):
        return tuple(
            TranscriptSegment(segment_index=i, raw_text=line)
            for i, line in enumerate(transcript.splitlines())
            if line.strip()
        )
    return tuple(transcript or ())


def _text_of(segment: TranscriptSegment) -> str:
    """The confirmed text when the admin has edited it, else the raw text.

    `confirmed_text` is what the human approved on the review screen, so it is
    what extraction should read. The raw text is never overwritten (§2.2).
    """
    return (getattr(segment, "confirmed_text", None) or segment.raw_text or "")


def _segment_id(segment: TranscriptSegment, index: int) -> str:
    if getattr(segment, "id", None) is not None:
        return f"seg-{segment.id}"
    return f"seg-{getattr(segment, 'segment_index', index)}"
