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
import argparse
from datetime import datetime, timezone, timedelta
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

try:
    import scipy.signal
    import numpy as np
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False

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
WEIGHTING = os.getenv("WEIGHTING", "flat").lower()
EDGE_VERSION = os.getenv("EDGE_VERSION", "raspi-edge-aweight-v1")

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

# Asia/Jakarta timezone (UTC+7)
TZ_JKT = timezone(timedelta(hours=7))

# Epsilon to avoid log(0)
EPSILON = 1e-10

# Reference value for dB calculation (max value for 32-bit signed int)
REF_VALUE = 2**31

# Graceful shutdown
running = True

def signal_handler(sig, frame):
    global running
    print("\n[edge] Shutting down...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[edge] Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
    else:
        print(f"[edge] MQTT connection failed, rc={rc}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[edge] MQTT disconnected unexpectedly, rc={rc}. Will auto-reconnect.")

# --- Filter Functions ---
def get_a_weighting_filter(fs):
    if not HAVE_SCIPY:
        return None, None
    
    pi = math.pi
    z = [0, 0, 0, 0]
    p = [-2 * pi * 20.598997,
         -2 * pi * 20.598997,
         -2 * pi * 12194.217,
         -2 * pi * 12194.217,
         -2 * pi * 107.65265,
         -2 * pi * 737.86223]
    k = (2 * pi * 12194.217)**2
    
    z_d, p_d, k_d = scipy.signal.bilinear_zpk(z, p, k, fs)
    b, a = scipy.signal.zpk2tf(z_d, p_d, k_d)
    
    # Normalize to 0dB at 1kHz
    w, h = scipy.signal.freqz(b, a, worN=[1000 * 2 * pi / fs])
    b = b / abs(h[0])
    return b, a

# --- Audio Functions ---
def record_audio():
    """Record audio from INMP441 using arecord, return raw bytes."""
    cmd = ["arecord", "-D", ALSA_DEVICE, "-c", str(CHANNELS), "-r", str(SAMPLE_RATE),
           "-f", SAMPLE_FORMAT, "-t", "raw", "-d", str(RECORD_SECONDS), "-q"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=RECORD_SECONDS + 5)
        return result.stdout if result.returncode == 0 else None
    except Exception as e:
        print(f"[edge] record error: {e}")
        return None

def compute_rms(raw_bytes, filter_b=None, filter_a=None):
    num_samples = len(raw_bytes) // BYTES_PER_SAMPLE
    if num_samples == 0: return 0.0, False, False
    
    clipping = False
    
    if filter_b is not None and filter_a is not None and HAVE_SCIPY:
        # We know numpy is available if HAVE_SCIPY is True
        samples = np.frombuffer(raw_bytes[:num_samples * BYTES_PER_SAMPLE], dtype='<i4')
        normalized = samples.astype(np.float32) / REF_VALUE
        
        # Check for clipping before filtering
        if np.max(np.abs(normalized)) >= 0.99:
            clipping = True
            
        filtered = scipy.signal.lfilter(filter_b, filter_a, normalized)
        rms = math.sqrt(np.mean(filtered**2))
    else:
        samples = struct.unpack(f"<{num_samples}i", raw_bytes[:num_samples * BYTES_PER_SAMPLE])
        normalized = [s / REF_VALUE for s in samples]
        
        if any(abs(s) >= 0.99 for s in normalized):
            clipping = True
            
        rms = math.sqrt(sum(s * s for s in normalized) / num_samples)
        
    low_signal = rms < 1e-6 # Set a threshold for "too quiet" / broken mic
    return rms, clipping, low_signal

def rms_to_db(rms):
    raw_db = 20 * math.log10(rms + EPSILON)
    db = CALIBRATION_SCALE * raw_db + CALIBRATION_OFFSET
    return round(max(30.0, min(120.0, db)), 1)

# --- Main ---
def main():
    global running
    
    parser = argparse.ArgumentParser(description="Acoustic Edge Service")
    parser.add_argument("--dry-run", action="store_true", help="Run without MQTT, capture one sample and print results")
    args = parser.parse_args()

    print(f"[edge] Acoustic Edge Service starting... ID: {DEVICE_ID}")
    
    # Configure Weighting
    active_weighting = WEIGHTING
    filter_b, filter_a = None, None
    if active_weighting == "a":
        if HAVE_SCIPY:
            print("[edge] A-weighting filter enabled (via scipy).")
            filter_b, filter_a = get_a_weighting_filter(SAMPLE_RATE)
            active_weighting = "A"
        else:
            print("[edge] WARNING: A-weighting requested but scipy/numpy is not installed!")
            print("[edge] Falling back to flat weighting. Please install scipy/numpy.")
            active_weighting = "flat"
    else:
        active_weighting = "flat"
        print("[edge] Flat weighting configured.")

    if args.dry_run:
        print("[edge] DRY RUN MODE: capturing single sample...")
        raw_audio = record_audio()
        if raw_audio:
            # Show flat vs A-weighted if scipy is available
            print(f"[edge] Sample captured, length {len(raw_audio)} bytes.")
            
            # 1. Flat
            rms_flat, clip_flat, low_flat = compute_rms(raw_audio, None, None)
            db_flat = rms_to_db(rms_flat)
            print(f"[edge] Flat SPL Estimate: {db_flat} dB")
            
            # 2. A-weighted
            db_a = "--"
            if HAVE_SCIPY:
                b, a = get_a_weighting_filter(SAMPLE_RATE)
                rms_a, clip_a, low_a = compute_rms(raw_audio, b, a)
                db_a = rms_to_db(rms_a)
                print(f"[edge] A-Weighted SPL Estimate: {db_a} dBA")
            
            # Final values for payload
            final_rms, final_clip, final_low = compute_rms(raw_audio, filter_b, filter_a)
            final_db = rms_to_db(final_rms)
            
            payload = {
                "schema_version": "1.0",
                "device_id": DEVICE_ID,
                "room": ROOM,
                "timestamp": datetime.now(TZ_JKT).isoformat(),
                "metric_type": "spl_estimate",
                "weighting": active_weighting,
                "window_seconds": float(RECORD_SECONDS),
                "spl_avg_db": final_db,
                "spl_max_db": final_db,
                "calibration_offset_db": CALIBRATION_OFFSET,
                "status": "ok",
                "quality_flags": {
                    "clipping": final_clip,
                    "low_signal": final_low,
                    "mic_error": False
                },
                "edge_version": EDGE_VERSION
            }
            print("\n[edge] Outgoing Payload Preview:")
            print(json.dumps(payload, indent=2))
        else:
            print("[edge] Failed to capture audio! (mic_error=True)")
            
        sys.exit(0)

    # Normal execution with MQTT
    client = mqtt.Client(client_id=f"edge_{DEVICE_ID}")
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    # LWT setup
    lwt_payload = json.dumps({"device_id": DEVICE_ID, "status": "offline", "reason": "connection_lost"})
    client.will_set(STATUS_TOPIC, lwt_payload, qos=1, retain=True)
    
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"[edge] Connection failed: {e}")

    # Mark online
    client.publish(STATUS_TOPIC, json.dumps({"device_id": DEVICE_ID, "status": "online"}), qos=1, retain=True)

    while running:
        cycle_start = time.time()
        raw_audio = record_audio()
        
        if raw_audio:
            rms, clipping, low_signal = compute_rms(raw_audio, filter_b, filter_a)
            db_est = rms_to_db(rms)
            
            payload = {
                "schema_version": "1.0",
                "device_id": DEVICE_ID,
                "room": ROOM,
                "timestamp": datetime.now(TZ_JKT).isoformat(),
                "metric_type": "spl_estimate",
                "weighting": active_weighting,
                "window_seconds": float(RECORD_SECONDS),
                "spl_avg_db": db_est,
                "spl_max_db": db_est,
                "calibration_offset_db": CALIBRATION_OFFSET,
                "status": "ok",
                "quality_flags": {
                    "clipping": clipping,
                    "low_signal": low_signal,
                    "mic_error": False
                },
                "edge_version": EDGE_VERSION
            }
            client.publish(TOPIC, json.dumps(payload), qos=1)
            
            # Heartbeat (simplified)
            client.publish(HEARTBEAT_TOPIC, json.dumps({"device_id": DEVICE_ID, "status": "online"}), qos=0)
        else:
            # Publish mic error
            payload = {
                "schema_version": "1.0",
                "device_id": DEVICE_ID,
                "room": ROOM,
                "timestamp": datetime.now(TZ_JKT).isoformat(),
                "metric_type": "spl_estimate",
                "weighting": active_weighting,
                "status": "error",
                "quality_flags": {
                    "clipping": False,
                    "low_signal": False,
                    "mic_error": True
                },
                "edge_version": EDGE_VERSION
            }
            client.publish(TOPIC, json.dumps(payload), qos=1)
            
        elapsed = time.time() - cycle_start
        time.sleep(max(0, PUBLISH_INTERVAL - elapsed))

    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    main()
