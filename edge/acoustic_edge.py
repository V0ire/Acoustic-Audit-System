import os
import time
import json
import math
import numpy as np
import sounddevice as sd
from datetime import datetime, timezone, timedelta
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "acoustic_device")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "password")
DEVICE_ID = os.getenv("DEVICE_ID", "ACOUSTIC-PI-001")
ROOM = os.getenv("ROOM", "R402")
PUBLISH_INTERVAL = int(os.getenv("PUBLISH_INTERVAL_SECONDS", 5))
CALIBRATION_OFFSET = float(os.getenv("CALIBRATION_OFFSET", 0.0))

TOPIC = f"acoustic/devices/{DEVICE_ID}/measurements"

# Set timezone to Asia/Jakarta (UTC+7)
TZ_JKT = timezone(timedelta(hours=7))

# Audio settings
SAMPLE_RATE = 44100
CHANNELS = 1
BLOCK_SIZE = int(SAMPLE_RATE * PUBLISH_INTERVAL) # Buffer for the whole interval

# Global variables for audio processing
latest_rms = 0.0

def audio_callback(indata, frames, time_info, status):
    global latest_rms
    if status:
        print(f"[edge] Audio Status: {status}")
    
    # Calculate RMS of the current audio block
    # indata is a numpy array of shape (frames, channels)
    # We use float64 to prevent overflow during sum of squares
    data = indata.astype(np.float64)
    rms = np.sqrt(np.mean(data**2))
    latest_rms = rms

def calculate_dba(rms, calibration_offset):
    # Avoid log(0)
    epsilon = 1e-10
    if rms < epsilon:
        rms = epsilon
    # Basic formula: 20 * log10(RMS) + C_cal
    db_est = 20 * math.log10(rms) + calibration_offset
    # Clamp to realistic acoustic ranges (e.g., 30 dBA to 120 dBA)
    return max(30.0, min(120.0, db_est))

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[edge] Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
    else:
        print(f"[edge] Failed to connect, return code {rc}")

def main():
    client = mqtt.Client(client_id=f"acoustic_{DEVICE_ID}")
    
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        
    client.on_connect = on_connect
    
    print("[edge] Starting Real Sensor MQTT publisher...")
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        
        # Start audio stream
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, 
                            blocksize=BLOCK_SIZE, callback=audio_callback):
            print(f"[edge] Audio stream started at {SAMPLE_RATE}Hz")
            
            while True:
                # Sleep for the interval to let the audio callback fill the buffer
                time.sleep(PUBLISH_INTERVAL)
                
                # Retrieve the latest RMS computed by the callback
                current_rms = latest_rms
                db_est = calculate_dba(current_rms, CALIBRATION_OFFSET)
                
                payload = {
                    "device_id": DEVICE_ID,
                    "room": ROOM,
                    "timestamp": datetime.now(TZ_JKT).isoformat(),
                    "total_dba": round(db_est, 1),
                    # Mocked for M2, to be replaced by actual FFT features in the future
                    "mechanical_confidence": 0.5, 
                    "human_activity_confidence": 0.5,
                    "source_hint": "mixed_or_unknown"
                }
                
                json_payload = json.dumps(payload)
                
                # Publish QoS 1
                client.publish(TOPIC, json_payload, qos=1)
                print(f"[edge] Published to {TOPIC}: {json_payload} (RMS: {current_rms:.5f})")
            
    except KeyboardInterrupt:
        print("\n[edge] Stopping publisher...")
    except Exception as e:
        print(f"[edge] Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
