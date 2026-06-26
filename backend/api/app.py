import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
import jwt
import bcrypt
import datetime

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
JWT_SECRET = os.getenv("JWT_SECRET", "default_secret_do_not_use_in_prod")
JWT_ALGORITHM = "HS256"

security = HTTPBearer()

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

class LoginRequest(BaseModel):
    username: str
    password: str

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/login")
def login(request: LoginRequest):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE username = %s", (request.username,))
            user = cur.fetchone()
            
            if not user:
                raise HTTPException(status_code=401, detail="Invalid username or password")
            
            # Verify password
            # password_hash is stored in the database, typically starting with $2b$ or similar for bcrypt
            try:
                is_valid = bcrypt.checkpw(request.password.encode('utf-8'), user['password_hash'].encode('utf-8'))
            except Exception as e:
                print(f"Bcrypt error: {e}")
                is_valid = False

            if not is_valid:
                raise HTTPException(status_code=401, detail="Invalid username or password")
            
            # Generate JWT
            expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            payload = {
                "sub": user["username"],
                "role": user["role"],
                "exp": expiration
            }
            token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
            
            return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

@app.get("/api/measurements")
def get_measurements(user_payload: dict = Depends(verify_jwt)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    device_id, 
                    room, 
                    measured_at, 
                    total_dba, 
                    mechanical_confidence, 
                    human_activity_confidence, 
                    source_hint
                FROM measurements
                ORDER BY measured_at DESC
                LIMIT 50
            """)
            rows = cur.fetchall()
            
            # Format datetime objects ke ISO format string
            for row in rows:
                if row['measured_at']:
                    row['measured_at'] = row['measured_at'].isoformat()
                    
            return rows
    except Exception as e:
        print(f"Error fetching measurements: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

@app.get("/api/devices")
def get_devices(user_payload: dict = Depends(verify_jwt)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    device_id, 
                    room, 
                    location, 
                    description,
                    created_at
                FROM devices
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            
            for row in rows:
                if row['created_at']:
                    row['created_at'] = row['created_at'].isoformat()
                    
            return rows
    except Exception as e:
        print(f"Error fetching devices: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()
