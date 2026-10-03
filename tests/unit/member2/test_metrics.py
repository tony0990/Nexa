import pytest

from nexa.asr import metrics


def test_normalize_arabic_variants_and_diacritics():
    assert metrics.normalize_text("أَحْمَد") == metrics.normalize_text("احمد")
    assert metrics.normalize_text("مدرسة") == metrics.normalize_text("مدرسه")
    assert metrics.normalize_text("إلى") == metrics.normalize_text("الي")


def test_normalize_digits_case_punctuation_and_number_words():
    assert metrics.normalize_text("الساعة ٣، Three!") == "الساعه 3 3"
    assert metrics.normalize_text("Hello,   WORLD.") == "hello world"


def test_arabic_clitic_glued_to_english_word_is_split():
    assert metrics.normalize_text("الـbackend") == "ال backend"
    assert metrics.normalize_text("الـbackend") == metrics.normalize_text("ال backend")
    assert metrics.normalize_text("والـbudget") == "وال budget"
    assert metrics.normalize_text("3العصر") == "3 العصر"
    assert metrics.phrase_hits(["backend"], "أحمد يخلص الـbackend") == (1, 1)


def test_egyptian_and_msa_weekday_and_number_spellings_are_equal():
    assert metrics.wer("يوم الاتنين الساعة تلاتة", "يوم الإثنين الساعة ثلاثة") == 0.0
    assert metrics.wer("الساعة تلاتة", "الساعة three") == 0.0
    assert metrics.wer("الساعة تلاتة", "الساعة 3") == 0.0
    assert metrics.wer("الحد اللي جاي", "الأحد اللي جاي") == 0.0
    assert metrics.phrase_hits(["يوم الخميس الساعة ثلاثة"], "الاجتماع يوم الخميس الساعة تلاتة") == (1, 1)
    # ...but different days/numbers must still count as errors
    assert metrics.wer("الاتنين", "الثلاثاء") == 1.0
    assert metrics.wer("الساعة تلاتة", "الساعة اربعة") == 0.5


def test_wer_identical_is_zero():
    assert metrics.wer("بكرة عندنا meeting", "بكرة عندنا meeting") == 0.0


def test_wer_counts_substitution_deletion_insertion():
    assert metrics.word_errors("a b c d", "a x c d") == (1, 4)  # substitution
    assert metrics.word_errors("a b c d", "a c d") == (1, 4)  # deletion
    assert metrics.word_errors("a b c d", "a b c d e") == (1, 4)  # insertion


def test_wer_can_exceed_one_and_handles_empty_reference():
    assert metrics.wer("a", "x y z") == 3.0
    assert metrics.wer("", "") == 0.0
    assert metrics.wer("", "hi") == 1.0


def test_number_word_equals_digit():
    assert metrics.wer("الساعة three", "الساعة 3") == 0.0


def test_cer():
    assert metrics.cer("abcd", "abcd") == 0.0
    assert metrics.cer("abcd", "abxd") == pytest.approx(0.25)


def test_phrase_hits_requires_contiguous_order():
    hyp = "أحمد يخلص الـdatabase قبل يوم الاتنين"
    assert metrics.phrase_hits(["يوم الاتنين"], hyp) == (1, 1)
    assert metrics.phrase_hits(["الاتنين يوم"], hyp) == (0, 1)  # wrong order
    assert metrics.phrase_hits(["قبل الاتنين"], hyp) == (0, 1)  # not contiguous


def test_phrase_hits_ignores_empty_phrases_and_reports_totals():
    assert metrics.phrase_hits([], "anything") == (0, 0)
    assert metrics.phrase_hits(["", "backend"], "the Backend is done") == (1, 1)


def test_phrase_hits_misses_when_english_term_is_transliterated():
    # Whisper forced to "ar" may write English words in Arabic script -> counts as a miss
    assert metrics.phrase_hits(["backend"], "أحمد يخلص الباك اند") == (0, 1)
