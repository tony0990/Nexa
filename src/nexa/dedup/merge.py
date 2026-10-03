"""Merging two duplicate candidates (§7, §23.3).

Section 23.3 freezes `DuplicateService.merge(left, right) -> ActionCandidate`.
It was never implemented — only `MergeAdvisor.recommend`, which returns strings
for the UI — so the Review screen's `[ Merge ]` button had nothing to call.

The rule that shapes every decision here is the last line of Section 7:

    Never silently delete uncertain information.

So merging is **additive**. The same deadline stated twice in a meeting —

    التقرير يتسلم الخميس.
    ...
    متنسوش التقرير يوم الخميس.

— becomes one candidate that keeps *both* original sentences as evidence, takes
the more specific value for each field rather than the first one seen, and stays
flagged for review if either input was. Nothing is discarded because it happened
to arrive second.

Merging is never automatic from here: Section 7 gives the admin
`[ Keep Both ]` / `[ Merge ]`, and `DuplicateService.compare` only recommends.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from nexa.intelligence.schemas import ActionCandidate

#: Joins the evidence sentences of merged candidates.
EVIDENCE_SEPARATOR = "\n"

# Ordered by how much review attention each reason deserves, most first. When
# two candidates disagree, the more serious reason survives the merge.
_REVIEW_PRIORITY = (
    "conflicting_signals",
    "ambiguous_date",
    "no_owner",
    "no_time",
    "fuzzy_range",
    "low_confidence",
)


def merge(left: ActionCandidate, right: ActionCandidate) -> ActionCandidate:
    """Combine two candidates the admin has confirmed are the same commitment.

    Field by field:

    * **task** — the longer text. "تخلص الـ report" and "تخلص الـ report
      النهائي" are the same task described with different detail; keeping the
      longer one loses nothing.
    * **owner / dates / times** — the first value that is actually present. A
      candidate that named an owner is strictly more informative than one that
      did not, regardless of which was extracted first.
    * **resolved_date** — only ever copied from an input, never recomputed and
      never guessed. Keeping §1.1 true: the deterministic layer owns this field.
    * **confidence** — the *lower* of the two. Two mentions do not make Nexa
      more certain about what was said, and quietly raising confidence here
      could push an item past a review threshold it should not clear.
    * **needs_review** — true if either was. The merge itself is not evidence
      that the ambiguity was resolved.
    * **evidence_text** — both sentences, joined. This is the whole point.
    * **extraction_id** — the left one's, so the merged row keeps a stable
      identity the audit trail already refers to.
    """
    task = _longer(left.task, right.task)
    merged_evidence = _merge_evidence(left.evidence_text, right.evidence_text)
    needs_review = bool(left.needs_review or right.needs_review)

    return ActionCandidate(
        task=task,
        owner_text=_first_present(left.owner_text, right.owner_text),
        raw_date_phrase=_first_present(left.raw_date_phrase, right.raw_date_phrase),
        raw_time_phrase=_first_present(left.raw_time_phrase, right.raw_time_phrase),
        resolved_date=_first_present(left.resolved_date, right.resolved_date),
        confidence=min(float(left.confidence or 0.0), float(right.confidence or 0.0)),
        needs_review=needs_review,
        review_reason=_worst_reason(left.review_reason, right.review_reason)
        if needs_review
        else None,
        # The span belonged to one segment and the merged evidence spans two, so
        # it can no longer address the text. Zeroed rather than left pointing at
        # the wrong characters.
        evidence_text=merged_evidence,
        evidence_span=(0, len(merged_evidence)),
        extraction_id=left.extraction_id,
    )


def merge_all(candidates: Sequence[ActionCandidate]) -> Optional[ActionCandidate]:
    """Fold several confirmed duplicates into one, left to right."""
    if not candidates:
        return None
    merged = candidates[0]
    for candidate in candidates[1:]:
        merged = merge(merged, candidate)
    return merged


def _longer(left: Optional[str], right: Optional[str]) -> str:
    left_text, right_text = (left or "").strip(), (right or "").strip()
    return left_text if len(left_text) >= len(right_text) else right_text


def _first_present(left, right):
    """The left value unless it is empty, in which case the right one."""
    if left is None or (isinstance(left, str) and not left.strip()):
        return right
    return left


def _merge_evidence(left: Optional[str], right: Optional[str]) -> str:
    """Both sentences, in order, without repeating an identical one."""
    seen: List[str] = []
    for text in (left, right):
        cleaned = (text or "").strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return EVIDENCE_SEPARATOR.join(seen)


def _worst_reason(left: Optional[str], right: Optional[str]) -> Optional[str]:
    """The reason that deserves the most review attention."""
    for reason in _REVIEW_PRIORITY:
        if reason in (left, right):
            return reason
    return left or right
