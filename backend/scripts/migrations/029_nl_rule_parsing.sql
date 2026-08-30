-- Migration 029: NL Rule Parsing tables
-- Creates tables for natural language rule parse requests and results.
-- Part of F099 - NL Rule Parsing Service (Phase 8 - NL Rule Builder)
BEGIN;

-- ============================================================
-- nl_rule_requests: Stores user-submitted NL rule parse requests
-- ============================================================
CREATE TABLE IF NOT EXISTS nl_rule_requests (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    workspace_id        UUID            NOT NULL,
    rule_text           TEXT            NOT NULL,
    context             JSONB           NULL,
    status              VARCHAR(20)     NOT NULL DEFAULT 'pending',
    created_by          UUID            NOT NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT pk_nl_rule_requests
        PRIMARY KEY (id),

    CONSTRAINT ck_nl_rule_requests_status
        CHECK (status IN ('pending', 'parsing', 'parsed', 'cannot_interpret', 'parse_error'))
);

CREATE INDEX IF NOT EXISTS ix_nl_rule_requests_workspace_id
    ON nl_rule_requests (workspace_id);

CREATE INDEX IF NOT EXISTS ix_nl_rule_requests_created_by
    ON nl_rule_requests (created_by);

CREATE INDEX IF NOT EXISTS ix_nl_rule_requests_created_at
    ON nl_rule_requests (created_at DESC);

-- ============================================================
-- nl_rule_parse_results: Stores parsed SIR output for each request
-- ============================================================
CREATE TABLE IF NOT EXISTS nl_rule_parse_results (
    id                      UUID                NOT NULL DEFAULT gen_random_uuid(),
    request_id              UUID                NOT NULL,
    sir_json                JSONB               NOT NULL,
    rule_type               VARCHAR(50)         NOT NULL,
    confidence              DOUBLE PRECISION    NOT NULL,
    requires_disambiguation BOOLEAN             NOT NULL DEFAULT false,
    parse_warnings          JSONB               NULL,
    model_version           VARCHAR(100)        NOT NULL,
    schema_version          VARCHAR(10)         NOT NULL DEFAULT '1.0',
    created_at              TIMESTAMPTZ         NOT NULL DEFAULT now(),

    CONSTRAINT pk_nl_rule_parse_results
        PRIMARY KEY (id),

    CONSTRAINT fk_nl_rule_parse_results_request
        FOREIGN KEY (request_id) REFERENCES nl_rule_requests(id) ON DELETE CASCADE,

    CONSTRAINT uq_nl_rule_parse_results_request_id
        UNIQUE (request_id),

    CONSTRAINT ck_nl_rule_parse_results_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS ix_nl_rule_parse_results_rule_type
    ON nl_rule_parse_results (rule_type);

COMMIT;
