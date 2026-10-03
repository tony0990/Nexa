from datetime import datetime
from typing import Optional
from nexa.dates.reference_time import get_reference_datetime
from nexa.dates.code_switch import split_code_switched_phrase
from nexa.dates.egyptian_rules import resolve_egyptian_phrase
from nexa.dates.english_rules import resolve_english_phrase
from nexa.dates.validator import validate_resolved_date
from nexa.intelligence.schemas import ResolvedTemporalValue

def resolve_temporal_value(phrase: str, ref_dt: datetime) -> ResolvedTemporalValue:
    """
    Orchestrates the rule chain:
    1. Code-switch splitting
    2. Egyptian AR pattern table
    3. English dateparser fallback
    4. Mark unresolved
    5. Run validator
    """
    # 1. Code-switch (simple version: if it mixes, we resolve parts)
    # For now, we try the whole phrase as AR then EN

    # Try Egyptian rules first
    resolved_dt, is_ambiguous = resolve_egyptian_phrase(phrase, ref_dt)
    method = "deterministic_rule"
    matched_rule = "egyptian_table"

    if resolved_dt is None:
        # Try English rules
        resolved_dt, is_ambiguous = resolve_english_phrase(phrase, ref_dt)
        method = "dateparser_fallback"
        matched_rule = "english_dateparser"

    if resolved_dt is None:
        # Mark unresolved
        return ResolvedTemporalValue(
            resolved_datetime=None,
            is_ambiguous=True,
            ambiguity_reason="unresolved",
            resolution_method="unresolved",
            matched_rule=None
        )

    # Run validator
    is_valid, error = validate_resolved_date(resolved_dt, ref_dt)
    if not is_valid:
        # Even if it resolved, if it's logically invalid (e.g. past),
        # we mark it unresolved or ambiguous.
        return ResolvedTemporalValue(
            resolved_datetime=None,
            is_ambiguous=True,
            ambiguity_reason=error,
            resolution_method="unresolved",
            matched_rule=None
        )

    return ResolvedTemporalValue(
        resolved_datetime=resolved_dt,
        is_ambiguous=is_ambiguous,
        ambiguity_reason=None if not is_ambiguous else "fuzzy_range",
        resolution_method=method,
        matched_rule=matched_rule
    )
