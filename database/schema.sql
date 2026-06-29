-- database/schema.sql
-- Clean Pro Upgrade Schema

CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) UNIQUE NOT NULL,
    room VARCHAR(100) NOT NULL,
    location TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) DEFAULT 'admin',
    display_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE llm_usage (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) REFERENCES users(username) ON DELETE CASCADE,
    role VARCHAR(50),
    action VARCHAR(50) DEFAULT 'generate',
    prompt_type VARCHAR(100) DEFAULT 'acoustic_summary',
    success BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE measurements (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) NOT NULL REFERENCES devices(device_id),
    room VARCHAR(100),
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    schema_version VARCHAR(20) DEFAULT '1.0',
    metric_type VARCHAR(50) DEFAULT 'spl_estimate',
    weighting VARCHAR(50) DEFAULT 'flat',
    window_seconds NUMERIC(6,2),

    spl_avg_db NUMERIC(6,2),
    spl_max_db NUMERIC(6,2),
    calibration_offset_db NUMERIC(5,2),
    status VARCHAR(50) DEFAULT 'ok',
    quality_flags JSONB DEFAULT '{}'::jsonb,
    edge_version VARCHAR(100),

    total_dba NUMERIC(6,2), -- Legacy fallback only

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_measurements_device_time
ON measurements (device_id, measured_at DESC);

CREATE TABLE device_health (
    device_id VARCHAR(100) PRIMARY KEY REFERENCES devices(device_id),
    last_seen TIMESTAMPTZ NOT NULL,
    status VARCHAR(50) NOT NULL,
    last_error TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
