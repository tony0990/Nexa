"""The mock LLM runtime must key on the segment, not the whole prompt.

`build_extraction_prompt` appends the few-shot library from prompts.py, whose
examples contain "أحمد", "سارة" and "John". The mock originally tested
`"أحمد" in prompt`, which was therefore true on *every* call — so it returned
the same canned action item for any input, and the release-blocking
zero-action precision guardrail was testing nothing at all.

That is the worst failure mode a test double has: it made the suite pass for
the wrong reason everywhere except the one test that happened to assert
emptiness.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nexa.dates.reference_time import CAIRO_TZ
from nexa.intelligence.extractor import Extractor
from nexa.intelligence.llm_runtime import LLMRuntime, _segment_under_extraction
from nexa.intelligence.prompts import FEW_SHOT_EXAMPLES, build_extraction_prompt

REF = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)


@pytest.fixture
def runtime() -> LLMRuntime:
    instance = LLMRuntime(model_path="mock")
    instance.start()
    return instance


@pytest.fixture
def extractor(runtime) -> Extractor:
    return Extractor(runtime)


# --------------------------------------------------- the prompt-matching trap
def test_the_few_shot_library_contains_the_mock_trigger_names():
    """Pins down why matching on the whole prompt is wrong."""
    corpus = " ".join(example["input"] for example in FEW_SHOT_EXAMPLES)
    for name in ("أحمد", "سارة", "John"):
        assert name in corpus


def test_prompt_contains_the_trigger_names_even_for_a_neutral_segment():
    prompt = build_extraction_prompt("الجو النهاردة جميل", REF)
    assert "أحمد" in prompt          # from the examples, not the segment
    assert "أحمد" not in _segment_under_extraction(prompt)


def test_segment_is_recovered_from_the_prompt():
    segment = "سارة، ابعتي الإيميل بكرة"
    assert _segment_under_extraction(build_extraction_prompt(segment, REF)) == segment


def test_segment_extraction_falls_back_to_the_whole_text():
    """A prompt built some other way must not yield an empty segment."""
    assert _segment_under_extraction("no markers here") == "no markers here"


# ----------------------------------------------- the guardrail now bites
ZERO_ACTION = [
    "إحنا محتاجين نفكر في موضوع الميزانية",
    "The current progress is okay",
    "أنا شايف إن الاجتماع كان مفيد جداً",
    "I think we should look into this later",
    "ممكن نناقش الموضوع ده في اجتماع تاني",
    "We are just brainstorming right now",
    "الجو النهاردة جميل جداً في القاهرة",
    "I appreciate your help with this",
    "ممكن حد يشرحلي النقطة دي تاني؟",
    "Let's just keep in touch",
]


@pytest.mark.parametrize("text", ZERO_ACTION)
def test_no_false_positive_on_a_zero_action_segment(extractor, text):
    assert extractor.extract(text, "seg", REF).items == []


# ---------------------------------------------- real segments still extract
@pytest.mark.parametrize(
    "text,owner",
    [
        ("أحمد، ابعت التقرير بكرة الساعة عشرة الصبح", "أحمد"),
        ("سارة، ابعتي الإيميل للعميل يوم الحد", "سارة"),
        ("John, please finish the documentation by Friday", "John"),
    ],
)
def test_a_real_action_segment_still_extracts(extractor, text, owner):
    """The fix must not make the mock useless — the demo path still works."""
    items = extractor.extract(text, "seg", REF).items
    assert len(items) == 1
    assert items[0].owner_text == owner


def test_the_llm_never_sets_a_resolved_date(extractor):
    """Section 1.1's "code disposes" rule, asserted on a real extraction."""
    items = extractor.extract("أحمد، ابعت التقرير بكرة", "seg", REF).items
    assert items and items[0].resolved_date is None


def test_runtime_must_be_started_first():
    with pytest.raises(RuntimeError):
        LLMRuntime(model_path="mock").complete("Input: anything\nOutput: ")
