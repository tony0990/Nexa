"""Tunable constants for Member 3 intelligence.

LLM runtime paths belong in M2. M3 only freezes scoring thresholds.
"""

# Anything below this composite score is routed to review, regardless of
# other (non-conflicting) signals. v1 starting point — see CHANGELOG.md.
CONFIDENCE_REVIEW_THRESHOLD: float = 0.55
