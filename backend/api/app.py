import os
import io
import csv
import json
import urllib.request
import urllib.error
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional

import jwt
import bcrypt
import psycopg2
import psycopg2.extras
from pydantic import BaseModel
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── Config ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://acoustic_user:acoustic_pass@127.0.0.1:5432/acoustic_db",
)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-fallback-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
STALE_AFTER_SECONDS = int(os.getenv("STALE_AFTER_SECONDS", "60"))

security = HTTPBearer(auto_error=False)

app = FastAPI(title="Acoustic Audit API", version="pro-final")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Helpers ─────────────────────────────────────────────────────────────────

def normalize_value(v):
    return float(v) if isinstance(v, Decimal) else v

def normalize_row(row):
    return {k: normalize_value(v) for k, v in dict(row).items()}

def db_conn():
    return psycopg2.connect(DATABASE_URL)

# ── Auth ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow().timestamp() + JWT_EXPIRE_HOURS * 3600
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("exp", 0) < datetime.utcnow().timestamp():
            raise HTTPException(status_code=401, detail="Token expired")
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_admin(user=Depends(verify_token)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

# ── Noise classification ───────────────────────────────────────────────────

def classify_noise(spl: float) -> tuple:
    """Returns (state, message) tuple."""
    if spl < 50:
        return "Quiet", "Low acoustic level, suitable for focused work."
    elif spl < 60:
        return "Normal", "Typical indoor acoustic condition."
    elif spl < 70:
        return "Elevated", "Noise level is rising and may reduce comfort."
    elif spl < 85:
        return "Noisy", "Noise may disturb concentration."
    else:
        return "Alert", "High acoustic level detected."

def get_unit(weighting: str) -> str:
    return "dBA" if weighting and weighting.upper() == "A" else "dB"

def parse_quality_flags(qf):
    if not qf:
        return {}
    if isinstance(qf, str):
        try:
            return json.loads(qf)
        except Exception:
            return {}
    return qf if isinstance(qf, dict) else {}

# ── Routes: health / root ──────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "Acoustic Audit API", "status": "ok"}

@app.get("/api/health")
def health():
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "ok", "database": "ok"}
    except Exception as exc:
        return {"status": "error", "database": "error", "detail": str(exc)}

# ── Login ───────────────────────────────────────────────────────────────────

@app.post("/api/login")
def login(body: LoginRequest):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT username, password_hash, role, is_active, display_name FROM users WHERE username = %s",
                (body.username,),
            )
            user = cur.fetchone()

    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials or inactive user")

    if not bcrypt.checkpw(body.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ponytail: fire-and-forget last_login update
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET last_login = NOW() WHERE username = %s", (body.username,))
            conn.commit()
    except Exception:
        pass

    token = create_token(user["username"], user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }

# ── Devices ─────────────────────────────────────────────────────────────────

@app.get("/api/devices")
def get_devices(user=Depends(verify_token)):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT d.device_id, d.room, d.location, d.description, d.created_at,
                       h.last_seen, h.status AS health_status, h.last_error, h.updated_at
                FROM devices d
                LEFT JOIN device_health h ON h.device_id = d.device_id
                ORDER BY d.device_id ASC
            """)
            rows = cur.fetchall()
    return {"devices": [normalize_row(r) for r in rows]}

# ── Measurements ────────────────────────────────────────────────────────────

@app.get("/api/measurements")
def get_measurements(
    user=Depends(verify_token),
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
):
    params, where = [], []
    if device_id:
        where.append("m.device_id = %s"); params.append(device_id)
    if start:
        where.append("m.measured_at >= %s"); params.append(start)
    if end:
        where.append("m.measured_at <= %s"); params.append(end)
    wc = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)

    query = f"""
        SELECT m.device_id, d.room, m.measured_at, m.total_dba,
               m.spl_avg_db, m.spl_max_db, m.calibration_offset_db, m.status,
               m.quality_flags, m.metric_type, m.weighting,
               m.window_seconds, m.schema_version, m.edge_version
        FROM measurements m JOIN devices d ON m.device_id = d.device_id
        {wc} ORDER BY m.measured_at DESC LIMIT %s
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [normalize_row(r) for r in rows]

# ── CSV Export ──────────────────────────────────────────────────────────────

@app.get("/api/measurements/export.csv")
def export_measurements_csv(
    user=Depends(verify_token),
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    params, where = [], []
    if device_id:
        where.append("m.device_id = %s"); params.append(device_id)
    if start:
        where.append("m.measured_at >= %s"); params.append(start)
    if end:
        where.append("m.measured_at <= %s"); params.append(end)
    wc = ("WHERE " + " AND ".join(where)) if where else ""

    cols = ["measured_at", "device_id", "room", "spl_avg_db", "spl_max_db",
            "weighting", "metric_type", "status", "calibration_offset_db",
            "edge_version", "quality_flags", "window_seconds", "schema_version"]

    query = f"""
        SELECT m.measured_at, m.device_id, d.room, m.spl_avg_db, m.spl_max_db,
               m.weighting, m.metric_type, m.status, m.calibration_offset_db,
               m.edge_version, m.quality_flags, m.window_seconds, m.schema_version
        FROM measurements m JOIN devices d ON m.device_id = d.device_id
        {wc} ORDER BY m.measured_at DESC LIMIT %s
    """
    params.append(limit)

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(cols)
    for row in rows:
        nr = normalize_row(row)
        w.writerow([nr.get(c) for c in cols])

    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=export.csv"})

# ── Report Summary ──────────────────────────────────────────────────────────

@app.get("/api/reports/summary")
def get_report_summary(
    user=Depends(verify_token),
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    params, where = [], []
    if device_id:
        where.append("device_id = %s"); params.append(device_id)
    if start:
        where.append("measured_at >= %s"); params.append(start)
    if end:
        where.append("measured_at <= %s"); params.append(end)
    wc = ("WHERE " + " AND ".join(where)) if where else ""

    query = f"""
        SELECT measured_at, spl_avg_db, spl_max_db, total_dba, weighting, status, quality_flags
        FROM measurements {wc} ORDER BY measured_at ASC
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    if not rows:
        return {"device_id": device_id, "start": start, "end": end,
                "sample_count": 0, "plain_summary": "No data available for the selected period."}

    spl_values, max_values, anomalies, peak_times = [], [], [], []
    above_threshold_count = 0
    threshold_db = 65.0
    weighting_dist, status_dist, quality_dist = {}, {}, {}

    for row in rows:
        nr = normalize_row(row)
        val = nr.get("spl_avg_db") if nr.get("spl_avg_db") is not None else nr.get("total_dba")
        max_val = nr.get("spl_max_db") if nr.get("spl_max_db") is not None else val

        w = nr.get("weighting") or "unknown"
        weighting_dist[w] = weighting_dist.get(w, 0) + 1
        s = nr.get("status") or "ok"
        status_dist[s] = status_dist.get(s, 0) + 1

        qf = parse_quality_flags(nr.get("quality_flags"))
        for k, v in qf.items():
            if v:
                quality_dist[k] = quality_dist.get(k, 0) + 1

        if val is not None:
            spl_values.append(val)
        if max_val is not None:
            max_values.append(max_val)

        if max_val is not None and max_val > threshold_db:
            above_threshold_count += 1
            anomalies.append({"measured_at": nr.get("measured_at"),
                              "type": "threshold_exceeded",
                              "reason": f"SPL exceeded {threshold_db} dB threshold"})
        if max_val is not None and val is not None:
            peak_times.append({"measured_at": nr.get("measured_at"),
                               "spl_max_db": max_val, "spl_avg_db": val})

    if not spl_values:
        return {"sample_count": len(rows),
                "plain_summary": "No valid numeric data found for the selected period."}

    avg_spl = round(sum(spl_values) / len(spl_values), 2)
    min_spl = round(min(spl_values), 2)
    max_spl = round(max(max_values), 2)
    peak_times = sorted(peak_times, key=lambda x: x["spl_max_db"], reverse=True)[:5]
    anomalies = anomalies[:10]

    return {
        "device_id": device_id, "start": start, "end": end,
        "sample_count": len(rows),
        "avg_spl": avg_spl, "min_spl": min_spl, "max_spl": max_spl,
        "threshold_db": threshold_db,
        "above_threshold_count": above_threshold_count,
        "peak_times": peak_times, "anomalies": anomalies,
        "weighting_dist": weighting_dist, "status_dist": status_dist,
        "quality_dist": quality_dist,
        "plain_summary": (f"During the selected period, the average SPL was {avg_spl} dB "
                          f"with a maximum of {max_spl} dB. "
                          f"{above_threshold_count} samples exceeded the {threshold_db} dB threshold."),
    }

# ── Users (admin) ──────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    display_name: str

class UserUpdate(BaseModel):
    role: str | None = None
    display_name: str | None = None
    is_active: bool | None = None

@app.get("/api/users")
def get_users(user=Depends(require_admin)):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT username, role, display_name, is_active, last_login, created_at FROM users ORDER BY created_at DESC")
            rows = cur.fetchall()
    return {"users": [normalize_row(r) for r in rows]}

@app.post("/api/users")
def create_user(body: UserCreate, user=Depends(require_admin)):
    if body.role not in ("admin", "supervisor", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, display_name) VALUES (%s, %s, %s, %s)",
                    (body.username, pw_hash, body.role, body.display_name),
                )
            conn.commit()
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    return {"status": "ok", "message": "User created"}

@app.patch("/api/users/{username}")
def update_user(username: str, body: UserUpdate, user=Depends(require_admin)):
    if username == user["sub"]:
        if body.role is not None or body.is_active is not None:
            raise HTTPException(status_code=400, detail="Cannot change own role or active status")
    if body.role and body.role not in ("admin", "supervisor", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")

    updates, params = [], []
    if body.role is not None:
        updates.append("role = %s"); params.append(body.role)
    if body.display_name is not None:
        updates.append("display_name = %s"); params.append(body.display_name)
    if body.is_active is not None:
        updates.append("is_active = %s"); params.append(body.is_active)
    if not updates:
        return {"status": "ok"}

    params.append(username)
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE username = %s", params)
        conn.commit()
    return {"status": "ok"}

@app.delete("/api/users/{username}")
def delete_user(username: str, user=Depends(require_admin)):
    if username == user["sub"]:
        raise HTTPException(status_code=400, detail="Cannot delete own account")
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_active = false WHERE username = %s", (username,))
        conn.commit()
    return {"status": "ok"}

# ── Device metadata (admin) ────────────────────────────────────────────────

class DeviceUpdate(BaseModel):
    room: str | None = None
    location: str | None = None
    description: str | None = None

class BulkDeviceUpdate(BaseModel):
    scope: str  # "single", "selected", "all"
    device_ids: list[str] = []
    fields: DeviceUpdate
    confirm_all: bool = False

@app.patch("/api/devices/{device_id}")
def update_device(device_id: str, body: DeviceUpdate, user=Depends(require_admin)):
    updates, params = [], []
    if body.room is not None:
        updates.append("room = %s"); params.append(body.room)
    if body.location is not None:
        updates.append("location = %s"); params.append(body.location)
    if body.description is not None:
        updates.append("description = %s"); params.append(body.description)
    if not updates:
        return {"status": "ok"}

    params.append(device_id)
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE devices SET {', '.join(updates)} WHERE device_id = %s", params)
        conn.commit()
    return {"status": "ok"}

@app.patch("/api/devices")
def bulk_update_devices(body: BulkDeviceUpdate, user=Depends(require_admin)):
    updates, params = [], []
    f = body.fields
    if f.room is not None:
        updates.append("room = %s"); params.append(f.room)
    if f.location is not None:
        updates.append("location = %s"); params.append(f.location)
    if f.description is not None:
        updates.append("description = %s"); params.append(f.description)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if body.scope == "all":
        if not body.confirm_all:
            raise HTTPException(status_code=400, detail="Must confirm_all=true for all-device update")
        query = f"UPDATE devices SET {', '.join(updates)}"
    elif body.scope in ("single", "selected"):
        if not body.device_ids:
            raise HTTPException(status_code=400, detail="No device_ids provided")
        placeholders = ",".join(["%s"] * len(body.device_ids))
        query = f"UPDATE devices SET {', '.join(updates)} WHERE device_id IN ({placeholders})"
        params.extend(body.device_ids)
    else:
        raise HTTPException(status_code=400, detail="Invalid scope")

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            affected = cur.rowcount
        conn.commit()
    return {"status": "ok", "affected": affected}

# ── Status Summary ──────────────────────────────────────────────────────────

@app.get("/api/status/summary")
def get_status_summary(
    user=Depends(verify_token),
    device_id: str | None = None,
):
    # Build query: prefer specific device, fallback to latest
    params = []
    device_filter = ""
    if device_id:
        device_filter = "AND m.device_id = %s"
        params.append(device_id)

    query = f"""
        SELECT m.device_id, d.room, d.location,
               m.spl_avg_db, m.spl_max_db, m.weighting,
               m.measured_at, m.quality_flags, m.total_dba
        FROM measurements m
        JOIN devices d ON m.device_id = d.device_id
        WHERE 1=1 {device_filter}
        ORDER BY m.measured_at DESC LIMIT 1
    """

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()

    if not row:
        return {
            "device_id": device_id or "Unknown", "room": "--", "location": "--",
            "latest_spl": 0, "latest_spl_max": 0, "weighting": "flat", "unit": "dB",
            "noise_state": "Unknown",
            "noise_message": "No acoustic measurement has been received yet.",
            "last_known_noise_state": "Unknown",
            "data_status": "No data", "device_status": "offline", "is_stale": True,
            "stale_seconds": 0, "updated_at": "", "quality": "Normal",
        }

    row = normalize_row(row)
    spl = row.get("spl_avg_db") or row.get("total_dba") or 0.0
    spl_max = row.get("spl_max_db") or spl
    weighting = row.get("weighting") or "flat"
    unit = get_unit(weighting)

    state, message = classify_noise(spl)

    now_utc = datetime.now(timezone.utc)
    measured_at = row["measured_at"]
    if measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=timezone.utc)
    time_diff = (now_utc - measured_at).total_seconds()

    is_stale = time_diff > STALE_AFTER_SECONDS
    data_status = "Stale" if is_stale else "Live"
    device_status = "stale" if is_stale else "online"

    qf = parse_quality_flags(row.get("quality_flags"))
    quality = "Normal"
    if qf.get("clipping"):
        quality = "Clipping"
    elif qf.get("low_signal"):
        quality = "Low signal"
    elif qf.get("mic_error"):
        quality = "Mic error"
    elif not qf:
        quality = "Not reported"

    return {
        "device_id": row["device_id"],
        "room": row["room"],
        "location": row["location"],
        "latest_spl": spl,
        "latest_spl_max": spl_max,
        "weighting": weighting,
        "unit": unit,
        "noise_state": state,
        "noise_message": message,
        "last_known_noise_state": state,
        "data_status": data_status,
        "device_status": device_status,
        "is_stale": is_stale,
        "stale_seconds": int(time_diff),
        "updated_at": row["measured_at"].isoformat(),
        "quality": quality,
    }

# ── AI Report ───────────────────────────────────────────────────────────────

AI_SYSTEM_PROMPT = """You are an acoustic monitoring analyst for the Acoustic Monitoring Console, an IoT-based room noise monitoring system.

Use only the acoustic summary JSON provided by the backend.
Answer in Indonesian.
Do not invent causes that are not supported by the data.
Do not claim the system is a certified sound level meter.
Do not claim certified LAeq unless the summary explicitly says LAeq is available.
Call all values "SPL estimate" unless otherwise specified.
If weighting is "flat" or unknown, say "dB SPL estimate", not "dBA".
If weighting is "A", you may say "dBA estimate".
If data_status is "Stale", clearly say the report is based on latest stored data, not current live data.
Mention quality issues if clipping, low_signal, mic_error, stale data, missing fields, or unusual spikes exist.
If spikes are provided, mention their timestamps and values.
Do not guess exact causes like door slam, motorcycle, or people talking unless source metadata exists.
Use cautious wording such as "possible short-duration noise event".

Required output structure:
1. Ringkasan kondisi
2. Detail angka utama
3. Analisis tren dan spike
4. Status data dan kualitas sensor
5. Interpretasi kenyamanan/risiko
6. Rekomendasi tindakan
7. Catatan keterbatasan""".strip()


def _build_ai_summary(device_id: str | None, start: str | None, end: str | None, limit: int = 100) -> dict:
    """Build rich AI-ready summary from DB. Phase 7 implementation."""
    params, where = [], []
    if device_id:
        where.append("m.device_id = %s"); params.append(device_id)
    if start:
        where.append("m.measured_at >= %s"); params.append(start)
    if end:
        where.append("m.measured_at <= %s"); params.append(end)
    wc = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get device metadata
            dev_meta = {"device_id": device_id or "unknown", "room": "--", "location": "--", "description": "--"}
            if device_id:
                cur.execute("SELECT device_id, room, location, description FROM devices WHERE device_id = %s", (device_id,))
                d = cur.fetchone()
                if d:
                    dev_meta = normalize_row(d)

            # Get measurements
            cur.execute(f"""
                SELECT m.measured_at, m.spl_avg_db, m.spl_max_db, m.total_dba,
                       m.weighting, m.status, m.quality_flags
                FROM measurements m
                {("JOIN devices d ON m.device_id = d.device_id" if not wc else "JOIN devices d ON m.device_id = d.device_id")}
                {wc} ORDER BY m.measured_at ASC LIMIT %s
            """, params)
            rows = cur.fetchall()

    if not rows:
        return {"device": dev_meta, "metrics": {"sample_count": 0}, "limitations": [
            "No data available for this period."]}

    spl_vals, max_vals = [], []
    quality_counts = {"normal": 0, "clipping": 0, "low_signal": 0, "mic_error": 0, "not_reported": 0}
    spikes = []
    dominant_weighting = "flat"

    for row in rows:
        nr = normalize_row(row)
        val = nr.get("spl_avg_db") if nr.get("spl_avg_db") is not None else nr.get("total_dba")
        mx = nr.get("spl_max_db") if nr.get("spl_max_db") is not None else val
        if val is not None:
            spl_vals.append(val)
        if mx is not None:
            max_vals.append(mx)

        w = nr.get("weighting") or "flat"
        if w.upper() == "A":
            dominant_weighting = "A"

        qf = parse_quality_flags(nr.get("quality_flags"))
        if not qf:
            quality_counts["not_reported"] += 1
        elif qf.get("clipping"):
            quality_counts["clipping"] += 1
        elif qf.get("low_signal"):
            quality_counts["low_signal"] += 1
        elif qf.get("mic_error"):
            quality_counts["mic_error"] += 1
        else:
            quality_counts["normal"] += 1

        # Spike: spl_max_db >= 65
        if mx is not None and mx >= 65:
            spikes.append({"measured_at": str(nr.get("measured_at")),
                           "spl_avg_db": val, "spl_max_db": mx,
                           "reason": "above fixed threshold"})

    avg_spl = round(sum(spl_vals) / len(spl_vals), 2) if spl_vals else 0

    # Also detect spikes above avg + 15
    for row in rows:
        nr = normalize_row(row)
        mx = nr.get("spl_max_db") if nr.get("spl_max_db") is not None else None
        if mx is not None and mx >= avg_spl + 15 and mx < 65:
            spikes.append({"measured_at": str(nr.get("measured_at")),
                           "spl_avg_db": nr.get("spl_avg_db"), "spl_max_db": mx,
                           "reason": "above baseline + 15 dB"})

    spikes = sorted(spikes, key=lambda x: x.get("spl_max_db", 0), reverse=True)[:10]
    unit = "dBA" if dominant_weighting == "A" else "dB"

    # Current noise state from latest measurement
    latest_spl = spl_vals[-1] if spl_vals else 0
    noise_state, _ = classify_noise(latest_spl)

    time_range_start = str(rows[0].get("measured_at", "")) if rows else ""
    time_range_end = str(rows[-1].get("measured_at", "")) if rows else ""

    return {
        "device": {
            **dev_meta,
            "microphone": {
                "type": "Configured edge microphone",
                "calibration_status": "prototype calibration offset",
                "limitations": "not a certified sound level meter",
            },
        },
        "time_range": {"start": time_range_start, "end": time_range_end},
        "metrics": {
            "sample_count": len(rows),
            "avg_spl": avg_spl,
            "min_spl": round(min(spl_vals), 2) if spl_vals else 0,
            "max_spl": round(max(max_vals), 2) if max_vals else 0,
            "unit": unit,
            "weighting": dominant_weighting,
            "metric_type": "spl_estimate",
        },
        "noise_state": {
            "current": noise_state,
            "data_status": "Live",  # ponytail: caller should override if stale
            "thresholds": {"quiet": "<50", "normal": "50-60", "elevated": "60-70", "noisy": "70-85", "alert": ">=85"},
        },
        "spikes": spikes,
        "quality": quality_counts,
        "algorithm_notes": {
            "spike_rule": "spike if spl_max_db >= 65 dB or exceeds recent average by >= 15 dB",
            "stale_rule": f"stale if latest measurement age > {STALE_AFTER_SECONDS}s",
        },
        "limitations": [
            "Values are SPL estimates from an IoT microphone.",
            f"{unit} weighting {'(A-weighted)' if dominant_weighting == 'A' else '(flat, not dBA)'}.",
            "Formal acoustic compliance requires calibration against a reference sound level meter.",
            "Do not infer exact noise source without source classification metadata.",
        ],
    }


def _get_ai_config() -> dict:
    """Read AI provider config with backward compat for old LLM_* env vars."""
    ai_enabled = os.getenv("AI_ENABLED", os.getenv("LLM_ENABLED", "false")).lower() == "true"
    provider = os.getenv("AI_PROVIDER", "none")
    timeout = int(os.getenv("AI_TIMEOUT_SECONDS", os.getenv("LLM_TIMEOUT_SECONDS", "30")))

    # OpenAI-compatible
    oai_base = os.getenv("AI_OPENAI_BASE_URL", os.getenv("LLM_BASE_URL", ""))
    oai_key = os.getenv("AI_OPENAI_API_KEY", os.getenv("LLM_API_KEY", ""))
    oai_model = os.getenv("AI_OPENAI_MODEL", os.getenv("LLM_MODEL", ""))

    # DigitalOcean Agent
    do_enabled = os.getenv("DO_AI_ENABLED", "false").lower() == "true"
    do_endpoint = os.getenv("DO_AI_ENDPOINT", "")
    do_key = os.getenv("DO_AI_API_KEY", "")
    do_agent_id = os.getenv("DO_AI_AGENT_ID", "")
    do_model = os.getenv("DO_AI_MODEL", "")

    # Auto-detect provider if not explicitly set
    if provider == "none":
        if do_enabled and do_endpoint and do_key:
            provider = "digitalocean_agent"
        elif ai_enabled and oai_base and oai_key:
            provider = "openai_compatible"

    return {
        "enabled": ai_enabled or do_enabled,
        "provider": provider,
        "timeout": timeout,
        "oai_base": oai_base, "oai_key": oai_key, "oai_model": oai_model,
        "do_endpoint": do_endpoint, "do_key": do_key, "do_agent_id": do_agent_id, "do_model": do_model,
    }


def _call_ai(cfg: dict, summary_json: str) -> tuple:
    """Call AI provider. Returns (text, success, error_msg)."""
    user_prompt = f"Analyze this acoustic monitoring summary.\n\nSUMMARY_JSON:\n{summary_json}"

    if cfg["provider"] == "openai_compatible":
        return _call_openai_compatible(cfg, user_prompt)
    elif cfg["provider"] == "digitalocean_agent":
        return _call_do_agent(cfg, user_prompt)
    else:
        return ("", False, "Unknown AI provider")


def _call_openai_compatible(cfg: dict, user_prompt: str) -> tuple:
    base = cfg["oai_base"].rstrip("/")
    req_data = {
        "model": cfg["oai_model"],
        "messages": [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(req_data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['oai_key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return (body["choices"][0]["message"]["content"], True, "")
    except Exception as e:
        return ("", False, str(e))


def _call_do_agent(cfg: dict, user_prompt: str) -> tuple:
    """Call DigitalOcean AI Agent endpoint.
    # TODO: verify exact DO Agent API shape when endpoint is configured.
    # For now, assume OpenAI-compatible chat completions shape.
    """
    endpoint = cfg["do_endpoint"].rstrip("/")
    req_data = {
        "messages": [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    if cfg["do_model"]:
        req_data["model"] = cfg["do_model"]
    if cfg["do_agent_id"]:
        req_data["agent_id"] = cfg["do_agent_id"]

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(req_data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['do_key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            # Try standard OpenAI shape first, then fallback
            if "choices" in body:
                return (body["choices"][0]["message"]["content"], True, "")
            elif "response" in body:
                return (body["response"], True, "")
            else:
                return (json.dumps(body), True, "")
    except Exception as e:
        return ("", False, str(e))


class ReportRequest(BaseModel):
    summary_data: dict | None = None
    device_id: str | None = None
    start: str | None = None
    end: str | None = None
    limit: int = 100

@app.post("/api/reports/generate-ai")
def generate_ai_report(body: ReportRequest, user=Depends(verify_token)):
    # Quota check
    limits = {"admin": 30, "supervisor": 15, "viewer": 5}
    quota = limits.get(user.get("role", "viewer"), 5)

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM llm_usage
                    WHERE username = %s AND created_at >= NOW() - INTERVAL '1 day'
                """, (user["sub"],))
                usage_count = cur.fetchone()[0]
    except Exception:
        usage_count = 0  # ponytail: don't block report if quota table is missing

    if usage_count >= quota:
        raise HTTPException(status_code=429, detail=f"Daily AI quota exceeded. Limit is {quota}.")

    # Build rich summary (Phase 7): prefer backend-generated if device_id provided
    if body.device_id:
        ai_summary = _build_ai_summary(body.device_id, body.start, body.end, body.limit)
    elif body.summary_data:
        ai_summary = body.summary_data  # backward compat
    else:
        ai_summary = {"error": "No device_id or summary_data provided"}

    summary_json = json.dumps(ai_summary, ensure_ascii=False, indent=2, default=str)

    cfg = _get_ai_config()
    report_text = ""
    success = False
    error_msg = ""

    if not cfg["enabled"]:
        # Deterministic fallback
        plain = ai_summary.get("plain_summary", "") if isinstance(ai_summary, dict) else ""
        if not plain and isinstance(ai_summary, dict):
            m = ai_summary.get("metrics", {})
            plain = f"Average SPL: {m.get('avg_spl', '--')} {m.get('unit', 'dB')}, Max: {m.get('max_spl', '--')} {m.get('unit', 'dB')}, Samples: {m.get('sample_count', 0)}"
        report_text = f"AI is not enabled. Deterministic summary:\n{plain}"
    else:
        report_text, success, error_msg = _call_ai(cfg, summary_json)
        if not success:
            plain = ai_summary.get("plain_summary", "") if isinstance(ai_summary, dict) else ""
            if not plain and isinstance(ai_summary, dict):
                m = ai_summary.get("metrics", {})
                plain = f"Average SPL: {m.get('avg_spl', '--')} {m.get('unit', 'dB')}, Max: {m.get('max_spl', '--')} {m.get('unit', 'dB')}"
            report_text = f"AI provider unavailable. Showing deterministic summary instead.\n\n{plain}"

    # Record usage (safe — don't crash if table missing)
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO llm_usage (username, role, success, error_message)
                    VALUES (%s, %s, %s, %s)
                """, (user["sub"], user.get("role"), success, error_msg[:500] if error_msg else ""))
            conn.commit()
    except Exception:
        pass  # ponytail: logging failure must not crash the report endpoint

    return {"report": report_text, "used_quota": usage_count + 1, "max_quota": quota}
