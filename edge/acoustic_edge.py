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

# ALSA device for INMP441
ALSA_DEVICE = os.getenv("ALSA_DEVICE", "plughw:2,0")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", 44100))
RECORD_SECONDS = int(os.getenv("RECORD_SECONDS", 2))
CHANNELS = 1
SAMPLE_FORMAT = "S32_LE"
BYTES_PER_SAMPLE = 4

TOPIC = f"acoustic/devices/{DEVICE_ID}/measurements"

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


# --- Audio Functions ---
def record_audio():
    """Record audio from INMP441 using arecord, return raw bytes."""
    cmd = [
        "arecord",
        "-D", ALSA_DEVICE,
        "-c", str(CHANNELS),
        "-r", str(SAMPLE_RATE),
        "-f", SAMPLE_FORMAT,
        "-t", "raw",
        "-d", str(RECORD_SECONDS),
        "-q",  # quiet
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=RECORD_SECONDS + 5,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            print(f"[edge] arecord error: {stderr}")
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        print("[edge] arecord timeout")
        return None
    except FileNotFoundError:
        print("[edge] arecord not found. Install alsa-utils.")
        return None
    except Exception as e:
        print(f"[edge] record error: {e}")
        return None


def compute_rms(raw_bytes):
    """Compute RMS from raw S32_LE audio bytes."""
    num_samples = len(raw_bytes) // BYTES_PER_SAMPLE
    if num_samples == 0:
        return 0.0

    # Unpack S32_LE samples
    samples = struct.unpack(f"<{num_samples}i", raw_bytes[:num_samples * BYTES_PER_SAMPLE])

    # Normalize to -1.0 to 1.0
    normalized = [s / REF_VALUE for s in samples]

    # RMS
    sum_sq = sum(s * s for s in normalized)
    rms = math.sqrt(sum_sq / num_samples)

    return rms


def rms_to_db(rms):
    """Convert RMS to estimated dBA using 2-point linear calibration.

    Formula: dB_est = SCALE * (20 * log10(RMS + epsilon)) + OFFSET
    Calibrated against phone sound meter readings:
      quiet room: raw=-35.3 → target 40 dBA
      normal talk: raw=-31.8 → target 56 dBA
    This is NOT certified dBA — it is a calibrated estimate.
    """
    raw_db = 20 * math.log10(rms + EPSILON)
    db = CALIBRATION_SCALE * raw_db + CALIBRATION_OFFSET
    # Clamp to realistic acoustic range
    db = max(30.0, min(120.0, db))
    return round(db, 1)


def estimate_confidence(total_dba):
    """Simple heuristic confidence estimation.

    Not a real classifier — provides rough hints based on dB level.
    High dB + steady = more likely mechanical.
    Variable / mid-range = more likely human activity.
    """
    # Mechanical: higher at sustained loud levels
    if total_dba > 70:
        mechanical = round(min(0.6 + (total_dba - 70) * 0.02, 0.95), 2)
    elif total_dba > 55:
        mechanical = round(0.3 + (total_dba - 55) * 0.02, 2)
    else:
        mechanical = round(max(0.1, total_dba * 0.005), 2)

    # Human activity: mid-range levels
    if 50 < total_dba < 70:
        human = round(0.4 + (total_dba - 50) * 0.015, 2)
    elif total_dba >= 70:
        human = round(max(0.15, 0.7 - (total_dba - 70) * 0.02), 2)
    else:
        human = round(max(0.1, total_dba * 0.006), 2)

    # Determine source hint
    if mechanical > human + 0.2:
        source_hint = "mechanical_like"
    elif human > mechanical + 0.2:
        source_hint = "human_activity_like"
    else:
        source_hint = "mixed_or_unknown"

    return mechanical, human, source_hint


def build_payload(total_dba, mechanical_conf, human_conf, source_hint):
    """Build JSON payload per AGENTS.md contract."""
    return {
        "device_id": DEVICE_ID,
        "room": ROOM,
        "timestamp": datetime.now(TZ_JKT).isoformat(),
        "total_dba": total_dba,
        "mechanical_confidence": mechanical_conf,
        "human_activity_confidence": human_conf,
        "source_hint": source_hint,
    }


# --- Main ---
def main():
    global running

    print(f"[edge] Acoustic Edge Service starting...")
    print(f"[edge] Device: {DEVICE_ID} | Room: {ROOM}")
    print(f"[edge] ALSA device: {ALSA_DEVICE}")
    print(f"[edge] Sample rate: {SAMPLE_RATE} Hz | Record duration: {RECORD_SECONDS}s")
    print(f"[edge] Calibration offset: {CALIBRATION_OFFSET} dB")
    print(f"[edge] Publish interval: {PUBLISH_INTERVAL}s")
    print(f"[edge] MQTT topic: {TOPIC}")

    # Setup MQTT client
    client = mqtt.Client(client_id=f"edge_{DEVICE_ID}")

    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # Enable auto-reconnect
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    # Connect to broker
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"[edge] Failed to connect to MQTT broker: {e}")
        print("[edge] Will retry on next cycle...")

    print("[edge] Running. Press Ctrl+C to stop.\n")

    while running:
        cycle_start = time.time()

        # 1. Record audio
        raw_audio = record_audio()
        if raw_audio is None or len(raw_audio) == 0:
            print("[edge] No audio data, skipping cycle")
            time.sleep(PUBLISH_INTERVAL)
            continue

        # 2. Compute RMS
        rms = compute_rms(raw_audio)

        # 3. Convert to dB estimate
        total_dba = rms_to_db(rms)

        # 4. Estimate confidence (heuristic)
        mechanical_conf, human_conf, source_hint = estimate_confidence(total_dba)

        # 5. Build payload
        payload = build_payload(total_dba, mechanical_conf, human_conf, source_hint)
        json_payload = json.dumps(payload)

        # 6. Publish
        try:
            result = client.publish(TOPIC, json_payload, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"[edge] Published: dBA={total_dba} mech={mechanical_conf} "
                      f"human={human_conf} hint={source_hint}")
            else:
                print(f"[edge] Publish failed, rc={result.rc}")
        except Exception as e:
            print(f"[edge] Publish error: {e}")

        # 7. Wait for next cycle
        elapsed = time.time() - cycle_start
        sleep_time = max(0, PUBLISH_INTERVAL - elapsed)
        time.sleep(sleep_time)

    # Cleanup
    print("[edge] Stopping MQTT client...")
    client.loop_stop()
    client.disconnect()
    print("[edge] Edge service stopped.")


if __name__ == "__main__":
    main()
