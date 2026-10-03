"""Deterministic composite confidence scoring.

The LLM never owns this number. Optional self-reported model confidence is
advisory only and cannot bypass the weighted formula.
"""

from __future__ import annotations

from nexa.intelligence.config import CONFIDENCE_REVIEW_THRESHOLD
from nexa.intelligence.schemas import ActionCandidate, ResolvedTemporalValue

from nexa.dates.ambiguity import classify_ambiguity


def score_confidence(
    candidate: ActionCandidate,
    temporal: ResolvedTemporalValue,
    llm_confidence: float | None = None,
) -> float:
    """Explainable v1 composite score. ``llm_confidence`` is ignored by design."""
    del llm_confidence  # advisory only — never used in the score

    score = 0.0
    if temporal.resolution_method == "deterministic_rule":
        score += 0.40
    elif temporal.resolution_method == "dateparser_fallback":
        score += 0.15
    score += 0.20 if candidate.owner_text else 0.0
    score += 0.15 if candidate.raw_time_phrase else 0.0
    score += 0.15 if len(candidate.task.strip()) >= 8 else 0.05
    score += 0.10 if not temporal.is_ambiguous else 0.0
    return min(score, 1.0)


def finalize_candidate(
    candidate: ActionCandidate,
    temporal: ResolvedTemporalValue,
    llm_confidence: float | None = None,
) -> ActionCandidate:
    """Wire scoring + ambiguity onto a candidate.

    ``resolved_date`` is copied only from ``temporal.resolved_datetime``.
    Unresolved or range-ambiguous values are never collapsed into a guess.
    """
    confidence = score_confidence(candidate, temporal, llm_confidence=llm_confidence)
    resolved_date = None if temporal.is_ambiguous and temporal.resolved_datetime is None else (
        None if temporal.resolution_method == "unresolved" else temporal.resolved_datetime
    )
    if temporal.resolution_method == "unresolved":
        resolved_date = None
    elif temporal.ambiguity_reason == "fuzzy_range":
        # Range resolutions must not silently collapse to a single point.
        resolved_date = None
    else:
        resolved_date = temporal.resolved_datetime

    scored = candidate.model_copy(
        update={
            "confidence": confidence,
            "resolved_date": resolved_date,
        }
    )
    needs_review, review_reason = classify_ambiguity(temporal, scored)
    return scored.model_copy(
        update={
            "needs_review": needs_review,
            "review_reason": review_reason,
        }
    )


# Re-export so callers can read the frozen threshold next to the scorer.
__all__ = [
    "CONFIDENCE_REVIEW_THRESHOLD",
    "finalize_candidate",
    "score_confidence",
]
