# Testing — Member 1 subsystem

## Running

```bash
python -m pytest
```

```bash
python -m pytest -m "not slow"
```

```bash
python -m pytest tests/unit/member1 -q
```

No database setup is needed: every test builds its own SQLite file in a
temporary directory, which means the "schema can be created from an empty
folder" requirement is exercised on every run.

## Layout

| Path | Covers |
|---|---|
| `tests/unit/member1/test_validation.py` | email/name rules, Arabic normalization, `LIKE` escaping |
| `tests/unit/member1/test_timezone_and_clock.py` | UTC/Cairo conversion, day/week/month bounds, `FixedClock` |
| `tests/unit/member1/test_filters.py` | date presets, condition building, filter combination |
| `tests/unit/member1/test_people_service.py` | employee/role CRUD, duplicates, activation, auditing |
| `tests/unit/member1/test_recipient_resolver.py` | target expansion, de-duplication, exclusions |
| `tests/unit/member1/test_audit_service.py` | recording, append-only enforcement, view model |
| `tests/integration/member1/test_migrations.py` | fresh schema, re-runs, failed migration, constraints |
| `tests/integration/member1/test_repositories.py` | every repository against real SQLite |
| `tests/integration/member1/test_search.py` | employee/meeting/task/global search, combined filters |
| `tests/integration/member1/test_transactions_and_backup.py` | rollback, savepoints, backup/restore |
| `tests/integration/member1/test_scale.py` | 1,000 employees/tasks (marked `slow`) |

## Fixtures

`tests/conftest.py` provides `db`, `clock`, `audit`, `people`, `resolver` and
`search`. Time is pinned to **Sunday 20 September 2026, 10:00 Cairo** via
`FixedClock`, so "today", "this week" and "overdue" mean the same thing on
every machine and on every day the suite runs. Sunday is deliberate: it is
the first day of the Egyptian working week, which makes the week-boundary
assertions unambiguous.

Nothing in the data layer calls `datetime.now()`; everything takes a `Clock`.
That is what makes the date-filter tests deterministic rather than flaky.

`tests/fixtures/dataset.py` builds the bulk dataset from a fixed random seed,
so a scale failure reproduces exactly.

## What the timing assertions are for

`test_scale.py` asserts queries finish within two seconds over 1,000
employees and 1,000 action items. That is not a benchmark — SQLite answers
these in milliseconds. It is a tripwire for an accidental N+1: a per-row role
lookup inside the employee list, for instance, would blow straight through
the budget on any machine.

## Timezone note

Tests read the expected UTC offset from the timezone itself rather than
hard-coding `+02:00`, because Egypt observes DST again since 2023 and a
machine without `tzdata` falls back to a fixed offset. Install the project
requirements (`pip install -r requirements/dev.txt`) to test against the real
Cairo rules.

## Not covered here

Audio, ASR, extraction, Gmail, the worker loop and the UI belong to Members
2-6 and have their own suites. Member 1's subsystem is complete and testable
without any of them: no test in this directory needs a microphone, a model
file or a network connection.
