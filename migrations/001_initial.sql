-- 001_initial.sql
-- Nexa core schema (Section 16). SQLite is the single source of truth for
-- application state and reminder state.
--
-- Conventions:
--   * timestamps are ISO-8601 UTC strings ("2026-09-20T18:30:00+00:00")
--   * due_date is a local calendar date "YYYY-MM-DD"
--   * due_time is a local wall time "HH:MM"
--   * due_at is the resolved UTC instant, NULL when the time is unspecified
--   * *_norm columns hold search-normalized copies maintained by the
--     repositories (see nexa.core.validation.normalize_search_text)

CREATE TABLE employees (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL,
    full_name_norm TEXT   NOT NULL DEFAULT '',
    email         TEXT    NOT NULL,
    department    TEXT,
    job_title     TEXT,
    search_text   TEXT    NOT NULL DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

-- One employee per address, case-insensitively: emails are stored lowercase.
CREATE UNIQUE INDEX ux_employees_email ON employees (email);

CREATE TABLE roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    name_norm   TEXT    NOT NULL DEFAULT '',
    description TEXT,
    active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE UNIQUE INDEX ux_roles_name_norm ON roles (name_norm);

CREATE TABLE employee_roles (
    employee_id INTEGER NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    role_id     INTEGER NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    PRIMARY KEY (employee_id, role_id)
);

CREATE TABLE meeting_templates (
    id                             INTEGER PRIMARY KEY AUTOINCREMENT,
    name                           TEXT    NOT NULL,
    name_norm                      TEXT    NOT NULL DEFAULT '',
    default_title                  TEXT,
    default_audio_source           TEXT,
    default_email_language         TEXT,
    default_report_target_config   TEXT,
    default_reminder_target_config TEXT,
    default_reminder_rule_config   TEXT,
    active                         INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at                     TEXT    NOT NULL,
    updated_at                     TEXT    NOT NULL
);

CREATE UNIQUE INDEX ux_meeting_templates_name_norm ON meeting_templates (name_norm);

CREATE TABLE meetings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT    NOT NULL,
    title_norm     TEXT    NOT NULL DEFAULT '',
    template_id    INTEGER REFERENCES meeting_templates (id) ON DELETE SET NULL,
    started_at     TEXT,
    ended_at       TEXT,
    audio_source   TEXT    NOT NULL DEFAULT 'MICROPHONE'
                   CHECK (audio_source IN ('MICROPHONE', 'COMPUTER', 'BOTH')),
    status         TEXT    NOT NULL DEFAULT 'DRAFT'
                   CHECK (status IN ('DRAFT', 'RECORDING', 'PROCESSING',
                                     'PENDING_REVIEW', 'APPROVED', 'ARCHIVED')),
    email_language TEXT    NOT NULL DEFAULT 'AR' CHECK (email_language IN ('AR', 'EN')),
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);

CREATE TABLE meeting_participants (
    meeting_id  INTEGER NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    PRIMARY KEY (meeting_id, employee_id)
);

CREATE TABLE transcript_segments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id     INTEGER NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    segment_index  INTEGER NOT NULL,
    start_ms       INTEGER NOT NULL DEFAULT 0,
    end_ms         INTEGER NOT NULL DEFAULT 0,
    raw_text       TEXT    NOT NULL,
    confirmed_text TEXT,
    text_norm      TEXT    NOT NULL DEFAULT '',
    language_hint  TEXT,
    created_at     TEXT    NOT NULL,
    UNIQUE (meeting_id, segment_index)
);

CREATE TABLE action_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id        INTEGER REFERENCES meetings (id) ON DELETE CASCADE,
    task              TEXT    NOT NULL,
    owner_employee_id INTEGER REFERENCES employees (id) ON DELETE SET NULL,
    owner_raw_text    TEXT,
    raw_date_phrase   TEXT,
    due_date          TEXT,
    due_time          TEXT,
    due_at            TEXT,
    source_text       TEXT,
    search_text       TEXT    NOT NULL DEFAULT '',
    confidence        REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    review_state      TEXT    NOT NULL DEFAULT 'NEEDS_REVIEW'
                      CHECK (review_state IN ('NEEDS_REVIEW', 'APPROVED', 'REJECTED')),
    status            TEXT    NOT NULL DEFAULT 'PENDING'
                      CHECK (status IN ('PENDING', 'COMPLETED', 'OVERDUE', 'CANCELLED')),
    completed_at      TEXT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

CREATE TABLE reminder_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_item_id  INTEGER NOT NULL REFERENCES action_items (id) ON DELETE CASCADE,
    rule_type       TEXT    NOT NULL,
    offset_minutes  INTEGER,
    fixed_local_time TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at      TEXT    NOT NULL
);

CREATE TABLE reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_item_id  INTEGER NOT NULL REFERENCES action_items (id) ON DELETE CASCADE,
    scheduled_at    TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'CLAIMED', 'SENDING', 'SENT',
                                      'RETRY_WAIT', 'FAILED', 'CANCELLED',
                                      'SNOOZED', 'SKIPPED_COMPLETED')),
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    claimed_at      TEXT,
    sent_at         TEXT,
    last_error      TEXT,
    idempotency_key TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

-- The worker relies on this to guarantee one send per reminder occurrence
-- (Section 5).
CREATE UNIQUE INDEX ux_reminders_idempotency_key
    ON reminders (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE delivery_targets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id     INTEGER REFERENCES meetings (id) ON DELETE CASCADE,
    action_item_id INTEGER REFERENCES action_items (id) ON DELETE CASCADE,
    delivery_kind  TEXT    NOT NULL CHECK (delivery_kind IN ('REPORT', 'REMINDER')),
    target_type    TEXT    NOT NULL
                   CHECK (target_type IN ('ALL', 'MEETING_PARTICIPANTS', 'ROLE',
                                          'EMPLOYEE', 'ASSIGNEE')),
    target_id      INTEGER,
    created_at     TEXT    NOT NULL
);

CREATE TABLE email_deliveries (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id            INTEGER REFERENCES meetings (id) ON DELETE SET NULL,
    action_item_id        INTEGER REFERENCES action_items (id) ON DELETE SET NULL,
    reminder_id           INTEGER REFERENCES reminders (id) ON DELETE SET NULL,
    recipient_employee_id INTEGER REFERENCES employees (id) ON DELETE SET NULL,
    recipient_email       TEXT    NOT NULL,
    subject               TEXT    NOT NULL DEFAULT '',
    language              TEXT    NOT NULL DEFAULT 'AR' CHECK (language IN ('AR', 'EN')),
    status                TEXT    NOT NULL DEFAULT 'PENDING'
                          CHECK (status IN ('PENDING', 'SENDING', 'SENT', 'FAILED')),
    gmail_message_id      TEXT,
    attempted_at          TEXT,
    sent_at               TEXT,
    error_message         TEXT
);

-- Append-only through the application: there is no UPDATE/DELETE path in the
-- audit repository, and these triggers make that a database rule too.
CREATE TABLE audit_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_type      TEXT    NOT NULL DEFAULT 'USER'
                    CHECK (actor_type IN ('USER', 'SYSTEM', 'WORKER')),
    actor_id        TEXT,
    event_type      TEXT    NOT NULL,
    entity_type     TEXT    NOT NULL,
    entity_id       TEXT,
    old_value_json  TEXT,
    new_value_json  TEXT,
    metadata_json   TEXT,
    created_at      TEXT    NOT NULL
);

CREATE TRIGGER trg_audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TRIGGER trg_audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
