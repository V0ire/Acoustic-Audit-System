import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Acoustic Audit System API")

# Setup CORS
cors_origin = os.getenv("CORS_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[cors_origin] if cors_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/measurements")
def get_measurements():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
<<<<<<< HEAD
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
                    m.weighting
                FROM measurements m
                JOIN devices d ON m.device_id = d.device_id
                ORDER BY m.measured_at DESC
=======
                    device_id, 
                    measured_at, 
                    spl_avg_db, 
                    spl_max_db,
                    calibration_offset_db,
                    status,
                    quality_flags
                FROM measurements
                ORDER BY measured_at DESC
>>>>>>> origin/database-deployment
                LIMIT 50
            """)
            rows = cur.fetchall()
            
            # Format datetime objects ke ISO format string
            for row in rows:
                if row['measured_at']:
                    row['measured_at'] = row['measured_at'].isoformat()
                # Ensure quality_flags is serializable
                if isinstance(row.get('quality_flags'), dict):
                    pass # already dict from RealDictCursor
                    
            return rows
    except Exception as e:
        print(f"Error fetching measurements: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

@app.get("/api/devices")
def get_devices():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    d.device_id, 
                    d.room,
                    dh.last_seen,
                    dh.status
                FROM devices d
                LEFT JOIN device_health dh ON d.device_id = dh.device_id
            """)
            rows = cur.fetchall()
            
            for row in rows:
                if row['last_seen']:
                    row['last_seen'] = row['last_seen'].isoformat()
                    
            return rows
    except Exception as e:
        print(f"Error fetching devices: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

@app.post("/api/login")
def login_stub():
    # Stub for M1, final JWT implementation in M3
    return {"message": "Login stub. JWT will be implemented in M3."}
