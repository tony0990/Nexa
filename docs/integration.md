# What broke when the work packages were actually joined

Section 17's plan worked: six members built in parallel against fakes and
nobody sat idle. The cost is that every fake is a guess about somebody else's
code, and a guess that is never run is a guess that is wrong.

This is the record of what the Member 5 merge actually broke, because the
pattern will repeat when Members 2 and 6 land.

Every defect below shares one shape: **each member's suite was green.** Member
5's 38 tests passed. Mine passed. Member 1's passed. The system still could not
send a single reminder.

## 1. A private copy of the frozen contracts

Member 5's upload included its own `src/nexa/contracts/` — all five modules,
each subtly different from the canonical ones. Section 17 calls the contracts
package a kickoff artifact to be frozen early, and it is in the repository; a
second copy is not a fork, it is a divergence that compiles.

What differed, and what each cost:

| | Member 5's copy | Canonical | Consequence |
|---|---|---|---|
| `DeliveryTarget` field order | `delivery_kind, target_type, target_id, …` | `id, meeting_id, action_item_id, delivery_kind, …` | built positionally → `"REMINDER"` bound to `id`, `target_type` stayed `"ALL"`, **every reminder resolved to zero recipients** |
| `RenderedEmail` recipient | `to: list[str]` | `to_email: str` | `AttributeError` on send |
| `SendResult` | `success`, `message_id`, `error`, `retryable` | `ok`, `gmail_message_id`, `error_message` | every field read on the send path |
| `AuditEvent.actor_type` default | `"system"` | `ActorType.SYSTEM` = `"SYSTEM"` | `audit_events.actor_type` is `CHECK (… IN ('USER','SYSTEM','WORKER'))` → **every worker audit write would fail** |
| `Reminder` | mutable, `id` required | frozen, all optional | harmless here; nothing mutated one |

The `DeliveryTarget` one is the instructive failure. Positional construction
against a dataclass is silent when the field *count* still matches: no
exception, no warning, just an object whose fields mean something else. The
worker claimed reminders, resolved nobody, and recorded `NO_RECIPIENTS`
forever.

**Resolution.** The private copy was deleted and Member 5's code adapted to the
canonical contracts. Canonical won not by seniority but because it matches
Member 1's schema: `email_deliveries.recipient_email` is one address and the
column is `gmail_message_id`, so `to: list[str]` and `message_id` were never
storable.

**Rule.** Never vendor a copy of `contracts/`. Import it. Construct dataclasses
with keyword arguments — a positional call is a silent misbinding waiting for
someone to reorder a field.

## 2. The retry contract did not exist

Member 5's worker needs to know whether a failed send is worth retrying. Their
`SendResult` had a `retryable` flag. The canonical one did not.

This was **my** omission, not theirs. Section 24.1 makes "retryable vs
permanent errors" Member 4's owned feature, and I built it properly — a full
taxonomy in `nexa.email.errors`, with `classify_status` and `EmailError.retryable`
— and then `EmailService.send` caught those exceptions and returned
`SendResult(ok=False, error_message=str(exc))`, dropping the one bit the worker
needed. The classification was correct and unreachable.

**Resolution.** Canonical `SendResult` gained `retryable: bool = True`, set from
the taxonomy by `GmailSender`, `EmailService` and `FakeEmailSender`. It defaults
to True for the same reason `classify_status` does: a retried reminder is
recoverable, a dropped one is not.

**Rule.** Owning a decision means owning its delivery. If the only channel to
the consumer cannot carry the answer, the feature is not done.

## 3. The audit vocabulary was split in two

Member 5 defined `AuditNames` with its own strings — `"reminder.create"`,
`"action.mark_complete"`, `"worker.start"`. Member 1's `audit/event_types.py`
defines `"reminder.created"`, `"action.completed"`, and nothing for the worker.
That file says the names are "written into the database forever… never renamed,
only added to".

Two vocabularies for one event stream means the audit-trail screen filters on
one spelling and half the history is invisible. Nothing would have failed; the
UI would just have been quietly incomplete.

**Resolution.** `AuditNames` now *aliases* `event_types`, so there is one
spelling and a rename fails at import instead of silently writing an unknown
event. Four names were added to Member 1's canonical file —
`reminder.retry_scheduled`, `reminder.late_recovered`, `worker.started`,
`worker.stopped` — rather than collapsing retry into failure and late recovery
into an ordinary send, which would have lost the distinction the trail exists to
show.

**Rule.** Event names are schema. Add to the canonical list; never define a
parallel one.

## 4. The tests ran against a schema nobody ships

Member 5's conftest hand-wrote its `CREATE TABLE` statements, with a comment
saying they mirrored Section 16. They were close, and they had **no CHECK
constraints and no foreign keys**.

Pointing the fixture at Member 1's real migrations immediately surfaced three
production bugs that the hand-copy had been hiding:

* `email_deliveries.subject` is `NOT NULL`; the recorder inserted `None`
  whenever there was no rendered email — so the delivery log crashed on exactly
  the failure it was trying to record.
* `email_deliveries.language` is `CHECK (language IN ('AR','EN','BILINGUAL'))`;
  the worker's fallback default was `"ENGLISH"`, so when the settings row was
  missing **every** delivery insert failed.
* `action_items.owner_employee_id` has a foreign key; the test employees only
  ever existed as Python objects.

**Rule.** An integration test that builds its own schema is a unit test wearing
a costume. Use the migrations.

## 5. The composition root had never been run

`apps/nexa_worker.py:build_dependencies` is where all six work packages meet.
It carried a comment to "adjust constructor arguments to their final
signatures", and all of them were still placeholders:

* `AuditService(factory)` and `RecipientResolver(factory)` — both take Member
  1's `Database` and a `Clock`, not a connection factory.
* `EmailService()` passed as `email_sender` — but that slot is the `EmailSender`
  protocol, `send(rendered) -> SendResult`. `EmailService` is the orchestrator
  and returns a `DeliveryAttempt`. The right object is `GmailSender`.
* No migration, so a worker starting before the GUI died on
  `no such table: settings`. Section 3.2's loop opens with "Open SQLite
  database" and the worker is allowed to be first.
* `--status` raised `sqlite3.OperationalError` on an un-migrated file — and the
  GUI polls `--status`.

**Rule.** A composition root with no test is not wiring, it is a diagram. There
is now `tests/integration/test_worker_app.py`, which runs it.

## What the suite looks like now

| | Covers |
|---|---|
| `tests/unit/memberN/`, `tests/integration/memberN/` | each package against its own fakes — fast, and the reason parallel work was possible |
| `tests/integration/test_cross_member.py` | the **real** seams: Member 4's `ReportService` and Member 1's `RecipientResolver` inside Member 5's worker, over a migrated database, with only the Gmail transport faked |
| `tests/integration/test_worker_app.py` | the composition root, and `NexaWorker.exe`'s CLI on missing, un-migrated and fresh databases |

Three of the cross-member tests fail if any of the above is reintroduced. That
is deliberate: the per-member suites cannot catch these, by construction.

## For Members 2 and 6

Expect the same five categories. Before you push:

1. Import `nexa.contracts`. Do not copy it.
2. Construct every shared dataclass with keyword arguments.
3. Point your test fixtures at `open_database()`, not at a hand-written schema.
4. Use `nexa.audit.event_types` for event names; add to it if yours is missing.
5. If you have a composition root or an entry point, write a test that executes
   it.

## Related

* [architecture.md](architecture.md) — the layer map and who owns what
* [email.md](email.md) — the retry taxonomy and the Member 1 delivery seam
* [date-rules.md](date-rules.md) — the same "silently wrong" pattern inside one
  package
