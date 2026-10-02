# Architecture

How the merged subsystems fit together, what is missing, and the rules that keep
six parallel work packages from colliding. The full specification is
[NEXA.md](../NEXA.md); this is the map of what actually exists in the repository.

## Two executables

```
Nexa.exe                     NexaWorker.exe
  dashboard, recording,        no UI; claims due reminders,
  review, preview, send        sends them, retries, logs
        \                             /
         \                           /
          +---- nexa.db (SQLite) ----+
               the single source of truth
```

Neither process trusts the other's memory. SQLite is the only shared state, so
closing the GUI cannot stop a reminder and a crashed worker cannot lose one
(Sections 3–5).

## Layers

```
         audio/  asr/            intelligence/  dates/  dedup/
         (Member 2)                      (Member 3)
              |                               |
       transcript segments            action candidates
              |                               |
              +---------- human review -------+        <- nothing is saved
                              |                           before approval
                              v
                core/  data/  people/  search/  audit/   (Member 1)
                              |
              +---------------+---------------+
              |                               |
      reports/  email/                 scheduling/  worker/
        (Member 4)                        (Member 5)
              |                               |
              +--------- ui/  i18n/  themes/ -+        (Member 6)
```

Dependencies point inward: `reports/` and `email/` know about `contracts/` and
`core/`, never about `ui/` or `worker/`. `data/` knows about no feature package
at all.

## What is in the repository

| Package | Owner | State |
|---|---|---|
| `src/nexa/contracts/` | shared | Domain models and service protocols for all six members |
| `src/nexa/core/` | 1 | Config, clock, timezone, errors, validation |
| `src/nexa/data/` | 1 | SQLite open/migrate, transactions, repositories, backup |
| `src/nexa/people/` | 1 | Employees, roles, recipient resolution |
| `src/nexa/search/` | 1 | Employee/meeting/task search, filters, global search |
| `src/nexa/audit/` | 1 | Append-only audit trail |
| `src/nexa/intelligence/` | 3 | LLM runtime, extraction, confidence, JSON repair |
| `src/nexa/dates/` | 3 | Egyptian and English temporal normalization |
| `src/nexa/dedup/` | 3 | Embeddings, similarity, duplicate detection |
| `src/nexa/reports/` | 4 | Report rendering in AR / EN / BILINGUAL |
| `src/nexa/email/` | 4 | Gmail OAuth and sending, MIME, preview, personalization |

### Not merged yet

| Expected by Section 18 | Owner |
|---|---|
| `src/nexa/audio/`, `src/nexa/asr/` | 2 |
| `src/nexa/scheduling/`, `src/nexa/worker/` | 5 |
| `src/nexa/ui/`, `src/nexa/i18n/`, `src/nexa/themes/` | 6 |
| `apps/nexa_desktop.py`, `apps/nexa_worker.py` | 6 (worker packaging with 5) |
| `resources/translations/`, `resources/icons/`, `resources/themes/` | 6 |
| `models/whisper/`, `models/llm/` | 2 / 3 (downloaded, gitignored) |
| `tests/e2e/`, `tests/audio/` | 6 / 2 |
| `scripts/download_models.py`, `scripts/benchmark_asr.py` | 2 |
| `scripts/build_windows.py` | 6 |
| `docs/demo-script.md` | 6 (needs the UI and worker to exist) |

Nobody has stubbed these out on purpose: an empty package created by the wrong
member is a merge conflict waiting to happen, and Section 19 rule 7 puts each
directory behind one owner.

## The contracts package

`src/nexa/contracts/` is the Section 17 kickoff artifact: domain dataclasses plus
`Protocol` service interfaces, and no implementation. It is what lets each member
build against a dependency that does not exist yet by writing a fake for it.

```python
class EmailSender(Protocol):
    def send(self, message: RenderedEmail) -> SendResult: ...
```

`GmailSender` and `FakeEmailSender` both satisfy that, which is why Member 5's
worker stress tests and Member 6's screens run with no Gmail account. The same
pattern covers transcription, extraction and the reminder queue.

Contracts are deliberately small and change rarely. The one change so far is the
`BILINGUAL` member added to `EmailLanguage`; see [email.md](email.md).

## Rules that make the split work

* **Time is injectable.** Nothing calls `datetime.now()`. Everything takes a
  `Clock`, so tests pin "now" and overdue/today/this-week logic is deterministic.
* **UTC in storage, Cairo on screen.** A naive datetime from the UI is read as
  local time. Dates in an email are formatted from the local calendar day, or a
  late-evening UTC deadline reports the wrong weekday.
* **Evidence is never overwritten.** `source_text`, `raw_date_phrase` and
  `raw_text` keep the original wording — including Arabic/English
  code-switching — and the normalized interpretation lives in separate columns
  (Section 2.2). The report carries the original phrase through to the reader.
* **Nothing is saved before a human approves it.** Extraction produces
  candidates; the review screen produces action items.
* **Uncertainty is shown, not guessed.** No owner means `Unassigned`, no time
  means "Time not specified", an ambiguous date keeps the raw phrase and is
  flagged `NEEDS_REVIEW`.
* **SQLite is the source of truth**, including for reminder state, so the worker
  and the GUI cannot disagree.
* **One owner per directory**, and cross-package calls go through the public
  service or the contract — never another member's private module.

## Where ownership has been crossed

Two places, both annotated in the code and both flagged for their owner:

1. `migrations/004_bilingual_email_language.sql` — Member 4 added a migration to
   Member 1's directory, because the BILINGUAL mode cannot be persisted under
   `001_initial.sql`'s CHECK constraints.
2. `src/nexa/data/database.py` — `migrate()` now reconnects after applying
   migrations, because an in-place schema edit is invisible to the connection
   that made it.

Member 3's packages were also relocated from the repository root into
`src/nexa/` to match Section 18, with their imports rewritten and no logic
changed.

## Testing

Every suite runs offline, from one command, with no microphone, model file,
Gmail account or network. `python -m pytest`; see [testing.md](testing.md) for
the layout and [email.md](email.md) for the report/Gmail specifics.
