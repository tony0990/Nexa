"""Ambiguity classification — explicit review flags, never silent guesses.

``classify_ambiguity`` never returns ``(False, <non-null reason>)``.
"""

from __future__ import annotations

from nexa.intelligence.config import CONFIDENCE_REVIEW_THRESHOLD
from nexa.intelligence.schemas import ActionCandidate, ResolvedTemporalValue

# Temporal problems outrank missing owner; low confidence is the last gate.
_REVIEW_PRIORITY = (
    "conflicting_signals",
    "ambiguous_date",
    "fuzzy_range",
    "no_owner",
    "low_confidence",
)


def classify_ambiguity(
    resolved: ResolvedTemporalValue,
    candidate: ActionCandidate,
) -> tuple[bool, str | None]:
    """Returns (needs_review, review_reason)."""
    reasons: list[str] = []

    if _is_conflicting(resolved, candidate):
        reasons.append("conflicting_signals")

    if _is_unresolved_date(resolved, candidate):
        reasons.append("ambiguous_date")
    elif _is_fuzzy_range(resolved):
        reasons.append("fuzzy_range")

    if not candidate.owner_text:
        reasons.append("no_owner")

    # Date-only (no raw_time_phrase) is a normal deadline — do not flag no_time.

    if candidate.confidence < CONFIDENCE_REVIEW_THRESHOLD:
        reasons.append("low_confidence")

    for reason in _REVIEW_PRIORITY:
        if reason in reasons:
            return True, reason

    return False, None


def _is_conflicting(resolved: ResolvedTemporalValue, candidate: ActionCandidate) -> bool:
    if resolved.ambiguity_reason == "conflicting_signals":
        return True
    if resolved.matched_rule == "conflicting_signals":
        return True
    date_phrase = (candidate.raw_date_phrase or "").strip()
    # Past + future markers in the same spoken date phrase (M1 may also set the reason).
    has_tomorrow = "بكرة" in date_phrase or "tomorrow" in date_phrase.lower()
    has_yesterday = "امبارح" in date_phrase or "yesterday" in date_phrase.lower()
    return has_tomorrow and has_yesterday


def _is_unresolved_date(resolved: ResolvedTemporalValue, candidate: ActionCandidate) -> bool:
    if resolved.resolution_method == "unresolved":
        return True
    if resolved.ambiguity_reason == "ambiguous_date":
        return True
    # A spoken date that produced no datetime and is not an explicit range.
    if (
        candidate.raw_date_phrase
        and resolved.resolved_datetime is None
        and not _is_fuzzy_range(resolved)
    ):
        return True
    return False


def _is_fuzzy_range(resolved: ResolvedTemporalValue) -> bool:
    if resolved.ambiguity_reason == "fuzzy_range":
        return True
    matched = (resolved.matched_rule or "").lower()
    if "range" in matched or "fuzzy" in matched:
        return True
    # Deterministic match that stayed ambiguous without collapsing to a point.
    if (
        resolved.is_ambiguous
        and resolved.resolution_method == "deterministic_rule"
        and resolved.resolved_datetime is None
        and resolved.ambiguity_reason != "conflicting_signals"
    ):
        return True
    return False
