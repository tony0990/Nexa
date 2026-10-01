from datetime import datetime
from typing import Optional
from dates.reference_time import get_reference_datetime
from dates.resolver import resolve_temporal_value
from intelligence.schemas import ResolvedTemporalValue

def normalize_date_phrase(phrase: str, ref_dt: Optional[datetime] = None) -> ResolvedTemporalValue:
    """
    Entry point: raw phrase -> ResolvedTemporalValue.
    Coordinates code-switching, Egyptian rules, English rules, and resolution.
    """
    if not phrase:
        return ResolvedTemporalValue(
            resolved_datetime=None,
            is_ambiguous=True,
            ambiguity_reason="no_phrase_provided",
            resolution_method="unresolved",
            matched_rule=None
        )

    if ref_dt is None:
        ref_dt = get_reference_datetime()

    # The resolver handles the chain (code-switch -> AR -> EN -> fallback)
    return resolve_temporal_value(phrase, ref_dt)
