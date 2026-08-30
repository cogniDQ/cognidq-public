-- Migration 010: Dashboards & Reporting Tables
-- Created: January 15, 2026
-- Description: Adds tables for dashboards, widgets, reports, and metrics

-- Dashboards table
CREATE TABLE IF NOT EXISTS dashboards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    layout JSONB NOT NULL DEFAULT '[]'::jsonb, -- widget positions and configs
    is_public BOOLEAN DEFAULT FALSE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Dashboard widgets table
CREATE TABLE IF NOT EXISTS dashboard_widgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dashboard_id UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    widget_type VARCHAR(50) NOT NULL, -- kpi, line_chart, bar_chart, pie_chart, table, gauge, heatmap
    title VARCHAR(255) NOT NULL,
    query_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    position JSONB NOT NULL DEFAULT '{}'::jsonb, -- {x, y, w, h}
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Reports table
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    report_type VARCHAR(50) NOT NULL, -- executive, detailed, source, trend, compliance
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    schedule JSONB, -- {frequency, recipients, enabled}
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Report executions table (track generated reports)
CREATE TABLE IF NOT EXISTS report_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, running, completed, failed
    file_path TEXT, -- path to generated file (S3/local)
    file_format VARCHAR(20), -- pdf, excel, csv, json
    error_message TEXT,
    execution_time_seconds DECIMAL(10, 2),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Metrics cache table (store aggregated metrics for fast retrieval)
CREATE TABLE IF NOT EXISTS metrics_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    metric_type VARCHAR(100) NOT NULL, -- overall_score, pass_rate, category_breakdown, etc.
    metric_key VARCHAR(255), -- additional identifier (e.g., source_id, category name)
    metric_value JSONB NOT NULL, -- the actual metric data
    time_period VARCHAR(50), -- day, week, month, all_time
    calculated_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_dashboards_org ON dashboards(organization_id);
CREATE INDEX IF NOT EXISTS idx_dashboards_created_by ON dashboards(created_by);
CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_dashboard ON dashboard_widgets(dashboard_id);
CREATE INDEX IF NOT EXISTS idx_reports_org ON reports(organization_id);
CREATE INDEX IF NOT EXISTS idx_reports_created_by ON reports(created_by);
CREATE INDEX IF NOT EXISTS idx_report_executions_report ON report_executions(report_id);
CREATE INDEX IF NOT EXISTS idx_report_executions_org ON report_executions(organization_id);
CREATE INDEX IF NOT EXISTS idx_report_executions_status ON report_executions(status);
CREATE INDEX IF NOT EXISTS idx_metrics_cache_org_type ON metrics_cache(organization_id, metric_type);
CREATE INDEX IF NOT EXISTS idx_metrics_cache_org_key ON metrics_cache(organization_id, metric_key);
CREATE INDEX IF NOT EXISTS idx_metrics_cache_calculated ON metrics_cache(calculated_at DESC);

-- Add comments
COMMENT ON TABLE dashboards IS 'User-created dashboards with custom widget layouts';
COMMENT ON TABLE dashboard_widgets IS 'Individual widgets within dashboards';
COMMENT ON TABLE reports IS 'Report definitions and schedules';
COMMENT ON TABLE report_executions IS 'History of generated reports';
COMMENT ON TABLE metrics_cache IS 'Cached aggregated metrics for performance';
