-- database/update_device_info.sql
-- Safe UPDATE to set real demo values for ACOUSTIC-PI-001
-- Run this manually: psql -U acoustic_user -d acoustic_db -f database/update_device_info.sql

UPDATE devices
SET room = '207',
    location = 'PPBS Gedung B',
    description = 'Acoustic monitoring node for Room 207, PPBS Gedung B'
WHERE device_id = 'ACOUSTIC-PI-001';
