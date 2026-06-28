import os
import io
import csv
from decimal import Decimal
from datetime import datetime, timezone
import json
import jwt
import bcrypt
import urllib.request
import urllib.error
from pydantic import BaseModel

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Query, Request, HTTPException, Depends
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://acoustic_user:acoustic_pass@127.0.0.1:5432/acoustic_db",
)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-fallback-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

security = HTTPBearer(auto_error=False)

app = FastAPI(title="Acoustic Audit API", version="pro-upgrade-local")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def normalize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def normalize_row(row):
    return {key: normalize_value(value) for key, value in dict(row).items()}


def db_conn():
    return psycopg2.connect(DATABASE_URL)


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


@app.get("/")
def root():
    return {
        "service": "Acoustic Audit API",
        "status": "ok",
    }


@app.get("/api/health")
def health():
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {
            "status": "ok",
            "database": "ok",
        }
    except Exception as exc:
        return {
            "status": "error",
            "database": "error",
            "detail": str(exc),
        }


@app.post("/api/login")
def login(body: LoginRequest):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT username, password_hash, role, is_active, display_name FROM users WHERE username = %s", (body.username,))
            user = cur.fetchone()

    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials or inactive user")

    if not bcrypt.checkpw(body.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET last_login = NOW() WHERE username = %s", (body.username,))
        conn.commit()

    token = create_token(user["username"], user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"]
    }


@app.get("/api/devices")
def get_devices(user=Depends(verify_token)):
    query = """
        SELECT
            d.device_id,
            d.room,
            d.location,
            d.description,
            d.created_at,
            h.last_seen,
            h.status AS health_status,
            h.last_error,
            h.updated_at
        FROM devices d
        LEFT JOIN device_health h ON h.device_id = d.device_id
        ORDER BY d.device_id ASC
    """

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()

    return {
        "devices": [normalize_row(row) for row in rows],
    }


@app.get("/api/measurements")
def get_measurements(
    user=Depends(verify_token),
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
):
    params = []
    where_clauses = []

    if device_id:
        where_clauses.append("m.device_id = %s")
        params.append(device_id)
        
    if start:
        where_clauses.append("m.measured_at >= %s")
        params.append(start)
        
    if end:
        where_clauses.append("m.measured_at <= %s")
        params.append(end)

    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    params.append(limit)

    query = f"""
        SELECT 
            m.device_id, 
            d.room, 
            m.measured_at, 
            m.total_dba, 
            m.spl_avg_db,
            m.spl_max_db,
            m.calibration_offset_db,
            m.status,
            m.quality_flags,
            m.metric_type,
            m.weighting,
            m.window_seconds,
            m.schema_version,
            m.edge_version
        FROM measurements m
        JOIN devices d ON m.device_id = d.device_id
        {where_clause}
        ORDER BY m.measured_at DESC
        LIMIT %s
    """

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [normalize_row(row) for row in rows]


@app.get("/api/measurements/export.csv")
def export_measurements_csv(
    user=Depends(verify_token),
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    params = []
    where_clauses = []

    if device_id:
        where_clauses.append("m.device_id = %s")
        params.append(device_id)
    if start:
        where_clauses.append("m.measured_at >= %s")
        params.append(start)
    if end:
        where_clauses.append("m.measured_at <= %s")
        params.append(end)

    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT 
            m.measured_at,
            m.device_id, 
            d.room, 
            m.spl_avg_db,
            m.spl_max_db,
            m.weighting,
            m.metric_type,
            m.status,
            m.calibration_offset_db,
            m.edge_version,
            m.quality_flags,
            m.window_seconds,
            m.schema_version
        FROM measurements m
        JOIN devices d ON m.device_id = d.device_id
        {where_clause}
        ORDER BY m.measured_at DESC
        LIMIT %s
    """
    
    params.append(limit)

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "measured_at", "device_id", "room", "spl_avg_db", "spl_max_db", 
        "weighting", "metric_type", "status", "calibration_offset_db", 
        "edge_version", "quality_flags", "window_seconds", "schema_version"
    ])
    
    for row in rows:
        norm_row = normalize_row(row)
        writer.writerow([
            norm_row.get("measured_at"),
            norm_row.get("device_id"),
            norm_row.get("room"),
            norm_row.get("spl_avg_db"),
            norm_row.get("spl_max_db"),
            norm_row.get("weighting"),
            norm_row.get("metric_type"),
            norm_row.get("status"),
            norm_row.get("calibration_offset_db"),
            norm_row.get("edge_version"),
            norm_row.get("quality_flags"),
            norm_row.get("window_seconds"),
            norm_row.get("schema_version")
        ])

    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=export.csv"})


@app.get("/api/reports/summary")
def get_report_summary(
    user=Depends(verify_token),
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    params = []
    where_clauses = []

    if device_id:
        where_clauses.append("device_id = %s")
        params.append(device_id)
    if start:
        where_clauses.append("measured_at >= %s")
        params.append(start)
    if end:
        where_clauses.append("measured_at <= %s")
        params.append(end)

    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT 
            measured_at,
            spl_avg_db,
            spl_max_db,
            total_dba,
            weighting,
            status,
            quality_flags
        FROM measurements
        {where_clause}
        ORDER BY measured_at ASC
    """

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            
    if not rows:
        return {
            "device_id": device_id,
            "start": start,
            "end": end,
            "sample_count": 0,
            "plain_summary": "No data available for the selected period."
        }

    spl_values = []
    max_values = []
    anomalies = []
    peak_times = []
    above_threshold_count = 0
    threshold_db = 65.0
    
    weighting_dist = {}
    status_dist = {}
    quality_dist = {}

    for row in rows:
        norm_row = normalize_row(row)
        # fallback to total_dba if spl_avg_db is missing
        val = norm_row.get("spl_avg_db") if norm_row.get("spl_avg_db") is not None else norm_row.get("total_dba")
        max_val = norm_row.get("spl_max_db") if norm_row.get("spl_max_db") is not None else val
        
        w = norm_row.get("weighting") or "unknown"
        weighting_dist[w] = weighting_dist.get(w, 0) + 1
        
        s = norm_row.get("status") or "ok"
        status_dist[s] = status_dist.get(s, 0) + 1
        
        q = norm_row.get("quality_flags")
        if q:
            if isinstance(q, str):
                import json
                try:
                    q = json.loads(q)
                except Exception:
                    q = {}
            if isinstance(q, dict):
                for k, v in q.items():
                    if v:
                        quality_dist[k] = quality_dist.get(k, 0) + 1

        if val is not None:
            spl_values.append(val)
        if max_val is not None:
            max_values.append(max_val)
            
        # check threshold
        if max_val is not None and max_val > threshold_db:
            above_threshold_count += 1
            anomalies.append({
                "measured_at": norm_row.get("measured_at"),
                "type": "threshold_exceeded",
                "reason": f"SPL exceeded {threshold_db} dB threshold"
            })
            peak_times.append({
                "measured_at": norm_row.get("measured_at"),
                "spl_max_db": max_val,
                "spl_avg_db": val
            })

    if not spl_values:
        return {
            "sample_count": len(rows),
            "plain_summary": "No valid numeric data found for the selected period."
        }

    avg_spl = round(sum(spl_values) / len(spl_values), 2)
    min_spl = round(min(spl_values), 2)
    max_spl = round(max(max_values), 2)
    
    # only keep top 5 peak times
    peak_times = sorted(peak_times, key=lambda x: x["spl_max_db"], reverse=True)[:5]
    # only keep top 10 anomalies
    anomalies = anomalies[:10]

    return {
        "device_id": device_id,
        "start": start,
        "end": end,
        "sample_count": len(rows),
        "avg_spl": avg_spl,
        "min_spl": min_spl,
        "max_spl": max_spl,
        "threshold_db": threshold_db,
        "above_threshold_count": above_threshold_count,
        "peak_times": peak_times,
        "anomalies": anomalies,
        "weighting_dist": weighting_dist,
        "status_dist": status_dist,
        "quality_dist": quality_dist,
        "plain_summary": f"During the selected period, the average SPL was {avg_spl} dB with a maximum of {max_spl} dB. {above_threshold_count} samples exceeded the {threshold_db} dB threshold."
    }

def require_admin(user=Depends(verify_token)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    display_name: str

class UserUpdate(BaseModel):
    role: str | None = None
    display_name: str | None = None
    is_active: bool | None = None

class DeviceUpdate(BaseModel):
    room: str | None = None
    location: str | None = None
    description: str | None = None

@app.get("/api/users")
def get_users(user=Depends(require_admin)):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT username, role, display_name, is_active, last_login, created_at FROM users ORDER BY created_at DESC")
            rows = cur.fetchall()
    return {"users": [normalize_row(row) for row in rows]}

@app.post("/api/users")
def create_user(body: UserCreate, user=Depends(require_admin)):
    if body.role not in ["admin", "supervisor", "viewer"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    password_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, display_name) VALUES (%s, %s, %s, %s)",
                    (body.username, password_hash, body.role, body.display_name)
                )
            conn.commit()
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    return {"status": "ok", "message": "User created"}

@app.patch("/api/users/{username}")
def update_user(username: str, body: UserUpdate, user=Depends(require_admin)):
    if body.role and body.role not in ["admin", "supervisor", "viewer"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    updates = []
    params = []
    if body.role is not None:
        updates.append("role = %s")
        params.append(body.role)
    if body.display_name is not None:
        updates.append("display_name = %s")
        params.append(body.display_name)
    if body.is_active is not None:
        updates.append("is_active = %s")
        params.append(body.is_active)
        
    if not updates:
        return {"status": "ok"}
        
    params.append(username)
    query = f"UPDATE users SET {', '.join(updates)} WHERE username = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
    return {"status": "ok"}

@app.patch("/api/devices/{device_id}")
def update_device(device_id: str, body: DeviceUpdate, user=Depends(require_admin)):
    updates = []
    params = []
    if body.room is not None:
        updates.append("room = %s")
        params.append(body.room)
    if body.location is not None:
        updates.append("location = %s")
        params.append(body.location)
    if body.description is not None:
        updates.append("description = %s")
        params.append(body.description)
        
    if not updates:
        return {"status": "ok"}
        
    params.append(device_id)
    query = f"UPDATE devices SET {', '.join(updates)} WHERE device_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
    return {"status": "ok"}

@app.get("/api/status/summary")
def get_status_summary(user=Depends(verify_token)):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    m.device_id, d.room, d.location,
                    m.spl_avg_db, m.spl_max_db, m.weighting, m.measured_at, m.quality_flags
                FROM measurements m
                JOIN devices d ON m.device_id = d.device_id
                ORDER BY m.measured_at DESC LIMIT 1
            """)
            row = cur.fetchone()
            
    if not row:
        return {"noise_state": "Offline", "message": "No data available."}
        
    row = normalize_row(row)
    spl = row.get("spl_avg_db") or row.get("total_dba") or 0
    spl_max = row.get("spl_max_db") or spl
    weighting = row.get("weighting") or "flat"
    unit = "dBA" if weighting.lower() == "a" else "dB"
    
    # Calculate noise state
    state = "Offline"
    severity = "low"
    message = "No recent measurement."
    
    # Simple check for staleness (if measured_at has timezone info)
    now_utc = datetime.now(timezone.utc)
    measured_at = row["measured_at"]
    if measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=timezone.utc)
    time_diff = (now_utc - measured_at).total_seconds()
    
    is_stale = time_diff > 120
    
    if is_stale:
        state = "Offline"
        severity = "high"
        message = "No recent measurement received."
    elif spl < 50:
        state = "Quiet"
        severity = "low"
        message = "Low acoustic level, suitable for focused work."
    elif spl < 60:
        state = "Normal"
        severity = "low"
        message = "Typical indoor acoustic condition."
    elif spl < 70:
        state = "Elevated"
        severity = "medium"
        message = "Noise level is rising and may reduce comfort."
    elif spl < 85:
        state = "Noisy"
        severity = "high"
        message = "Noise may disturb concentration."
    else:
        state = "Alert"
        severity = "critical"
        message = "High acoustic level detected."
        
    # Check quality
    qf = row.get("quality_flags") or {}
    if isinstance(qf, str):
        try:
            qf = json.loads(qf)
        except:
            qf = {}
            
    quality = "Normal"
    if qf.get("clipping"):
        quality = "Clipping"
    elif qf.get("low_signal"):
        quality = "Low signal"
    elif qf.get("mic_error"):
        quality = "Mic error"

    return {
        "device_id": row["device_id"],
        "room": row["room"],
        "location": row["location"],
        "latest_spl": spl,
        "latest_spl_max": spl_max,
        "weighting": weighting,
        "unit": unit,
        "noise_state": state,
        "severity": severity,
        "message": message,
        "last_seen": row["measured_at"],
        "is_stale": is_stale,
        "quality": quality
    }

class ReportRequest(BaseModel):
    summary_data: dict

@app.post("/api/reports/generate-ai")
def generate_ai_report(body: ReportRequest, user=Depends(verify_token)):
    # Quota check
    limits = {"admin": 30, "supervisor": 15, "viewer": 5}
    quota = limits.get(user.get("role", "viewer"), 5)
    
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM llm_usage 
                WHERE username = %s AND created_at >= NOW() - INTERVAL '1 day'
            """, (user["sub"],))
            usage_count = cur.fetchone()[0]
            
    if usage_count >= quota:
        raise HTTPException(status_code=429, detail=f"Daily LLM quota exceeded. Limit is {quota}.")
        
    # Attempt LLM call
    llm_enabled = os.getenv("LLM_ENABLED", "false").lower() == "true"
    base_url = os.getenv("LLM_BASE_URL", "")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
    
    report_text = ""
    success = False
    error_msg = ""
    
    if not llm_enabled or not base_url or not api_key:
        report_text = "LLM configuration is disabled or incomplete. Falling back to deterministic summary:\\n" + body.summary_data.get("plain_summary", "")
    else:
        system_prompt = "You are an acoustic analysis assistant. Answer in Indonesian. Use only provided acoustic summary JSON. Do not invent causes. Call measurements 'SPL estimate'. Do not claim certified dBA or certified LAeq."
        user_prompt = f"Tolong buatkan laporan singkat berdasarkan data akustik berikut:\n{json.dumps(body.summary_data)}"
        
        req_data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        
        req = urllib.request.Request(
            base_url + "/chat/completions",
            data=json.dumps(req_data).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                resp_json = json.loads(response.read().decode("utf-8"))
                report_text = resp_json["choices"][0]["message"]["content"]
                success = True
        except Exception as e:
            success = False
            error_msg = str(e)
            report_text = f"LLM request failed: {error_msg}. Fallback:\\n" + body.summary_data.get("plain_summary", "")
            
    # Record usage
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO llm_usage (username, role, success, error_message)
                VALUES (%s, %s, %s, %s)
            """, (user["sub"], user.get("role"), success, error_msg))
        conn.commit()
        
    return {"report": report_text, "used_quota": usage_count + 1, "max_quota": quota}
