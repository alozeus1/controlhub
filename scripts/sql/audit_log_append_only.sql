-- Make the audit log append-only for the application role.
--
-- The hash chain (app/services/audit_chain.py) makes tampering detectable and
-- the mirror (app/services/audit_sink.py) preserves a copy. This script removes
-- the ability in the first place: the application simply has no grant to UPDATE
-- or DELETE audit rows, so the most damaging action an attacker with the app's
-- database credentials could take is not available to that credential at all.
--
-- Run as a superuser / the database owner — NOT as the application role, which
-- by design cannot grant itself these rights back.
--
--   psql "$SQLALCHEMY_DATABASE_URI" -v app_role=controlhub_app \
--        -f scripts/sql/audit_log_append_only.sql
--
-- Prerequisites:
--   * The application connects as a NON-owner role. If it connects as the table
--     owner (or a superuser), these REVOKEs have no effect — ownership implies
--     full DML regardless of grants, and RLS is bypassed. Check with:
--         SELECT tableowner FROM pg_tables WHERE tablename = 'audit_log';
--     If that is your app role, create a separate owner first; otherwise this
--     script gives you a false sense of protection.
--   * Migrations must run as the owner, not the application role.

\set app_role :app_role

BEGIN;

-- Baseline: the app may read and append, nothing else.
REVOKE ALL ON TABLE audit_log FROM :"app_role";
GRANT SELECT, INSERT ON TABLE audit_log TO :"app_role";

-- The sequence is needed for INSERT to allocate ids.
GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO :"app_role";

-- system_state holds the mirror's high-water mark and must stay writable,
-- otherwise the mirror re-ships the whole log on every run.
GRANT SELECT, INSERT, UPDATE ON TABLE system_state TO :"app_role";
GRANT USAGE, SELECT ON SEQUENCE system_state_id_seq TO :"app_role";

COMMIT;

-- Verification. Expect exactly INSERT and SELECT — no UPDATE, no DELETE.
SELECT privilege_type
FROM information_schema.role_table_grants
WHERE table_name = 'audit_log' AND grantee = :'app_role'
ORDER BY privilege_type;

-- Then confirm the denial holds, connected AS the application role:
--   DELETE FROM audit_log WHERE id = -1;   -- must fail: permission denied
