# Nexa Data Model

Owner: **Member 1** (core data, people, search, audit).
Source of truth: `migrations/*.sql`. This document explains the decisions the
SQL cannot state.

## Storage conventions

| Concept | Stored as | Example |
|---|---|---|
| Instant in time | ISO-8601 UTC string | `2026-09-20T18:30:00+00:00` |
| Local calendar day | `YYYY-MM-DD` | `2026-09-24` |
| Local wall time | `HH:MM` | `15:00` |
| Boolean | `INTEGER` 0/1 with a CHECK | `active` |
| Structured config | JSON `TEXT` | `default_reminder_rule_config` |
| Normalized search copy | `*_norm` / `search_text` | `full_name_norm` |

Everything is written in UTC and displayed in `Africa/Cairo`. A naive
datetime arriving from the UI is interpreted as **local** time, never UTC —
see `nexa.core.timezone`.

`tzdata` is a real dependency on Windows. Without it, `Africa/Cairo` silently
degrades to a fixed +02:00 offset and every reminder during Egyptian summer
time would fire an hour late. `nexa.core.timezone.has_iana_timezone()` tells
the first-run check whether the real rules are present.

## Deadlines: `due_date`, `due_time`, `due_at`

Section 2.1 requires Nexa to show uncertainty instead of inventing it, so the
three columns are not redundant:

* `due_date` — the day the deadline falls on. Always set when a day is known.
* `due_time` — the wall time, or `NULL` for *"time not specified"*.
* `due_at` — the resolved UTC instant, computed **only** when both a date and
  a time are known.

A task due "Thursday" with no stated hour keeps `due_at = NULL`. Day-level
filters use `due_date`; anything that needs an exact instant (reminder
scheduling) uses `due_at` and must handle `NULL` explicitly rather than
guessing midnight.

## Evidence columns are write-once

`action_items.source_text`, `owner_raw_text` and `raw_date_phrase` hold the
original spoken wording (Section 2.2). The repository writes them on create
and never recomputes them from the normalized interpretation — including on
`reschedule()`, which changes the deadline while the evidence still says
"قبل يوم الاتنين". Same rule for `transcript_segments.raw_text`, which a
human correction stores alongside in `confirmed_text` rather than replacing.

## Search normalization

Arabic is written in several equivalent ways. `أحمد` and `احمد` are the same
name; `فاطمة` and `فاطمه` are the same person; transcribed code-switching
produces `الـpresentation` with a tatweel in the middle.

So every searchable row carries a normalized copy, maintained by the
repositories on write (`nexa.core.validation.normalize_search_text`):

* NFKC, then strip tashkeel, superscript alef and tatweel
* fold `أ إ آ ٱ → ا`, `ى → ي`, `ة → ه`, `ؤ → و`, `ئ → ي`
* Arabic-Indic digits → ASCII
* casefold, collapse whitespace

Queries are normalized the same way, so the two always meet. The original
text is never modified.

`employees.search_text` and `action_items.search_text` concatenate every
field the entity can be found by — for a task, that includes the evidence, so
an admin who remembers the sentence can find the item it produced.

Substring search uses `LIKE '%term%'`, which no B-tree can accelerate. At the
scale Nexa targets (thousands of rows) this is comfortably fast; the indexes
in `002_search_indexes.sql` cover the filter predicates and the ordering,
which is where the cost actually is. If an organization ever outgrows this,
the replacement is FTS5 with a custom tokenizer, not more indexes.

## Append-only audit

`audit_events` has no update or delete path: the repository exposes none, and
`001_initial.sql` installs `BEFORE UPDATE` / `BEFORE DELETE` triggers that
`RAISE(ABORT)`. The rule therefore survives someone opening the file in a
SQLite browser.

Old and new values are stored as JSON and, via `AuditService.log_change`,
contain **only the fields that actually changed** — so an idempotent save
writes nothing at all rather than a row full of unchanged values.

## Reminder idempotency

`reminders.idempotency_key` has a partial unique index (`WHERE
idempotency_key IS NOT NULL`). This is what prevents the duplicate sends
described in Section 5: the worker derives a stable key per occurrence, and
the database refuses a second row for it. Reminders created without a key —
ad-hoc ones — do not collide with each other.

## Deletion policy

* Employees are **deactivated**, not deleted: past reports and audit rows keep
  referring to a real person. Inactive employees are excluded from every
  recipient resolution.
* Deleting a meeting cascades to its participants, transcript segments and
  action items — a meeting that never really happened leaves nothing behind.
* Deleting an employee sets `action_items.owner_employee_id` to `NULL` rather
  than removing the task.
* `email_deliveries` keeps its rows when the related meeting or reminder goes
  away (`ON DELETE SET NULL`): delivery history is evidence.

## Who writes what

Member 1 owns every table, but other members write through these repositories:

| Member | Writes via |
|---|---|
| 2 (audio/ASR) | `MeetingRepository.add_segments`, `confirm_segment` |
| 3 (extraction) | `ActionRepository.create` / `bulk_create` |
| 4 (email) | `DeliveryRepository.record_attempt`, `mark_sent`, `mark_failed` |
| 5 (worker) | `ReminderRepository`, `ActionRepository.set_status` |
| 6 (UI) | `PeopleService`, `SearchService`, `AuditService` |

No member writes SQL against another member's tables. Adding a column means
adding a migration, not editing `001_initial.sql`.
