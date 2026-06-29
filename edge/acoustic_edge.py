"""
Acoustic Edge Service — Real INMP441 I2S Microphone
Reads audio from INMP441 via arecord (ALSA), computes RMS/dB estimate,
publishes JSON payload to MQTT broker every PUBLISH_INTERVAL seconds.

Device: plughw:2,0 (inmp441 card)
Format: S32_LE, 44100 Hz, mono
"""

import os
import sys
import time
import json
import struct
import subprocess
import math
import signal
import numpy as np
from scipy import signal as dsp_signal
from datetime import datetime, timezone, timedelta
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "acoustic_device")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "password")
DEVICE_ID = os.getenv("DEVICE_ID", "ACOUSTIC-PI-001")
ROOM = os.getenv("ROOM", "R402")
PUBLISH_INTERVAL = int(os.getenv("PUBLISH_INTERVAL_SECONDS", 5))
CALIBRATION_OFFSET = float(os.getenv("CALIBRATION_OFFSET", 0))
CALIBRATION_SCALE = float(os.getenv("CALIBRATION_SCALE", 1.0))
WEIGHTING = os.getenv("WEIGHTING", "flat")

# ALSA device for INMP441
ALSA_DEVICE = os.getenv("ALSA_DEVICE", "plughw:2,0")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", 44100))
RECORD_SECONDS = int(os.getenv("RECORD_SECONDS", 2))
CHANNELS = 1
SAMPLE_FORMAT = "S32_LE"
BYTES_PER_SAMPLE = 4

TOPIC = f"acoustic/devices/{DEVICE_ID}/measurements"
HEARTBEAT_TOPIC = f"acoustic/devices/{DEVICE_ID}/heartbeat"
STATUS_TOPIC = f"acoustic/devices/{DEVICE_ID}/status"

TZ_JKT = timezone(timedelta(hours=7))
EPSILON = 1e-10
REF_VALUE = 2**31

running = True

def signal_handler(sig, frame):
    global running
    print("\n[edge] Shutting down...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[edge] Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
    else:
        print(f"[edge] MQTT connection failed, rc={rc}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[edge] MQTT disconnected unexpectedly, rc={rc}.")

def record_audio():
    cmd = ["arecord", "-D", ALSA_DEVICE, "-c", str(CHANNELS), "-r", str(SAMPLE_RATE),
           "-f", SAMPLE_FORMAT, "-t", "raw", "-d", str(RECORD_SECONDS), "-q"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=RECORD_SECONDS + 5)
        return result.stdout if result.returncode == 0 else None
    except Exception as e:
        print(f"[edge] record error: {e}")
        return None

def apply_a_weighting(samples, sample_rate):
    sos = dsp_signal.aweighting(sample_rate)
    return dsp_signal.sosfilt(sos, samples)

def compute_rms(raw_bytes):
    num_samples = len(raw_bytes) // BYTES_PER_SAMPLE
    if num_samples == 0: return 0.0
    samples = np.frombuffer(raw_bytes, dtype=np.int32)
    
    if WEIGHTING == "A":
        samples = apply_a_weighting(samples.astype(float), SAMPLE_RATE)
    
    normalized = samples / REF_VALUE
    return np.sqrt(np.mean(normalized**2))

def rms_to_db(rms):
    raw_db = 20 * math.log10(rms + EPSILON)
    db = CALIBRATION_SCALE * raw_db + CALIBRATION_OFFSET
    return round(max(30.0, min(120.0, db)), 1)

def main():
    global running
    print(f"[edge] Acoustic Edge Service starting... ID: {DEVICE_ID} | Weighting: {WEIGHTING}")
    
    client = mqtt.Client(client_id=f"edge_{DEVICE_ID}")
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    lwt_payload = json.dumps({"device_id": DEVICE_ID, "status": "offline", "reason": "connection_lost"})
    client.will_set(STATUS_TOPIC, lwt_payload, qos=1, retain=True)
    
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=120)
        client.loop_start()
    except Exception as e:
        print(f"[edge] Connection failed: {e}")

    client.publish(STATUS_TOPIC, json.dumps({"device_id": DEVICE_ID, "status": "online"}), qos=1, retain=True)

    while running:
        cycle_start = time.time()
        raw_audio = record_audio()
        
        if raw_audio:
            rms = compute_rms(raw_audio)
            db_est = rms_to_db(rms)
            
            print(f"[edge] Publishing SPL: {db_est} dB")
            
            payload = {
                "schema_version": "1.0",
                "device_id": DEVICE_ID,
                "room": ROOM,
                "timestamp": datetime.now(TZ_JKT).isoformat(),
                "metric_type": "a_weighted_estimate" if WEIGHTING == "A" else "spl_estimate",
                "weighting": WEIGHTING,
                "spl_avg_db": db_est,
                "spl_max_db": db_est,
                "calibration_offset_db": CALIBRATION_OFFSET,
                "status": "ok",
                "quality_flags": {"clipping": False, "low_signal": False, "mic_error": False},
                "edge_version": "raspi-edge-aweight-v1"
            }
            client.publish(TOPIC, json.dumps(payload), qos=1)
            client.publish(HEARTBEAT_TOPIC, json.dumps({"device_id": DEVICE_ID, "status": "online"}), qos=0)
            
        elapsed = time.time() - cycle_start
        time.sleep(max(0, PUBLISH_INTERVAL - elapsed))

    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    main()
