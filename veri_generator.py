"""
MDB308 Akıllı Sınıf — Mock Telemetry Generator
Gerçek ESP32 olmadan sistemi canlı test etmek için kullanılır.
sinif101/sensors/data topic'ine her 3 saniyede bir JSON basar.

Senaryo döngüsü:
  - 20 adım boyunca sınıf BOŞ  (occupancy=0) → CO2 düşer, O2 normale döner
  - 40 adım boyunca sınıf DOLU (occupancy=5) → CO2 400→1500, O2 20.9→19.0
"""

import json
import logging
import random
import signal
import socket
import time

import paho.mqtt.client as mqtt

BROKER_HOST     = "localhost"
BROKER_PORT     = 1883
TOPIC           = "sinif101/sensors/data"
PUBLISH_INTERVAL = 3.0   # saniye
CLIENT_ID       = "mdb308_mock_generator"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GEN] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("veri_generator")

# ── paho v2 client ────────────────────────────────────────────────────────────
client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id=CLIENT_ID,
)

def on_connect(cl, userdata, connect_flags, reason_code, properties):
    if not reason_code.is_failure:
        log.info("Broker'a bağlandı: %s:%d → %s", BROKER_HOST, BROKER_PORT, TOPIC)
    else:
        log.error("Bağlantı hatası: %s", reason_code)

def on_disconnect(cl, userdata, disconnect_flags, reason_code, properties):
    if reason_code.is_failure:
        log.warning("Bağlantı kesildi: %s", reason_code)

client.on_connect    = on_connect
client.on_disconnect = on_disconnect

# ── Bağlantı retry ───────────────────────────────────────────────────────────
running = True

def _stop(sig, frame):
    global running
    running = False
    log.info("Simülatör durduruluyor...")

signal.signal(signal.SIGINT,  _stop)
signal.signal(signal.SIGTERM, _stop)

while running:
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        break
    except (ConnectionRefusedError, socket.error) as exc:
        log.warning("Broker bulunamadı, 3 sn sonra tekrar (%s)", exc)
        time.sleep(3)

client.loop_start()

# ── Simülasyon Durumu ─────────────────────────────────────────────────────────
temp    = 22.0
hum     = 45.0
pres    = 1013.0
co2     = 400.0
o2      = 20.9
pir     = 0
dist    = 300.0   # cm (uzakta — boş sınıf)

# Senaryo: EMPTY_STEPS adım boş, FULL_STEPS adım dolu
EMPTY_STEPS = 20
FULL_STEPS  = 40
step        = 0
scenario    = "empty"   # "empty" | "full"
occ         = 0

log.info("Mock telemetry başladı. Senaryo: %d adım BOŞ → %d adım DOLU (döngü)", EMPTY_STEPS, FULL_STEPS)

# ── Yardımcı: sınırlandırılmış random walk ───────────────────────────────────
def walk(val: float, delta: float, lo: float, hi: float) -> float:
    return round(max(lo, min(hi, val + random.uniform(-delta, delta))), 2)

# ── Ana döngü ─────────────────────────────────────────────────────────────────
while running:
    # Senaryo geçişi
    if scenario == "empty" and step >= EMPTY_STEPS:
        scenario = "full"
        step     = 0
        log.info("▶ Senaryo: DOLU (occupancy=5) — CO2 yükseliyor, O2 düşüyor")
    elif scenario == "full" and step >= FULL_STEPS:
        scenario = "empty"
        step     = 0
        log.info("▶ Senaryo: BOŞ (occupancy=0) — değerler normale dönüyor")

    if scenario == "full":
        occ = 5
        pir = 1
        dist = round(random.uniform(60, 180), 1)   # birisi yakında
        # CO2 kademeli artış: her adımda +~27 ppm, max 1500
        co2_target = 400 + (step / FULL_STEPS) * 1100
        co2 = round(min(1500, co2 + (co2_target - co2) * 0.15 + random.uniform(-5, 5)), 1)
        # O2 kademeli düşüş: her adımda düşer, min 19.0
        o2_target = 20.9 - (step / FULL_STEPS) * 1.9
        o2 = round(max(19.0, o2 + (o2_target - o2) * 0.15 + random.uniform(-0.02, 0.02)), 2)
    else:
        occ = 0
        pir = 0
        dist = round(random.uniform(280, 350), 1)   # kimse yok, uzak mesafe
        # Normale dönüş
        co2 = round(max(400.0, co2 - random.uniform(20, 40)), 1)
        o2  = round(min(20.9,  o2  + random.uniform(0.03, 0.08)), 2)

    # Sıcaklık, nem, basınç: random walk
    temp_lo = 23.0 if occ > 0 else 22.0   # dolu sınıf biraz daha sıcak
    temp_hi = 29.0 if occ > 0 else 25.0
    temp = walk(temp, 0.3, temp_lo, temp_hi)
    hum  = walk(hum,  0.8, 40.0, 60.0)
    pres = walk(pres, 0.4, 1008.0, 1015.0)

    payload = json.dumps({
        "temperature_c": temp,
        "humidity_pct":  hum,
        "pressure_hpa":  pres,
        "co2_ppm":       co2,
        "o2_pct":        o2,
        "pir_detected":  pir,
        "occupancy":     occ,
        "distance_cm":   dist,
    })

    result = client.publish(TOPIC, payload, qos=0)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        log.info(
            "[%s|step%02d] occ=%d temp=%.1f co2=%.0f o2=%.2f hum=%.0f pres=%.0f",
            scenario.upper(), step, occ, temp, co2, o2, hum, pres,
        )
    else:
        log.warning("Publish hatası rc=%d", result.rc)

    step += 1
    time.sleep(PUBLISH_INTERVAL)

client.loop_stop()
client.disconnect()
log.info("Generator kapatıldı.")
