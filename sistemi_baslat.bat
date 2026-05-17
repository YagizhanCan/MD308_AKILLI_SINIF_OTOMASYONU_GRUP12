@echo off
cd /d "%~dp0"

start "MDB308 | MQTT Broker" cmd /k "where /q mosquitto && mosquitto -v || (if exist \"C:\Program Files\mosquitto\mosquitto.exe\" (\"C:\Program Files\mosquitto\mosquitto.exe\" -v) else (echo [HATA] Mosquitto bulunamadi, PATH kontrol edin & pause))"
timeout /t 2 /nobreak >nul
start "MDB308 | MQTT Gateway" cmd /k "..\venv\Scripts\python.exe mqtt_gateway.py"
timeout /t 2 /nobreak >nul
start "MDB308 | Streamlit" cmd /k "..\venv\Scripts\streamlit.exe run arayuz.py"
timeout /t 2 /nobreak >nul
start "MDB308 | Mock Data Generator" cmd /k "..\venv\Scripts\python.exe veri_generator.py"
echo Sistema baslatildi: http://localhost:8501
