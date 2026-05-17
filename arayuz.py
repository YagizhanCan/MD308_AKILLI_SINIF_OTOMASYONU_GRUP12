"""
MDB308 Akıllı Sınıf — Streamlit Dashboard
Veritabanını okur; canlı O2, Basınç, CO2 ve 4 röle durumunu
modern metric'ler, renkli badge'lar ve interaktif grafiklerle gösterir.

Çalıştırma: streamlit run arayuz.py
"""

import time
from datetime import datetime

import pandas as pd
import streamlit as st

from db_yoneticisi import fetch_history, fetch_latest, fetch_relay_log, fetch_stats, init_db

# ── Sayfa Yapılandırması ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="MDB308 Akıllı Sınıf",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS Özelleştirme ──────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .metric-badge {
        display:inline-block; padding:3px 10px; border-radius:6px;
        font-size:13px; font-weight:600;
    }
    .badge-ok     { background:#16a34a22; color:#22c55e; border:1px solid #22c55e55; }
    .badge-warn   { background:#b4510022; color:#f59e0b; border:1px solid #f59e0b55; }
    .badge-danger { background:#dc262622; color:#ef4444; border:1px solid #ef444455; }
    .relay-on     { background:#1d4ed822; color:#60a5fa; border:1px solid #60a5fa55;
                    padding:4px 14px; border-radius:6px; font-weight:700; }
    .relay-off    { background:#27272a;   color:#6b7280; border:1px solid #3f3f46;
                    padding:4px 14px; border-radius:6px; }
    .alert-critical { background:#7f1d1d44; border-left:4px solid #ef4444;
                      padding:8px 14px; border-radius:4px; color:#f87171; }
    .alert-danger   { background:#78350f44; border-left:4px solid #f59e0b;
                      padding:8px 14px; border-radius:4px; color:#fbbf24; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Yardımcı Fonksiyonlar ─────────────────────────────────────────────────────
def _badge(label: str, cls: str) -> str:
    return f'<span class="metric-badge {cls}">{label}</span>'


def _relay_badge(name: str, state: int) -> str:
    label = f"● {name.upper()}: {'AÇIK' if state else 'KAPALI'}"
    cls   = "relay-on" if state else "relay-off"
    return f'<span class="{cls}">{label}</span>'


def _co2_badge(v: float) -> str:
    if v > 2000: return _badge("Tehlikeli", "badge-danger")
    if v > 1000: return _badge("Uyarı",     "badge-warn")
    return _badge("İyi", "badge-ok")


def _o2_badge(v: float) -> str:
    if v < 17:   return _badge("Kritik",    "badge-danger")
    if v < 19.5: return _badge("Düşük",     "badge-warn")
    return _badge("Normal", "badge-ok")


def _temp_badge(v: float) -> str:
    if v > 30 or v < 15: return _badge("Tehlikeli", "badge-danger")
    if v > 27 or v < 18: return _badge("Uyarı",     "badge-warn")
    return _badge("İyi", "badge-ok")


def _pres_badge(v: float) -> str:
    if v < 990 or v > 1028: return _badge("Anormal", "badge-warn")
    return _badge("Normal", "badge-ok")


# ── Kenar Çubuğu ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚡ MDB308 Akıllı Sınıf")
    st.caption("Enerji Verimliliği Otomasyon Sistemi")
    st.divider()

    refresh_sec = st.slider("Yenileme aralığı (sn)", 1, 30, 5)
    history_min = st.selectbox("Grafik geçmişi", [15, 30, 60, 120, 240], index=2)
    st.divider()

    st.subheader("👨‍💻 Hazırlayanlar")
    st.markdown("""
- YAĞIZHAN CAN — 21120205711
- Muhammed Emin Aydın — 23120101038
- Yunus Emre Boztepe — 23120205036
- Ali Karaca — 23120606062
- Berkay Keskin — 23120101090
- Ahmet Murat Kıvrak — 23120606040
""")
    st.divider()
    st.subheader("Sistem Bilgisi")
    st.markdown("""
    - **MCU:** ESP32-WROOM-32
    - **Protokol:** MQTT @ localhost:1883
    - **Sensörler:** BME280, MQ-135, Grove O2, PIR, HC-SR04
    - **Röle:** 4 kanal optokuplörlü
    """)

    st.divider()
    st.caption("MDB308 · Proje 3 · 2025")

# ── DB Başlat ─────────────────────────────────────────────────────────────────
init_db()

# ── Ana Döngü ─────────────────────────────────────────────────────────────────
placeholder = st.empty()

while True:
    latest_list = fetch_latest(1)
    history     = fetch_history(history_min)
    relay_log   = fetch_relay_log(20)
    stats       = fetch_stats()

    with placeholder.container():
        # ── Başlık ────────────────────────────────────────────────────────────
        col_h1, col_h2 = st.columns([4, 1])
        with col_h1:
            st.markdown("## Grup 12 Proje 3: Enerji Verimliliği için Akıllı Sınıf Otomasyon ve Analiz Sistemi")
        with col_h2:
            st.markdown(
                f"<div style='text-align:right;color:#6b7280;font-size:13px;margin-top:8px;'>"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}</div>",
                unsafe_allow_html=True,
            )

        if not latest_list:
            st.info("Veritabanında henüz kayıt yok. MQTT gateway'i başlatın: `python mqtt_gateway.py`")
        else:
            row = latest_list[0]
            co2  = row.get("co2_ppm")   or 0.0
            o2   = row.get("o2_pct")    or 0.0
            temp = row.get("temperature_c") or 0.0
            hum  = row.get("humidity_pct")  or 0.0
            pres = row.get("pressure_hpa")  or 0.0
            aqi  = row.get("aqi")           or 0
            occ  = row.get("occupancy")     or 0
            dist = row.get("distance_cm")
            pir  = row.get("pir_detected")  or 0
            alert_lvl = row.get("alert_level", "normal")

            rl = row.get("relay_lights",      0)
            ra = row.get("relay_ac",          0)
            ro = row.get("relay_outlets",     0)
            rv = row.get("relay_ventilation", 0)

            # ── Kritik Uyarı Banner ───────────────────────────────────────────
            if alert_lvl == "critical":
                st.markdown(
                    f'<div class="alert-critical">🚨 <b>KRİTİK UYARI</b> — '
                    f'CO₂: {co2:.0f} ppm | O₂: {o2:.1f}% | Sıcaklık: {temp:.1f}°C</div>',
                    unsafe_allow_html=True,
                )
            elif alert_lvl in ("danger", "warning"):
                st.markdown(
                    f'<div class="alert-danger">⚠ <b>UYARI [{alert_lvl.upper()}]</b> — '
                    f'CO₂: {co2:.0f} ppm | O₂: {o2:.1f}% | Temp: {temp:.1f}°C</div>',
                    unsafe_allow_html=True,
                )

            # ── Ana Metrikler ─────────────────────────────────────────────────
            st.markdown("### 📊 Anlık Sensör Değerleri")
            m1, m2, m3, m4, m5, m6 = st.columns(6)

            with m1:
                st.metric("🌡 Sıcaklık", f"{temp:.1f} °C")
                st.markdown(_temp_badge(temp), unsafe_allow_html=True)

            with m2:
                st.metric("💨 CO₂", f"{co2:.0f} ppm")
                st.markdown(_co2_badge(co2), unsafe_allow_html=True)

            with m3:
                st.metric("🫁 O₂", f"{o2:.1f} %")
                st.markdown(_o2_badge(o2), unsafe_allow_html=True)

            with m4:
                st.metric("💧 Nem", f"{hum:.0f} %")

            with m5:
                st.metric("🔵 Basınç", f"{pres:.0f} hPa")
                st.markdown(_pres_badge(pres), unsafe_allow_html=True)

            with m6:
                st.metric("🌫 AQI", str(aqi))
                aqi_cls = "badge-ok" if aqi < 50 else "badge-warn" if aqi < 150 else "badge-danger"
                aqi_lbl = "Çok İyi" if aqi < 50 else "Orta" if aqi < 100 else "Hassas" if aqi < 150 else "Sağlıksız"
                st.markdown(_badge(aqi_lbl, aqi_cls), unsafe_allow_html=True)

            st.divider()

            # ── Röle Durumları ────────────────────────────────────────────────
            st.markdown("### 🔌 Röle Çıkışları")
            r1, r2, r3, r4 = st.columns(4)

            with r1:
                st.markdown(_relay_badge("Işık (180W)", rl), unsafe_allow_html=True)
                st.caption("Tetik: doluluk ≥ 1")
            with r2:
                st.markdown(_relay_badge("Klima (950W)", ra), unsafe_allow_html=True)
                st.caption("Tetik: doluluk ≥ 3 veya sıcaklık > 27°C")
            with r3:
                st.markdown(_relay_badge("Projeksiyon (250W)", ro), unsafe_allow_html=True)
                st.caption("Tetik: doluluk ≥ 1")
            with r4:
                st.markdown(_relay_badge("Fan (120W)", rv), unsafe_allow_html=True)
                st.caption("Tetik: CO₂ > 1200 veya O₂ < 19.5%")

            # Güç hesabı
            smart_w = rl * 180 + ra * 950 + ro * 250 + rv * 120 + 0.8
            trad_w  = 180 + 950 + 250 + 120 + 0.8
            savings = max(0, round((1 - smart_w / trad_w) * 100))

            ep1, ep2, ep3, ep4 = st.columns(4)
            ep1.metric("⚡ Akıllı Sistem", f"{smart_w:.0f} W")
            ep2.metric("📌 Geleneksel", "1500 W")
            ep3.metric("💚 Tasarruf", f"%{savings}")
            ep4.metric("👥 Doluluk", f"{occ} kişi | PIR: {'✅' if pir else '❌'}")

            st.divider()

            # ── Grafikler ─────────────────────────────────────────────────────
            if history:
                df = pd.DataFrame(history)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.set_index("timestamp")

                st.markdown("### 📈 Zaman Serisi Grafikleri")

                tab1, tab2, tab3, tab4 = st.tabs(
                    ["🌡 Sıcaklık & Nem", "💨 CO₂ & O₂", "🔵 Basınç & AQI", "⚡ Enerji"]
                )

                with tab1:
                    if "temperature_c" in df.columns and "humidity_pct" in df.columns:
                        st.line_chart(
                            df[["temperature_c", "humidity_pct"]].rename(
                                columns={"temperature_c": "Sıcaklık (°C)", "humidity_pct": "Nem (%)"}
                            ),
                            use_container_width=True,
                        )

                with tab2:
                    if "co2_ppm" in df.columns and "o2_pct" in df.columns:
                        col_co2, col_o2 = st.columns(2)
                        with col_co2:
                            st.caption("CO₂ (ppm) — Uyarı: >1000 | Tehlike: >2000")
                            st.line_chart(df[["co2_ppm"]].rename(columns={"co2_ppm": "CO₂ (ppm)"}))
                        with col_o2:
                            st.caption("O₂ (%) — Uyarı: <19.5 | Tehlike: <17")
                            st.line_chart(df[["o2_pct"]].rename(columns={"o2_pct": "O₂ (%)"}))

                with tab3:
                    col_p, col_a = st.columns(2)
                    with col_p:
                        if "pressure_hpa" in df.columns:
                            st.caption("Basınç (hPa) — Normal: 990–1028")
                            st.line_chart(df[["pressure_hpa"]].rename(columns={"pressure_hpa": "Basınç (hPa)"}))
                    with col_a:
                        if "aqi" in df.columns:
                            st.caption("AQI — <50 Çok İyi | <150 Orta | >200 Sağlıksız")
                            st.line_chart(df[["aqi"]].rename(columns={"aqi": "AQI"}))

                with tab4:
                    if all(c in df.columns for c in ["relay_lights", "relay_ac", "relay_outlets", "relay_ventilation"]):
                        df["akilli_w"] = (
                            df["relay_lights"] * 180
                            + df["relay_ac"] * 950
                            + df["relay_outlets"] * 250
                            + df["relay_ventilation"] * 120
                            + 0.8
                        )
                        df["geleneksel_w"] = trad_w
                        st.caption("Mavi: Akıllı sistem (değişken) | Sarı: Geleneksel (1500 W sabit)")
                        st.line_chart(
                            df[["akilli_w", "geleneksel_w"]].rename(
                                columns={"akilli_w": "Akıllı (W)", "geleneksel_w": "Geleneksel (W)"}
                            ),
                            use_container_width=True,
                        )

            st.divider()

            # ── Röle Olay Günlüğü ─────────────────────────────────────────────
            st.markdown("### 📋 Röle Olay Günlüğü (Son 20)")
            if relay_log:
                df_log = pd.DataFrame(relay_log)
                df_log["durum"] = df_log["state"].map({1: "AÇILDI", 0: "KAPANDI"})
                st.dataframe(
                    df_log[["timestamp", "relay", "durum", "trigger"]].rename(
                        columns={"timestamp": "Zaman", "relay": "Röle",
                                 "durum": "Durum", "trigger": "Tetikleyici"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Henüz röle olayı kaydedilmedi.")

            # ── İstatistikler ─────────────────────────────────────────────────
            if stats.get("total_records", 0) > 0:
                with st.expander("📊 Oturum İstatistikleri"):
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("Toplam Kayıt",  stats.get("total_records", 0))
                    s2.metric("Ort. Sıcaklık", f"{stats.get('avg_temp') or 0:.1f} °C")
                    s3.metric("Ort. CO₂",      f"{stats.get('avg_co2')  or 0:.0f} ppm")
                    s4.metric("Min O₂",        f"{stats.get('min_o2')   or 0:.1f} %")

    time.sleep(refresh_sec)
