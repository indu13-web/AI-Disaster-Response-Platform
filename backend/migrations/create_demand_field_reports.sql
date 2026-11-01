-- ==============================================================================
-- Migration: Create demand_field_reports table (Isolated & Non-destructive)
-- Purpose: Stores incoming field observations, population updates, severity changes,
--          and manual satellite damage assessments for dynamic demand recalculation.
-- Safety: Does NOT modify or touch any existing ResQ tables.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS demand_field_reports (
    id SERIAL PRIMARY KEY,
    zone_id INTEGER NOT NULL,
    report_type VARCHAR(50) NOT NULL, -- 'field_report', 'population_update', 'severity_change', 'satellite_assessment'
    payload JSONB NOT NULL,
    validation_status VARCHAR(30) NOT NULL, -- 'accepted', 'flagged_for_review', 'rejected'
    source_text VARCHAR(200) NOT NULL,
    idempotency_key VARCHAR(100) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_demand_field_reports_zone_id ON demand_field_reports (zone_id);
