# NEXA — Smart Meeting Voice AI & Reminder Desktop Application

## Team Build Plan, Architecture, Ownership & File Structure

**Target:** Windows desktop application (`Nexa.exe`) + background reminder process (`NexaWorker.exe`)  
**Primary language environment:** Egyptian Arabic + English + Arabic/English code-switching  
**Notification channel for V1:** Gmail  
**Core cost target:** Zero recurring software cost  
**Timezone:** `Africa/Cairo`  
**Team size:** 6 members  
**Document purpose:** Give every team member a complete mental model of the project, a clear independent work package, owned files, interfaces, test targets, and integration rules.

---

# 1. Project Overview


## Language & Employee Entry Rules — Final Decision

These rules are fixed for the current Nexa scope:

- The application UI can be switched between **Arabic and English**.
- Email/report language is selected as **Arabic OR English only** for each send/report. There is no bilingual email mode.
- The Review/Confirmation screen must preserve the **original spoken sentence exactly as it was transcribed/confirmed by the user**, including Arabic-English code-switching.
- The professional email is generated from the approved structured data and is written formally in the selected language; it does not copy colloquial speech verbatim.

Example original evidence:

`الـpresentation Thursday الساعة three`

Possible Arabic email wording:

`يرجى التأكد من جاهزية العرض التقديمي يوم الخميس في تمام الساعة الثالثة.`

Possible English email wording:

`Please ensure that the presentation is ready by Thursday at 3:00 PM.`

## 1.1 What is Nexa?

Nexa is a local-first Windows desktop application that listens to a meeting, transcribes the meeting locally, understands Egyptian Arabic, English, and mixed Arabic-English speech, and extracts only actionable information that is connected to a date, time, deadline, appointment, or scheduled meeting.

Nexa is **not** intended to summarize every sentence in the meeting. Its main purpose is to transform spoken scheduling information into structured, reviewable, trackable actions and reminders.

The system should support this full workflow:

1. The admin starts a meeting in Nexa.
2. Nexa records microphone audio, computer audio, or both.
3. Speech is transcribed locally.
4. The original transcript is preserved for review.
5. The AI extracts only tasks, dates, deadlines, appointments, owners, and time-related commitments.
6. Nexa shows the extracted items before saving anything.
7. The admin can edit, delete, assign, merge, or manually add items.
8. Nexa keeps the exact original phrase that caused each extraction as evidence.
9. The admin chooses report recipients by employee, role, meeting participant, assignee, or everyone.
10. The admin chooses the report language: Arabic, English, or Arabic or English Arabic + English.
11. Nexa generates a formal professional email report.
12. The admin previews and approves the email.
13. Nexa sends the meeting report through Gmail.
14. Nexa creates reminder records for future deadlines.
15. `NexaWorker.exe` continues checking reminders even when the main GUI is closed.
16. At the correct time, the worker sends personalized reminder emails.
17. The system records every important action in an audit trail.
18. Tasks can later be searched, filtered, completed, snoozed, edited, or cancelled.

---

# 2. Important Design Decisions

## 2.1 Human approval is mandatory

AI output is never saved directly as final truth.

```text
Meeting Audio
    ↓
Speech-to-Text
    ↓
AI Candidate Extraction
    ↓
Human Review
    ↓
Human Approval
    ↓
Database + Reminders + Email
```

If Nexa is uncertain, it must show uncertainty instead of inventing information.

Examples:

- No owner mentioned → `Unassigned`
- No time mentioned → `Time not specified`
- Ambiguous date → keep the raw phrase and mark `Needs Review`
- Several employees named Ahmed → ask the admin to choose the correct employee

---

## 2.2 The original wording must never be lost

If a person says:

> `الـpresentation Thursday الساعة three`

Nexa should preserve exactly that confirmed phrase in the review/evidence section.

It may separately show:

```text
Original phrase:
الـpresentation Thursday الساعة three

Nexa interpretation:
Date: Thursday, 10 September 2026
Time: 3:00 PM
```

The normalized interpretation must **not overwrite** the original phrase.

This gives the system traceability and allows the admin to check why Nexa made a decision.

---

## 2.3 Three separate language settings

Language is handled at three independent levels.

| Setting | Options | Purpose |
|---|---|---|
| Application UI Language | Arabic / English | Menus, buttons, labels, dialogs |
| Email / Report Language | Arabic / English | Professional meeting reports and reminders |
| Spoken Meeting Language | Automatic multilingual | Arabic, English, Egyptian Arabic, or mixed speech |

Changing the UI to Arabic must not force emails to Arabic.

Example:

- UI language: Arabic
- Meeting language: mixed Arabic-English
- Email language: English

This is valid.

---

# 3. What is `NexaWorker.exe`?

The application is intentionally split into two executables.

## 3.1 `Nexa.exe`

This is the application the user sees.

It contains:

- Dashboard
- Meeting recording
- Review screen
- Employee management
- Roles
- Search
- Filters
- Email preview
- Schedule
- History
- Settings
- Dark mode
- Arabic / English UI

When the user closes this window, the GUI should not need to remain open just to send reminders.

---

## 3.2 `NexaWorker.exe`

`NexaWorker.exe` is a small background process whose main job is to handle scheduled work.

It does **not** need to display the full UI.

Its loop is conceptually:

```text
Start Worker
    ↓
Open SQLite database
    ↓
Find pending reminders whose due time has arrived
    ↓
Claim reminder safely
    ↓
Build personalized email
    ↓
Send using Gmail API
    ↓
Success?
    ├─ Yes → mark SENT + write log
    └─ No  → retry according to retry policy
    ↓
Wait
    ↓
Repeat
```

The worker can be configured to launch automatically with Windows.

### Why have a worker instead of leaving `Nexa.exe` open?

Because the user may close the main application after the meeting. A reminder system should not depend on keeping a large GUI window open.

The worker is:

- smaller
- easier to restart
- easier to test
- less memory intensive
- independent from the UI
- responsible only for background jobs

---

# 4. Why Nexa Should Own Scheduling Instead of Gmail

Gmail's normal user interface contains a **Schedule Send** feature. However, the Gmail API currently exposes sending operations such as `messages.send` and `drafts.send`, but it does not provide a public API operation that lets Nexa create Gmail's native scheduled-send entries directly.

Therefore the correct architecture is:

```text
Nexa Database
    ↓
Scheduled reminder record
    ↓
NexaWorker.exe waits until due_at
    ↓
Gmail API sends message at that time
```

This is actually safer for Nexa because all scheduling logic remains under our control.

## 4.1 Example

Suppose the system has these tasks:

```text
Reminder A
Task: Database
Due: Monday 10:00 AM
Reminder: Sunday 8:00 PM

Reminder B
Task: HR List
Due: Monday 12:00 PM
Reminder: Monday 8:00 AM

Reminder C
Task: Presentation
Due: Monday 3:00 PM
Reminder: Monday 8:00 AM
```

These are not stored as one combined timer.

They become three separate database records with three unique IDs.

```text
reminder_id = 1001
scheduled_at = 2026-09-06 20:00
status = PENDING

reminder_id = 1002
scheduled_at = 2026-09-07 08:00
status = PENDING

reminder_id = 1003
scheduled_at = 2026-09-07 08:00
status = PENDING
```

At 8:00 AM, the worker can safely send reminder 1002 and 1003 separately.

No reminder gets confused with another.

---

# 5. Reminder Safety: Preventing Duplicate or Mixed Sends

Every reminder has its own:

- reminder ID
- action item ID
- recipient IDs
- scheduled timestamp
- reminder type
- current status
- attempt count
- last error
- sent timestamp
- idempotency key

Recommended states:

```text
PENDING
CLAIMED
SENDING
SENT
RETRY_WAIT
FAILED
CANCELLED
SNOOZED
SKIPPED_COMPLETED
```

Before sending a reminder, the worker performs a database transaction to claim it.

This prevents two worker loops from sending the same reminder twice.

Conceptually:

```text
UPDATE reminders
SET status = 'CLAIMED'
WHERE id = ?
  AND status = 'PENDING';
```

If zero rows were updated, another process already claimed it or it is no longer eligible.

---

# 6. Final V1 Feature Set

## 6.1 Meeting Intelligence

- Record microphone
- Record Windows computer audio
- Record microphone + computer audio
- Long meeting support
- Local STT
- Egyptian Arabic support
- English support
- Arabic-English code switching
- Editable transcript
- Preserve confirmed transcript
- Extract several actions from one meeting
- Extract owner when explicitly mentioned
- Extract date
- Extract time
- Extract deadline
- Extract scheduled meeting/appointment
- Confidence score
- Evidence/source phrase
- Human review
- Manual add
- Edit
- Delete
- Duplicate detection

---

## 6.2 Employees and Roles

- Add employee
- Edit employee
- Remove/deactivate employee
- Employee email
- Department
- Job title
- Multiple roles per employee
- Add/edit/delete roles
- Search employee
- Filter employees
- Active/inactive state

---

## 6.3 Recipient Targeting

Report and reminder recipients are independent.

Possible target types:

- All employees
- Everyone in the meeting
- Selected roles
- Specific employees
- Assigned employee only
- Assigned employee + selected role
- Custom combination

Duplicate recipients must be removed automatically.

---

## 6.4 Search

Global search should support:

### Employee search

Search by:

- full name
- email
- department
- job title
- role

### Meeting search

Search by:

- meeting title
- date
- participant
- extracted task text

### Task search

Search by:

- task name
- owner
- meeting
- date
- status
- evidence text

A global search bar can later search all three categories at once.

---

## 6.5 Filters

Recommended filters:

### Tasks

- Today
- Tomorrow
- This week
- Next week
- This month
- Upcoming
- Overdue
- Completed
- Pending
- Snoozed
- Unassigned
- By employee
- By role
- By meeting

### Meetings

- Today
- This week
- This month
- Approved
- Pending review
- Has failed email

### Employees

- Active
- Inactive
- Department
- Role

---

## 6.6 Mark Complete

Every action item can be marked complete.

When marked complete:

1. `action_items.status = COMPLETED`
2. Completion timestamp is recorded.
3. Actor is recorded in audit trail.
4. Future unsent reminders for that action are cancelled or marked `SKIPPED_COMPLETED`.
5. The dashboard updates immediately.

Optional later behavior:

- send a completion notification
- ask for completion notes

Not required for V1.

---

## 6.7 Snooze

A user can snooze a pending reminder.

Options:

```text
30 minutes
1 hour
3 hours
Tomorrow morning
Custom date/time
```

Snoozing does not modify the actual task deadline.

It modifies or creates the reminder occurrence only.

Example:

```text
Task deadline: Monday 3:00 PM
Original reminder: Monday 8:00 AM
Snoozed reminder: Monday 10:00 AM
```

The deadline remains 3:00 PM.

All snooze actions are written to the audit log.

---

# 7. Duplicate Detection

Duplicate detection is needed because the same deadline may be repeated several times in a meeting.

Example:

> `التقرير يتسلم الخميس.`

Later:

> `متنسوش التقرير يوم الخميس.`

Nexa should usually create one action candidate, not two unrelated tasks.

Duplicate detection should use multiple signals:

- normalized task similarity
- same or close deadline
- same owner
- same meeting
- semantic similarity from the local model

Possible outcomes:

```text
NOT_DUPLICATE
POSSIBLE_DUPLICATE
AUTO_MERGE_SAFE
```

Auto-merge should only happen when confidence is high.

Otherwise the Review UI displays:

```text
Possible duplicate detected

[ Keep Both ]
[ Merge ]
```

Never silently delete uncertain information.

---

# 8. Meeting Templates

Meeting templates reduce repetitive setup.

Examples:

- Weekly Team Meeting
- Project Review
- Management Meeting
- HR Meeting
- Department Stand-up
- Custom

A template can define:

| Field | Example |
|---|---|
| Meeting name pattern | Weekly Development Meeting |
| Default audio source | Mic + Computer |
| Default participants | Development Team |
| Default report recipients | Managers + Participants |
| Default reminder recipients | Assignee |
| Default email language | Arabic or English |
| Default reminder rules | Previous day 8 PM + event day 8 AM |

Templates do not contain AI behavior. They contain meeting configuration defaults.

---

# 9. Email Preview

No meeting report should be sent without a preview option.

Preview screen should show:

- From account
- To recipients
- Cc if supported later
- Subject
- selected language
- rendered HTML email
- plain-text fallback
- action item table

Buttons:

```text
[ Back to Review ]
[ Edit Recipients ]
[ Change Language ]
[ Refresh Preview ]
[ Send Now ]
```

For reminders:

```text
[ Preview Reminder Template ]
```

can be available in Settings and on each task.

---

# 10. Professional Email Languages

The user chooses one of three modes for every report or from meeting-template defaults.

## 10.1 Arabic

Formal Arabic suitable for institutional communication.

The email should not copy casual meeting speech directly into the report body except where evidence is intentionally shown.

Example task spoken as:

> `أحمد يخلص الـbackend قبل Monday`

Professional Arabic report version:

> استكمال أعمال الواجهة الخلفية (Backend) — المسؤول: أحمد — الموعد النهائي: يوم الاثنين.

---

## 10.2 English

Professional business English.

Example:

> Complete the backend implementation — Owner: Ahmed — Deadline: Monday.

---

## 10.3 Arabic or English

Recommended layout:

```text
NEXA
Meeting Action Report | تقرير مهام الاجتماع

Meeting | الاجتماع
Digital Transformation Weekly Meeting

Date | التاريخ
4 September 2026 | 4 سبتمبر 2026

Action Items | المهام
...
```

Do not mechanically translate employee names.

Technical terms can remain in English when that is clearer.

---

# 11. Personalized Reminders

Meeting reports may be shared with a large group, but reminders should be personalized to the recipient.

Example for Ahmed:

```text
Subject:
[Nexa Reminder] Database Integration — Due Tomorrow

Dear Ahmed,

This is a reminder that your assigned action item
"Database Integration"
is due tomorrow.

Deadline: Monday, 7 September 2026
Meeting: Weekly Development Meeting

Regards,
Nexa
```

Arabic and Arabic or English versions must be available.

A recipient should receive only the tasks relevant to them unless the admin explicitly targets them for broader reminders.

---

# 12. Audit Trail

Nexa should record important changes rather than only storing the final state.

Examples:

```text
10:00  Meeting created
10:02  Recording started
10:48  Recording stopped
10:51  AI extraction completed
10:55  Action #17 date changed from Sep 8 to Sep 9
10:55  Changed by Admin
10:57  Action #18 assigned to Ahmed Hassan
11:00  Meeting approved
11:01  Report sent to 8 recipients
Sep 8 20:00  Reminder sent to Ahmed Hassan
Sep 9 09:10  Action marked complete
```

Recommended audited events:

- meeting create/edit/delete
- recording start/stop
- extraction completion
- action item create/edit/delete
- duplicate merge
- owner assignment
- status change
- mark complete
- snooze
- reminder create/cancel/send/fail
- email send
- employee create/edit/deactivate
- role changes
- settings changes

Audit records should be append-only through the normal application UI.

---

# 13. High-Level Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                        Nexa.exe                              │
│                    PySide6 Desktop UI                       │
└──────┬─────────────┬─────────────┬──────────────┬────────────┘
       │             │             │              │
       ▼             ▼             ▼              ▼
  Meeting UI    Admin/People   Search/Filters   Email Preview
       │             │             │              │
       └─────────────┴──────┬──────┴──────────────┘
                            ▼
                 Application Services
                            │
       ┌────────────────────┼──────────────────────┐
       ▼                    ▼                      ▼
 Audio + ASR          Meeting Intelligence      Data Layer
       │                    │                      │
       ▼                    ▼                      ▼
 Local Audio           Local LLM + Dates        SQLite
 Recording             + Validation             Database
                            │                      │
                            ▼                      ▼
                     Action Candidates      Approved Items
                                                   │
                   ┌───────────────────────────────┤
                   ▼                               ▼
            Report / Gmail                 Reminder Queue
                   │                               │
                   ▼                               ▼
             Gmail API                     NexaWorker.exe
                                                   │
                                                   ▼
                                              Gmail API
```

---

# 14. Technology Stack

| Area | Recommended Tool | Cost | Internet | Notes |
|---|---|---:|---|---|
| Language | Python 3.11/3.12 | $0 | No | Main development language |
| GUI | PySide6 / Qt | $0 | No | Professional native desktop UI |
| Database | SQLite | $0 | No | Local source of truth |
| ORM/Data access | SQLAlchemy or explicit sqlite3 repositories | $0 | No | Choose one approach and keep it consistent |
| Audio capture | PyAudioWPatch / WASAPI | $0 | No | Supports Windows loopback |
| VAD | Silero VAD | $0 | No | Detect speech / silence |
| STT runtime | faster-whisper | $0 | No after model download | Efficient local Whisper runtime |
| STT candidates | Whisper multilingual + Egyptian code-switch model | $0 | No after download | Benchmark before final selection |
| Local LLM | Qwen3 4B GGUF candidate | $0 | No after download | Structured extraction |
| LLM runtime | llama.cpp | $0 | No | Local inference |
| Date parsing | dateparser + custom Egyptian rules | $0 | No | Deterministic temporal layer |
| Templates | Jinja2 | $0 | No | Professional HTML emails |
| Gmail | Gmail API + OAuth2 | $0 for normal project usage | Yes | Actual delivery |
| Secrets | Python keyring / Windows Credential Manager | $0 | No | OAuth token storage |
| Scheduling | SQLite queue + worker + APScheduler/timed loop | $0 | No except send | Database remains source of truth |
| Packaging | PyInstaller | $0 | No | Build Windows executables |
| Testing | pytest | $0 | No | Unit/integration/E2E |

---

# 15. AI Models and Runtime Requirements

## 15.1 Speech-to-Text benchmark candidates

Member 2 must benchmark rather than assume one model is best.

| Candidate | Purpose | Expected Tradeoff |
|---|---|---|
| Whisper Small multilingual | Baseline | Fast / lower resource |
| Whisper Medium multilingual | Accuracy baseline | Slower / stronger general multilingual recognition |
| Egyptian Arabic-English fine-tuned Whisper model | Code-switch candidate | Potentially better Egyptian mixed speech |

Test data must include actual team voices and actual Egyptian code-switching.

Example utterances:

```text
بكرة عندنا meeting الساعة ten.

أحمد يخلص الـbackend before Thursday.

The final report يتبعت يوم الاتنين الساعة four.

الـpresentation تكون ready twenty September.
```

---

## 15.2 Local extraction model

Recommended starting candidate:

```text
Qwen3-4B GGUF
Quantization: Q4_K_M or equivalent practical local quantization
Runtime: llama.cpp
```

The AI output must be constrained to a validated schema.

Example:

```json
{
  "items": [
    {
      "task": "Finish database integration",
      "owner_text": "Ahmed",
      "raw_date_phrase": "قبل يوم الاتنين",
      "resolved_date": "2026-09-07",
      "resolved_time": null,
      "source_text": "أحمد يخلص الـdatabase قبل يوم الاتنين",
      "confidence": 0.94
    }
  ]
}
```

---

# 16. Core Data Model

## 16.1 `employees`

```text
id
full_name
email
department
job_title
active
created_at
updated_at
```

## 16.2 `roles`

```text
id
name
description
active
created_at
updated_at
```

## 16.3 `employee_roles`

```text
employee_id
role_id
```

## 16.4 `meetings`

```text
id
title
template_id
started_at
ended_at
audio_source
status
email_language
created_at
updated_at
```

## 16.5 `meeting_participants`

```text
meeting_id
employee_id
```

## 16.6 `transcript_segments`

```text
id
meeting_id
segment_index
start_ms
end_ms
raw_text
confirmed_text
language_hint
created_at
```

## 16.7 `action_items`

```text
id
meeting_id
task
owner_employee_id
owner_raw_text
raw_date_phrase
due_date
due_time
due_at
source_text
confidence
review_state
status
completed_at
created_at
updated_at
```

Possible `status`:

```text
PENDING
COMPLETED
OVERDUE
CANCELLED
```

## 16.8 `reminder_rules`

```text
id
action_item_id
rule_type
offset_minutes
fixed_local_time
enabled
created_at
```

## 16.9 `reminders`

```text
id
action_item_id
scheduled_at
status
attempt_count
next_attempt_at
claimed_at
sent_at
last_error
idempotency_key
created_at
updated_at
```

## 16.10 `delivery_targets`

```text
id
meeting_id
action_item_id
delivery_kind
    REPORT
    REMINDER

target_type
    ALL
    MEETING_PARTICIPANTS
    ROLE
    EMPLOYEE
    ASSIGNEE

target_id
created_at
```

## 16.11 `email_deliveries`

```text
id
meeting_id
action_item_id
reminder_id
recipient_employee_id
recipient_email
subject
language
status
gmail_message_id
attempted_at
sent_at
error_message
```

## 16.12 `meeting_templates`

```text
id
name
default_title
default_audio_source
default_email_language
default_report_target_config
default_reminder_target_config
default_reminder_rule_config
active
created_at
updated_at
```

## 16.13 `audit_events`

```text
id
actor_type
actor_id
event_type
entity_type
entity_id
old_value_json
new_value_json
metadata_json
created_at
```

## 16.14 `settings`

```text
key
value_json
updated_at
```

Important settings include:

```text
ui_language
theme
timezone
default_email_language
default_evening_reminder_time
default_morning_reminder_time
missed_reminder_recovery_hours
audio_retention_policy
transcript_retention_policy
gmail_sender_display_name
```

---

# 17. Shared Contracts — Freeze These Before Parallel Development

To prevent one member from waiting for another, the team begins with a small shared contracts package.

This is a **kickoff artifact**, not a large implementation owned by one developer.

Everyone agrees to these interfaces before feature development starts.

```text
src/nexa/contracts/
├── audio.py
├── transcription.py
├── extraction.py
├── meetings.py
├── people.py
├── scheduling.py
├── email.py
├── audit.py
└── events.py
```

Example contracts:

```python
class AudioRecordingService:
    def start(self, source: str) -> str: ...
    def stop(self) -> "RecordedAudio": ...


class TranscriptionService:
    def transcribe(self, audio_path: str) -> "Transcript": ...


class ExtractionService:
    def extract(
        self,
        transcript: "Transcript",
        reference_datetime: "datetime"
    ) -> list["ActionCandidate"]: ...


class MeetingRepository:
    def create(self, meeting: "Meeting") -> "Meeting": ...
    def save_action(self, action: "ActionItem") -> "ActionItem": ...


class RecipientResolver:
    def resolve(self, targets: list["DeliveryTarget"]) -> list["Employee"]: ...


class EmailSender:
    def send(self, message: "RenderedEmail") -> "SendResult": ...


class ReminderQueue:
    def enqueue_for_action(self, action: "ActionItem") -> list["Reminder"]: ...
    def claim_due(self, now: "datetime", limit: int) -> list["Reminder"]: ...
```

Each member must create a **fake implementation** of the dependency they do not own.

Examples:

```text
FakeTranscriptionService
FakeExtractionService
FakeEmailSender
FakeReminderQueue
InMemoryEmployeeRepository
```

This means Member 6 can build the entire UI before the real ASR exists.

Member 5 can test scheduling with `FakeEmailSender` before Gmail integration exists.

Member 4 can generate reports using fake employee lists before the final employee database is complete.

No member should sit idle waiting for another member's feature branch.

---

# 18. Shared Repository Structure

```text
Nexa/
│
├── README.md
├── pyproject.toml
├── requirements/
│   ├── base.txt
│   ├── ai.txt
│   ├── dev.txt
│   └── build.txt
│
├── src/
│   └── nexa/
│       │
│       ├── contracts/
│       ├── core/
│       ├── data/
│       ├── people/
│       ├── search/
│       ├── audit/
│       │
│       ├── audio/
│       ├── asr/
│       │
│       ├── intelligence/
│       ├── dates/
│       ├── dedup/
│       │
│       ├── reports/
│       ├── email/
│       │
│       ├── scheduling/
│       ├── worker/
│       │
│       ├── ui/
│       ├── i18n/
│       └── themes/
│
├── apps/
│   ├── nexa_desktop.py
│   └── nexa_worker.py
│
├── resources/
│   ├── email_templates/
│   ├── translations/
│   ├── icons/
│   └── themes/
│
├── models/
│   ├── whisper/
│   └── llm/
│
├── migrations/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── fixtures/
│   └── audio/
│
├── scripts/
│   ├── download_models.py
│   ├── seed_demo_data.py
│   ├── benchmark_asr.py
│   ├── build_windows.py
│   └── create_demo_database.py
│
└── docs/
    ├── architecture.md
    ├── data-model.md
    ├── testing.md
    └── demo-script.md
```

---

# 19. Team Ownership Rules

1. Each file tree below has one primary owner.
2. Other members may call it only through its public service/interface.
3. No member directly imports another member's private implementation modules.
4. Cross-module communication uses contracts and domain models.
5. Every owned module must have fake/test adapters.
6. Every member writes unit tests for their own module.
7. Feature branches must not edit another member's directory without coordination.
8. Shared contracts are intentionally small and frozen early.
9. Integration tests are added after public interfaces are stable.
10. SQLite is the source of truth for application state and reminder state.

---

# 20. Work Distribution Summary

The six work packages are designed to be similar in engineering difficulty and effort.

| Member | Main Ownership | Difficulty | Main Deliverable |
|---|---|---|---|
| 1 | Core Data, Employees, Roles, Search, Filters, Audit | High | Reliable local application/data platform |
| 2 | Audio Capture, STT, Voice Benchmarking | High | Meeting audio → accurate transcript |
| 3 | AI Extraction, Dates, Confidence, Duplicate Detection | High | Transcript → reviewed structured actions |
| 4 | Reports, Gmail, Language Rendering, Personalization | High | Approved data → professional emails |
| 5 | Scheduling, Worker, Snooze, Completion, Reliability | High | Deadlines → reliable background reminders |
| 6 | Desktop UI/UX, i18n UI, Theme, Workflow Shell, Packaging | High | Complete usable Arabic or English Windows application |

Every member has a complete independently testable subsystem.

---

# 21. MEMBER 1 — Core Data, Employees, Roles, Search, Filters & Audit

## Mission

Build the reliable local platform that stores Nexa's data and provides employee/role administration, search/filter APIs, and audit recording.

Member 1 does **not** need real audio, AI, Gmail, or the final UI to finish their subsystem.

---

## 21.1 Owned Features

### Data layer

- SQLite setup
- schema creation
- migrations
- transaction helper
- repository pattern
- database backup helper

### Employees

- create employee
- update employee
- deactivate employee
- reactivate employee
- email validation
- department/job title fields

### Roles

- CRUD roles
- many-to-many employee-role assignment
- remove assignment
- role membership query

### Recipient resolution core

Resolve abstract targets to unique employee records:

```text
ALL
MEETING_PARTICIPANTS
ROLE
EMPLOYEE
ASSIGNEE
```

The Gmail sender itself belongs to Member 4.

### Search

- employee search
- meeting search
- task search
- global search API

### Filters

Backend query filtering for:

- status
- date range
- owner
- role
- meeting
- overdue
- completed
- snoozed
- active/inactive employees

### Audit trail

- append audit event
- query by entity
- query by date
- query by actor
- export audit view model

---

## 21.2 Owned File Structure

```text
src/nexa/
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── clock.py
│   ├── timezone.py
│   ├── errors.py
│   └── validation.py
│
├── data/
│   ├── __init__.py
│   ├── database.py
│   ├── transactions.py
│   ├── models.py
│   ├── repositories/
│   │   ├── employees.py
│   │   ├── roles.py
│   │   ├── meetings.py
│   │   ├── actions.py
│   │   ├── reminders.py
│   │   ├── deliveries.py
│   │   ├── templates.py
│   │   └── audit.py
│   └── backup.py
│
├── people/
│   ├── __init__.py
│   ├── service.py
│   ├── recipient_resolver.py
│   └── validators.py
│
├── search/
│   ├── __init__.py
│   ├── service.py
│   ├── employee_search.py
│   ├── meeting_search.py
│   ├── task_search.py
│   └── filters.py
│
└── audit/
    ├── __init__.py
    ├── service.py
    └── event_types.py

migrations/
├── 001_initial.sql
├── 002_search_indexes.sql
└── 003_audit_indexes.sql

tests/unit/member1/
tests/integration/member1/
```

---

## 21.3 Public Interfaces

```python
PeopleService.create_employee(...)
PeopleService.update_employee(...)
PeopleService.assign_role(...)

RecipientResolver.resolve(targets)

SearchService.search_employees(query, filters)
SearchService.search_meetings(query, filters)
SearchService.search_tasks(query, filters)
SearchService.global_search(query)

AuditService.record(event)
AuditService.history(entity_type, entity_id)
```

---

## 21.4 What Member 1 Needs

| Need | Source |
|---|---|
| Python | Project standard |
| SQLite | Local |
| Shared domain models | Kickoff contracts |
| Sample employees | Own fixtures |
| Sample meetings/tasks | Own fixtures |
| Gmail | Not required |
| Whisper | Not required |
| Local LLM | Not required |
| Final UI | Not required |

---

## 21.5 Independent Testing

Member 1 can create 1,000 fake employees, roles, meetings, and tasks and validate:

- search speed
- filtering
- unique recipient resolution
- transactions
- audit history

---

## 21.6 Definition of Done

- Schema can be created from an empty folder.
- Migrations run safely.
- Employee/role CRUD works.
- Searches produce expected results.
- Filters can be combined.
- Recipient resolution removes duplicates.
- Audit trail records changes.
- All repository/service tests pass.

---

# 22. MEMBER 2 — Audio Capture, STT & Voice Benchmarking

## Mission

Turn a real Windows meeting into a reliable editable transcript while supporting Egyptian Arabic, English, and mixed Arabic-English speech.

Member 2 can work with local audio files and does not need the AI extractor, Gmail, scheduler, database UI, or final UI.

---

## 22.1 Owned Features

### Audio device management

- list microphones
- list output devices
- select source
- test audio source

### Recording modes

- microphone only
- computer audio only
- microphone + computer audio

### Long meeting recorder

- chunking
- temporary files
- clean stop
- failure recovery
- sample-rate normalization

### Voice activity detection

- silence trimming where appropriate
- do not accidentally remove meaningful short speech

### Speech-to-text

- faster-whisper runtime
- model loading
- CPU/GPU detection
- INT8 option
- transcription timestamps
- multilingual handling

### Benchmark system

Compare candidate STT models on real team audio.

Metrics:

- word error rate as a supporting metric
- task keyword accuracy
- date phrase accuracy
- English technical-word accuracy
- mixed Arabic-English accuracy
- runtime
- RAM usage

---

## 22.2 Owned File Structure

```text
src/nexa/
├── audio/
│   ├── __init__.py
│   ├── devices.py
│   ├── recorder.py
│   ├── microphone.py
│   ├── loopback.py
│   ├── mixer.py
│   ├── chunks.py
│   ├── wav_utils.py
│   └── vad.py
│
└── asr/
    ├── __init__.py
    ├── service.py
    ├── faster_whisper_engine.py
    ├── model_registry.py
    ├── hardware.py
    ├── transcript.py
    ├── benchmark.py
    └── metrics.py

scripts/
└── benchmark_asr.py

tests/audio/
├── arabic/
├── english/
├── mixed/
├── noisy/
└── long/

tests/unit/member2/
tests/integration/member2/
```

---

## 22.3 Public Interfaces

```python
AudioDeviceService.list_inputs()
AudioDeviceService.list_loopback_outputs()

RecorderService.start(source_config)
RecorderService.pause()
RecorderService.resume()
RecorderService.stop() -> RecordedAudio

TranscriptionService.transcribe(audio_path) -> Transcript
TranscriptionService.transcribe_chunks(chunks) -> Transcript
```

---

## 22.4 Models / Tools Needed

| Component | Candidate |
|---|---|
| ASR runtime | faster-whisper |
| Baseline model | Whisper Small multilingual |
| Accuracy comparison | Whisper Medium multilingual |
| Egyptian mixed candidate | Egyptian Arabic-English code-switched Whisper fine-tune |
| VAD | Silero VAD |
| Windows system audio | WASAPI loopback / PyAudioWPatch |

---

## 22.5 Benchmark Dataset Requirement

Each of the 6 team members should record a test pack.

Minimum recommended set:

```text
10 Arabic-only clips/person
10 English-only clips/person
15 mixed-language clips/person
5 noisy clips/person
```

Total minimum:

```text
240 recordings
```

The dataset should intentionally include:

- employee names
- department names
- dates
- relative dates
- English technical terms
- spoken English numbers inside Arabic
- multiple tasks in one sentence

---

## 22.6 Independent Testing

Member 2 should be able to run:

```text
python scripts/benchmark_asr.py --dataset tests/audio
```

and output a comparison table without requiring the GUI or AI extractor.

---

## 22.7 Definition of Done

- Mic recording works.
- System audio recording works on supported Windows devices.
- Combined mode is usable.
- 60–90 minute recording test completes.
- Transcript includes timestamps.
- Original mixed-language words are preserved as accurately as possible.
- Benchmark report identifies the chosen production model.
- Transcription can run through the public interface only.

---

# 23. MEMBER 3 — AI Extraction, Egyptian Date Understanding & Duplicate Detection

## Mission

Turn a confirmed transcript into safe structured action candidates without summarizing irrelevant meeting discussion or inventing missing facts.

Member 3 can use text fixtures and does not need live audio, Gmail, worker, or final UI.

---

## 23.1 Owned Features

### Local LLM runtime adapter

- llama.cpp integration
- model process/runtime management
- structured-output prompt
- timeout handling
- malformed JSON recovery

### Action extraction

Extract:

- task
- owner raw text
- raw date phrase
- raw time phrase
- date/time candidate
- source evidence
- confidence

### Egyptian temporal normalization

Support expressions such as:

```text
النهاردة
بكرة
بعد بكرة
الخميس الجاي
الحد اللي جاي
أول الأسبوع
آخر الأسبوع
آخر الشهر
قبل نهاية اليوم
تلاتة ونص
تلاتة إلا ربع
3 العصر
three PM
EOD
before Monday
next Thursday
```

### Deterministic date validation

Use LLM for understanding but validate with deterministic date logic.

### Ambiguity detection

Examples:

```text
الخميس
آخر الأسبوع
بعد الاجتماع
قريب
```

Should produce appropriate confidence and review flags.

### Owner candidate extraction

Return raw owner text without forcing a database employee ID.

Employee matching can happen later through the people service.

### Duplicate detection

- lexical similarity
- semantic similarity
- date proximity
- owner similarity
- merge recommendation

---

## 23.2 Owned File Structure

```text
src/nexa/
├── intelligence/
│   ├── __init__.py
│   ├── service.py
│   ├── llm_runtime.py
│   ├── extractor.py
│   ├── schemas.py
│   ├── prompts.py
│   ├── confidence.py
│   ├── evidence.py
│   └── json_repair.py
│
├── dates/
│   ├── __init__.py
│   ├── normalizer.py
│   ├── egyptian_rules.py
│   ├── english_rules.py
│   ├── code_switch.py
│   ├── resolver.py
│   ├── validator.py
│   └── ambiguity.py
│
└── dedup/
    ├── __init__.py
    ├── service.py
    ├── similarity.py
    └── merge.py

resources/
└── extraction_prompts/
    ├── system.txt
    └── examples.json

tests/fixtures/transcripts/
tests/unit/member3/
tests/integration/member3/
```

---

## 23.3 Public Interfaces

```python
ExtractionService.extract(transcript, reference_datetime)
    -> list[ActionCandidate]

DateResolver.resolve(raw_phrase, reference_datetime)
    -> ResolvedTemporalValue

DuplicateService.compare(candidate, existing_candidates)
    -> DuplicateDecision

DuplicateService.merge(left, right)
    -> ActionCandidate
```

---

## 23.4 Model / Tool Requirements

| Component | Recommendation |
|---|---|
| Local LLM | Qwen3-4B GGUF starting candidate |
| Runtime | llama.cpp |
| Structured schema | Pydantic/dataclasses validation |
| Relative dates | dateparser |
| Egyptian handling | Custom rules + tests |

---

## 23.5 Critical Extraction Rule

The extractor must be optimized for **precision**, not for producing many items.

If the meeting says:

> `الـpresentation محتاجة شغل أكتر.`

Expected:

```json
{"items": []}
```

If it says:

> `الـpresentation لازم تخلص الخميس.`

Expected: one candidate.

---

## 23.6 Independent Testing

Build a transcript test suite containing:

- Arabic only
- English only
- mixed speech
- multiple actions
- no actions
- ambiguous dates
- repeated tasks
- same owner
- missing owner
- missing time

No audio is required for these tests.

---

## 23.7 Definition of Done

- Extractor returns valid schema only.
- No prose leakage from model output.
- Multiple actions extracted correctly.
- No-date discussion is ignored.
- Original evidence phrase is returned.
- Date interpretation is separated from raw phrase.
- Ambiguity is explicit.
- Duplicate detector produces deterministic decision categories.
- Test precision target is prioritized over recall.

---

# 24. MEMBER 4 — Reports, Gmail Delivery, Email Languages & Personalization

## Mission

Turn approved structured meeting data into formal professional emails in Arabic, English, or Arabic or English format and deliver them reliably through Gmail.

Member 4 can work entirely from fake meetings/actions/employees and does not need real audio, real AI, the final worker, or the final UI.

---

## 24.1 Owned Features

### Gmail OAuth

- desktop OAuth flow
- minimum required scope
- token refresh
- Windows Credential Manager integration
- connection test
- disconnect/reconnect

### Gmail sender

- MIME creation
- HTML + plain-text body
- To handling
- Gmail message ID capture
- error mapping
- retryable vs permanent errors

### Report rendering

Three modes:

```text
ARABIC
ENGLISH
BILINGUAL
```

### Formal language generation strategy

Do **not** let the LLM invent report content.

Approved action data is the source of truth.

Use deterministic professional templates and controlled phrasing.

Optional LLM-assisted wording can be added only behind strict data constraints later.

### Email preview model

Return a complete rendered preview object before sending.

### Personalized reminders

Render recipient-specific reminder content.

### Delivery logging interface

Member 4 returns send result data. Member 1's data layer persists it through repository contracts.

---

## 24.2 Owned File Structure

```text
src/nexa/
├── reports/
│   ├── __init__.py
│   ├── service.py
│   ├── models.py
│   ├── renderer.py
│   ├── formatter.py
│   ├── arabic.py
│   ├── english.py
│   ├── Arabic or English.py
│   └── subject_builder.py
│
└── email/
    ├── __init__.py
    ├── service.py
    ├── gmail_client.py
    ├── oauth.py
    ├── token_store.py
    ├── mime_builder.py
    ├── errors.py
    ├── preview.py
    └── personalization.py

resources/email_templates/
├── ar/
│   ├── meeting_report.html.j2
│   ├── meeting_report.txt.j2
│   ├── reminder.html.j2
│   └── reminder.txt.j2
│
├── en/
│   ├── meeting_report.html.j2
│   ├── meeting_report.txt.j2
│   ├── reminder.html.j2
│   └── reminder.txt.j2
│
└── Arabic or English/
    ├── meeting_report.html.j2
    ├── meeting_report.txt.j2
    ├── reminder.html.j2
    └── reminder.txt.j2

tests/unit/member4/
tests/integration/member4/
```

---

## 24.3 Public Interfaces

```python
ReportService.build_meeting_report(
    meeting,
    actions,
    recipients,
    language
) -> RenderedEmail

ReportService.build_reminder(
    employee,
    action,
    meeting,
    language
) -> RenderedEmail

EmailPreviewService.preview(rendered_email) -> EmailPreview

EmailSender.send(rendered_email) -> SendResult

GmailConnectionService.connect()
GmailConnectionService.test()
GmailConnectionService.disconnect()
```

---

## 24.4 What Member 4 Needs

| Need | Source |
|---|---|
| Gmail test account | Team/admin setup |
| Google OAuth client | Team/admin setup |
| Fake meetings | Own fixtures |
| Fake actions | Own fixtures |
| Fake employees | Own fixtures |
| Real ASR | Not required |
| Real AI | Not required |
| Real scheduler | Not required |
| Final UI | Not required |

---

## 24.5 Email Quality Requirements

- correct RTL for Arabic
- readable LTR for English
- clean Arabic or English layout
- mobile-friendly HTML
- plain-text fallback
- no raw JSON
- no casual tone in formal report
- dates formatted appropriately by language
- employee names preserved
- technical English terminology preserved where useful
- report contains only approved data

---

## 24.6 Definition of Done

- Gmail connect/disconnect works.
- Email can be previewed without being sent.
- Arabic report is professional.
- English report is professional.
- Arabic or English report is professionally structured.
- Personalized reminders work.
- Gmail message ID is captured.
- Invalid/revoked credentials produce a clear error.
- Rendering can be fully tested without network access.

---

# 25. MEMBER 5 — Scheduling, `NexaWorker.exe`, Snooze, Complete & Reliability

## Mission

Build Nexa's reliable background execution system so deadlines and reminders never become mixed, duplicated, or dependent on the main GUI being open.

Member 5 uses a `FakeEmailSender`, so this work does not wait for Gmail integration.

---

## 25.1 Owned Features

### Reminder rule engine

Default rules:

```text
Previous day: 8:00 PM
Event day: 8:00 AM
```

Smart rule for early events:

If an event occurs before or near the normal morning reminder time, the reminder must be moved earlier according to policy rather than sent after the event.

### Reminder creation

Action approval creates independent reminder records.

### Background worker

- worker entry point
- due-item polling
- safe claiming
- sending through `EmailSender` interface
- database status transitions
- graceful shutdown

### Retry logic

Recommended initial policy:

```text
Attempt 1: immediately
Attempt 2: +1 minute
Attempt 3: +5 minutes
Attempt 4: +15 minutes
Attempt 5: +30 minutes
Then: FAILED
```

### Missed reminder recovery

If Windows was unavailable at scheduled time:

```text
scheduled_at <= now
AND
now - scheduled_at <= recovery_window
```

send immediately and tag delivery as late recovery.

### Mark complete behavior

When completed:

- cancel future pending reminders
- preserve old sent reminders
- update state

### Snooze behavior

- create/update future reminder occurrence
- never change the actual deadline unless explicitly editing the task

### Reschedule behavior

When task due date changes:

- invalidate obsolete unsent reminders
- recalculate reminder schedule
- audit the change through contract

### Worker startup strategy

- Windows startup registration helper
- single-instance lock
- health/status heartbeat

---

## 25.2 Owned File Structure

```text
src/nexa/
├── scheduling/
│   ├── __init__.py
│   ├── service.py
│   ├── rules.py
│   ├── calculator.py
│   ├── queue.py
│   ├── states.py
│   ├── snooze.py
│   ├── completion.py
│   ├── reschedule.py
│   ├── retry.py
│   └── recovery.py
│
└── worker/
    ├── __init__.py
    ├── service.py
    ├── runner.py
    ├── claim.py
    ├── heartbeat.py
    ├── single_instance.py
    ├── windows_startup.py
    └── health.py

apps/
└── nexa_worker.py

tests/unit/member5/
tests/integration/member5/
```

---

## 25.3 Public Interfaces

```python
ReminderService.schedule_for_action(action, policy)
    -> list[Reminder]

ReminderService.cancel_for_action(action_id)
ReminderService.snooze(reminder_id, new_time)
ReminderService.reschedule_action(action_id, new_due_at)

CompletionService.mark_complete(action_id, actor)

WorkerService.run_once(now)
WorkerService.run_forever()

RetryPolicy.next_attempt(attempt_number, now)
```

---

## 25.4 Fake Dependencies

Member 5 creates:

```python
class FakeEmailSender:
    def send(self, rendered_email):
        return SendResult(success=True, message_id="fake-123")
```

and fake repositories if necessary.

Therefore the scheduler can be fully validated before Gmail exists.

---

## 25.5 Required Stress Tests

### Same time

Create 100 reminders due at exactly 8:00 AM.

Expected:

- all are independently processed
- no duplicates
- no missing records

### Restart

Stop worker during a batch, restart it.

Expected:

- sent items are not sent twice
- claim recovery policy handles abandoned claims safely

### Device offline

Simulate computer off for 30 minutes.

Expected:

- eligible reminders use late recovery

### Completed task

Mark action complete before reminder.

Expected:

- reminder is never sent

### Snooze

Snooze a reminder.

Expected:

- original time is not sent
- new time is sent
- task deadline remains unchanged

---

## 25.6 Definition of Done

- `NexaWorker.exe` can run without the GUI.
- 100 same-time reminders do not mix.
- duplicate sends are prevented.
- retries work.
- missed reminder recovery works.
- completion cancels future reminders.
- snooze works independently of due date.
- worker single-instance protection works.
- worker exposes enough status for the GUI to display healthy/offline state.

---

# 26. MEMBER 6 — Desktop UI/UX, Arabic/English UI, Dark Mode & Packaging

## Mission

Build the professional Windows experience that ties the user workflow together while using only public service interfaces and fake backends during development.

Member 6 does not need to wait for real AI, audio, Gmail, or the worker because every screen can be built using fake services and fixture data.

---

## 26.1 Owned Features

### Application shell

Sidebar:

```text
Dashboard
Meeting
Review
Schedule
Employees & Roles
Email History
Audit Trail
Settings
```

### Dashboard

Cards:

- upcoming deadlines
- reminders today
- pending review
- overdue tasks
- email failures

### Meeting screen

- title
- meeting template
- participants
- audio source
- start/pause/resume/stop
- recording timer
- audio status

### Review screen

For each candidate:

- exact source phrase
- extracted task
- owner suggestion
- resolved date/time
- confidence
- duplicate warning
- approve/edit/delete/merge

### Schedule screen

- calendar/list mode
- task status
- mark complete
- snooze
- reschedule
- send test reminder

### Employees & Roles screen

- employee list
- role list
- search
- filters
- add/edit/deactivate

### Search UX

- global search
- employee results
- meeting results
- task results

### Email preview screen

- language selector
- recipient selector
- rendered preview
- send button

### Audit trail screen

- timeline
- filters
- entity history

### Settings

- Arabic / English UI
- light / dark theme
- Gmail connection state
- default email language
- reminder times
- retention settings
- model status
- worker status

### Packaging

- `Nexa.exe`
- `NexaWorker.exe` packaging coordination
- resources
- icons
- version info
- first-run setup UI

---

## 26.2 Owned File Structure

```text
src/nexa/
├── ui/
│   ├── __init__.py
│   ├── app.py
│   ├── main_window.py
│   ├── navigation.py
│   ├── state.py
│   │
│   ├── dashboard/
│   │   ├── page.py
│   │   └── viewmodel.py
│   │
│   ├── meeting/
│   │   ├── page.py
│   │   └── viewmodel.py
│   │
│   ├── review/
│   │   ├── page.py
│   │   ├── action_card.py
│   │   ├── duplicate_dialog.py
│   │   └── viewmodel.py
│   │
│   ├── schedule/
│   │   ├── page.py
│   │   ├── calendar.py
│   │   ├── snooze_dialog.py
│   │   └── viewmodel.py
│   │
│   ├── people/
│   │   ├── page.py
│   │   ├── employee_dialog.py
│   │   ├── role_dialog.py
│   │   └── viewmodel.py
│   │
│   ├── search/
│   │   ├── global_search.py
│   │   ├── filters.py
│   │   └── results.py
│   │
│   ├── email_preview/
│   │   ├── page.py
│   │   └── viewmodel.py
│   │
│   ├── history/
│   │   ├── email_history.py
│   │   └── audit_history.py
│   │
│   ├── settings/
│   │   ├── page.py
│   │   └── viewmodel.py
│   │
│   └── widgets/
│       ├── cards.py
│       ├── tables.py
│       ├── badges.py
│       ├── dialogs.py
│       └── empty_states.py
│
├── i18n/
│   ├── service.py
│   ├── ar.json
│   └── en.json
│
└── themes/
    ├── manager.py
    ├── light.qss
    └── dark.qss

apps/
└── nexa_desktop.py

scripts/
└── build_windows.py

tests/unit/member6/
tests/integration/member6/
```

---

## 26.3 UI Architecture Rule

No business logic inside buttons/widgets.

Example:

Bad:

```python
button.clicked.connect(lambda: directly_modify_sqlite_and_send_gmail())
```

Correct:

```text
UI
↓
ViewModel / Controller
↓
Public Service Interface
↓
Implementation
```

---

## 26.4 Arabic UI Requirements

- RTL layout where appropriate
- English technical words must still render correctly
- mixed text must not break tables
- date/time formatting can follow selected UI language
- icons should not depend on text direction when meaning changes

---

## 26.5 Dark Mode

Dark mode is a first-class theme, not a last-minute inversion.

Requirements:

- light theme
- dark theme
- theme persistence
- readable tables
- readable confidence states
- HTML email preview must not accidentally inherit desktop QSS

---

## 26.6 Fake Services

Member 6 creates a demo service container:

```text
FakeAudioService
FakeTranscriptionService
FakeExtractionService
FakePeopleService
FakeSearchService
FakeEmailService
FakeReminderService
FakeAuditService
```

This allows the entire UI workflow to be demoed before backend integration.

---

## 26.7 Definition of Done

- Full navigation works.
- Arabic UI works.
- English UI works.
- Theme switching works.
- Search/filter screens work with fake data.
- Review screen shows exact source phrase.
- Mark Complete/Snooze dialogs work against service contracts.
- Email preview supports three language modes.
- First-run setup screen exists.
- Windows build script creates the application package.

---

# 27. Independence Matrix

This table explains how members avoid blocking each other.

| Member | Real Dependency Not Needed During Development | Replacement |
|---|---|---|
| 1 | AI/audio/Gmail/UI | Fixture data |
| 2 | AI/database/Gmail/UI | Audio files + local benchmark harness |
| 3 | Real STT/Gmail/database/UI | Transcript fixtures |
| 4 | Real AI/worker/UI | Fake meetings/employees/actions |
| 5 | Real Gmail/UI/AI | FakeEmailSender + fake repositories |
| 6 | Every backend implementation | Fake service container |

This is the central rule that keeps the six developers productive in parallel.

---

# 28. Recommended Git Workflow

```text
main
│
├── member1/core-data
├── member2/audio-asr
├── member3/intelligence
├── member4/email-reports
├── member5/scheduler-worker
└── member6/ui-desktop
```

Short-lived feature branches can be created under each ownership area.

Recommended rules:

- protect `main`
- pull request required
- tests required
- no cross-owner directory edits without review
- contracts changes require approval from the whole team or tech lead

---

# 29. Integration Sequence

The code can be written in parallel, but integration should happen in this order because it minimizes debugging complexity.

## Integration A

```text
Member 1 + Member 6
```

UI + real database/people/search.

## Integration B

```text
Member 2 + Member 6
```

Meeting screen + real recorder/transcription.

## Integration C

```text
Member 2 → Member 3 → Member 6
```

Transcript → extraction → review UI.

## Integration D

```text
Member 1 + Member 4 + Member 6
```

Recipients + email preview + Gmail.

## Integration E

```text
Member 1 + Member 5 + Member 4
```

Reminder records + worker + Gmail sending.

## Integration F

Full E2E.

---

# 30. Meeting Template Flow

```text
New Meeting
    ↓
Choose Template
    ↓
Nexa pre-fills:
    title
    participants
    audio source
    report recipients
    reminder recipients
    email language
    reminder rules
    ↓
Admin may edit any field
    ↓
Start Meeting
```

Templates are convenience defaults, not locked policies.

---

# 31. Search and Filter UX

## Global Search

Top search field:

```text
Search employees, meetings or tasks...
```

Results grouped:

```text
Employees (3)
Meetings (2)
Tasks (7)
```

### Example

Search:

```text
Ahmed
```

May return:

```text
Employee
Ahmed Hassan — Development

Meeting
Weekly Development Meeting — Participant: Ahmed Hassan

Tasks
Database Integration — Ahmed Hassan — Sep 7
API Review — Ahmed Hassan — Sep 10
```

---

# 32. Status Model

## Meeting

```text
DRAFT
RECORDING
PROCESSING
PENDING_REVIEW
APPROVED
ARCHIVED
```

## Action Item

```text
PENDING
COMPLETED
OVERDUE
CANCELLED
```

## Reminder

```text
PENDING
CLAIMED
SENDING
SENT
RETRY_WAIT
FAILED
CANCELLED
SNOOZED
SKIPPED_COMPLETED
```

## Email Delivery

```text
PENDING
SENDING
SENT
FAILED
```

---

# 33. Smart Reminder Rules

Default policy:

## Reminder A

Previous day at:

```text
20:00 Africa/Cairo
```

## Reminder B

Event day at:

```text
08:00 Africa/Cairo
```

## Early event protection

If the event is too early for an 08:00 reminder, use a configurable policy.

Recommended initial rule:

```text
if event_time <= 09:00:
    reminder = max(previous_reasonable_time, event_time - 2 hours)
else:
    reminder = 08:00
```

The exact business policy can be adjusted from Settings.

---

# 34. Scheduled Meetings vs Scheduled Reminders

Nexa contains two different concepts.

## Scheduled Meeting

A future meeting itself.

Example:

```text
Project Review
10 Sep 2026
2:00 PM
```

This can appear on Nexa's Schedule screen and may optionally receive a pre-meeting reminder.

## Scheduled Reminder

An email that Nexa must send at a future time.

Example:

```text
Remind Ahmed about Project Review
10 Sep 2026
8:00 AM
```

They must not be stored as one object.

This separation prevents confusion.

Recommended later table if scheduled future meetings are managed before they happen:

```text
scheduled_meetings
    id
    title
    scheduled_start
    scheduled_end
    template_id
    participant_config
    reminder_config
    status
```

For V1, normal `meetings` can support a planned state if the team wants to keep the schema simpler.

---

# 35. Gmail Scheduling Decision

Recommended V1:

```text
DO NOT depend on Gmail native Schedule Send.
```

Use:

```text
SQLite reminder queue
+
NexaWorker.exe
+
Gmail API send at execution time
```

Advantages:

- one source of truth
- visible status inside Nexa
- easy snooze
- easy cancel
- mark complete can cancel future reminder
- retries controlled by Nexa
- audit trail controlled by Nexa
- duplicate protection controlled by Nexa
- works consistently for personalized messages

Optional later enhancement:

Nexa may create Gmail drafts for admin convenience, but Gmail drafts should not become the authoritative schedule because the worker still needs to decide when to send.

---

# 36. Email and Reminder Recipient Logic

## Meeting Report

Possible recipients:

```text
All employees
Meeting participants
Selected roles
Selected employees
Custom combination
```

## Task Reminder

Recommended default:

```text
Assigned employee
```

Optional:

```text
Assigned employee + selected role
Same recipients as meeting report
Custom
```

Always de-duplicate by employee/email before sending.

---

# 37. Privacy Defaults

Recommended defaults:

```text
Audio:
Delete after meeting approval

Full transcript:
Delete after meeting approval or retain according to organization policy

Action items:
Keep

Evidence snippets:
Keep

Audit trail:
Keep
```

Configurable retention policies should be provided.

The organization must use meeting recording in accordance with its own legal and internal consent requirements.

---

# 38. Security Requirements

- OAuth tokens never stored as plain text inside config files.
- Use Windows Credential Manager through an appropriate keyring adapter.
- No Gmail password storage.
- SQLite file access restricted to application user where practical.
- Audit log records administrative changes.
- Email sending uses least-privilege Gmail scopes practical for the selected flow.
- Logs must not print OAuth tokens.
- Crash reports must not include secrets.
- Model prompts should not be transmitted to a cloud service in the zero-cost/local design.

---

# 39. Testing Plan

## 39.1 STT

- Arabic
- English
- mixed
- noisy room
- multiple speakers
- computer audio
- microphone audio
- 60–90 minute meeting

## 39.2 Extraction

- one action
- multiple actions
- no action
- ambiguous date
- no owner
- duplicate task
- English dates
- Egyptian dates
- code-switched dates

## 39.3 Email

- Arabic
- English
- Arabic or English
- HTML
- plain text
- one recipient
- many recipients
- invalid email
- revoked OAuth
- no internet

## 39.4 Worker

- one reminder
- 100 reminders same second/minute
- restart during processing
- failed send + retry
- missed reminder recovery
- cancelled reminder
- snoozed reminder
- completed task

## 39.5 Search

- employee
- meeting
- task
- combined filters
- empty result
- Arabic names
- English names

## 39.6 UI

- Arabic mode
- English mode
- light mode
- dark mode
- mixed Arabic-English text rendering
- small laptop resolution
- high DPI

---

# 40. Example Acceptance Meeting

Meeting speech:

> `أحمد يخلص الـdatabase before Monday، والـpresentation تكون ready يوم الخميس الساعة three. وبالنسبة للbudget هنتكلم فيها بعدين.`

Expected candidates:

```text
1.
Task: Finish database
Owner raw text: أحمد
Deadline: Monday
Evidence: أحمد يخلص الـdatabase before Monday

2.
Task: Presentation ready
Owner: Unassigned
Deadline: Thursday
Time: 3:00 PM
Evidence: الـpresentation تكون ready يوم الخميس الساعة three
```

Expected ignored discussion:

```text
وبالنسبة للbudget هنتكلم فيها بعدين
```

because there is no actionable scheduled deadline.

---

# 41. Recommended Milestones

## Milestone 0 — Contract Freeze

Whole team:

- agree domain models
- agree service interfaces
- agree error/result types
- create fake implementations

Then parallel work begins.

## Milestone 1 — Six Independent Subsystems

Each member completes their definition of done using fixtures/fakes.

## Milestone 2 — Pairwise Integration

Integrate subsystem pairs according to Section 29.

## Milestone 3 — End-to-End Alpha

```text
Record
→ Transcribe
→ Extract
→ Review
→ Save
→ Preview Email
→ Send Report
→ Create Reminders
→ Worker Sends Reminder
```

## Milestone 4 — Feature Completion

Add:

- search
- filters
- complete
- snooze
- duplicate handling
- meeting templates
- audit UI
- personalization
- Arabic or English reports
- dark mode

## Milestone 5 — Ministry Demo Build

- clean installer/package
- demo dataset
- clean database reset script
- presentation script
- offline AI models available locally
- Gmail test account prepared
- backup demo audio available

---

# 42. Demo Safety Plan

For the ministry demonstration, never rely on only one live input path.

Prepare:

1. Live microphone demo.
2. A known prerecorded meeting file as fallback.
3. Local AI models already downloaded.
4. Gmail authenticated before the demo.
5. A demo employee database already populated.
6. A short reminder with a near test time.
7. Internet fallback information for email sending.

The AI pipeline should still work locally if internet fails; only Gmail delivery should be affected.

---

# 43. Build Outputs

Final package should contain logically:

```text
Nexa/
│
├── Nexa.exe
├── NexaWorker.exe
│
├── resources/
│   ├── email_templates/
│   ├── translations/
│   ├── themes/
│   └── icons/
│
├── models/
│   ├── whisper/
│   └── llm/
│
├── data/
│   └── nexa.db
│
└── logs/
```

The exact installer/package format can be finalized after the application stabilizes.

---

# 44. First-Run Experience

```text
Welcome to Nexa

1. Choose UI language
   Arabic / English

2. Check AI models
   Speech model      ✓
   Local AI model    ✓

3. Connect Gmail
   [ Connect Google Account ]

4. Organization settings
   Organization name
   Sender display name

5. Reminder defaults
   Previous-day reminder
   Morning reminder

6. Privacy
   Audio retention
   Transcript retention

7. Finish
```

---

# 45. Final End-to-End Flow

This is the final project flow that every team member should understand.

```text
1. Admin opens Nexa

2. Starts New Meeting

3. Chooses or creates a Meeting Template

4. Chooses:
   Microphone / Computer Audio / Both

5. Selects meeting participants if known

6. Nexa records the meeting

7. Speech is transcribed locally

8. Nexa preserves the original confirmed wording

9. Nexa extracts only:
   tasks
   deadlines
   dates
   times
   scheduled appointments/meetings
   owners when explicitly mentioned

10. Nexa resolves relative dates using:
    AI understanding
    + Egyptian/English date rules
    + deterministic validation

11. Nexa detects possible duplicates

12. Meeting ends

13. Review screen opens

14. For every extracted candidate, the admin sees:
    exact original phrase
    extracted task
    owner suggestion
    interpreted date/time
    confidence
    duplicate warning if any

15. Admin can:
    edit
    delete
    merge duplicates
    add manually
    assign employee
    assign role
    correct date/time

16. Admin approves the final action items

17. Admin selects Meeting Report recipients:
    All Employees
    Meeting Participants
    Roles
    Specific Employees
    Custom combination

18. Admin selects Reminder recipients separately

19. Admin chooses email language:
    Arabic
    English
    Arabic or English Arabic + English

20. Nexa builds a formal professional email report

21. Admin opens Email Preview

22. Admin can change:
    recipients
    language
    final approved details

23. Admin approves delivery

24. Meeting and action data are saved to SQLite

25. Nexa creates independent reminder records
    for every required reminder occurrence

26. Professional meeting report is sent through Gmail

27. Gmail result is stored in Email History

28. Audit Trail records the important actions

29. Admin may close Nexa.exe

30. NexaWorker.exe continues running in the background

31. NexaWorker checks the SQLite reminder queue

32. When a reminder reaches its scheduled time:
    worker safely claims that reminder only

33. Nexa resolves the final reminder recipients

34. Nexa builds personalized professional reminder emails
    in the selected language mode

35. Gmail sends the reminder

36. Success:
    reminder → SENT
    delivery log → SENT
    Gmail message ID stored

37. Temporary failure:
    reminder → RETRY_WAIT
    worker retries according to policy

38. Computer was unavailable at the original time:
    worker applies missed-reminder recovery policy

39. User can later search:
    employees
    meetings
    tasks

40. User can filter by:
    date
    status
    employee
    role
    meeting
    overdue/completed/snoozed

41. User can Mark Complete
    → future reminders are cancelled

42. User can Snooze
    → reminder time changes
    → actual task deadline does not change

43. User can Reschedule the task
    → obsolete unsent reminders are cancelled
    → new reminders are calculated

44. Every important modification is added to Audit Trail

45. Dashboard always reflects the latest state:
    upcoming deadlines
    reminders today
    pending review
    overdue items
    completed items
    email failures
```

---

# 46. Final Definition of Done

Nexa is considered complete for V1 only when this complete scenario works:

A user starts a Windows meeting and says naturally:

> `أحمد يخلص الـdatabase before Monday، والـpresentation تكون ready يوم الخميس الساعة three.`

Nexa must:

1. Record the speech.
2. Transcribe it locally.
3. Preserve the exact original confirmed wording.
4. Extract two action items.
5. Correctly interpret the relative dates using `Africa/Cairo`.
6. Show evidence and confidence.
7. Allow editing and assignment.
8. Allow Arabic/English UI switching.
9. Allow Arabic/English/Arabic or English email selection.
10. Preview a professional formal report.
11. Send the approved report through Gmail.
12. Create independent reminder records.
13. Allow the GUI to close.
14. Keep `NexaWorker.exe` running.
15. Send the correct personalized reminder at the correct time.
16. Prevent duplicate sending.
17. Record delivery status.
18. Support search and filters.
19. Support Mark Complete.
20. Support Snooze.
21. Support duplicate detection.
22. Support meeting templates.
23. Support dark mode.
24. Record the complete audit trail.

If this scenario works reliably, Nexa is a complete **Smart Meeting Voice AI & Reminder System**, not merely a transcription demo.