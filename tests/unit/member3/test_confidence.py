import pytest
from nexa.intelligence.schemas import ActionCandidate, ResolvedTemporalValue
from nexa.intelligence.confidence import score_confidence

def test_confidence_weights():
    # Case 1: High confidence deterministic
    candidate_high = ActionCandidate(
        task="Finish the monthly report",
        owner_text="Ahmed",
        raw_date_phrase="Tomorrow",
        raw_time_phrase="10am",
        resolved_date=None,
        confidence=0.0, # will be overwritten by scorer
        needs_review=False,
        evidence_text="...",
        evidence_span=(0, 10),
        extraction_id="1"
    )
    temporal_high = ResolvedTemporalValue(
        resolved_datetime=None, # simplified
        is_ambiguous=False,
        resolution_method="deterministic_rule",
        matched_rule="egyptian_table"
    )

    score = score_confidence(candidate_high, temporal_high)
    # 0.40 (det) + 0.20 (owner) + 0.15 (time) + 0.15 (task len) + 0.10 (not ambig) = 1.0
    assert score == 1.0

def test_confidence_low_weights():
    # Case 2: Low confidence fallback
    candidate_low = ActionCandidate(
        task="Do it", # short task
        owner_text=None,
        raw_date_phrase="Sometime",
        raw_time_phrase=None,
        resolved_date=None,
        confidence=0.0,
        needs_review=True,
        evidence_text="...",
        evidence_span=(0, 10),
        extraction_id="2"
    )
    temporal_low = ResolvedTemporalValue(
        resolved_datetime=None,
        is_ambiguous=True,
        resolution_method="unresolved",
        matched_rule=None
    )

    score = score_confidence(candidate_low, temporal_low)
    # 0.0 (unres) + 0.0 (no owner) + 0.0 (no time) + 0.05 (short task) + 0.0 (ambig) = 0.05
    assert score == 0.05
