"""A deterministic, offline extractor that satisfies the `LLMRuntime` contract.

Why this exists. Member 3's `LLMRuntime` is a mock that returns canned JSON keyed
on a handful of names, so no real meeting could ever be processed, and the real
llama.cpp backend needs a ~2 GB model plus a C++ build on Windows. This runtime
lets the *entire* Member 3 pipeline — prompt, JSON parse, deterministic date
resolution, confidence, dedup — run on real transcripts with nothing to download.
`LLMRuntime` stays the seam: when a real model is wanted it replaces this class
and nothing else changes.

It follows the same rules the real prompt gives the model (§5.1):

* **Precision over recall.** An item needs BOTH a task signal (an obligation, an
  imperative, a future commitment) AND a stated date or time. "إحنا محتاجين نفكر
  في الميزانية" and "الجو النهاردة جميل" are each half an action and yield none.
* **Never invent.** An owner, date or time that was not said stays `null`.
* **Preserve wording.** `raw_date_phrase`, `raw_time_phrase`, `owner_text` and
  `evidence_text` are slices of the original text, not normalized or translated.

Arabic is matched through character classes (`ا/أ/إ/آ`, `ه/ة`, `ي/ى`) rather than
by normalizing the text first, because the output has to be the speaker's own
spelling and normalization changes string lengths.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from nexa.core.validation import normalize_search_text
from nexa.dates.clock_time import find_time_phrase

from .llm_runtime import LLMRuntime, _segment_under_extraction

# --------------------------------------------------------------------- helpers
_CLASSES = {
    "ا": "[اأإآ]", "ه": "[هة]", "ة": "[هة]", "ي": "[يى]", "ى": "[يى]", "و": "[وؤ]",
}


def ar(word: str) -> str:
    """A regex that matches `word` in any common Arabic spelling variant."""
    return "".join(_CLASSES.get(ch, re.escape(ch)) for ch in word)


def _alt(words: Iterable[str]) -> str:
    return "(?:" + "|".join(ar(w) for w in sorted(words, key=len, reverse=True)) + ")"


_TOKEN = re.compile(r"[^\s،,;؛.!?؟:()\"«»]+")

# ---------------------------------------------------------------- date phrases
_WEEKDAYS_AR = ["الأحد", "الحد", "الاثنين", "الاتنين", "التنين", "الثلاثاء", "التلات", "التلاتاء",
                "الأربعاء", "الاربع", "الخميس", "الجمعة", "السبت"]
_WEEKDAYS_EN = r"(?:mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
_MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "ابريل", "مايو", "يونيو", "يوليو", "أغسطس", "اغسطس",
              "سبتمبر", "أكتوبر", "اكتوبر", "نوفمبر", "ديسمبر"]
_MONTHS_EN = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_NEXT_AR = _alt(["الجاي", "الجاية", "الجايه", "القادم", "القادمة", "اللي جاي", "ده", "دي", "الجاى"])

_PREP_EN = r"(?:(?:by|before|until|till|on|from)\s+)?"
_PREP_AR = rf"(?:{_alt(['قبل', 'لحد', 'حتى', 'يوم'])}\s+)?"
_EOD_EN = r"(?:end of (?:the )?day|eod|close of business|cob)"
_EOD_AR = rf"{_alt(['نهاية', 'اخر', 'آخر'])}\s+{_alt(['اليوم'])}"

# Order matters: at the same start position the first matching alternative wins,
# so the longer, more specific shapes come first ("before EOD tomorrow" must
# beat a bare "tomorrow").
_DATE_PATTERNS = [
    # end-of-day deadlines, optionally anchored to a day
    rf"\b(?:(?:by|before|until)\s+)?{_EOD_EN}(?:\s+(?:today|tomorrow|{_WEEKDAYS_EN}))?\b",
    rf"\b(?:by|before|until)\s+(?:today|tomorrow)\s+{_EOD_EN}\b",
    rf"{_PREP_AR}{_EOD_AR}",
    # relative days
    rf"(?<![\w؀-ۿ]){_PREP_AR}{_alt(['بعد بكرة', 'بعد بكره'])}",
    rf"(?<![\w؀-ۿ]){_PREP_AR}{_alt(['النهاردة', 'النهارده', 'اليوم', 'بكرة', 'بكره', 'غدا', 'امبارح'])}(?![\w؀-ۿ])",
    rf"\b{_PREP_EN}(?:the day after tomorrow|tomorrow|today|tonight|yesterday)\b",
    # next/this week|month
    rf"{_alt(['الأسبوع', 'الاسبوع', 'الشهر'])}\s+{_NEXT_AR}",
    rf"{_alt(['آخر', 'اخر', 'نهاية', 'أول', 'اول', 'بداية'])}\s+{_alt(['الأسبوع', 'الاسبوع', 'الشهر'])}",
    rf"\b{_PREP_EN}(?:next|this|coming)\s+(?:week|month)\b",
    rf"\b{_PREP_EN}end of (?:the )?(?:week|month)\b",
    # weekdays, with optional prefix and qualifier
    rf"(?:{_alt(['قبل', 'لحد', 'حتى', 'يوم'])}\s+)*{_alt(_WEEKDAYS_AR)}(?:\s+{_NEXT_AR})?(?![\w؀-ۿ])",
    rf"\b(?:(?:by|before|on|until|next|this|coming|upcoming)\s+)*{_WEEKDAYS_EN}\b",
    # calendar dates
    rf"{_PREP_AR}\d{{1,2}}\s+{_alt(_MONTHS_AR)}(?:\s+\d{{4}})?",
    rf"\b{_PREP_EN}\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTHS_EN}(?:\s+\d{{4}})?\b",
    rf"\b{_PREP_EN}{_MONTHS_EN}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    # number-word day of month: "يوم عشرين سبتمبر"
    rf"{_PREP_AR}[؀-ۿ]{{3,12}}\s+{_alt(_MONTHS_AR)}(?![\w؀-ۿ])",
    # "in 3 days", "بعد 3 ايام"
    rf"{_alt(['بعد', 'خلال'])}\s+(?:\d+|{_alt(['يومين', 'ثلاث', 'تلات', 'اربع', 'خمس'])})\s*{_alt(['يوم', 'ايام', 'أيام', 'اسبوع', 'أسبوع', 'اسابيع', 'ساعة', 'ساعات'])}",
    r"\bin\s+(?:\d+|a|an|one|two|three|four|five)\s+(?:day|days|week|weeks|hour|hours)\b",
    # stated but vague: kept verbatim so the reviewer sees it; it resolves to review
    rf"(?<![\w؀-ۿ]){_alt(['قريب', 'قريبا', 'دلوقتي', 'حالا', 'فورا', 'بسرعة'])}(?![\w؀-ۿ])",
    r"\b(?:soon|asap|as soon as possible|right away|immediately)\b",
]
_DATE_RE = re.compile("|".join(f"(?:{p})" for p in _DATE_PATTERNS), re.IGNORECASE)

# ------------------------------------------------------------- task signals
# An obligation word, on its own, is weak: "محتاجين نفكر" is a discussion.
_OBLIGATION = re.compile(
    rf"(?<![\w؀-ۿ]){_alt(['لازم', 'يجب', 'ضروري', 'مطلوب', 'محتاج', 'محتاجين', 'عايز', 'عايزين', 'لابد', 'لا بد', 'مفروض'])}(?![\w؀-ۿ])"
    r"|\b(?:must|need(?:s)? to|has to|have to|had better|supposed to|required to|make sure|don'?t forget|remember to|follow up)\b",
    re.IGNORECASE,
)
_WILL = re.compile(
    r"\b(?:will|shall|i'?ll|we'?ll|going to|gonna|can you|could you|would you|can (?:someone|anyone|somebody)|could (?:someone|anyone|somebody)|who can|please)\b",
    re.IGNORECASE,
)
# Work verbs, as stems. Arabic is matched after stripping the subject prefix.
_AR_VERB_STEMS = [
    "خلص", "جهز", "بعت", "ابعت", "ارسل", "سلم", "تسلم", "راجع", "اتاكد", "تاكد", "كلم", "اتصل", "حضر", "اعمل", "عمل",
    "اكتب", "ارفع", "نفذ", "حدث", "ضيف", "شوف", "تابع", "قدم", "نسق", "رتب", "احجز", "اطبع", "جرب", "اختبر", "صلح",
    "ابدا", "كمل", "غير", "اقفل", "افتح", "حدد", "وزع", "ظبط", "اظبط", "ناقش", "اجهز", "انهي", "انهى", "اخلص", "نظم",
    "جمع", "اجمع", "حل", "حلل", "عدل", "اعدل", "ادفع", "حول", "ابلغ", "بلغ", "اطلب", "ابحث", "دور", "زور", "استلم",
    "تستلم", "سجل", "وقع", "اعتمد", "وافق", "ارجع", "رد", "ردي",
    "بدا", "طلع", "اطلع", "نزل", "انزل", "بلغ", "تبعت", "تتبعت", "تخلص", "تتسلم", "تتعمل", "تتراجع", "اتبعت",
    "اشتغل", "شغل", "اقفل", "قفل", "اكمل", "انجز", "ابعتلي", "ابعتي",
]
_AR_STEM_SET = tuple(normalize_search_text(s) for s in _AR_VERB_STEMS)
_AR_PREFIXES = ("", "ي", "ت", "ن", "ا", "هي", "هت", "هن", "ه", "ح", "حن", "حت", "حي", "ب", "م", "يت", "تت", "نت", "ات")
_EN_VERBS = (
    "send", "finish", "complete", "submit", "deliver", "prepare", "review", "update", "call", "email", "write", "fix",
    "schedule", "book", "check", "confirm", "share", "upload", "deploy", "test", "create", "build", "finalize",
    "organize", "arrange", "provide", "draft", "publish", "pay", "order", "follow", "ship", "release", "present",
    "sign", "approve", "collect", "gather", "plan", "set up", "wrap up", "hand in", "get", "make", "close", "launch",
    "kick off", "start", "begin", "roll out", "migrate", "handle", "own", "take care of", "walk through",
)
_EN_VERB_RE = re.compile(r"\b(?:" + "|".join(re.escape(v) for v in sorted(_EN_VERBS, key=len, reverse=True)) + r")(?:s|es|ed|ing)?\b", re.IGNORECASE)

# "Thinking about it" is not a commitment (§2.1, §5.1 rule 6).
_DISCUSSION = re.compile(
    rf"{_alt(['نفكر', 'نناقش', 'نتكلم', 'نشوف', 'ممكن', 'يمكن', 'يمكننا', 'ياريت', 'لو ', 'احتمال', 'نبحث', 'نتناقش', 'نتشاور'])}"
    r"|\b(?:brainstorm|brainstorming|maybe|perhaps|might|could|should we|think about|thinking|discuss|talk about|look into|keep in touch|appreciate|suggest|wonder)\b",
    re.IGNORECASE,
)
# Phrases that make a clause an explicit commitment even next to a soft word.
_STRONG = re.compile(
    rf"{_alt(['لازم', 'يجب', 'ضروري', 'مطلوب', 'لابد', 'مفروض'])}"
    r"|\b(?:must|has to|have to|will|please|by|before|deadline|due)\b",
    re.IGNORECASE,
)

_LEAD_CUES = re.compile(
    rf"^(?:{_alt(['لازم', 'يجب', 'ضروري', 'مطلوب', 'محتاج', 'محتاجين', 'لابد', 'مفروض', 'عايز', 'عايزين', 'وكمان', 'كمان', 'و', 'ف', 'بس', 'يعني', 'طيب', 'اذا', 'ان'])}\s+)+"
    r"|^(?:please|kindly|also|and|so|then|we need to|you need to|need to|needs to|must|should|will|i'?ll|we'?ll|can you|could you|can someone|could someone|can anyone|would you)\s+",
    re.IGNORECASE,
)
_SCHEDULED = re.compile(
    r"\b(?:is|are|was|be)?\s*(?:scheduled|due|deadline|set for|planned|expected|slated|booked|going out)\b"
    rf"|{_alt(['عندنا', 'هيكون', 'هتكون', 'تكون', 'هيبقى', 'يبقى', 'موعد', 'ميعاد', 'متحدد', 'محدد'])}",
    re.IGNORECASE,
)
_DEADLINE_WORDS = {normalize_search_text(w) for w in ("eod", "end of day", "end of the day", "close of business", "cob", "اخر اليوم", "نهاية اليوم")}
_TIME_LEAD = re.compile(r"^(?:" + _alt(["الساعة", "الساعه"]) + r"|at)\s+", re.IGNORECASE)
_PAST_DATE = re.compile(
    rf"{_alt(['امبارح', 'إمبارح', 'البارحة', 'اول امبارح', 'الماضي', 'الماضية', 'اللي فات', 'اللى فات', 'الفايت'])}"
    r"|\b(?:yesterday|last\s+\w+|\w+\s+ago|previous)\b",
    re.IGNORECASE,
)
_QUESTION_END = re.compile(r"[?؟]\s*$")

_CONNECTORS = {normalize_search_text(w) for w in ("and", "then", "also", "so", "but", "و", "ف", "ثم", "بعدين", "وكمان", "كمان", "يا", "ya")}


class _ShiftedMatch:
    """A token match whose start was moved past a stripped prefix character."""

    def __init__(self, match, shift: int) -> None:
        self._m, self._shift = match, shift

    def group(self, n: int = 0) -> str:
        return self._m.group(n)[self._shift:]

    def end(self) -> int:
        return self._m.end()

    def start(self) -> int:
        return self._m.start() + self._shift


_STOP_FIRST_TOKENS = {
    normalize_search_text(w) for w in (
        "لازم", "يجب", "ضروري", "مطلوب", "محتاج", "محتاجين", "عايز", "عايزين", "الـ", "ال", "في", "من", "علي", "على",
        "ان", "انه", "انها", "ده", "دي", "دا", "كل", "كمان", "و", "ف", "ثم", "بعدين", "طيب", "يعني", "بس", "اه", "تمام",
        "the", "a", "an", "we", "you", "it", "this", "that", "please", "also", "and", "so", "then", "need", "must", "should",
        "will", "can", "could", "would", "just", "let", "lets", "ok", "okay", "yes", "no", "i", "they", "he", "she",
        "هنا", "هناك", "هذا", "هذه", "ممكن", "احنا", "إحنا", "انا", "أنا", "انت", "هو", "هي", "هم",
    )
}


@dataclass
class _Group:
    text: str
    start: int
    end: int
    continued: bool = False  # a later clause of the same sentence


# ---------------------------------------------------------------- segmentation
_DOT = "․"  # one-dot leader: looks like "." but is not a sentence end
# "p.m." is special: its FIRST dot is part of the abbreviation, but its last dot
# may also be the end of the sentence ("...at 3 p.m. Sarah will send..."). So only
# the inner dot is hidden, and the trailing one is left to split on. Every other
# abbreviation ("e.g.", "Mr.") is never sentence-final in practice, and decimals
# ("2.30") never are, so all their dots are hidden.
_INNER_DOT = re.compile(r"(?i)(?<![A-Za-z])([ap])\.(?=m\b)")
_ABBREVIATION = re.compile(
    r"(?i)(?<![A-Za-z])(?:e\.g\.|i\.e\.|etc\.|vs\.|mr\.|mrs\.|ms\.|dr\.)|(?<=\d)\.(?=\d)"
)


def _protect_dots(text: str) -> str:
    """Hide the full stops that do not end a sentence.

    Replaced one-for-one, so every offset into the text stays valid; the real
    character is restored when the sentence text is sliced back out of `text`.
    """
    text = _INNER_DOT.sub(lambda m: m.group(1) + _DOT, text)
    return _ABBREVIATION.sub(lambda m: m.group(0).replace(".", _DOT), text)


# Whisper does not always punctuate. "…by Friday The weather is nice today" has no
# full stop, and without one the weather remark would be swallowed into the task.
# A capitalised word that starts a new sentence is the signal, in two shapes:
#   1. a sentence-starting function word: The, We, It, Please, ...
#   2. a capitalised name followed by a modal: "Sarah will", "Omar needs to"
# Both require the previous character to be lowercase or a digit, so real
# punctuation and sentence starts are untouched. Names after a preposition
# ("send it to Sarah") are not followed by a modal and so are never split.
_STARTER_WORDS = (
    "The|This|That|These|Those|We|They|He|She|It|There|Please|Also|However|Then|Today|Tomorrow|Let's|Next|Now"
)
_MODAL = r"(?:will|shall|should|must|needs?|has|have|can|could|would|is|are|was|were)"
_UNPUNCTUATED_START = re.compile(
    rf"(?<=[a-z0-9])( )(?=(?:(?:{_STARTER_WORDS})\b|[A-Z][a-z]+ {_MODAL}\b))"
)


def _mark_unpunctuated_boundaries(text: str) -> str:
    """Turn the space before an unpunctuated sentence start into a full stop.

    One character for one character, so offsets into the real text stay valid; the
    sentence text itself is sliced from the original, which still has the space.
    """
    return _UNPUNCTUATED_START.sub(".", text)


def _split_sentences(text: str) -> List[_Group]:
    """Sentences with their offsets in `text`."""
    groups: List[_Group] = []
    protected = _mark_unpunctuated_boundaries(_protect_dots(text))
    for match in re.finditer(r"[^.!?؟\n…]+[.!?؟…]*", protected):
        chunk = text[match.start():match.end()]
        stripped = chunk.strip()
        if stripped:
            offset = match.start() + (len(chunk) - len(chunk.lstrip()))
            groups.append(_Group(stripped, offset, offset + len(stripped)))
    return groups


def _split_clauses(sentence: _Group) -> List[_Group]:
    """Split a sentence at commas/semicolons into independent commitments.

    A clause that carries no task signal of its own ("بكرة", "by Friday") is a
    modifier of the clause before it, so it is merged back rather than orphaned.
    """
    parts: List[_Group] = []
    for match in re.finditer(r"[^،,;؛]+", sentence.text):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        offset = sentence.start + match.start() + (len(raw) - len(raw.lstrip()))
        parts.append(_Group(stripped, offset, offset + len(stripped)))

    def span(start: int, end: int) -> _Group:
        # Always sliced from the sentence, never built by concatenation: evidence
        # must be the speaker's exact words (§2.2), and joining clauses with a
        # separator of my own invents characters that were never said.
        return _Group(sentence.text[start - sentence.start: end - sentence.start], start, end)

    merged: List[_Group] = []
    for part in parts:
        if merged and not _is_standalone(part.text):
            merged[-1] = span(merged[-1].start, part.end)
        else:
            merged.append(part)
    # A leading signal-less clause (an owner name on its own: "سارة،") belongs to
    # the clause after it.
    if len(merged) > 1 and not _is_standalone(merged[0].text) and len(merged[0].text.split()) <= 2:
        head = merged.pop(0)
        merged[0] = span(head.start, merged[0].end)
        merged[0].continued = False
        for later in merged[1:]:
            later.continued = True
    else:
        for index, group in enumerate(merged):
            group.continued = index > 0
    return merged


# ------------------------------------------------------------------- detection
def _has_ar_verb(text: str) -> bool:
    for token in _TOKEN.findall(text):
        folded = normalize_search_text(token)
        if len(folded) < 3:
            continue
        for prefix in _AR_PREFIXES:
            if prefix and not folded.startswith(prefix):
                continue
            rest = folded[len(prefix):]
            if any(rest == stem or (len(stem) >= 3 and rest.startswith(stem)) for stem in _AR_STEM_SET):
                return True
    return False


def _has_task_signal(text: str) -> bool:
    return bool(
        _OBLIGATION.search(text)
        or _WILL.search(text)
        or _has_ar_verb(text)
        or _EN_VERB_RE.search(text)
    )


def _is_standalone(text: str) -> bool:
    """A clause that can be an action on its own.

    A task signal does it. So does a stated date together with a stated clock
    time ("الـpresentation Thursday الساعة three", "بكرة عندنا meeting الساعة
    ten"): spoken schedules often drop the verb, and a date plus a time is
    already a specific commitment rather than a general remark.
    """
    if _has_task_signal(text) or _SCHEDULED.search(text):
        return True
    return bool(_find_date(text) and find_time_phrase(text))


def _find_date(text: str) -> Optional[re.Match]:
    return _DATE_RE.search(text)


def _find_owner(text: str, known_names: Sequence[str], continued: bool = False) -> Optional[str]:
    """The person the commitment is addressed to, as spoken, or None."""
    # 1. A known employee name anywhere in the clause.
    folded_known = {}
    for name in known_names:
        for part in {name, *name.split()}:
            key = normalize_search_text(part)
            if len(key) >= 2:
                folded_known.setdefault(key, part)
    if folded_known:
        for token in _TOKEN.findall(text):
            key = normalize_search_text(token)
            for candidate in (key, key[1:] if key[:1] in ("ل", "و", "ف") else None):
                if candidate and candidate in folded_known:
                    return token[1:] if candidate != key else token

    # 2. "ask/tell Ahmed to ...", "قول لأحمد", "خلي أحمد"
    match = re.search(
        r"\b(?i:ask|tell|have|get|let|remind)\s+([A-Z][\w'-]+)\b", text
    ) or re.search(
        rf"{_alt(['قول', 'قولي', 'كلم', 'خلي', 'خلّي', 'اطلب من', 'بلغ', 'ذكر', 'ذكّر'])}\s+(?:ل)?([؀-ۿ]{{2,}})", text
    )
    if match and normalize_search_text(match.group(1)) not in _STOP_FIRST_TOKENS:
        return match.group(1)

    # 3. The clause opens with a name followed by a comma, a modal or a verb.
    tokens = list(_TOKEN.finditer(text))
    # Skip leading connectors: "and Omar needs to ...", "ثم سارة ...".
    while tokens and normalize_search_text(tokens[0].group(0)) in _CONNECTORS:
        tokens.pop(0)
    if not tokens:
        return None
    first = tokens[0].group(0)
    # A clause that continues a sentence ("..., ومنى تراجع ...") carries the
    # conjunction glued to the name. Strip it only here: at the start of a
    # sentence a leading و is far more likely part of a real name (وليد, وائل).
    if continued and len(first) > 3 and first[0] == "و" and normalize_search_text(first) not in folded_known:
        first = first[1:]
        tokens[0] = _ShiftedMatch(tokens[0], 1)
    folded = normalize_search_text(first)
    if folded in _STOP_FIRST_TOKENS or folded.startswith("ال") or len(folded) < 2:
        return None
    after = text[tokens[0].end(): tokens[0].end() + 3]
    followed_by_comma = bool(re.match(r"\s*[،,]", after))
    rest = text[tokens[0].end():]
    if first[0].isascii():
        if not first[0].isupper():
            return None
        # "Team A", "Team B"
        if folded in {"team", "فريق"} and len(tokens) > 1:
            return f"{first} {tokens[1].group(0)}"
        if followed_by_comma or re.match(r"\s+(?:will|should|must|needs?|has|can|to|is|please|to)\b", rest, re.IGNORECASE) \
                or _EN_VERB_RE.match(rest.lstrip()):
            return first
        return None
    if len(tokens) > 1 and folded in {"فريق", "قسم"}:
        return f"{first} {tokens[1].group(0)}"
    if followed_by_comma or _has_ar_verb(rest.split("،")[0]) or _OBLIGATION.search(rest):
        return first
    return None


def _strip_spans(text: str, spans: Iterable[tuple]) -> str:
    out, last = [], 0
    for start, end in sorted(spans):
        if start < last:
            continue
        out.append(text[last:start])
        last = end
    out.append(text[last:])
    return re.sub(r"\s+", " ", "".join(out)).strip(" ،,.؟?!-:؛;")


def _build_task(group_text: str, owner: Optional[str], date_span, time_span) -> str:
    spans = []
    if date_span:
        spans.append(date_span)
    if time_span:
        spans.append(time_span)
    task = _strip_spans(group_text, spans)
    # "The deadline for the final report is 25 September" states a due date for
    # something; the thing being delivered is the task.
    due = re.match(r"(?i)^(?:the\s+)?(?:deadline|due date)\s+(?:for|of|to)\s+(.+?)\s*(?:is|will be|:)?\s*$", task)
    if due:
        task = due.group(1).strip()
    if owner:
        task = re.sub(rf"^\s*{re.escape(owner)}\s*[،,]?\s*", "", task, count=1)
        task = re.sub(rf"\b(?:ask|tell|have|let|remind)\s+{re.escape(owner)}\s+(?:to\s+)?", "", task, flags=re.IGNORECASE)
        task = re.sub(rf"(?:^|\s)[لوف]?{re.escape(owner)}(?=\s|$)", " ", task, count=1)
    # Drop leading cues repeatedly ("وكمان لازم ...", "please ...").
    previous = None
    while previous != task:
        previous = task
        task = _LEAD_CUES.sub("", task).strip(" ،,.")
    task = re.sub(r"\b(?:by|before|on|until|at|in|for|from|of|to|with|due)\s*$", "", task, flags=re.IGNORECASE).strip(" ،,.")
    task = re.sub(rf"\s+{_alt(['قبل', 'لحد', 'حتى', 'يوم', 'في', 'الساعة'])}\s*$", "", task).strip(" ،,.")
    return task or group_text.strip(" ،,.")


# ----------------------------------------------------------------- the runtime
def extract_items(text: str, known_names: Sequence[str] = ()) -> List[dict]:
    """Action items in `text`, as the JSON objects the real prompt asks for."""
    items: List[dict] = []
    for sentence in _split_sentences(text):
        if _QUESTION_END.search(sentence.text) and not _WILL.search(sentence.text):
            # A bare question asks for information. A *request* phrased as one
            # ("Sarah, can you send the invoice by Wednesday?") is a commitment
            # and keeps flowing through; _WILL is what marks it as a request.
            continue
        for group in _split_clauses(sentence):
            date_match = _find_date(group.text)
            full_time = find_time_phrase(group.text)
            if full_time and normalize_search_text(full_time) in _DEADLINE_WORDS:
                full_time = None  # "EOD" is a deadline, handled as a date phrase
            # Gold convention (the labelled fixtures): the time phrase is the bare
            # time — "three", "3 PM" — not the "الساعة"/"at" that introduces it.
            time_phrase = _TIME_LEAD.sub("", full_time).strip() if full_time else None
            has_time = bool(time_phrase)
            # Some date phrases double as times ("tonight", "end of day"): those
            # still count, but only once.
            if not date_match and not has_time:
                continue
            if not _is_standalone(group.text):
                continue
            # Soft language needs an explicit commitment word beside it.
            if _DISCUSSION.search(group.text) and not _STRONG.search(group.text):
                continue

            if date_match and _PAST_DATE.search(date_match.group(0)):
                # "أحمد بعت التقرير امبارح" reports something already done. A past
                # date is evidence of an event, never of a deadline.
                continue

            owner = _find_owner(group.text, known_names, group.continued)
            raw_date = date_match.group(0).strip() if date_match else None
            time_span = None
            if has_time:
                idx = group.text.lower().find(full_time.lower())
                if idx >= 0:
                    time_span = (idx, idx + len(full_time))
            date_span = date_match.span() if date_match else None
            if date_span and time_span and not (date_span[1] <= time_span[0] or time_span[1] <= date_span[0]):
                # A time word inside the date phrase ("tonight"): keep it as the
                # date and drop the duplicate time phrase.
                time_span, time_phrase = None, None

            task = _build_task(group.text, owner, date_span, time_span)
            if len(task) < 2:
                continue

            confidence = 0.55 + (0.15 if owner else 0.0) + (0.15 if raw_date else 0.0) + (0.05 if time_phrase else 0.0)
            offset = text.find(group.text)
            items.append(
                {
                    "task": task,
                    "owner_text": owner,
                    "raw_date_phrase": raw_date,
                    "raw_time_phrase": time_phrase,
                    "confidence": round(min(confidence, 0.95), 2),
                    "needs_review": owner is None,
                    "review_reason": "no_owner" if owner is None else None,
                    "evidence_text": group.text,
                    "evidence_span": [max(offset, 0), max(offset, 0) + len(group.text)],
                    "extraction_id": str(uuid.uuid4()),
                }
            )
    return items


class RuleBasedRuntime(LLMRuntime):
    """`LLMRuntime` backed by `extract_items` instead of a model.

    `known_names` is the active employee list. Matching a spoken name against it
    is far more reliable than guessing from word position, and it never invents
    a person: a name that is not in the list falls through to the positional
    heuristic and, failing that, to `null`.
    """

    def __init__(self, known_names: Sequence[str] = (), **kwargs) -> None:
        super().__init__(model_path="rule-based", **kwargs)
        self.known_names: List[str] = list(known_names)

    def set_known_names(self, names: Iterable[str]) -> None:
        self.known_names = [n for n in names if n]

    def complete(self, prompt: str, *, temperature: float = 0.0, max_tokens: int = 512,
                 grammar: Optional[str] = None) -> str:
        if not self._is_running:
            raise RuntimeError("LLMRuntime must be started via start() before calling complete().")
        segment = _segment_under_extraction(prompt)
        return json.dumps({"items": extract_items(segment, self.known_names)}, ensure_ascii=False)
