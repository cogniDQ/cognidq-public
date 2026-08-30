-- Migration 005: Data Sources & Schema Metadata
-- Created: 2026-01-13
-- Description: Tables for managing data source connections and schema metadata

-- Data Sources table
CREATE TABLE IF NOT EXISTS data_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL, -- postgresql, mysql, snowflake, databricks, s3, azure_datalake, gcs
    connection_config JSONB NOT NULL, -- encrypted credentials and connection parameters
    status VARCHAR(50) DEFAULT 'active', -- active, inactive, error, testing
    last_tested_at TIMESTAMP,
    test_result JSONB, -- last test connection result
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_datasource_name_per_org UNIQUE(organization_id, name)
);

-- Data Source Schema Metadata table
CREATE TABLE IF NOT EXISTS data_source_schemas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    schema_name VARCHAR(255),
    table_name VARCHAR(255),
    column_name VARCHAR(255),
    column_type VARCHAR(100),
    is_nullable BOOLEAN,
    is_primary_key BOOLEAN DEFAULT FALSE,
    default_value TEXT,
    metadata JSONB, -- additional column metadata (max_length, precision, scale, etc.)
    refreshed_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_column_per_table UNIQUE(data_source_id, schema_name, table_name, column_name)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_datasources_org ON data_sources(organization_id);
CREATE INDEX IF NOT EXISTS idx_datasources_type ON data_sources(type);
CREATE INDEX IF NOT EXISTS idx_datasources_status ON data_sources(status);
CREATE INDEX IF NOT EXISTS idx_schema_metadata_datasource ON data_source_schemas(data_source_id);
CREATE INDEX IF NOT EXISTS idx_schema_metadata_table ON data_source_schemas(data_source_id, schema_name, table_name);

-- Add datasources permissions to existing permissions table
INSERT INTO permissions (resource, action, description) VALUES
    ('datasources', 'read', 'View data sources'),
    ('datasources', 'write', 'Create and update data sources'),
    ('datasources', 'delete', 'Delete data sources'),
    ('datasources', 'test', 'Test data source connections'),
    ('datasources', 'refresh', 'Refresh data source schema metadata')
ON CONFLICT (resource, action) DO NOTHING;

-- Assign datasources permissions to Admin role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.name = 'Admin' 
  AND r.is_system = TRUE
  AND p.resource = 'datasources'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign read-only datasources permissions to Viewer role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.name = 'Viewer' 
  AND r.is_system = TRUE
  AND p.resource = 'datasources'
  AND p.action = 'read'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign read/write/test/refresh datasources permissions to Editor role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.name = 'Editor' 
  AND r.is_system = TRUE
  AND p.resource = 'datasources'
  AND p.action IN ('read', 'write', 'test', 'refresh')
ON CONFLICT (role_id, permission_id) DO NOTHING;
