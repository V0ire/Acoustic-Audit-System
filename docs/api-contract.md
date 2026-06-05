# API Contract (v1.0)

**Base URL:** `http://<vps-ip>:8000/api`

## 1. POST /login
* **Fungsi:** Mendapatkan token JWT.
* **Auth:** Tidak ada.
* **Request Body (JSON):**
  ```json
  { "username": "admin", "password": "password123" }
  ```
* **Response Body (JSON):**
  ```json
  { "token": "eyJhbGciOiJIUzI1NiIsInR5cCI..." }
  ```   

## 2. GET /measurements
* **Fungsi:** Mendapatkan data pengukuran.
* **Auth:** Wajib (Header: `Authorization: Bearer <token>`)
* **Params (Query):**
- `start_date` (string, YYYY-MM-DD)
- `end_date` (string, YYYY-MM-DD)
- `room` (string, opsional)

**Response Body (JSON):**
```json
[
  {
    "room": "R402",
    "measured_at": "2026-06-05T10:15:00+07:00",
    "total_dba": 67.4,
    "mechanical_confidence": 0.81,
    "human_activity_confidence": 0.29,
    "source_hint": "mechanical_like"
  }
]