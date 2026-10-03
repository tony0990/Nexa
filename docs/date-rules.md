# Egyptian date rules: three bugs and what they teach

Member 3's temporal layer shipped with three defects that the test suite caught
but that nobody had fixed. They are written up here because each one is an
instance of a pattern that will recur in this codebase — Arabic substring
matching, spelling variance, and a test double that lies.

All three **failed silently**, producing a plausible wrong answer rather than an
error. In a system whose whole job is deadlines, that is the expensive kind.

## 1. The shorter phrase shadowed the longer one

`بعد بكرة` ("the day after tomorrow") resolved to **tomorrow**.

The lookup ran `if "بكرة" in phrase` before `if "بعد بكرة" in phrase`, and
`بكرة` is a substring of `بعد بكرة`. The first branch won every time, and the
second was dead code.

Nothing about the result looked wrong: a date came back, it was a weekday, it
was in the future. A task due Saturday was quietly recorded as due Friday.

The same trap existed between `الاربع` and `الأربعاء`, and between `امبارح` and
`أول امبارح`.

**Fix.** Phrase tables are sorted longest-key-first and matched in that order,
so the most specific phrase always wins. `test_day_after_tomorrow_is_not_tomorrow`
and `test_longer_weekday_names_are_not_shadowed` pin it down.

**Rule.** Any substring-matched lookup table in Arabic needs longest-first
ordering. Arabic compounds by prefixing, so containment is the norm, not the
exception.

## 2. One spelling of Sunday was missing

`الأحد ده` ("this Sunday") resolved to **nothing at all** — the caller got
`None` and the action item ended up with no deadline.

The table held only the colloquial `الحد`. `الأحد` is not a superstring of it:
the hamza-carrying alef sits between the ل and the ح, so there is no substring
relationship at all. Any transcript using the formal spelling lost its date.

Enumerating spellings by hand cannot work here. `أحمد`/`احمد`, `فاطمة`/`فاطمه`,
tashkeel present or absent — ASR output is not consistent, and the variant
nobody listed fails silently.

**Fix.** Both the phrases and the table keys are folded through Member 1's
`normalize_search_text`, which already strips tashkeel and unifies the
alef/ya/ta-marbuta forms for search. One function now serves both subsystems, so
Arabic matching behaves the same way everywhere.

`test_lookup_keys_are_stored_normalized` asserts the keys really are normalized
— a raw-text key in a normalized table would never match anything, which is the
same silent miss in a new costume.

**Rule.** Never match raw Arabic. Normalize both sides, and reuse
`normalize_search_text` rather than writing a second folding function that
drifts from the first.

## 3. A resolved date was thrown away because it was in the past

`امبارح` ("yesterday") resolved correctly to the right calendar day, and the
resolver then **discarded it**, returning `resolved_datetime=None`.

The validator correctly reports that a past date is not a good deadline. The
resolver's response was to null the date out entirely — which throws away
information the reviewer needs. `امبارح` is not ambiguous: the date is known
exactly. Only its *suitability as a deadline* is in question, and that is the
admin's call on the review screen.

The behavioural difference matters:

| | Review screen could say |
|---|---|
| Before | "Time not specified" |
| After | "Nexa read this as 23 September, which is in the past" |

The first is strictly less useful and contradicts Section 2.1 ("show uncertainty
instead of inventing information") and Section 2.2 (the evidence trail must
survive).

**Fix.** The resolver keeps `resolved_datetime`, sets `is_ambiguous = True` and
carries the validator's reason in `ambiguity_reason`. `resolution_method` stays
as whatever resolved it, because it *did* resolve; validation is a separate
verdict. The validator itself is unchanged — it was already right.

**Rule.** A failed validation is a flag, not an eraser. Record the finding
alongside the value, never instead of it.

## 4. The mock runtime made the precision guardrail meaningless

Not a date bug, but the most dangerous of the four.

`LLMRuntime.complete()` is a test double that returns canned JSON based on
what it sees. It matched on the **whole prompt**:

```python
if "أحمد" in prompt:
    return '{"items": [...]}'
```

But `build_extraction_prompt` appends the few-shot library from `prompts.py`,
and those examples contain `أحمد`, `سارة` and `John`. So that condition was
**true on every call**, for every input. The mock returned the same action item
for any segment, including the zero-action fixtures.

`test_zero_action_precision` is marked release-blocking. It was the only test
that noticed, and it noticed for the wrong reason — every other extraction test
was passing against a mock that ignored its input entirely.

**Fix.** The mock keys on the segment under extraction, recovered from the final
`Input:` block of the prompt. `test_mock_runtime.py` asserts both halves: that
the prompt really does contain the trigger names when the segment does not, and
that real segments still extract.

**Rule.** A test double keyed on a prompt must look only at the part the caller
supplied. A double that matches its own fixtures is worse than no double,
because the suite goes green.

## Related

* [architecture.md](architecture.md) — where this layer sits and who owns it
* [email.md](email.md) — how a resolved deadline becomes text in a report, and
  why that formatting uses the local calendar day
