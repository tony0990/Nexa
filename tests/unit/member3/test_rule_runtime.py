"""The rule-based extractor, against the labelled fixture corpus and beyond it.

`RuleBasedRuntime` replaces the canned mock as the thing a real meeting runs
through. Two kinds of test:

* **The corpus.** Member 3's labelled fixtures are the project's own ground
  truth. Every non-zero fixture must reproduce its expected item count, owner,
  date phrase and time phrase, and every `zero_action` fixture must produce
  nothing — that last one is the release-blocking precision guardrail (§39.2).
* **Held out.** The rules were tuned against the corpus, so agreement with it is
  necessary but proves little about unseen text. The `HELD_OUT` cases were
  written afterwards, in the voices of real meetings, and are the check against
  having overfitted.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from nexa.intelligence.rule_runtime import RuleBasedRuntime, extract_items
from nexa.intelligence.prompts import build_extraction_prompt

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "transcripts"


def _load():
    out = []
    for path in sorted(glob.glob(str(FIXTURES / "*" / "*.json"))):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if "segment_text" in data:           # the dedup pairs have another shape
            out.append(pytest.param(data, id=Path(path).stem))
    return out


CORPUS = _load()
ACTION_FIXTURES = [p for p in CORPUS if p.values[0]["category"] != "zero_action"]
ZERO_FIXTURES = [p for p in CORPUS if p.values[0]["category"] == "zero_action"]


# ------------------------------------------------------------------ the corpus
@pytest.mark.parametrize("fixture", ZERO_FIXTURES)
def test_zero_action_fixtures_yield_nothing(fixture):
    """Release-blocking: precision matters far more than completeness (§5.1)."""
    assert extract_items(fixture["segment_text"]) == []


@pytest.mark.parametrize("fixture", ACTION_FIXTURES)
def test_every_fixture_reproduces_its_labels(fixture):
    expected = fixture["expected"]["items"]
    got = extract_items(fixture["segment_text"])
    assert len(got) == len(expected), fixture["segment_text"]
    for want, have in zip(expected, got):
        assert (have["owner_text"] or "") == (want.get("owner_text") or "")
        assert (have["raw_date_phrase"] or "").lower() == (want.get("raw_date_phrase") or "").lower()
        assert (have["raw_time_phrase"] or "").lower() == (want.get("raw_time_phrase") or "").lower()


def test_the_corpus_is_actually_loaded():
    """A glob that matches nothing would make the tests above vacuous."""
    assert len(ACTION_FIXTURES) >= 25
    assert len(ZERO_FIXTURES) >= 5


# ----------------------------------------------------------------- held out
HELD_OUT = [
    # (text, owner, date phrase, time phrase)
    ("محمد لازم يبعت العرض للعميل يوم الأحد الساعة اتنين.", "محمد", "يوم الأحد", "اتنين"),
    ("Sarah, can you send the invoice to finance by Wednesday at 2 pm?", "Sarah", "by Wednesday", "2 pm"),
    ("يا ريم، جهزي التقرير قبل يوم الخميس.", "ريم", "قبل يوم الخميس", None),
    ("Dina will book the meeting room tomorrow.", "Dina", "tomorrow", None),
    ("لازم نراجع العقد الأسبوع الجاي.", None, "الأسبوع الجاي", None),
    ("Please upload the recordings by Friday.", None, "by Friday", None),
    ("عمر هيسلم الكود يوم التلات الساعة خمسة.", "عمر", "يوم التلات", "خمسة"),
    ("Youssef needs to deploy the fix next Monday.", "Youssef", "next Monday", None),
]


@pytest.mark.parametrize("text,owner,date,clock", HELD_OUT)
def test_held_out_sentences(text, owner, date, clock):
    items = extract_items(text)
    assert len(items) == 1, f"{text!r} -> {[i['task'] for i in items]}"
    item = items[0]
    assert item["owner_text"] == owner
    assert item["raw_date_phrase"] == date
    assert item["raw_time_phrase"] == clock


HELD_OUT_NEGATIVE = [
    "أحمد بعت التقرير امبارح.",                   # a past event, not a deadline
    "Ahmed sent the report yesterday.",
    "الاجتماع كان حلو جدا النهاردة.",              # a date, no commitment
    "I think Thursday could work, maybe.",       # soft language
    "ممكن نتكلم عن الميزانية الأسبوع الجاي.",       # discussion
    "Thanks everyone, great meeting today.",
    "What time is the meeting tomorrow?",        # a bare question
    "هل الجو حلو النهاردة؟",
    "We should probably look into the budget next month.",
]


@pytest.mark.parametrize("text", HELD_OUT_NEGATIVE)
def test_held_out_negatives_yield_nothing(text):
    assert extract_items(text) == [], text


# --------------------------------------------------------------- behaviours
def test_two_commitments_in_one_sentence_become_two_items():
    items = extract_items("سارة تبعت الـ minutes النهاردة، كريم يجهّز الـ slides بكرة.")
    assert [i["owner_text"] for i in items] == ["سارة", "كريم"]
    assert [i["raw_date_phrase"] for i in items] == ["النهاردة", "بكرة"]


def test_a_date_clause_is_attached_to_the_task_before_it():
    """"…، بكرة" is a modifier of the previous clause, not an action of its own."""
    items = extract_items("ابعت التقرير للعميل، بكرة الصبح.")
    assert len(items) == 1
    assert items[0]["raw_date_phrase"] == "بكرة"


def test_evidence_is_the_original_wording_and_offsets_address_it():
    text = "كلام عادي. أحمد، لازم تخلص الـ report بكرة الساعة 10 الصبح."
    (item,) = extract_items(text)
    start, end = item["evidence_span"]
    assert text[start:end] == item["evidence_text"]
    assert "الساعة 10 الصبح" in item["evidence_text"]


def test_nothing_is_invented():
    """§5.1 rule 3: an unstated owner, date or time stays null."""
    (item,) = extract_items("Please send the report by Friday.")
    assert item["owner_text"] is None
    assert item["raw_time_phrase"] is None
    assert item["needs_review"] is True
    assert item["review_reason"] == "no_owner"


def test_the_task_text_drops_the_owner_and_date_but_keeps_the_action():
    (item,) = extract_items("John, please finish the documentation by Friday.")
    assert item["task"] == "finish the documentation"


def test_a_known_employee_is_matched_even_mid_sentence():
    """With the employee list, position no longer matters."""
    items = extract_items("لازم نبعت الـ proposal لأحمد يوم الخميس.", known_names=["أحمد حسن"])
    assert items and items[0]["owner_text"] == "أحمد"


def test_a_known_name_with_a_leading_waw_is_not_mangled():
    """وليد is a name, not "and" + "ليد"."""
    items = extract_items("وليد يراجع العقد بكرة.", known_names=["وليد سمير"])
    assert items[0]["owner_text"] == "وليد"


def test_every_item_has_a_unique_stable_id():
    items = extract_items("سارة تبعت التقرير بكرة، كريم يجهز العرض الخميس.")
    assert len({i["extraction_id"] for i in items}) == len(items) == 2


def test_empty_and_blank_text_are_safe():
    assert extract_items("") == []
    assert extract_items("   \n  ") == []


def test_a_mixed_script_sentence_works():
    (item,) = extract_items("Team A delivers the API by Tuesday.")
    assert item["owner_text"] == "Team A"


# ------------------------------------------------------------ as a runtime
def test_the_runtime_speaks_the_llm_contract():
    """Same JSON shape the real prompt asks a model for, via `LLMRuntime`."""
    runtime = RuleBasedRuntime()
    runtime.start()
    assert runtime.is_ready()
    prompt = build_extraction_prompt("أحمد، لازم تخلص الـ report بكرة.", __import__("datetime").datetime(2026, 9, 24, 12))
    data = json.loads(runtime.complete(prompt))
    assert data["items"] and data["items"][0]["owner_text"] == "أحمد"


def test_the_runtime_reads_the_segment_not_the_few_shot_examples():
    """The bug that made the old mock useless: it matched its own examples."""
    runtime = RuleBasedRuntime()
    runtime.start()
    prompt = build_extraction_prompt("الجو حلو النهاردة.", __import__("datetime").datetime(2026, 9, 24, 12))
    assert json.loads(runtime.complete(prompt))["items"] == []


def test_the_runtime_must_be_started():
    with pytest.raises(RuntimeError):
        RuleBasedRuntime().complete("Input: x\nOutput: ")


def test_known_names_can_be_updated_after_construction():
    runtime = RuleBasedRuntime()
    runtime.set_known_names(["وليد"])
    assert runtime.known_names == ["وليد"]


# ------------------------------------------- found by running a real paragraph
def test_a_known_name_glued_to_a_conjunction_is_matched():
    """"وسارة" is "and Sara": the و is not part of the name."""
    (item,) = extract_items("طيب وسارة تبعتلي الـ mockups بكرة.", known_names=["سارة علي"])
    assert item["owner_text"] == "سارة"
    assert "سارة" not in item["task"]


def test_a_request_to_anyone_is_an_unowned_action():
    (item,) = extract_items("Can someone book the demo room for Tuesday at 3 pm?")
    assert item["owner_text"] is None
    assert item["task"] == "book the demo room"
    assert item["raw_time_phrase"] == "3 pm"


def test_a_deadline_statement_yields_the_thing_being_delivered():
    (item,) = extract_items("The deadline for the final report is 25 September.")
    assert item["task"] == "the final report"
    assert item["raw_date_phrase"] == "25 September"


@pytest.mark.parametrize(
    "text,time_phrase",
    [("Karim will deploy to staging tomorrow morning.", "morning"), ("ابعت الملف بكرة الصبح.", "الصبح")],
)
def test_a_time_of_day_word_is_a_time_not_part_of_the_task(text, time_phrase):
    (item,) = extract_items(text)
    assert item["raw_time_phrase"] == time_phrase
    assert time_phrase not in item["task"]


def test_the_task_text_has_no_dangling_preposition():
    assert extract_items("The demo is scheduled for next Thursday at 3 PM.")[0]["task"] == "The demo is scheduled"


def test_no_source_file_contains_a_stray_control_character():
    """A `\b` in a regex once reached the source as a literal backspace.

    It was invisible in an editor and silently changed what two patterns matched
    (English "yesterday" stopped being recognised as past). The rule is cheap to
    assert across everything Member 3 and the extractor touch.
    """
    root = Path(__file__).resolve().parents[3] / "src" / "nexa"
    offenders = []
    for path in list(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(ord(ch) < 32 and ch not in "\t\r\n" for ch in text):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


# ------------------------- found by running the real Whisper model's output
def test_an_abbreviation_does_not_end_a_sentence():
    """Whisper writes "3 p.m."; splitting at that full stop stranded the time."""
    text = "Ahmed, please finish the database integration by Friday at 3 p.m. Sarah will send the invoice tomorrow morning."
    items = extract_items(text)
    assert [i["owner_text"] for i in items] == ["Ahmed", "Sarah"]
    assert items[0]["raw_time_phrase"] == "3 p.m."
    assert items[0]["task"] == "finish the database integration"
    assert items[1]["task"] == "send the invoice"


def test_offsets_stay_valid_when_a_stop_is_protected():
    text = "Meet at 3 p.m. today. Ahmed, send the file by Friday."
    (item,) = [i for i in extract_items(text) if i["owner_text"] == "Ahmed"]
    start, end = item["evidence_span"]
    assert text[start:end] == item["evidence_text"]


@pytest.mark.parametrize("fixture", ACTION_FIXTURES)
def test_evidence_is_always_a_verbatim_slice_of_the_input(fixture):
    """§2.2: the review screen shows the speaker's exact words, never a rewrite.

    Clause merging once joined fragments with a "، " of its own, so the evidence
    contained a character nobody said.
    """
    text = fixture["segment_text"]
    for item in extract_items(text):
        assert item["evidence_text"] in text
        start, end = item["evidence_span"]
        assert text[start:end] == item["evidence_text"]


# ------------------- found by a live loopback recording through the real model
def test_missing_punctuation_does_not_fuse_two_sentences():
    """Whisper omitted the full stop, and the weather remark became part of the task."""
    text = "Please finish the database integration by Friday at 3 p.m.. Sarah will send the invoice tomorrow morning The weather is nice today"
    items = extract_items(text)
    assert [i["owner_text"] for i in items] == [None, "Sarah"]
    assert items[1]["task"] == "send the invoice"
    assert all("weather" not in i["task"] for i in items)


@pytest.mark.parametrize(
    "text,count",
    [
        ("Ahmed will send the file by Friday Sarah will review it tomorrow", 2),
        ("Please send the report by Monday We should celebrate", 1),
        ("Send the file to Sarah by Friday", 1),           # a name after "to" is not a new clause
        ("Ask Mohamed to review the contract by Thursday", 1),
    ],
)
def test_unpunctuated_boundaries_split_only_where_a_new_sentence_starts(text, count):
    assert len(extract_items(text)) == count


def test_a_boundary_split_keeps_evidence_verbatim():
    text = "Ahmed will send the file by Friday Sarah will review it tomorrow"
    for item in extract_items(text):
        start, end = item["evidence_span"]
        assert text[start:end] == item["evidence_text"]
