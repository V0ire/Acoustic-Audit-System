-- database/migration_role2.sql
-- Run this manually: psql -U acoustic_user -d acoustic_db -f database/migration_role2.sql

-- 1. Add missing user fields
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;

-- 2. Create LLM usage table
CREATE TABLE IF NOT EXISTS llm_usage (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) REFERENCES users(username) ON DELETE CASCADE,
    role VARCHAR(50),
    action VARCHAR(50) DEFAULT 'generate',
    prompt_type VARCHAR(100) DEFAULT 'acoustic_summary',
    success BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Set demo device metadata (if not already set)
UPDATE devices
SET room = '207',
    location = 'PPBS Gedung B',
    description = 'Acoustic monitoring node for Room 207, PPBS Gedung B'
WHERE device_id = 'ACOUSTIC-PI-001';
