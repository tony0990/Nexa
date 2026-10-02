-- Allow the BILINGUAL report language (Sections 10.3, 24.1).
--
-- OWNERSHIP NOTE: migrations/ is Member 1's directory (Section 21.2). Member 4
-- adds this because the BILINGUAL rendering mode cannot be persisted without
-- it: 001_initial.sql constrains meetings.email_language and
-- email_deliveries.language to ('AR','EN'), so an admin choosing BILINGUAL
-- would hit a CHECK violation on the first save. Member 1 should review it.
--
-- WHY NOT THE USUAL TABLE REBUILD
--
-- SQLite cannot ALTER a CHECK constraint, so the standard fix is to rebuild the
-- table: create a new one, copy the rows, DROP the old, rename. That is
-- *destructive here* and was measured to be:
--
--   With PRAGMA foreign_keys = ON — which the migration runner sets — DROP TABLE
--   performs an implicit DELETE FROM first, and that fires ON DELETE CASCADE on
--   every child. Dropping `meetings` therefore deletes meeting_participants,
--   transcript_segments and action_items. A rebuild of these two tables was
--   tried against a seeded database and took all three child tables from 1 row
--   to 0.
--
-- SQLite's own 12-step ALTER TABLE procedure says to set PRAGMA
-- foreign_keys = OFF *before* starting the transaction. The runner wraps each
-- migration in BEGIN/COMMIT, and that pragma is a no-op inside a transaction,
-- so the safe rebuild is not expressible in a migration file as the runner
-- stands. PRAGMA defer_foreign_keys and PRAGMA legacy_alter_table were both
-- tried and neither prevents the cascade.
--
-- WHAT THIS DOES INSTEAD
--
-- Edits the two CHECK clauses in place via writable_schema. No row is read,
-- written or deleted, no table is dropped, and every index, trigger and foreign
-- key stays exactly as it was — which is why this is the smaller risk despite
-- writable_schema's reputation. Verified against a seeded database: children
-- kept, indexes kept, `PRAGMA integrity_check` ok, `PRAGMA foreign_key_check`
-- clean, 'BILINGUAL' accepted, and a junk value still rejected.
--
-- The replacements are scoped by table name and anchored on the full
-- `CHECK (<column> IN ('AR', 'EN'))` text, which is why widening
-- email_deliveries.language cannot accidentally match meetings.email_language:
-- the `CHECK (` prefix makes `CHECK (language` and `CHECK (email_language`
-- distinct strings.

PRAGMA writable_schema = ON;

UPDATE sqlite_master
   SET sql = replace(
           sql,
           'CHECK (email_language IN (''AR'', ''EN''))',
           'CHECK (email_language IN (''AR'', ''EN'', ''BILINGUAL''))'
       )
 WHERE type = 'table'
   AND name = 'meetings';

UPDATE sqlite_master
   SET sql = replace(
           sql,
           'CHECK (language IN (''AR'', ''EN''))',
           'CHECK (language IN (''AR'', ''EN'', ''BILINGUAL''))'
       )
 WHERE type = 'table'
   AND name = 'email_deliveries';

PRAGMA writable_schema = OFF;

-- Self-verification. replace() silently does nothing when the pattern does not
-- match, so a reformatted 001_initial.sql would leave this migration recorded as
-- applied while having changed nothing at all. The guard table's CHECK fails in
-- that case, which aborts the script and rolls the whole migration back.
CREATE TABLE _m004_guard (ok INTEGER NOT NULL CHECK (ok = 1));

INSERT INTO _m004_guard (ok)
SELECT CASE
           WHEN (
               SELECT COUNT(*)
                 FROM sqlite_master
                WHERE type = 'table'
                  AND name IN ('meetings', 'email_deliveries')
                  AND sql LIKE '%BILINGUAL%'
           ) = 2 THEN 1
           ELSE 0
       END;

DROP TABLE _m004_guard;
