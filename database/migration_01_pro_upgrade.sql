-- database/migration_01_pro_upgrade.sql

-- Additive migration for Pro features
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS spl_avg_db NUMERIC(6,2);
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS spl_max_db NUMERIC(6,2);
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS calibration_offset_db NUMERIC(5,2);
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS status VARCHAR(50);
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS quality_flags JSONB;
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS metric_type VARCHAR(50);
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS weighting VARCHAR(50);

CREATE TABLE IF NOT EXISTS device_health (
    device_id VARCHAR(100) PRIMARY KEY REFERENCES devices(device_id),
    last_seen TIMESTAMPTZ NOT NULL,
    status VARCHAR(50) NOT NULL,
    last_error TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
