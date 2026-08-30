-- Migration 006: Ingestion Jobs
-- Create tables for data ingestion tracking

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    data_source_id UUID REFERENCES data_sources(id) ON DELETE SET NULL,
    
    -- File details
    file_path VARCHAR(512) NOT NULL,
    file_type VARCHAR(50),
    original_filename VARCHAR(255),
    
    -- Target
    target_table VARCHAR(255) NOT NULL,
    
    -- Ingestion mode
    mode VARCHAR(20) NOT NULL DEFAULT 'append',  -- append, replace, upsert
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed, cancelled
    
    -- Progress
    total_rows INTEGER,
    processed_rows INTEGER DEFAULT 0,
    failed_rows INTEGER DEFAULT 0,
    
    -- Error tracking
    error_message TEXT,
    
    -- Metadata (profile, columns, etc.)
    metadata JSONB,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Audit
    created_by UUID REFERENCES users(id) ON DELETE SET NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_org ON ingestion_jobs(organization_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_datasource ON ingestion_jobs(data_source_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_created ON ingestion_jobs(created_at DESC);

-- Add upload directory configuration comment
COMMENT ON TABLE ingestion_jobs IS 'Tracks data ingestion jobs from file uploads';
