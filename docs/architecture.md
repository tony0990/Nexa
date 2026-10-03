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
| `src/nexa/audio/` | 2 | Device listing, mic/loopback/combined capture, chunking, mixing, VAD |
| `src/nexa/asr/` | 2 | faster-whisper engine, model registry, benchmark harness, metrics |
| `src/nexa/intelligence/` | 3 | LLM runtime, extraction, confidence, JSON repair, `ExtractionService` |
| `src/nexa/dates/` | 3 | Egyptian and English temporal normalization |
| `src/nexa/dedup/` | 3 | Embeddings, similarity, duplicate detection |
| `src/nexa/reports/` | 4 | Report rendering in AR / EN / BILINGUAL |
| `src/nexa/email/` | 4 | Gmail OAuth and sending, MIME, preview, personalization |
| `src/nexa/scheduling/` | 5 | Reminder rules, SQLite queue, snooze, completion, reschedule, recovery |
| `src/nexa/worker/` | 5 | Worker loop, claiming, retry, heartbeat, single instance, Windows startup |
| `apps/nexa_worker.py` | 5 | `NexaWorker.exe` entry point |

### Not merged yet

| Expected by Section 18 | Owner |
|---|---|
| `src/nexa/ui/`, `src/nexa/i18n/`, `src/nexa/themes/` | 6 |
| `apps/nexa_desktop.py` | 6 |
| `resources/translations/`, `resources/icons/`, `resources/themes/` | 6 |
| `models/whisper/`, `models/llm/` | 2 / 3 (downloaded, gitignored) |
| `tests/e2e/`, `tests/audio/` | 6 / 2 |
| `scripts/download_models.py`, `scripts/benchmark_asr.py` | 2 |
| `scripts/build_windows.py` | 6 |
| `docs/demo-script.md` | 6 (needs the UI and worker to exist) |

Nobody has stubbed these out on purpose: an empty package created by the wrong
member is a merge conflict waiting to happen, and Section 19 rule 7 puts each
directory behind one owner. [remaining-work.md](remaining-work.md) is the full
audit, including the parts that need hardware or a human rather than code.

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

All annotated in the code and flagged for their owner:

1. `migrations/004_bilingual_email_language.sql` — Member 4 added a migration to
   Member 1's directory, because the BILINGUAL mode cannot be persisted under
   `001_initial.sql`'s CHECK constraints.
2. `src/nexa/data/database.py` — `migrate()` now reconnects after applying
   migrations, because an in-place schema edit is invisible to the connection
   that made it.
3. `src/nexa/contracts/email.py` — `SendResult` gained `retryable`, which
   Member 5's worker needs and Member 4 owns (Section 24.1). Additive.
4. `src/nexa/audit/event_types.py` — four names added for the worker, which had
   been using a parallel vocabulary. Additive; see
   [integration.md](integration.md).
5. `src/nexa/scheduling/` and `src/nexa/worker/` — Member 5's packages were
   relocated out of a nested `Nexa/` directory and adapted to the canonical
   contracts. Their private copy of `contracts/` was deleted.

`src/nexa/contracts/` — every service protocol is now `@runtime_checkable`.
Member 2 marked theirs; the other eight were not, so an `isinstance` check
against them raised `TypeError`. Additive and uniform.

Member 3's packages were relocated from the repository root into `src/nexa/`
to match Section 18, with their imports rewritten and no logic changed. Three
bugs in them were later fixed on request; see [date-rules.md](date-rules.md).

## Testing

Every suite runs offline, from one command, with no microphone, model file,
Gmail account or network. `python -m pytest`; see [testing.md](testing.md) for
the layout and [email.md](email.md) for the report/Gmail specifics.

Per-member suites use fakes for what they do not own, which is what made
parallel work possible and is also why they cannot catch a join that is wrong.
`tests/integration/test_cross_member.py` and `tests/integration/test_worker_app.py`
exist for that; [integration.md](integration.md) records what they caught.
