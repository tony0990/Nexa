-- 003_audit_indexes.sql
-- The audit trail is queried three ways (Section 21.1): by entity, by date,
-- and by actor. Each query also orders by time, so time is part of each index.

CREATE INDEX ix_audit_events_entity
    ON audit_events (entity_type, entity_id, created_at);

CREATE INDEX ix_audit_events_created_at
    ON audit_events (created_at);

CREATE INDEX ix_audit_events_actor
    ON audit_events (actor_type, actor_id, created_at);

CREATE INDEX ix_audit_events_type
    ON audit_events (event_type, created_at);
