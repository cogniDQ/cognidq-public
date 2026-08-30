-- Migration: 011_f006_membership_indexes.sql
-- Feature: F006 — User Invitation and Workspace Membership
-- Packet: P01 — DB Indexes Migration
-- Created: 2026-03-30
-- Description:
--   Adds two composite indexes to support:
--   1. Efficient duplicate-pending-invitation check (org + email, pending only)
--   2. Efficient last-admin count queries (org + status)
--
-- Safe to run multiple times (CREATE INDEX IF NOT EXISTS).
-- No table or column changes.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Partial index on invitations(organization_id, email) WHERE accepted = false
--    Supports: duplicate pending invitation check in invite_user service
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_invitations_org_email_pending
    ON invitations (organization_id, email)
    WHERE (accepted = false);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Composite index on organization_members(organization_id, status)
--    Supports: last-admin count query (WHERE role='admin' AND status='active')
--              and member list filtering by status
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_org_members_org_status
    ON organization_members (organization_id, status);

COMMIT;
