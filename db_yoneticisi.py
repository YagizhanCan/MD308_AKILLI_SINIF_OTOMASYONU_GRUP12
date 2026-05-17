"""
MDB308 Akıllı Sınıf — Veritabanı Yöneticisi
SQLite3 tabanlı; sensor_readings (16 kolon) ve relay_log tabloları.
"""

import sqlite3
import contextlib
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "akilli_sinif.db"

_CREATE_READINGS = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    temperature_c     REAL,
    humidity_pct      REAL,
    pressure_hpa      REAL,
    co2_ppm           REAL,
    o2_pct            REAL,
    aqi               INTEGER,
    pir_detected      INTEGER DEFAULT 0,
    occupancy         INTEGER DEFAULT 0,
    distance_cm       REAL,
    relay_lights      INTEGER DEFAULT 0,
    relay_ac          INTEGER DEFAULT 0,
    relay_outlets     INTEGER DEFAULT 0,
    relay_ventilation INTEGER DEFAULT 0,
    alert_level       TEXT    DEFAULT 'normal'
)
"""

_CREATE_RELAY_LOG = """
CREATE TABLE IF NOT EXISTS relay_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    relay     TEXT NOT NULL,
    state     INTEGER NOT NULL,
    trigger   TEXT
)
"""

_CREATE_IDX_TS   = "CREATE INDEX IF NOT EXISTS idx_readings_ts ON sensor_readings(timestamp)"
_CREATE_IDX_RLOG = "CREATE INDEX IF NOT EXISTS idx_relay_ts   ON relay_log(timestamp)"


@contextlib.contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.execute(_CREATE_READINGS)
        con.execute(_CREATE_RELAY_LOG)
        con.execute(_CREATE_IDX_TS)
        con.execute(_CREATE_IDX_RLOG)


def insert_reading(
    temperature_c: Optional[float],
    humidity_pct: Optional[float],
    pressure_hpa: Optional[float],
    co2_ppm: Optional[float],
    o2_pct: Optional[float],
    aqi: Optional[int],
    pir_detected: int,
    occupancy: int,
    distance_cm: Optional[float],
    relay_lights: int,
    relay_ac: int,
    relay_outlets: int,
    relay_ventilation: int,
    alert_level: str = "normal",
) -> int:
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO sensor_readings (
                timestamp, temperature_c, humidity_pct, pressure_hpa,
                co2_ppm, o2_pct, aqi,
                pir_detected, occupancy, distance_cm,
                relay_lights, relay_ac, relay_outlets, relay_ventilation,
                alert_level
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ts, temperature_c, humidity_pct, pressure_hpa,
                co2_ppm, o2_pct, aqi,
                pir_detected, occupancy, distance_cm,
                relay_lights, relay_ac, relay_outlets, relay_ventilation,
                alert_level,
            ),
        )
        return cur.lastrowid


def insert_relay_event(relay: str, state: int, trigger: Optional[str] = None) -> None:
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as con:
        con.execute(
            "INSERT INTO relay_log (timestamp, relay, state, trigger) VALUES (?,?,?,?)",
            (ts, relay, state, trigger),
        )


def fetch_latest(n: int = 1) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM sensor_readings ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_history(minutes: int = 60) -> list[dict]:
    from datetime import timedelta
    since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM sensor_readings WHERE timestamp >= ? ORDER BY id ASC",
            (since,),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_relay_log(n: int = 50) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM relay_log ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_stats() -> dict:
    with _conn() as con:
        row = con.execute(
            """
            SELECT
                COUNT(*)          AS total_records,
                AVG(temperature_c) AS avg_temp,
                AVG(co2_ppm)       AS avg_co2,
                AVG(o2_pct)        AS avg_o2,
                MAX(co2_ppm)       AS max_co2,
                MIN(o2_pct)        AS min_o2
            FROM sensor_readings
            """
        ).fetchone()
    return dict(row) if row else {}


def delete_old_readings(keep_days: int = 7) -> int:
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=keep_days)).isoformat(timespec="seconds")
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM sensor_readings WHERE timestamp < ?", (cutoff,)
        )
        return cur.rowcount


if __name__ == "__main__":
    init_db()
    print(f"Veritabanı başlatıldı: {DB_PATH}")
    print("Tablo şeması hazır — sensor_readings (16 kolon) + relay_log")
