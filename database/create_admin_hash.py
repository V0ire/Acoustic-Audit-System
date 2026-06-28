#!/usr/bin/env python3
"""
Generate a bcrypt password hash for the admin user.
Run on VPS: python3 database/create_admin_hash.py

Then copy the SQL output and run it in psql.
"""
import sys

try:
    import bcrypt
except ImportError:
    print("Error: bcrypt not installed. Run: pip3 install bcrypt")
    sys.exit(1)

username = input("Username [admin]: ").strip() or "admin"
password = input("Password: ").strip()

if not password:
    print("Error: password cannot be empty")
    sys.exit(1)

hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

print()
print("=== Run this SQL in psql ===")
print()
print(f"INSERT INTO users (username, password_hash, role)")
print(f"VALUES ('{username}', '{hashed}', 'admin')")
print(f"ON CONFLICT (username)")
print(f"DO UPDATE SET password_hash = EXCLUDED.password_hash;")
print()
print("=== Done ===")
