# Nexa

Smart Meeting Voice AI & Reminder desktop application for Windows.
Full specification, architecture and team ownership: [NEXA.md](NEXA.md).

`main` holds the merged work of **Members 1, 3 and 4**, plus the shared
`contracts` package from the Section 17 kickoff.

## What is implemented here

| Area | Package | Owner | Status |
|---|---|---|---|
| Shared contracts (kickoff artifact) | `src/nexa/contracts/` | shared | Domain models + service protocols for all six members |
| Config, clock, timezone, errors, validation | `src/nexa/core/` | 1 | Done |
| SQLite setup, migrations, transactions, repositories, backup | `src/nexa/data/` | 1 | Done |
| Employees, roles, recipient resolution | `src/nexa/people/` | 1 | Done |
| Search, filters, global search | `src/nexa/search/` | 1 | Done |
| Append-only audit trail | `src/nexa/audit/` | 1 | Done |
| LLM runtime, action extraction, confidence | `src/nexa/intelligence/` | 3 | Done |
| Egyptian + English temporal normalization | `src/nexa/dates/` | 3 | Done |
| Duplicate detection, embeddings, merge advice | `src/nexa/dedup/` | 3 | Done |
| Report rendering, Arabic/English/bilingual, subjects | `src/nexa/reports/` | 4 | Done |
| Gmail OAuth, sending, preview, personalization | `src/nexa/email/` | 4 | Done |

Audio/ASR (Member 2), scheduling and `NexaWorker.exe` (Member 5) and the
desktop UI (Member 6) are not merged yet.

## Requirements

Python 3.10+ (the project targets 3.11/3.12).

```bash
pip install -r requirements/dev.txt     # core + reports/email + pytest
pip install -r requirements/ai.txt      # adds the local model runtimes
```

`requirements/base.txt` is the runtime set, `ai.txt` the heavy local model
stacks (kept separate so the data and email layers install without them),
`dev.txt` adds pytest and `build.txt` adds PyInstaller.

## Quick start

```bash
python -m pytest
```

```bash
python -m pytest -m "not slow"          # skip Member 1's scale tests
```

```bash
python scripts/seed_demo_data.py --data-dir ./demo-data --reset
```

```bash
python scripts/preview_emails.py        # writes sample emails to build/
```

```bash
python scripts/setup_gmail.py status    # offline; says what Gmail setup is missing
```

```python
from nexa.core.config import NexaConfig
from nexa.data.database import open_database
from nexa.people.service import PeopleService
from nexa.search.service import SearchService
from nexa.search.filters import TaskFilters

db = open_database(NexaConfig(data_dir="./demo-data"))   # creates + migrates

people = PeopleService(db)
ahmed = people.create_employee("أحمد حسن", "ahmed@example.com", department="Development")

search = SearchService(db)
search.search_employees("احمد")                  # matches despite the spelling
search.search_tasks(None, TaskFilters(overdue=True))
search.global_search("Ahmed").group_counts()     # {'employees': 1, ...}
```

Rendering and sending an approved report, with no Gmail account needed:

```python
from nexa.email import EmailService, FakeEmailSender

emails = EmailService(sender=FakeEmailSender())

preview = emails.preview_meeting_report(meeting, actions, recipients, "EN")
preview.subject, preview.recipient_count, preview.warnings

summary = emails.send_meeting_report(meeting, actions, recipients, "EN")
summary.gmail_message_ids
```

## Public interfaces

Member 1 (Section 21.3):

```python
PeopleService.create_employee(...)      # also update/deactivate/reactivate
PeopleService.assign_role(employee_id, role_id)
PeopleService.role_members(role_id)

RecipientResolver.resolve(targets)      # -> unique, sendable employees
RecipientResolver.resolve_detailed(targets)   # + reasons and skip list

SearchService.search_employees(query, filters)
SearchService.search_meetings(query, filters)
SearchService.search_tasks(query, filters)
SearchService.global_search(query)

AuditService.record(event)
AuditService.history(entity_type, entity_id)
```

Member 4 (Section 24.3):

```python
ReportService.build_meeting_report(meeting, actions, recipients, language)
ReportService.build_reminder(employee, action, meeting, language)

EmailPreviewService.preview(rendered_email)
EmailSender.send(rendered_email)                 # GmailSender or FakeEmailSender

GmailConnectionService.connect() / .test() / .disconnect() / .status()

EmailService.preview_meeting_report(...)         # render, never send
EmailService.send_meeting_report(...)            # -> SendSummary
EmailService.send_personalized_reminders(...)
```

Other members call these; nobody imports another member's private modules or
writes SQL against another member's tables (Section 19).

## Notes for the rest of the team

* **The database creates itself.** `open_database(config)` on an empty folder
  runs every migration in order. Re-running is a no-op.
* **Time is injectable.** Nothing calls `datetime.now()`; pass a `Clock`
  (`SystemClock` in the app, `FixedClock` in tests).
* **Everything is UTC in storage, Cairo on screen.** A naive datetime from the
  UI is read as local time. Email deadlines are formatted from the local
  calendar day, so a late-evening UTC instant does not report the wrong day.
* **Evidence is never overwritten.** `source_text`, `raw_date_phrase` and
  `raw_text` keep the original wording; the normalized interpretation lives in
  separate columns, and the report carries the original phrase through.
* **Arabic search is spelling-tolerant.** `احمد` finds `أحمد`; see
  [docs/data-model.md](docs/data-model.md).
* **Recipient resolution de-duplicates by employee *and* email**, and reports
  who it skipped and why instead of dropping them silently.
* **Deactivate, don't delete.** Inactive employees never receive email but
  stay attached to their history.
* **Three report languages: `AR`, `EN`, `BILINGUAL`** (Section 24.1's "Three
  modes"). Bilingual pairs the *frame* — labels, dates, salutation, closing —
  and shows names and task text once, untranslated. Note Section 1 states there
  is no bilingual mode, contradicting Sections 10.3, 24.1, 24.2 and 24.6;
  [docs/email.md](docs/email.md) records the conflict and how to drop the mode
  if Section 1 wins.
* **Migration 004 widens two CHECK constraints in place, not by rebuilding.**
  Rebuilding either table cascade-deletes its children under the runner's
  `foreign_keys = ON`. Measured, pinned down by a test, and explained in
  [docs/email.md](docs/email.md).
* **Email is offline-testable.** `FakeEmailSender` satisfies the same
  `EmailSender` protocol as `GmailSender` and still builds real MIME, so it
  rejects what Gmail would reject. Members 5 and 6 need no Google account.
* **Member 4 never writes to the database.** Sending returns
  `DeliveryAttempt`/`SendSummary` objects; Member 1's `DeliveryRepository`
  persists them (Section 24.1).
* **OAuth tokens live in Windows Credential Manager**, never in a config file,
  and never appear in a `repr`, a log line or an error message (Section 38).
  The only scope requested is `gmail.send`.
* **Gmail needs a one-time admin setup** — a Google Cloud OAuth client and a
  sending account (Section 24.4 calls this team/admin setup, not a member's
  task). Steps and the Testing-mode gotchas are in
  [docs/email.md](docs/email.md); `python scripts/setup_gmail.py status` reports
  what is missing without sending anything.

## Documentation

* [docs/architecture.md](docs/architecture.md) — how the merged subsystems fit
  together and which parts are still missing
* [docs/date-rules.md](docs/date-rules.md) — the Egyptian temporal layer's three
  fixed bugs and the matching rules they imply
* [docs/data-model.md](docs/data-model.md) — storage conventions and the
  decisions behind the schema
* [docs/email.md](docs/email.md) — report rendering, Gmail delivery and the
  retry contract
* [docs/testing.md](docs/testing.md) — how to run the suite and what it covers
* [NEXA.md](NEXA.md) — the full project specification
