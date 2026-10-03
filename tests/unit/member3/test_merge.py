"""Merging confirmed duplicates (§7, §23.3).

Section 23.3 freezes `DuplicateService.merge(left, right) -> ActionCandidate`
and it had never been implemented, so the Review screen's `[ Merge ]` button had
nothing to call.

Section 7's closing line is the specification for all of this:

    Never silently delete uncertain information.

Every test below is a way of not deleting something.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nexa.dedup import DuplicateService, merge, merge_all
from nexa.dedup.merge import EVIDENCE_SEPARATOR
from nexa.intelligence.schemas import ActionCandidate

# The Section 7 example: one deadline stated twice in the same meeting.
FIRST = ActionCandidate(
    task="تسليم التقرير",
    owner_text=None,
    raw_date_phrase="الخميس",
    confidence=0.8,
    needs_review=True,
    review_reason="no_owner",
    evidence_text="التقرير يتسلم الخميس.",
    evidence_span=(0, 21),
    extraction_id="u1",
)
SECOND = ActionCandidate(
    task="تسليم التقرير النهائي",
    owner_text="أحمد",
    raw_date_phrase="يوم الخميس",
    confidence=0.9,
    needs_review=False,
    evidence_text="متنسوش التقرير يوم الخميس.",
    evidence_span=(0, 26),
    extraction_id="u2",
)


def test_both_original_sentences_survive():
    """The whole point of the merge."""
    merged = merge(FIRST, SECOND)
    assert FIRST.evidence_text in merged.evidence_text
    assert SECOND.evidence_text in merged.evidence_text
    assert merged.evidence_text.count(EVIDENCE_SEPARATOR) == 1


def test_identical_evidence_is_not_repeated():
    same = SECOND.model_copy(update={"extraction_id": "u3"})
    merged = merge(SECOND, same)
    assert merged.evidence_text == SECOND.evidence_text


def test_the_more_detailed_task_wins():
    assert merge(FIRST, SECOND).task == SECOND.task
    assert merge(SECOND, FIRST).task == SECOND.task, "order must not matter here"


def test_an_owner_is_never_lost_to_ordering():
    """A candidate that named someone is strictly more informative."""
    assert merge(FIRST, SECOND).owner_text == "أحمد"
    assert merge(SECOND, FIRST).owner_text == "أحمد"


def test_a_present_date_phrase_beats_a_missing_one():
    undated = FIRST.model_copy(update={"raw_date_phrase": None})
    assert merge(undated, SECOND).raw_date_phrase == "يوم الخميس"


def test_the_left_value_wins_when_both_are_present():
    """Neither is more informative, so the merge is deterministic, not clever."""
    assert merge(FIRST, SECOND).raw_date_phrase == FIRST.raw_date_phrase


def test_confidence_is_the_lower_of_the_two():
    """Two mentions are not evidence that Nexa heard it more accurately.

    Taking the max could push a merged item past a review threshold it should
    not clear.
    """
    assert merge(FIRST, SECOND).confidence == 0.8
    assert merge(SECOND, FIRST).confidence == 0.8


def test_needs_review_survives_from_either_side():
    """Merging is not evidence the ambiguity was resolved."""
    assert merge(FIRST, SECOND).needs_review is True
    assert merge(SECOND, FIRST).needs_review is True


def test_two_clean_candidates_merge_clean():
    other = SECOND.model_copy(update={"extraction_id": "u9", "task": "x"})
    merged = merge(SECOND, other)
    assert merged.needs_review is False
    assert merged.review_reason is None


def test_the_more_serious_review_reason_survives():
    ambiguous = FIRST.model_copy(update={"review_reason": "ambiguous_date"})
    low = SECOND.model_copy(update={"needs_review": True, "review_reason": "low_confidence"})
    assert merge(low, ambiguous).review_reason == "ambiguous_date"
    assert merge(ambiguous, low).review_reason == "ambiguous_date"


def test_resolved_date_is_copied_never_computed():
    """§1.1: only the deterministic date layer writes this field."""
    when = datetime(2026, 9, 24, 15, 0)
    dated = SECOND.model_copy(update={"resolved_date": when})
    assert merge(FIRST, dated).resolved_date == when
    # Neither input had one: the merge must not invent one.
    assert merge(FIRST, SECOND).resolved_date is None


def test_the_left_identity_is_kept():
    """The audit trail already refers to it."""
    assert merge(FIRST, SECOND).extraction_id == "u1"


def test_the_span_addresses_the_merged_text():
    """A span from one segment cannot address two joined sentences."""
    merged = merge(FIRST, SECOND)
    assert merged.evidence_span == (0, len(merged.evidence_text))


def test_merge_does_not_mutate_its_inputs():
    before = (FIRST.model_dump(), SECOND.model_dump())
    merge(FIRST, SECOND)
    assert (FIRST.model_dump(), SECOND.model_dump()) == before


def test_the_result_is_still_a_valid_candidate():
    merged = merge(FIRST, SECOND)
    assert isinstance(merged, ActionCandidate)
    assert 0.0 <= merged.confidence <= 1.0
    assert merged.task and merged.evidence_text


# ------------------------------------------------------------------ merge_all
def test_merge_all_folds_three_mentions():
    third = ActionCandidate(
        task="تسليم التقرير",
        raw_time_phrase="الساعة 3",
        confidence=0.95,
        needs_review=False,
        evidence_text="التقرير الساعة 3",
        evidence_span=(0, 16),
        extraction_id="u3",
    )
    merged = merge_all([FIRST, SECOND, third])
    assert merged.owner_text == "أحمد"
    assert merged.raw_time_phrase == "الساعة 3"
    assert merged.evidence_text.count(EVIDENCE_SEPARATOR) == 2
    assert merged.confidence == 0.8


def test_merge_all_of_one_returns_it():
    assert merge_all([FIRST]).extraction_id == FIRST.extraction_id


def test_merge_all_of_nothing_is_none():
    assert merge_all([]) is None


# --------------------------------------------------------- the frozen surface
def test_the_service_exposes_merge():
    """§23.3 puts `merge` on DuplicateService, next to `compare`."""
    assert hasattr(DuplicateService, "merge")
    assert DuplicateService.merge(FIRST, SECOND).owner_text == "أحمد"


def test_compare_only_recommends_and_never_merges():
    """§7 gives the admin `[ Keep Both ]` / `[ Merge ]`; code does not choose."""
    import inspect

    source = inspect.getsource(DuplicateService.compare)
    assert "merge(" not in source.replace("merge_candidates", "")
    assert "recommended_action" in source
