"""The Member 2 → Member 3 seam: a Transcript becomes reviewable actions.

Section 23.2 lists `intelligence/service.py` and Section 23.3 freezes
`ExtractionService.extract(transcript, reference_datetime) -> list[ActionCandidate]`.
The file did not exist, and the two halves did not meet:

* Member 2 produces a `Transcript` of `TranscriptSegment`s.
* Member 3's `Extractor.extract` takes one segment's **text** and returns an
  `intelligence.schemas.ExtractionResult` of pydantic candidates.
* The contract expects a whole `Transcript` in and
  `contracts.extraction.ActionCandidate` out — a different class with the same
  name.

Nothing could go from audio to actions. These tests cover the join, including
the rules it has to preserve: the LLM never sets a date (§1.1), the original
wording survives (§2.2), and uncertainty is shown rather than guessed (§2.1).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nexa.contracts.extraction import ActionCandidate as ContractCandidate
from nexa.contracts.extraction import ExtractionService as ExtractionServiceProtocol
from nexa.contracts.meetings import TranscriptSegment
from nexa.contracts.transcription import Transcript
from nexa.dates.reference_time import CAIRO_TZ
from nexa.intelligence.service import ExtractionService

# Thursday 24 September 2026, 12:00 Cairo.
REF = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)

ARABIC_ACTION = "أحمد، لازم تخلص الـ report بكرة الساعة 10 الصبح"
ENGLISH_ACTION = "John, please finish the documentation by Friday"
NO_ACTION = "إحنا محتاجين نفكر في موضوع الميزانية"
ALSO_NO_ACTION = "We are just brainstorming right now"


def transcript(*texts: str) -> Transcript:
    """A Transcript shaped the way Member 2's ASR produces one."""
    return Transcript(
        segments=tuple(
            TranscriptSegment(
                id=index + 1,
                meeting_id=1,
                segment_index=index,
                start_ms=index * 5000,
                end_ms=(index + 1) * 5000,
                raw_text=text,
            )
            for index, text in enumerate(texts)
        ),
        language_hint="ar",
        model_name="test",
        duration_ms=len(texts) * 5000,
    )


@pytest.fixture
def service() -> ExtractionService:
    return ExtractionService()


# ------------------------------------------------------------ the frozen shape
def test_service_satisfies_the_frozen_contract(service):
    """Section 23.3's signature, and the contract's own candidate type."""
    assert isinstance(service, ExtractionServiceProtocol)

    out = service.extract(transcript(ARABIC_ACTION), REF)
    assert out, "the fixture segment should yield one candidate"
    assert all(isinstance(item, ContractCandidate) for item in out)


def test_it_accepts_a_real_transcript_not_a_string(service):
    out = service.extract(transcript(ARABIC_ACTION, ENGLISH_ACTION), REF)
    assert len(out) == 2


def test_a_bare_segment_sequence_also_works(service):
    """The review screen sometimes has only the segments."""
    segments = transcript(ARABIC_ACTION).segments
    assert len(service.extract(segments, REF)) == 1


def test_plain_text_also_works(service):
    """Convenience for demos; one line per segment."""
    out = service.extract(f"{ARABIC_ACTION}\n{ENGLISH_ACTION}", REF)
    assert len(out) == 2


# ------------------------------------------------------------------- the chain
def test_dates_are_resolved_deterministically(service):
    """§1.1: the LLM proposes a phrase, the code disposes of the date."""
    candidate = service.extract(transcript(ARABIC_ACTION), REF)[0]
    assert candidate.raw_date_phrase == "بكرة"          # untouched, as spoken
    assert candidate.resolved_date is not None
    assert candidate.resolved_date.isoformat() == "2026-09-25"


def test_english_deadlines_resolve_forward(service):
    """"by Friday" on a Thursday is tomorrow, not six days ago."""
    candidate = service.extract(transcript(ENGLISH_ACTION), REF)[0]
    assert candidate.raw_date_phrase == "by Friday"
    assert candidate.resolved_date.isoformat() == "2026-09-25"


def test_the_original_wording_survives(service):
    """§2.2: the confirmed sentence reaches the review screen intact."""
    candidate = service.extract(transcript(ARABIC_ACTION), REF)[0]
    assert candidate.source_text == ARABIC_ACTION


def test_confirmed_text_is_preferred_over_raw_text(service):
    """The admin's correction on the review screen is what extraction reads."""
    segment = TranscriptSegment(
        id=1, segment_index=0,
        raw_text="احمد لازم تخلص الريبورت بكره",
        confirmed_text=ARABIC_ACTION,
    )
    out = service.extract(Transcript(segments=(segment,)), REF)
    assert out and out[0].owner_text == "أحمد"


def test_owner_stays_the_spoken_name(service):
    """Never an employee id — resolving the person is the review screen's job."""
    candidate = service.extract(transcript(ARABIC_ACTION), REF)[0]
    assert candidate.owner_text == "أحمد"


def test_confidence_is_scored(service):
    candidate = service.extract(transcript(ARABIC_ACTION), REF)[0]
    assert 0.0 <= candidate.confidence <= 1.0
    assert candidate.confidence > 0.0


# -------------------------------------------------------------- zero actions
@pytest.mark.parametrize("text", [NO_ACTION, ALSO_NO_ACTION])
def test_discussion_yields_no_candidates(service, text):
    """§2.1 and §39.2: precision matters more than completeness."""
    assert service.extract(transcript(text), REF) == []


def test_mixed_transcript_extracts_only_the_actions(service):
    out = service.extract(
        transcript(NO_ACTION, ARABIC_ACTION, ALSO_NO_ACTION, ENGLISH_ACTION), REF
    )
    assert len(out) == 2
    assert {item.owner_text for item in out} == {"أحمد", "John"}


def test_an_empty_transcript_is_safe(service):
    assert service.extract(transcript(), REF) == []
    assert service.extract(Transcript(), REF) == []


def test_blank_segments_are_skipped(service):
    assert service.extract(transcript("", "   ", ARABIC_ACTION), REF) != []


# ------------------------------------------------------------- robustness
def test_one_failing_segment_does_not_lose_the_meeting(service, monkeypatch):
    """A whole meeting's extraction must not be lost to one bad segment."""
    original = service.extractor.extract
    calls = {"n": 0}

    def flaky(text, segment_id, reference_datetime):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model hiccup")
        return original(text, segment_id, reference_datetime)

    monkeypatch.setattr(service.extractor, "extract", flaky)
    out = service.extract(transcript(ARABIC_ACTION, ENGLISH_ACTION), REF)
    assert len(out) == 1, "the second segment should still have been extracted"


def test_detailed_extraction_keeps_the_segment_pairing(service):
    """The review screen shows evidence next to each candidate (§2.2)."""
    detailed = service.extract_detailed(transcript(ARABIC_ACTION, NO_ACTION), REF)
    assert len(detailed) == 2
    first = detailed[0]
    assert first.segment.raw_text == ARABIC_ACTION
    assert first.segment.id == 1
    assert len(first.candidates) == 1
    # evidence_span offsets are relative to this segment, not the transcript.
    span = first.candidates[0].evidence_span
    assert span[0] >= 0 and span[1] >= span[0]
    assert detailed[1].candidates == []


def test_segment_ids_reach_the_extractor(service):
    detailed = service.extract_detailed(transcript(ARABIC_ACTION), REF)
    assert detailed[0].result.segment_id == "seg-1"


def test_duplicate_detection_is_optional(service):
    """`nexa.dedup` needs the embedding model from requirements/ai.txt."""
    assert service.duplicates is None
    assert service.extract(transcript(ARABIC_ACTION), REF)


def test_a_broken_duplicate_detector_does_not_break_extraction():
    class Exploding:
        def compare(self, candidate, existing):
            raise RuntimeError("no model installed")

    service = ExtractionService(duplicates=Exploding())
    assert len(service.extract(transcript(ARABIC_ACTION, ENGLISH_ACTION), REF)) == 2


def test_duplicates_are_flagged_for_review_never_merged():
    """§24.1 and §7 put the merge decision with the admin."""

    class AlwaysDuplicate:
        def compare(self, candidate, existing):
            if not existing:
                return []

            class Decision:
                is_duplicate = True
                recommended_action = "merge"

            return [Decision()]

    service = ExtractionService(duplicates=AlwaysDuplicate())
    detailed = service.extract_detailed(
        transcript(ARABIC_ACTION, ENGLISH_ACTION), REF
    )
    flagged = [c for e in detailed for c in e.candidates if c.needs_review]
    assert flagged, "the second candidate should have been flagged"
    # Both candidates still exist: nothing was merged away.
    assert sum(len(e.candidates) for e in detailed) == 2
