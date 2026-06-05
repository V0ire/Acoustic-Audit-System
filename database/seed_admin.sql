-- database/seed_admin.sql

-- Insert alat dummy untuk tes M1
INSERT INTO devices (device_id, room, location, description)
VALUES ('ACOUSTIC-PI-001', 'R402', 'Lantai 4 Gedung RSI', 'Alat testing dummy M1')
ON CONFLICT (device_id) DO NOTHING;

-- Insert user admin (Password hash ini cuma dummy sementara, nanti di M2 diurus tim API pakai bcrypt)
INSERT INTO users (username, password_hash, role)
VALUES ('admin', 'dummy_hash_sementara', 'admin')
ON CONFLICT (username) DO NOTHING;