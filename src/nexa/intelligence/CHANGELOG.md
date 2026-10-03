# Intelligence changelog

## Confidence weights (v1)

Recorded at M3 freeze. Do not treat as final — retune once ≥50 labeled fixtures exist.

| Signal | Weight |
|---|---|
| `resolution_method == deterministic_rule` | 0.40 |
| `resolution_method == dateparser_fallback` | 0.15 |
| `resolution_method == unresolved` | 0.00 |
| `owner_text` present | 0.20 |
| `raw_time_phrase` present | 0.15 |
| `len(task.strip()) >= 8` | 0.15 else 0.05 |
| `not temporal.is_ambiguous` | 0.10 |

`CONFIDENCE_REVIEW_THRESHOLD = 0.55` in `config.py`. LLM self-reported confidence is advisory only and is not added into the score.

## Ambiguity review priority (v1)

When multiple conditions apply, the first match wins:

1. `conflicting_signals`
2. `ambiguous_date`
3. `fuzzy_range`
4. `no_owner`
5. `low_confidence`

Date-only deadlines (missing `raw_time_phrase`) do **not** set `no_time`.
Range resolutions never collapse `resolved_date` to a single datetime.
