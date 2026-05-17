"""
MDB308 Akıllı Sınıf — MQTT Gateway (Asenkron Backend Servisi)
ESP32'den gelen JSON sensör verilerini dinler, HTML karar motorunu çalıştırır,
röle komutlarını yayınlar ve veritabanına kaydeder.

Karar motoru (akilli-sinif-simulasyon-v2.html → updateDevices()):
  relay_lights     : occupancy >= 1
  relay_ac         : occupancy >= 3 OR temperature_c > 27
  relay_outlets    : occupancy >= 1
  relay_ventilation: co2_ppm > 1200 OR o2_pct < 19.5
"""

import asyncio
import json
import logging
import signal
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

try:
    import paho.mqtt.client as mqtt
except ImportError as e:
    print(f"Warning: paho-mqtt not installed. Install with: pip install paho-mqtt")
    mqtt = None

from db_yoneticisi import init_db, insert_reading, insert_relay_event

# ── Yapılandırma ──────────────────────────────────────────────────────────────
BROKER_HOST = "localhost"
BROKER_PORT  = 1883
KEEPALIVE    = 60
CLIENT_ID    = "mdb308_gateway"

TOPIC_SENSOR_DATA   = "sinif101/sensors/data"       # ESP32 → Gateway (JSON)
TOPIC_RELAY_LIGHTS  = "sinif101/relay/lights/cmd"   # Gateway → ESP32
TOPIC_RELAY_AC      = "sinif101/relay/ac/cmd"
TOPIC_RELAY_OUTLETS = "sinif101/relay/outlets/cmd"
TOPIC_RELAY_VENT    = "sinif101/relay/ventilation/cmd"

# Uyumluluk: HTML simülasyonundaki bireysel topic'leri de dinle
TOPIC_SUBSCRIBE_LIST = [
    (TOPIC_SENSOR_DATA, 0),
    ("sinif101/env/temperature_c", 0),
    ("sinif101/env/co2_ppm", 0),
    ("sinif101/env/o2_pct", 0),
    ("sinif101/env/humidity_pct", 0),
    ("sinif101/env/pressure_hpa", 0),
    ("sinif101/sensors/pir", 0),
    ("sinif101/sensors/occupancy", 0),
    ("sinif101/sensors/distance_cm", 0),
]

LOG_LEVEL = logging.INFO
DB_WRITE_INTERVAL = 5  # saniyede bir DB'ye yaz (throttle)

# ── Eşik Değerleri (HTML karar motoru + uyarı sistemi) ────────────────────────
@dataclass
class Thresholds:
    # Röle tetikleyicileri
    lights_min_occ: int   = 1
    ac_min_occ: int       = 3
    ac_temp_trigger: float = 27.0
    outlets_min_occ: int  = 1
    vent_co2_trigger: float = 1200.0
    vent_o2_trigger: float  = 19.5

    # Uyarı seviyeleri
    co2_warn: float    = 1000.0
    co2_danger: float  = 2000.0
    co2_critical: float = 2500.0
    o2_warn: float     = 19.5
    o2_danger: float   = 17.0
    temp_warn_hi: float = 27.0
    temp_danger_hi: float = 30.0
    temp_warn_lo: float = 18.0
    temp_danger_lo: float = 15.0
    hum_warn_hi: float = 65.0
    hum_danger_hi: float = 72.0
    pres_warn_lo: float = 990.0
    pres_warn_hi: float = 1028.0

THR = Thresholds()

# ── Sensör Durumu ─────────────────────────────────────────────────────────────
@dataclass
class SensorState:
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float]  = None
    pressure_hpa: Optional[float]  = None
    co2_ppm: Optional[float]       = None
    o2_pct: Optional[float]        = None
    aqi: Optional[int]             = None
    pir_detected: int              = 0
    occupancy: int                 = 0
    distance_cm: Optional[float]   = None

    # Röle durumları (backend kararı)
    relay_lights: int      = 0
    relay_ac: int          = 0
    relay_outlets: int     = 0
    relay_ventilation: int = 0

    # Önceki röle durumları (değişim tespiti)
    _prev_relays: dict = field(default_factory=lambda: {
        "lights": -1, "ac": -1, "outlets": -1, "ventilation": -1
    })

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mqtt_gateway")


# ── AQI Hesabı (HTML calcAQI() ile özdeş) ─────────────────────────────────────
def calc_aqi(co2: float, o2: float, temp: float, hum: float) -> int:
    c = min(250.0, max(0.0, (co2 - 400) / 10.4))
    o = max(0.0, min(250.0, (20.9 - o2) * 40))
    t = max(0.0, (18 - temp) * 5 if temp < 18 else (temp - 26) * 8 if temp > 26 else 0)
    h = (hum - 65) * 2 if hum > 65 else (25 - hum) * 1.5 if hum < 25 else 0
    return min(500, round(c * 0.5 + o * 0.3 + t * 0.15 + h * 0.05))


# ── Uyarı Seviyesi ─────────────────────────────────────────────────────────────
def compute_alert_level(state: SensorState) -> str:
    co2  = state.co2_ppm  or 0
    o2   = state.o2_pct   or 21.0
    temp = state.temperature_c or 22.0

    if co2 > THR.co2_critical or o2 < THR.o2_danger or temp > THR.temp_danger_hi or temp < THR.temp_danger_lo:
        return "critical"
    if co2 > THR.co2_danger or o2 < THR.o2_warn:
        return "danger"
    if co2 > THR.co2_warn or temp > THR.temp_warn_hi or temp < THR.temp_warn_lo:
        return "warning"
    return "normal"


# ── Karar Motoru (HTML updateDevices() mantığı) ───────────────────────────────
def apply_decision_logic(state: SensorState) -> dict[str, int]:
    occ  = state.occupancy
    temp = state.temperature_c or 22.0
    co2  = state.co2_ppm       or 400.0
    o2   = state.o2_pct        or 20.9

    return {
        "lights":      1 if occ >= THR.lights_min_occ else 0,
        "ac":          1 if (occ >= THR.ac_min_occ or temp > THR.ac_temp_trigger) else 0,
        "outlets":     1 if occ >= THR.outlets_min_occ else 0,
        "ventilation": 1 if (co2 > THR.vent_co2_trigger or o2 < THR.vent_o2_trigger) else 0,
    }


# ── MQTT Gateway ──────────────────────────────────────────────────────────────
class MQTTGateway:
    def __init__(self):
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._queue:  asyncio.Queue = asyncio.Queue()
        self._state   = SensorState()
        self._client  = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=CLIENT_ID,
            protocol=mqtt.MQTTv5,
        )
        self._last_db_write: float = 0.0
        self._running = True

        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message

    # ── Paho callbacks — v2 imzası (reason_code + properties zorunlu) ──────────
    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        if not reason_code.is_failure:
            log.info("MQTT broker bağlantısı kuruldu: %s:%d", BROKER_HOST, BROKER_PORT)
            client.subscribe(TOPIC_SUBSCRIBE_LIST)
            log.info("Abone olundu: %d topic", len(TOPIC_SUBSCRIBE_LIST))
        else:
            log.error("MQTT bağlantı hatası: %s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if reason_code.is_failure:
            log.warning("MQTT bağlantısı beklenmedik şekilde kesildi: %s — yeniden bağlanılacak...", reason_code)
        else:
            log.info("MQTT bağlantısı temiz kapatıldı.")

    def _on_message(self, client, userdata, msg):
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(
                self._queue.put_nowait,
                (msg.topic, msg.payload.decode("utf-8", errors="replace")),
            )

    # ── Async işlem döngüsü ───────────────────────────────────────────────────
    async def _process_loop(self):
        import time
        while self._running:
            try:
                topic, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._handle_message(topic, payload)

                # DB yazma throttle
                now = time.monotonic()
                if now - self._last_db_write >= DB_WRITE_INTERVAL:
                    await self._write_to_db()
                    self._last_db_write = now

            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                log.exception("Mesaj işleme hatası: %s", exc)

    async def _handle_message(self, topic: str, payload: str):
        s = self._state

        try:
            # Birleşik JSON (ESP32 → sinif101/sensors/data)
            if topic == TOPIC_SENSOR_DATA:
                data = json.loads(payload)
                s.temperature_c = data.get("temperature_c", s.temperature_c)
                s.humidity_pct  = data.get("humidity_pct",  s.humidity_pct)
                s.pressure_hpa  = data.get("pressure_hpa",  s.pressure_hpa)
                s.co2_ppm       = data.get("co2_ppm",       s.co2_ppm)
                s.o2_pct        = data.get("o2_pct",        s.o2_pct)
                s.pir_detected  = int(data.get("pir_detected", s.pir_detected))
                s.distance_cm   = data.get("distance_cm",   s.distance_cm)
                log.debug("JSON payload alındı: temp=%.1f co2=%.0f o2=%.1f",
                          s.temperature_c or 0, s.co2_ppm or 0, s.o2_pct or 0)

            # Bireysel topic'ler (HTML sim uyumluluğu)
            elif topic == "sinif101/env/temperature_c":
                s.temperature_c = float(payload)
            elif topic == "sinif101/env/co2_ppm":
                s.co2_ppm = float(payload)
            elif topic == "sinif101/env/o2_pct":
                s.o2_pct = float(payload)
            elif topic == "sinif101/env/humidity_pct":
                s.humidity_pct = float(payload)
            elif topic == "sinif101/env/pressure_hpa":
                s.pressure_hpa = float(payload)
            elif topic == "sinif101/sensors/pir":
                s.pir_detected = int(payload)
            elif topic == "sinif101/sensors/occupancy":
                s.occupancy = int(payload)
            elif topic == "sinif101/sensors/distance_cm":
                s.distance_cm = float(payload)

        except (ValueError, json.JSONDecodeError) as exc:
            log.warning("Payload parse hatası [%s]: %s", topic, exc)
            return

        # AQI hesapla
        if all(v is not None for v in [s.co2_ppm, s.o2_pct, s.temperature_c, s.humidity_pct]):
            s.aqi = calc_aqi(s.co2_ppm, s.o2_pct, s.temperature_c, s.humidity_pct)

        # Karar motoru çalıştır
        await self._run_decision_engine()

    async def _run_decision_engine(self):
        s = self._state
        relays = apply_decision_logic(s)

        s.relay_lights      = relays["lights"]
        s.relay_ac          = relays["ac"]
        s.relay_outlets     = relays["outlets"]
        s.relay_ventilation = relays["ventilation"]

        # Değişen röleleri yayınla ve logla
        topic_map = {
            "lights":      TOPIC_RELAY_LIGHTS,
            "ac":          TOPIC_RELAY_AC,
            "outlets":     TOPIC_RELAY_OUTLETS,
            "ventilation": TOPIC_RELAY_VENT,
        }
        for name, new_val in relays.items():
            if s._prev_relays[name] != new_val:
                cmd = "ON" if new_val else "OFF"
                self._client.publish(topic_map[name], cmd, qos=1, retain=True)
                insert_relay_event(
                    relay   = name,
                    state   = new_val,
                    trigger = self._build_trigger_reason(name, s),
                )
                log.info("RÖLE değişti: %-12s → %s", name.upper(), cmd)
                s._prev_relays[name] = new_val

        alert = compute_alert_level(s)
        if alert in ("danger", "critical"):
            log.warning("UYARI [%s]: CO2=%.0f O2=%.1f Temp=%.1f",
                        alert.upper(),
                        s.co2_ppm or 0, s.o2_pct or 0, s.temperature_c or 0)

    def _build_trigger_reason(self, relay: str, s: SensorState) -> str:
        if relay == "lights":
            return f"occupancy={s.occupancy}"
        if relay == "ac":
            return f"occupancy={s.occupancy}, temp={s.temperature_c}"
        if relay == "outlets":
            return f"occupancy={s.occupancy}"
        if relay == "ventilation":
            return f"co2={s.co2_ppm}, o2={s.o2_pct}"
        return ""

    async def _write_to_db(self):
        s = self._state
        alert = compute_alert_level(s)
        try:
            row_id = insert_reading(
                temperature_c     = s.temperature_c,
                humidity_pct      = s.humidity_pct,
                pressure_hpa      = s.pressure_hpa,
                co2_ppm           = s.co2_ppm,
                o2_pct            = s.o2_pct,
                aqi               = s.aqi,
                pir_detected      = s.pir_detected,
                occupancy         = s.occupancy,
                distance_cm       = s.distance_cm,
                relay_lights      = s.relay_lights,
                relay_ac          = s.relay_ac,
                relay_outlets     = s.relay_outlets,
                relay_ventilation = s.relay_ventilation,
                alert_level       = alert,
            )
            log.debug("DB kayıt: id=%d alert=%s", row_id, alert)
        except Exception as exc:
            log.error("DB yazma hatası: %s", exc)

    # ── Başlatma / Durdurma ───────────────────────────────────────────────────
    async def run(self):
        self._loop = asyncio.get_running_loop()

        # Graceful retry — broker henüz ayakta değilse crash olmadan bekle
        while self._running:
            try:
                self._client.connect(BROKER_HOST, BROKER_PORT, keepalive=KEEPALIVE)
                break
            except (ConnectionRefusedError, socket.error) as exc:
                log.warning(
                    "⚠️  MQTT Broker bulunamadı, 3 saniye sonra tekrar deneniyor... (%s)", exc
                )
                await asyncio.sleep(3)

        if not self._running:
            return

        self._client.loop_start()

        log.info("Gateway başladı — broker: %s:%d", BROKER_HOST, BROKER_PORT)
        log.info("Karar motoru eşikleri: CO2>%.0f | O2<%.1f%% | Temp>%.1f°C | Occ>=%d",
                 THR.vent_co2_trigger, THR.vent_o2_trigger,
                 THR.ac_temp_trigger, THR.ac_min_occ)

        try:
            await self._process_loop()
        finally:
            self._client.loop_stop()
            self._client.disconnect()
            log.info("Gateway kapatıldı.")

    def stop(self):
        self._running = False


# ── Entry Point ───────────────────────────────────────────────────────────────
async def main():
    init_db()
    gateway = MQTTGateway()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, gateway.stop)
        except NotImplementedError:
            pass  # Windows'ta SIGTERM desteği yok

    await gateway.run()


if __name__ == "__main__":
    asyncio.run(main())
