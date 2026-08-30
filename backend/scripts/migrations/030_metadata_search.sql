-- Migration 030: Metadata Search Abstraction (F101)
-- Creates metadata_asset_index and metadata_term_index tables
-- with full-text search (tsvector) and trigram indexes

-- ─────────────────────────────────────────────────────────────
-- Asset index: canonical metadata from datasets, fields, datasources
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.metadata_asset_index (
    asset_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID         NOT NULL,
    asset_type      VARCHAR(20)  NOT NULL CHECK (asset_type IN ('dataset', 'field', 'datasource')),
    name            VARCHAR(500) NOT NULL,
    display_name    VARCHAR(500),
    description     VARCHAR(2000),
    business_domain VARCHAR(100),
    data_type       VARCHAR(100),
    parent_asset_id UUID,
    source_table    VARCHAR(100) NOT NULL,
    source_id       UUID         NOT NULL,
    search_text     TSVECTOR,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, source_table, source_id)
);

CREATE INDEX IF NOT EXISTS ix_meta_asset_workspace ON control.metadata_asset_index(workspace_id);
CREATE INDEX IF NOT EXISTS ix_meta_asset_type ON control.metadata_asset_index(asset_type);
CREATE INDEX IF NOT EXISTS ix_meta_asset_domain ON control.metadata_asset_index(business_domain);
CREATE INDEX IF NOT EXISTS ix_meta_asset_search ON control.metadata_asset_index USING GIN(search_text);
CREATE INDEX IF NOT EXISTS ix_meta_asset_name_trgm ON control.metadata_asset_index USING GIN(name gin_trgm_ops);

-- ─────────────────────────────────────────────────────────────
-- Term index: glossary terms and synonyms
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.metadata_term_index (
    term_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID         NOT NULL,
    business_name    VARCHAR(500) NOT NULL,
    technical_name   VARCHAR(500),
    definition       VARCHAR(2000),
    synonyms         JSONB        DEFAULT '[]'::jsonb,
    domain           VARCHAR(100),
    linked_asset_ids JSONB        DEFAULT '[]'::jsonb,
    source           VARCHAR(100) DEFAULT 'manual',
    trust_level      VARCHAR(20)  DEFAULT 'medium'
                     CHECK (trust_level IN ('low', 'medium', 'high', 'authoritative')),
    search_text      TSVECTOR,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_meta_term_workspace ON control.metadata_term_index(workspace_id);
CREATE INDEX IF NOT EXISTS ix_meta_term_domain ON control.metadata_term_index(domain);
CREATE INDEX IF NOT EXISTS ix_meta_term_search ON control.metadata_term_index USING GIN(search_text);
CREATE INDEX IF NOT EXISTS ix_meta_term_name_trgm ON control.metadata_term_index USING GIN(business_name gin_trgm_ops);

-- ─────────────────────────────────────────────────────────────
-- Trigger: auto-update search_text tsvector on asset index
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION control.update_asset_search_text()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_text := to_tsvector('english',
        coalesce(NEW.name, '') || ' ' ||
        coalesce(NEW.display_name, '') || ' ' ||
        coalesce(NEW.description, '') || ' ' ||
        coalesce(NEW.business_domain, '')
    );
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_asset_search_text ON control.metadata_asset_index;
CREATE TRIGGER trg_asset_search_text
    BEFORE INSERT OR UPDATE ON control.metadata_asset_index
    FOR EACH ROW EXECUTE FUNCTION control.update_asset_search_text();

-- ─────────────────────────────────────────────────────────────
-- Trigger: auto-update search_text tsvector on term index
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION control.update_term_search_text()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_text := to_tsvector('english',
        coalesce(NEW.business_name, '') || ' ' ||
        coalesce(NEW.technical_name, '') || ' ' ||
        coalesce(NEW.definition, '') || ' ' ||
        coalesce(NEW.domain, '') || ' ' ||
        coalesce(array_to_string(
            ARRAY(SELECT jsonb_array_elements_text(coalesce(NEW.synonyms, '[]'::jsonb))),
            ' '
        ), '')
    );
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_term_search_text ON control.metadata_term_index;
CREATE TRIGGER trg_term_search_text
    BEFORE INSERT OR UPDATE ON control.metadata_term_index
    FOR EACH ROW EXECUTE FUNCTION control.update_term_search_text();
