-- database/schema.sql

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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE measurements (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) NOT NULL REFERENCES devices(device_id),
    measured_at TIMESTAMPTZ NOT NULL,
    total_dba NUMERIC(6,2) NOT NULL,
    low_freq_ratio NUMERIC(5,3),
    speech_band_ratio NUMERIC(5,3),
    spectral_flatness NUMERIC(5,3),
    spectral_flux NUMERIC(5,3),
    mechanical_confidence NUMERIC(5,3),
    human_activity_confidence NUMERIC(5,3),
    source_hint VARCHAR(100),
    spl_avg_db NUMERIC(6,2),
    spl_max_db NUMERIC(6,2),
    calibration_offset_db NUMERIC(5,2),
    status VARCHAR(50),
    quality_flags JSONB,
    metric_type VARCHAR(50),
    weighting VARCHAR(50),
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