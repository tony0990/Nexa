# Nexa

Smart Meeting Voice AI & Reminder desktop application for Windows.
Full specification, architecture and team ownership: [NEXA.md](NEXA.md).

This branch contains **Member 1's work package** — the local data platform
every other subsystem is built on — plus the shared `contracts` package from
the Section 17 kickoff.

## What is implemented here

| Area | Package | Status |
|---|---|---|
| Shared contracts (kickoff artifact) | `src/nexa/contracts/` | Domain models + service protocols for all six members |
| Config, clock, timezone, errors, validation | `src/nexa/core/` | Done |
| SQLite setup, migrations, transactions, repositories, backup | `src/nexa/data/` | Done |
| Employees, roles, recipient resolution | `src/nexa/people/` | Done |
| Search, filters, global search | `src/nexa/search/` | Done |
| Append-only audit trail | `src/nexa/audit/` | Done |

Audio/ASR (Member 2), extraction (3), email (4), scheduling/worker (5) and
the desktop UI (6) are not in this branch.

## Requirements

Python 3.10+ (the project targets 3.11/3.12). The data platform has no
third-party runtime dependency except `tzdata`, which Windows needs for the
`Africa/Cairo` rules.

```bash
pip install -r requirements/dev.txt
```

## Quick start

```bash
python -m pytest
```

```bash
python scripts/seed_demo_data.py --data-dir ./demo-data --reset
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

## Public interfaces (Section 21.3)

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

Other members call these; nobody imports another member's private modules or
writes SQL against another member's tables (Section 19).

## Notes for the rest of the team

* **The database creates itself.** `open_database(config)` on an empty folder
  runs every migration in order. Re-running is a no-op.
* **Time is injectable.** Nothing calls `datetime.now()`; pass a `Clock`
  (`SystemClock` in the app, `FixedClock` in tests).
* **Everything is UTC in storage, Cairo on screen.** A naive datetime from the
  UI is read as local time.
* **Evidence is never overwritten.** `source_text`, `raw_date_phrase` and
  `raw_text` keep the original wording; the normalized interpretation lives in
  separate columns.
* **Arabic search is spelling-tolerant.** `احمد` finds `أحمد`; see
  [docs/data-model.md](docs/data-model.md).
* **Recipient resolution de-duplicates by employee *and* email**, and reports
  who it skipped and why instead of dropping them silently.
* **Deactivate, don't delete.** Inactive employees never receive email but
  stay attached to their history.

## Documentation

* [docs/data-model.md](docs/data-model.md) — storage conventions and the
  decisions behind the schema
* [docs/testing.md](docs/testing.md) — how to run the suite and what it covers
* [NEXA.md](NEXA.md) — the full project specification
