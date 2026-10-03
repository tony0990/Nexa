"""ASR metrics for the Nexa benchmark.

REVIEW THIS FILE YOURSELF: these functions define what "best model" means.

Conventions (write your reference transcripts the same way):
  * Arabic is compared after light normalization (see `normalize_text`):
    diacritics/tatweel removed, alef/yaa/taa-marbuta variants unified.
  * English is lowercased; English number words 0-20 become digits
    ("three" == "3"), because Whisper may emit either.
  * Arabic clitics glued to English words are split off: "الـbackend" == "ال backend".
  * Egyptian/MSA spellings of weekdays and hour numbers are treated as equal
    ("الاتنين" == "الاثنين", "تلاتة" == "ثلاثة" == "three" == "3"); see `_AR_EQUIVALENTS`.
  * Punctuation is ignored. Word order and word boundaries are NOT relaxed.

Metrics return raw counts where possible so results can be pooled across clips
(corpus-level WER = total errors / total reference words), which is fairer than
averaging per-clip WERs of very short clips.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

_DIACRITICS = re.compile("[ً-ٰٟ]")
_TATWEEL = "ـ"
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ALEF_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})
_LETTER_VARIANTS = str.maketrans({"ى": "ي", "ة": "ه"})
# Keep letters/digits (any script) and whitespace; everything else is punctuation.
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
# Code-switching glues Arabic clitics to English words ("الـbackend", "والـbudget", "3العصر").
# Split at every Arabic<->Latin/digit boundary so "الـbackend", "ال backend" and "الbackend"
# all normalize to the same tokens, and English terms stay matchable.
_SCRIPT_BOUNDARY = re.compile(r"(?<=[؀-ۿ])(?=[a-z0-9])|(?<=[a-z0-9])(?=[؀-ۿ])")

def _key(word: str) -> str:
    """Same character normalization as normalize_text, applied to a dictionary key."""
    return word.translate(_ALEF_VARIANTS).translate(_LETTER_VARIANTS)


# Egyptian vs Modern Standard spellings that Whisper uses interchangeably. Without this
# a correct "الساعة تلاتة" scores as an error against "الساعة ثلاثة". Kept deliberately
# small (weekdays + hour numbers): extend it only from mistakes you actually see.
_AR_EQUIVALENTS = {
    _key(variant): canonical
    for canonical, variants in {
        "الاثنين": ["الاتنين", "الاثنين", "الإثنين", "الاثنان"],
        "الثلاثاء": ["الثلاثاء", "التلات", "التلاتاء", "الثلاث"],
        "الاربعاء": ["الأربعاء", "الاربعاء", "الاربع", "الأربع"],
        "الاحد": ["الأحد", "الاحد", "الحد"],
        "1": ["واحد", "واحدة"],
        "2": ["اتنين", "اثنين", "إثنين", "اثنان", "اتنتين"],
        "3": ["تلاتة", "ثلاثة", "تلات", "ثلاث"],
        "4": ["اربعة", "أربعة", "اربع", "أربع"],
        "5": ["خمسة", "خمس"],
        "6": ["ستة", "ست"],
        "7": ["سبعة", "سبع"],
        "8": ["تمانية", "ثمانية", "تمن", "ثمان", "ثماني"],
        "9": ["تسعة", "تسع"],
        "10": ["عشرة", "عشر"],
    }.items()
    for variant in variants
}

_EN_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _DIACRITICS.sub("", text).replace(_TATWEEL, "")
    text = text.translate(_ARABIC_INDIC).translate(_ALEF_VARIANTS).translate(_LETTER_VARIANTS)
    text = text.lower()
    text = _NON_WORD.sub(" ", text.replace("_", " "))
    text = _SCRIPT_BOUNDARY.sub(" ", text)
    words = [_AR_EQUIVALENTS.get(w, _EN_NUMBERS.get(w, w)) for w in text.split()]
    return " ".join(words)


def tokenize(text: str) -> list[str]:
    return normalize_text(text).split()


def edit_distance(ref: Sequence[str], hyp: Sequence[str]) -> int:
    """Levenshtein distance (substitution/insertion/deletion all cost 1)."""
    if not ref:
        return len(hyp)
    if not hyp:
        return len(ref)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i]
        for j, h in enumerate(hyp, start=1):
            cost = 0 if r == h else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """Returns (errors, reference_word_count) for pooling across clips."""
    ref, hyp = tokenize(reference), tokenize(hypothesis)
    return edit_distance(ref, hyp), len(ref)


def char_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    ref = normalize_text(reference).replace(" ", "")
    hyp = normalize_text(hypothesis).replace(" ", "")
    return edit_distance(ref, hyp), len(ref)


def wer(reference: str, hypothesis: str) -> float:
    errors, n = word_errors(reference, hypothesis)
    return errors / n if n else (0.0 if not tokenize(hypothesis) else 1.0)


def cer(reference: str, hypothesis: str) -> float:
    errors, n = char_errors(reference, hypothesis)
    return errors / n if n else (0.0 if not hypothesis.strip() else 1.0)


def phrase_hits(phrases: Sequence[str], hypothesis: str) -> tuple[int, int]:
    """Returns (found, total): how many target phrases appear intact in the hypothesis.

    A phrase counts only if all its (normalized) words appear contiguously and in
    order - "الخميس الساعة 3" must not match "الخميس ... 3".
    Used for task keywords, date phrases and English technical terms.
    """
    hyp = tokenize(hypothesis)
    found = 0
    total = 0
    for phrase in phrases:
        target = tokenize(phrase)
        if not target:
            continue
        total += 1
        n = len(target)
        if any(hyp[i : i + n] == target for i in range(len(hyp) - n + 1)):
            found += 1
    return found, total
