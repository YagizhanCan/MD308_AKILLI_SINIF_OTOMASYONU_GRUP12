/*
 * MDB308 Akıllı Sınıf — ESP32 MQTT Düğümü
 * Donanım: ESP32-WROOM-32
 * Sensörler:
 *   - BME280    (I2C 0x76): Sıcaklık, Nem, Basınç
 *   - MQ-135    (ADC GPIO34): CO2 / Hava Kalitesi (analog)
 *   - SEN0322   (I2C 0x70): Grove O2 Elektrokimyasal
 *   - HC-SR04   (GPIO25/26): Ultrasonik mesafe
 *   - HC-SR501  (GPIO27):    PIR hareket
 * Aktuatörler:
 *   - Röle 1 Işık        (GPIO16): sinif101/relay/lights/cmd
 *   - Röle 2 Klima       (GPIO17): sinif101/relay/ac/cmd
 *   - Röle 3 Projeksiyon (GPIO18): sinif101/relay/outlets/cmd
 *   - Röle 4 Fan         (GPIO19): sinif101/relay/ventilation/cmd
 *
 * Kütüphaneler (Arduino Library Manager):
 *   Adafruit BME280 Library    >= 2.2.4
 *   Adafruit Unified Sensor    >= 1.1.14
 *   PubSubClient               >= 2.8.0
 *   ArduinoJson                >= 7.0.0
 *   DFRobot_OxygenSensor       >= 1.0.1
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
// #include <ArduinoJson.h>  // Install via Arduino Library Manager if needed
#include <DFRobot_OxygenSensor.h>

// ── Wi-Fi / MQTT Yapılandırması ───────────────────────────────────────────────
#define WIFI_SSID        "WIFI_ADI"
#define WIFI_PASSWORD    "WIFI_SIFRESI"
#define MQTT_BROKER      "192.168.1.100"   // broker IP (localhost = PC IP)
#define MQTT_PORT        1883
#define MQTT_CLIENT_ID   "esp32_sinif101"

// ── MQTT Topic'leri ───────────────────────────────────────────────────────────
#define TOPIC_DATA          "sinif101/sensors/data"
#define TOPIC_CMD_LIGHTS    "sinif101/relay/lights/cmd"
#define TOPIC_CMD_AC        "sinif101/relay/ac/cmd"
#define TOPIC_CMD_OUTLETS   "sinif101/relay/outlets/cmd"
#define TOPIC_CMD_VENT      "sinif101/relay/ventilation/cmd"

// ── GPIO Pin Haritası ─────────────────────────────────────────────────────────
#define PIN_SDA          21
#define PIN_SCL          22
#define PIN_MQ135        34      // ADC1_CH6 (sadece giriş)
#define PIN_PIR          27
#define PIN_TRIG         25      // HC-SR04
#define PIN_ECHO         26      // HC-SR04
#define PIN_RELAY_LIGHTS 16
#define PIN_RELAY_AC     17
#define PIN_RELAY_OUTLETS 18
#define PIN_RELAY_VENT   19

// ── Sabitler ──────────────────────────────────────────────────────────────────
#define BME280_ADDR      0x76
#define O2_ADDR          0x70
#define O2_SAMPLES       20      // O2 sensörü örnekleme sayısı
#define PUBLISH_INTERVAL 2000    // ms — veri yayınlama periyodu
#define ECHO_TIMEOUT     30000   // µs — HC-SR04 zaman aşımı
#define MQ135_RL         10.0f   // kΩ yük direnci
#define MQ135_R0         76.63f  // kΩ temiz havada Rs (kalibrasyon)
#define ADC_VREF         3.3f
#define ADC_RESOLUTION   4095.0f

// ── Nesneler ──────────────────────────────────────────────────────────────────
WiFiClient          wifiClient;
PubSubClient        mqttClient(wifiClient);
Adafruit_BME280     bme;
DFRobot_OxygenSensor oxygen;

unsigned long lastPublish = 0;

// ── Röle durumları (gateway komutlarından güncellenir) ────────────────────────
bool relayLights  = false;
bool relayAC      = false;
bool relayOutlets = false;
bool relayVent    = false;

// ─────────────────────────────────────────────────────────────────────────────
// MQ-135 → CO2 ppm dönüşümü (güç yasası kalibrasyon modeli)
//   Rs = (Vcc/Vout - 1) × RL
//   ppm = 110.47 × (Rs/R0)^(-2.862)    [CO2 eğri sabitleri]
// ─────────────────────────────────────────────────────────────────────────────
float mq135ToCO2(int raw) {
    float voltage = (raw / ADC_RESOLUTION) * ADC_VREF;
    if (voltage < 0.01f) return 400.0f;
    float rs = ((ADC_VREF / voltage) - 1.0f) * MQ135_RL;
    float ratio = rs / MQ135_R0;
    float ppm = 110.47f * powf(ratio, -2.862f);
    // Gerçekçi sınırlar: 400–5000 ppm
    return constrain(ppm, 400.0f, 5000.0f);
}

// ─────────────────────────────────────────────────────────────────────────────
// HC-SR04 mesafe ölçümü (cm)
// ─────────────────────────────────────────────────────────────────────────────
float readDistance() {
    digitalWrite(PIN_TRIG, LOW);
    delayMicroseconds(2);
    digitalWrite(PIN_TRIG, HIGH);
    delayMicroseconds(10);
    digitalWrite(PIN_TRIG, LOW);

    long duration = pulseIn(PIN_ECHO, HIGH, ECHO_TIMEOUT);
    if (duration == 0) return -1.0f;        // zaman aşımı
    return duration * 0.034f / 2.0f;        // cm
}

// ─────────────────────────────────────────────────────────────────────────────
// MQTT mesajı alındığında (gateway → röle komutları)
// ─────────────────────────────────────────────────────────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    String msg;
    for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
    bool state = (msg == "ON");

    if (strcmp(topic, TOPIC_CMD_LIGHTS)  == 0) {
        relayLights  = state;
        // Optokuplörlü röle: LOW = AÇIK (aktif düşük), HIGH = KAPALI
        // Eğer modülünüz aktif yüksek ise LOW/HIGH'ı ters çevirin
        digitalWrite(PIN_RELAY_LIGHTS,  state ? LOW : HIGH);
    } else if (strcmp(topic, TOPIC_CMD_AC) == 0) {
        relayAC      = state;
        digitalWrite(PIN_RELAY_AC,      state ? LOW : HIGH);
    } else if (strcmp(topic, TOPIC_CMD_OUTLETS) == 0) {
        relayOutlets = state;
        digitalWrite(PIN_RELAY_OUTLETS, state ? LOW : HIGH);
    } else if (strcmp(topic, TOPIC_CMD_VENT) == 0) {
        relayVent    = state;
        digitalWrite(PIN_RELAY_VENT,    state ? LOW : HIGH);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Wi-Fi bağlantısı
// ─────────────────────────────────────────────────────────────────────────────
void connectWiFi() {
    Serial.print("[WiFi] Bağlanılıyor: ");
    Serial.println(WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    uint8_t attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("\n[WiFi] Bağlı! IP: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\n[WiFi] HATA — ESP32 yeniden başlatılıyor...");
        ESP.restart();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MQTT yeniden bağlantı
// ─────────────────────────────────────────────────────────────────────────────
void reconnectMQTT() {
    while (!mqttClient.connected()) {
        Serial.print("[MQTT] Broker'a bağlanılıyor...");
        if (mqttClient.connect(MQTT_CLIENT_ID)) {
            Serial.println(" BAĞLANDI");
            mqttClient.subscribe(TOPIC_CMD_LIGHTS);
            mqttClient.subscribe(TOPIC_CMD_AC);
            mqttClient.subscribe(TOPIC_CMD_OUTLETS);
            mqttClient.subscribe(TOPIC_CMD_VENT);
            Serial.println("[MQTT] Röle komut topic'lerine abone olundu");
        } else {
            Serial.print(" HATA, rc=");
            Serial.print(mqttClient.state());
            Serial.println(" — 3 saniye sonra tekrar denenecek");
            delay(3000);
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("\n=== MDB308 Akıllı Sınıf ESP32 Başlıyor ===");

    // GPIO başlat
    pinMode(PIN_PIR,  INPUT);
    pinMode(PIN_TRIG, OUTPUT);
    pinMode(PIN_ECHO, INPUT);
    // Röle pinleri: başlangıçta HIGH = KAPALI (optokuplör aktif düşük)
    pinMode(PIN_RELAY_LIGHTS,  OUTPUT); digitalWrite(PIN_RELAY_LIGHTS,  HIGH);
    pinMode(PIN_RELAY_AC,      OUTPUT); digitalWrite(PIN_RELAY_AC,      HIGH);
    pinMode(PIN_RELAY_OUTLETS, OUTPUT); digitalWrite(PIN_RELAY_OUTLETS, HIGH);
    pinMode(PIN_RELAY_VENT,    OUTPUT); digitalWrite(PIN_RELAY_VENT,    HIGH);

    // I2C başlat
    Wire.begin(PIN_SDA, PIN_SCL);

    // BME280
    if (!bme.begin(BME280_ADDR)) {
        Serial.println("[BME280] HATA: Sensör bulunamadı! Adres ve kablolama kontrol edin.");
    } else {
        bme.setSampling(
            Adafruit_BME280::MODE_NORMAL,
            Adafruit_BME280::SAMPLING_X16,
            Adafruit_BME280::SAMPLING_X16,
            Adafruit_BME280::SAMPLING_X16,
            Adafruit_BME280::FILTER_X16,
            Adafruit_BME280::STANDBY_MS_0_5
        );
        Serial.println("[BME280] Hazır");
    }

    // SEN0322 O2 sensörü
    if (!oxygen.begin(O2_ADDR)) {
        Serial.println("[O2-SEN0322] HATA: Sensör bulunamadı!");
    } else {
        Serial.println("[O2-SEN0322] Hazır");
    }

    // Wi-Fi & MQTT
    connectWiFi();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(mqttCallback);
    mqttClient.setBufferSize(512);
}

// ─────────────────────────────────────────────────────────────────────────────
void loop() {
    // Bağlantı sağlığı
    if (WiFi.status() != WL_CONNECTED) connectWiFi();
    if (!mqttClient.connected())       reconnectMQTT();
    mqttClient.loop();

    unsigned long now = millis();
    if (now - lastPublish < PUBLISH_INTERVAL) return;
    lastPublish = now;

    // ── Sensör Okumaları ──────────────────────────────────────────────────────
    float temperature = bme.readTemperature();        // °C
    float humidity    = bme.readHumidity();           // %
    float pressure    = bme.readPressure() / 100.0f;  // hPa

    int   mq135Raw    = analogRead(PIN_MQ135);
    float co2_ppm     = mq135ToCO2(mq135Raw);

    float o2_pct      = oxygen.getOxygenData(O2_SAMPLES); // % (20 örnek ortalaması)

    bool  pirDetected = digitalRead(PIN_PIR) == HIGH;
    float distance    = readDistance();

    // NaN / sonsuz değer koruması
    if (isnan(temperature)) temperature = 0.0f;
    if (isnan(humidity))    humidity    = 0.0f;
    if (isnan(pressure))    pressure    = 0.0f;
    if (isnan(o2_pct))      o2_pct      = 20.9f;

    // ── JSON Paketi ───────────────────────────────────────────────────────────
    JsonDocument doc;
    doc["temperature_c"] = serialized(String(temperature, 1));
    doc["humidity_pct"]  = serialized(String(humidity,    1));
    doc["pressure_hpa"]  = serialized(String(pressure,    1));
    doc["co2_ppm"]       = serialized(String(co2_ppm,     0));
    doc["o2_pct"]        = serialized(String(o2_pct,      2));
    doc["pir_detected"]  = pirDetected ? 1 : 0;
    doc["distance_cm"]   = distance >= 0 ? serialized(String(distance, 1))
                                         : serialized(String(-1));
    doc["relay_lights"]  = relayLights  ? 1 : 0;
    doc["relay_ac"]      = relayAC      ? 1 : 0;
    doc["relay_outlets"] = relayOutlets ? 1 : 0;
    doc["relay_vent"]    = relayVent    ? 1 : 0;

    char buffer[512];
    size_t len = serializeJson(doc, buffer, sizeof(buffer));

    if (mqttClient.publish(TOPIC_DATA, buffer, len)) {
        Serial.printf("[MQTT] Yayınlandı: T=%.1f°C CO2=%.0fppm O2=%.1f%% P=%.1fhPa PIR=%d\n",
                      temperature, co2_ppm, o2_pct, pressure, pirDetected ? 1 : 0);
    } else {
        Serial.println("[MQTT] HATA: Yayın başarısız!");
    }
}
