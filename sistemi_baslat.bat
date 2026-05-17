@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY_EXEC=python"
if exist "venv\Scripts\python.exe" (
    set "PY_EXEC=venv\Scripts\python.exe"
) else if exist "..\venv\Scripts\python.exe" (
    set "PY_EXEC=..\venv\Scripts\python.exe"
)

start "MDB308 | MQTT Broker" cmd /k "where /q mosquitto && mosquitto -v || (if exist \"C:\Program Files\mosquitto\mosquitto.exe\" (\"C:\Program Files\mosquitto\mosquitto.exe\" -v) else (echo [HATA] Mosquitto bulunamadi & pause))"
timeout /t 2 /nobreak >nul
start "MDB308 | MQTT Gateway" cmd /k "%PY_EXEC% mqtt_gateway.py"
timeout /t 2 /nobreak >nul
start "MDB308 | Streamlit Dashboard" cmd /k "%PY_EXEC% -m streamlit run arayuz.py"
timeout /t 2 /nobreak >nul
start "MDB308 | Mock Data Generator" cmd /k "%PY_EXEC% veri_generator.py"

echo ============================================
echo  Sistem venv uzerinden baslatildi!
echo ============================================
