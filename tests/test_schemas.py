"""Schema contract validation — M0 smoke tests."""

from datetime import datetime, timezone

from intelligence.schemas import (
    ActionCandidate,
    DuplicateDecision,
    ExtractionResult,
    ResolvedTemporalValue,
)


def test_action_candidate_round_trip():
    candidate = ActionCandidate(
        task="Finish database integration",
        owner_text="أحمد",
        raw_date_phrase="before Monday",
        raw_time_phrase=None,
        resolved_date=None,
        confidence=0.85,
        needs_review=False,
        evidence_text="أحمد يخلص الـdatabase before Monday",
        evidence_span=(0, 35),
        extraction_id="00000000-0000-4000-8000-000000000001",
    )
    assert candidate.owner_text == "أحمد"
    assert candidate.resolved_date is None


def test_extraction_result_empty_items():
    result = ExtractionResult(
        items=[],
        segment_id="zero_action_001",
        model_version="m0-fixture",
        extracted_at=datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc),
    )
    assert result.items == []


def test_resolved_temporal_value_unresolved():
    resolved = ResolvedTemporalValue(
        resolved_datetime=None,
        is_ambiguous=True,
        ambiguity_reason="no_matching_rule",
        resolution_method="unresolved",
        matched_rule=None,
    )
    assert resolved.resolution_method == "unresolved"


def test_duplicate_decision_schema():
    decision = DuplicateDecision(
        is_duplicate=True,
        similarity_score=0.9,
        reason="combined",
        recommended_action="merge",
        compared_ids=("id-a", "id-b"),
    )
    assert decision.recommended_action == "merge"
