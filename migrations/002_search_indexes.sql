-- 002_search_indexes.sql
-- Indexes supporting the search and filter APIs (Sections 6.4 / 6.5).
--
-- Substring search uses LIKE '%term%', which cannot use a B-tree index, so
-- these indexes target the parts that dominate real queries: the filter
-- predicates (status, owner, meeting, dates, active flags) and the prefix
-- lookups used by autocomplete.

CREATE INDEX ix_employees_active ON employees (active);
CREATE INDEX ix_employees_department ON employees (department);
CREATE INDEX ix_employees_name_norm ON employees (full_name_norm);

CREATE INDEX ix_employee_roles_role ON employee_roles (role_id);

CREATE INDEX ix_meetings_status ON meetings (status);
CREATE INDEX ix_meetings_started_at ON meetings (started_at);
CREATE INDEX ix_meetings_template ON meetings (template_id);
CREATE INDEX ix_meetings_title_norm ON meetings (title_norm);

CREATE INDEX ix_meeting_participants_employee ON meeting_participants (employee_id);

CREATE INDEX ix_transcript_segments_meeting ON transcript_segments (meeting_id, segment_index);

CREATE INDEX ix_action_items_meeting ON action_items (meeting_id);
CREATE INDEX ix_action_items_owner ON action_items (owner_employee_id);
CREATE INDEX ix_action_items_status ON action_items (status);
CREATE INDEX ix_action_items_review_state ON action_items (review_state);
CREATE INDEX ix_action_items_due_date ON action_items (due_date);
CREATE INDEX ix_action_items_due_at ON action_items (due_at);
-- The dashboard's hottest query: "pending items due in this window".
CREATE INDEX ix_action_items_status_due ON action_items (status, due_date);

CREATE INDEX ix_reminders_action ON reminders (action_item_id);
CREATE INDEX ix_reminders_status_scheduled ON reminders (status, scheduled_at);

CREATE INDEX ix_delivery_targets_meeting ON delivery_targets (meeting_id, delivery_kind);
CREATE INDEX ix_delivery_targets_action ON delivery_targets (action_item_id, delivery_kind);

CREATE INDEX ix_email_deliveries_meeting ON email_deliveries (meeting_id);
CREATE INDEX ix_email_deliveries_status ON email_deliveries (status);
CREATE INDEX ix_email_deliveries_recipient ON email_deliveries (recipient_employee_id);
