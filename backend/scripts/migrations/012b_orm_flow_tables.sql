-- 012b_orm_flow_tables.sql
-- ----------------------------------------------------------------------
-- Materialise the ``flow_*`` tables defined by the SQLAlchemy ORM in
-- ``app/models/flow.py`` so that subsequent migrations (notably 013_f031_issues
-- and 026_f095_kqi_models) can reference them without relying on a runtime
-- ``Base.metadata.create_all`` pass.
--
-- These DDL statements mirror the ORM definitions (DQFlow, FlowExecution,
-- FlowNodeResult, FlowTemplate). Idempotent: every CREATE uses
-- ``IF NOT EXISTS``.
-- ----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.dq_flows (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    flow_definition JSONB NOT NULL,
    status          VARCHAR(50) NOT NULL DEFAULT 'draft',
    is_active       BOOLEAN DEFAULT TRUE,
    schedule        JSONB,
    tags            TEXT[],
    version         INTEGER DEFAULT 1,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    owner_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    CONSTRAINT check_flow_status CHECK (status IN ('draft','active','inactive','archived'))
);

CREATE INDEX IF NOT EXISTS idx_flows_workspace      ON public.dq_flows (organization_id);
CREATE INDEX IF NOT EXISTS idx_flows_status         ON public.dq_flows (status);
CREATE INDEX IF NOT EXISTS idx_flows_created_by     ON public.dq_flows (created_by);
CREATE INDEX IF NOT EXISTS idx_flows_created_at     ON public.dq_flows (created_at);
CREATE INDEX IF NOT EXISTS idx_flows_tags           ON public.dq_flows USING gin (tags);
CREATE INDEX IF NOT EXISTS idx_flows_definition     ON public.dq_flows USING gin (flow_definition);


CREATE TABLE IF NOT EXISTS public.flow_executions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flow_id           UUID NOT NULL REFERENCES public.dq_flows(id) ON DELETE CASCADE,
    execution_type    VARCHAR(50) NOT NULL DEFAULT 'manual',
    status            VARCHAR(50) NOT NULL DEFAULT 'pending',
    started_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    duration_seconds  INTEGER,
    nodes_executed    INTEGER DEFAULT 0,
    nodes_passed      INTEGER DEFAULT 0,
    nodes_failed      INTEGER DEFAULT 0,
    nodes_skipped     INTEGER DEFAULT 0,
    execution_config  JSONB,
    result_summary    JSONB,
    error_message     TEXT,
    error_details     JSONB,
    executed_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMP DEFAULT NOW(),
    CONSTRAINT check_execution_type   CHECK (execution_type IN ('manual','scheduled','triggered','test')),
    CONSTRAINT check_execution_status CHECK (status IN ('pending','running','completed','failed','cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_flow_exec_flow     ON public.flow_executions (flow_id);
CREATE INDEX IF NOT EXISTS idx_flow_exec_status   ON public.flow_executions (status);
CREATE INDEX IF NOT EXISTS idx_flow_exec_type     ON public.flow_executions (execution_type);
CREATE INDEX IF NOT EXISTS idx_flow_exec_started  ON public.flow_executions (started_at);
CREATE INDEX IF NOT EXISTS idx_flow_exec_user     ON public.flow_executions (executed_by);
CREATE INDEX IF NOT EXISTS idx_flow_exec_summary  ON public.flow_executions USING gin (result_summary);


CREATE TABLE IF NOT EXISTS public.flow_node_results (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id      UUID NOT NULL REFERENCES public.flow_executions(id) ON DELETE CASCADE,
    node_id           VARCHAR(100) NOT NULL,
    node_type         VARCHAR(50)  NOT NULL,
    status            VARCHAR(50)  NOT NULL DEFAULT 'pending',
    started_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    duration_seconds  INTEGER,
    result_data       JSONB,
    error_message     TEXT,
    error_details     JSONB,
    execution_order   INTEGER,
    created_at        TIMESTAMP DEFAULT NOW(),
    CONSTRAINT check_node_status CHECK (status IN ('pending','running','completed','warning','failed','skipped'))
);

CREATE INDEX IF NOT EXISTS idx_node_results_execution ON public.flow_node_results (execution_id);
CREATE INDEX IF NOT EXISTS idx_node_results_node_id   ON public.flow_node_results (node_id);
CREATE INDEX IF NOT EXISTS idx_node_results_status    ON public.flow_node_results (status);
CREATE INDEX IF NOT EXISTS idx_node_results_type      ON public.flow_node_results (node_type);
CREATE INDEX IF NOT EXISTS idx_node_results_order     ON public.flow_node_results (execution_id, execution_order);
CREATE INDEX IF NOT EXISTS idx_node_results_data      ON public.flow_node_results USING gin (result_data);


CREATE TABLE IF NOT EXISTS public.flow_templates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(255) NOT NULL UNIQUE,
    description         TEXT,
    category            VARCHAR(100),
    template_definition JSONB NOT NULL,
    preview_image_url   TEXT,
    is_public           BOOLEAN DEFAULT FALSE,
    use_count           INTEGER DEFAULT 0,
    created_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_templates_category   ON public.flow_templates (category);
CREATE INDEX IF NOT EXISTS idx_templates_public     ON public.flow_templates (is_public);
CREATE INDEX IF NOT EXISTS idx_templates_use_count  ON public.flow_templates (use_count);


-- ----------------------------------------------------------------------
-- DQ Rules + executions + violations (defined by ``app/models/rule.py``).
-- Required by 013_f031_issues.sql which FKs ``issues.rule_id`` -> dq_rules.
-- ----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.dq_rules (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id      UUID NOT NULL,
    name                 VARCHAR(255) NOT NULL,
    description          TEXT,
    category             VARCHAR(50),
    rule_type            VARCHAR(50),
    canonical_rule       JSONB NOT NULL,
    compiled_sql         TEXT,
    compiled_postgres    TEXT,
    compiled_mysql       TEXT,
    compiled_snowflake   TEXT,
    compiled_spark       TEXT,
    data_source_id       UUID REFERENCES public.data_sources(id) ON DELETE SET NULL,
    target_schema        VARCHAR(255),
    target_table         VARCHAR(255),
    target_columns       TEXT[],
    status               VARCHAR(50) DEFAULT 'draft',
    is_active            BOOLEAN DEFAULT TRUE,
    schedule             JSONB,
    threshold_config     JSONB,
    notification_config  JSONB,
    tags                 TEXT[],
    meta_data            JSONB,
    created_by           UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_by           UUID REFERENCES users(id) ON DELETE SET NULL,
    owner_user_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at           TIMESTAMP DEFAULT NOW(),
    updated_at           TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dq_rules_workspace   ON public.dq_rules (organization_id);
CREATE INDEX IF NOT EXISTS idx_dq_rules_status      ON public.dq_rules (status);
CREATE INDEX IF NOT EXISTS idx_dq_rules_data_source ON public.dq_rules (data_source_id);


CREATE TABLE IF NOT EXISTS public.rule_executions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id           UUID NOT NULL REFERENCES public.dq_rules(id) ON DELETE CASCADE,
    execution_type    VARCHAR(50) NOT NULL,
    status            VARCHAR(50) DEFAULT 'pending',
    started_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    duration_seconds  INTEGER,
    rows_scanned      BIGINT DEFAULT 0,
    rows_passed       BIGINT DEFAULT 0,
    rows_failed       BIGINT DEFAULT 0,
    pass_rate         DECIMAL(5,2),
    error_message     TEXT,
    error_details     JSONB,
    result_details    JSONB,
    execution_params  JSONB,
    environment       JSONB,
    executed_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rule_exec_rule    ON public.rule_executions (rule_id);
CREATE INDEX IF NOT EXISTS idx_rule_exec_status  ON public.rule_executions (status);


CREATE TABLE IF NOT EXISTS public.rule_violations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL REFERENCES public.rule_executions(id) ON DELETE CASCADE,
    row_identifier      TEXT,
    row_number          BIGINT,
    violation_details   JSONB NOT NULL,
    severity            VARCHAR(50),
    category            VARCHAR(50),
    is_sample           BOOLEAN DEFAULT FALSE,
    meta_data           JSONB,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rule_viol_execution ON public.rule_violations (execution_id);
