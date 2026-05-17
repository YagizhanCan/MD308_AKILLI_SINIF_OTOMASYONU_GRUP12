# ⚡ Grup 12 Proje 3: Enerji Verimliliği için Akıllı Sınıf Otomasyon ve Analiz Sistemi

Bu proje, **MDB308 - IoT ve Dağıtık Sistemler** dersi kapsamında geliştirilmiş; geleneksel, monolitik ve statik otomasyon sistemlerini reddeden, tamamen **Asenkron, Olay-Güdümlü (Event-Driven Pub/Sub)** ve **Sensör Füzyonu (Sensor Fusion)** tabanlı bir Akıllı Sınıf Ekosistemidir.

Sistem, edge katmanındaki (ESP32) donanımsal telemetri verilerini, merkezi bir mesaj kuyruğu (MQTT Broker) üzerinden bağımsız (decoupled) bir Python Gateway servisine aktarır. Karar motoru veriyi gerçek zamanlı işleyerek hem veritabanı (SQLite3) I/O operasyonlarını yürütür hem de akıllı aktüasyon stratejileriyle **%45 ila %80 arasında dinamik enerji tasarrufu** sağlar.

---

## 🚀 Öne Çıkan Mimari Üstünlükler (SOTA Features)

* **Decoupled (Bağımsız) Topoloji:** Edge donanım ile sunucu katmanları seri port (COM) kısıtlamalarından arındırılmış, ağ seviyesinde tamamen izole edilmiştir.
* **Asenkron Reaktif Pipeline (`asyncio`):** Python tabanlı Gateway katmanı, `asyncio.Queue` mimarisiyle thread-blocking yaşamadan saniyede yüzlerce veri paketini (throughput) işleyebilir.
* **Fault-Tolerant & Resilient Ağ Gücü:** Ağ kesintilerine, gecikmelerine (latency) veya MQTT Broker çökmelerine karşı dirençli otomatik yeniden bağlanma (`Graceful Retry`) mekanizması.
* **Donanım Bağımsız Sunum (Telemetry Generator):** Fiziksel donanım bağlı olmasa bile sistemi canlı simüle eden, rastgele dalgalanmalı (Random Walk) akıllı bir yapay veri simülatörü barındırır.
* **Çok Boyutlu Hava Kalitesi (AQI) İndeksi:** Sınıf içi CO2, O2, sıcaklık ve nem parametrelerini gerçek zamanlı ağırlıklandırarak anlık iç mekan sağlık endeksini hesaplar.

---

## 🛠 Teknoloji Yığını (Tech Stack)

* **Donanım / Firmware:** ESP32-WROOM-32, C++ (Arduino Framework), I2C Veri Yolu Protokolü.
* **Mesaj Dağıtım Daemon'ı:** Eclipse Mosquitto MQTT Broker (`port: 1883`).
* **Asenkron Sunucu & Karar Motoru:** Python 3.10+, `paho-mqtt (v2.x - Callback API v2)`, `asyncio`.
* **Veri Depolama Katmanı:** SQLite3 (İndekslenmiş zaman serisi şeması, 16 Aktif Kolon).
* **Analitik Dashboard UI:** Streamlit Web Framework, Pandas Zaman Serisi Manipülasyonu.

---

## 📊 Karar Motoru Matrisi (Decision Logic Grid)

Sistem, sınıftaki insan varlığını (PIR) ve nesne mesafesini (HC-SR04) füzyona uğratarak kesin doluluk oranını (`occupancy`) belirler ve aktüatörleri şu kurallara göre yönetir:

| Aktüatör Düğümü | Nominal Güç | Tetikleyici Kriter (Trigger Reason) |
| :--- | :--- | :--- |
| **💡 Işıklar (Relay 1)** | 180W | `occupancy >= 1` (Sınıfta en az 1 kişi var) |
| **❄️ Klima (Relay 2)** | 950W | `occupancy >= 3` VEYA `temperature_c > 27°C` |
| **🔌 Prizler (Relay 3)** | 250W | `occupancy >= 1` (Sınıf boşken enerji tamamen kesilir) |
| **🌀 Havalandırma (Relay 4)** | 120W | `co2_ppm > 1200` VEYA `o2_pct < 19.5%` |

---

## 📁 Proje Klasör Yapısı

```text
MDBAKILLISINIF/
├── .vscode/
│   ├── c_cpp_properties.json  # C++ IntelliSense ve AST Parser konfigürasyonu
│   └── settings.json          # İzole venv Python interpreter ayarı
├── db_yoneticisi.py           # SQLite3 şema tanımı ve CRUD operasyonları
├── mqtt_gateway.py            # Asenkron backend servisi ve karar motoru
├── arayuz.py                  # Streamlit interaktif analitik dashboard
├── veri_generator.py          # Canlı demo için mock telemetri simülatörü
├── esp32_node.ino             # ESP32 firmware (Sensör okuma, JSON serialize, Pub/Sub)
├── requirements.txt           # Python bağımlılık deklarasyonları
└── sistemi_baslat.bat         # Tek tıkla deploy sağlayan Windows Batch scripti
⚙️ Kurulum ve Canlı Çalıştırma Protokolü
Projeyi yerel makinenizde sıfır hata (Zero-Crash) ile ayağa kaldırmak için aşağıdaki adımları terminalinizde sırasıyla koşturun:

1. Depoyu Klonlayın ve Klasöre Girin
Bash
git clone [https://github.com/KULLANICI_ADIN/REPO_ADIN.git](https://github.com/KULLANICI_ADIN/REPO_ADIN.git)
cd REPO_ADIN/MDBAKILLISINIF
2. İzole Sanal Ortamı (venv) Kurun ve Aktif Edin
Bash
python -m venv venv
# Windows için aktif etme:
.\venv\Scripts\activate
3. SOTA Bağımlılık Ağacını Yükleyin
Bash
pip install -r requirements.txt
4. Sistemi Tek Tıkla Ateşleyin
Klasör içindeki otomasyon scriptini çalıştırın:

Bash
.\sistemi_baslat.bat
Bu komut; yerel Mosquitto Broker'ı, asenkron ağ geçidini, yapay veri simülatörünü ve Streamlit web arayüzünü ayrı pencerelerde otomatik olarak başlatacaktır.
Tarayıcınızda anında açılacak adres: http://localhost:8501


👨‍💻 Geliştirici Grubu (Grup 12 Üyeleri)
Bu proje, aşağıda bilgileri yer alan Grup 12 üyeleri tarafından uçtan uca tasarlanmış, kodlanmış ve entegre edilmiştir:

YAĞIZHAN CAN - 21120205711 (Sistem Mimarisi, Asenkron Gateway, DB & Ajan Yönetimi)

Muhammed Emin Aydın - 23120101038

Yunus Emre Boztepe - 23120205036

Ali Karaca - 23120606062

Berkay Keskin - 23120101090

Ahmet Murat Kıvrak - 23120606040

MDB308 — IoT ve Dağıtık Sistemler Proje Sunumu © 2026
