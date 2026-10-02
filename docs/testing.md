# Testing

Member 1's subsystem in detail, plus the Member 3 and Member 4 suites
that run alongside it.

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

## Member 3 and Member 4

Those work packages live beside Member 1's and run in the same command:

| Path | Covers |
|---|---|
| `tests/unit/member3/` | schemas, JSON repair, date rules, confidence, dedup, precision guardrail |
| `tests/unit/member4/test_rendering.py` | languages, date/time formatting, owners, HTML/plain-text bodies, escaping |
| `tests/unit/member4/test_bilingual.py` | paired labels/dates, untranslated names and tasks, LTR layout, subjects |
| `tests/unit/member4/test_oauth_flow.py` | the real OAuth flow against a faked `InstalledAppFlow` |
| `tests/unit/member4/test_mime_and_subjects.py` | RFC 2047 headers, part ordering, base64url, header injection, subject urgency |
| `tests/unit/member4/test_personalization.py` | per-recipient task isolation, completed tasks, batching |
| `tests/unit/member4/test_errors_and_oauth.py` | retryable/permanent split, token storage, secret redaction |
| `tests/integration/member4/test_preview_and_send.py` | preview → send, partial failures, the Member 1 delivery seam |
| `tests/integration/member4/test_connection.py` | Gmail connect/test/disconnect, revoked grants |
| `tests/integration/member4/test_bilingual_migration.py` | migration 004 is lossless, self-guarding, and does not rebuild tables |

Member 4's fixtures are `tests/fixtures/member4.py`, pinned to the same
instant as Member 1's. Three Member 3 date/precision tests currently fail;
see the README.

## Not covered here

Audio and ASR (Member 2), the worker loop (Member 5) and the UI (Member 6)
have their own suites. Everything merged so far is testable without any of
them: no test in this repository needs a microphone, a model file, a Gmail
account or a network connection. Member 4's Gmail transport is faked at the
`EmailSender` protocol and the OAuth flow is stubbed, so the only unverified
path is a live `connect()` against a real Google client.
