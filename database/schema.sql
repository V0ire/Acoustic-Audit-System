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
    spl_avg_db NUMERIC(6,2),
    spl_max_db NUMERIC(6,2),
    calibration_offset_db NUMERIC(5,2),
    status VARCHAR(50),
    quality_flags JSONB,
    total_dba NUMERIC(6,2), -- Legacy fallback
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_measurements_device_time
ON measurements (device_id, measured_at DESC);

CREATE INDEX idx_measurements_device_time
ON measurements (device_id, measured_at DESC);