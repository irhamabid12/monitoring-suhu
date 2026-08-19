import os
import time
import json
import socket
import uuid
import websocket
import subprocess
import threading
from datetime import datetime, timedelta
from w1thermsensor import W1ThermSensor
import requests
import binascii

# URL WebSocket server
WEBSOCKET_URL = "wss://e-mon.rsudrsoetomo.jatimprov.go.id/ws_monitoring_suhu/"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "setting_ds18b20.json")

device_id = None
mac_address = None
ema_values = {}
ema_lock = threading.Lock()  # Lock untuk thread safety akses ema_values

# === Konfigurasi Algoritma Pembacaan Suhu ===
# Alpha EMA: 0.2 = responsif tapi tetap halus (cocok untuk kulkas farmasi 2–8°C)
# Semakin besar alpha → lebih responsif, semakin kecil → lebih halus
smoothing_alpha = 0.2

# Median filter: ambil N sample lalu ambil nilai tengah untuk tolak spike
NUM_SAMPLES = 3       # Jumlah sample per pembacaan
SAMPLE_INTERVAL = 0.1  # Jeda antar sample (detik) — 100ms cukup untuk DS18B20

# Fungsi untuk generate device id
def generate_device_id():
    global device_id, mac_address

    # Ambil MAC address perangkat
    mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                            for elements in range(0, 2*6, 2)][::-1])
    
    device_id = binascii.crc32(mac_address.encode()) & 0xffffffff

# inisiasi variable time interval notifikasi
last_temp_notification_time = None

notification_interval = timedelta(minutes=5) # set delay selama 5 menit antara

# Fungsi untuk mendapatkan IP address dari eth0
def get_ip_from_eth0():
    try:
        ip_address = subprocess.check_output("hostname -I", shell=True).decode("utf-8").strip()
        ip_list = ip_address.split()
        for ip in ip_list:
            if ip.startswith("10."):
                return ip
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return None

def get_median_temperature(sensor):
    """
    Ambil NUM_SAMPLES pembacaan lalu kembalikan nilai median.
    Teknik ini efektif menolak spike/glitch tanpa membuang presisi.
    DS18B20 sudah menangani konversi 12-bit (~750ms) secara internal.
    """
    samples = []
    for _ in range(NUM_SAMPLES):
        try:
            t = sensor.get_temperature()
            if t is not None:
                samples.append(t)
        except Exception:
            pass
        time.sleep(SAMPLE_INTERVAL)  # Beri jeda antar sample
    if not samples:
        return None
    samples.sort()
    return samples[len(samples) // 2]  # Nilai median


# Fungsi untuk membaca suhu dari semua sensor DS18B20
def read_ds18b20():
    global last_temp_notification_time

    try:
        sensors = W1ThermSensor.get_available_sensors()  # Dapatkan semua sensor DS18B20 yang terhubung

        # Ambil IP address perangkat 
        ip_address = get_ip_from_eth0()
        
        # Ambil waktu saat ini
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Ambil hostname perangkat secara dinamis
        device_name = socket.gethostname()
        
        all_sensor_data = []

        for index, sensor in enumerate(sensors, start=1):
            # panggil function create json file dan tambahkan configurasi berdasarkan sensor id
            ensure_sensor_settings(sensor.id, f"{device_id}{index}")

            # Ambil data dari setting_ds18b20.json
            settings = load_settings(sensor.id)
            
            # ambil nilai parameter di file setting_ds18b20.json
            temp_calibration = settings.get("temp_calibration")
            min_temp = settings.get("min_temp", 0)
            max_temp = settings.get("max_temp", 100)

            location = settings.get("location")
            label = settings.get("label")

            # parameter notifikasi wa
            wa_number = settings.get("wa_number")

            # endpoint notif wa
            wa_api_url = "http://10.1.1.140/api/monitoring_suhu/notification/sendnotification"

            # Default nilai awal
            status = "OK"
            temperature = None
            notifikasi_info = None

            try:
                # === Step 1: Median Filter — tolak spike/glitch ===
                # Ambil NUM_SAMPLES pembacaan dan gunakan nilai median
                temp_raw = get_median_temperature(sensor)
                if temp_raw is None:
                    raise ValueError("Sensor tidak terbaca")

                # === Step 2: Kalibrasi offset ===
                calibrated_temp = round(temp_raw + (temp_calibration or 0.0), 1)

                # === Step 3: EMA Smoothing — thread-safe ===
                # EMA memperhalus fluktuasi kecil tanpa menunda respons perubahan suhu nyata
                with ema_lock:
                    if sensor.id not in ema_values:
                        # Inisialisasi: nilai pertama langsung menjadi seed EMA
                        ema_values[sensor.id] = calibrated_temp
                    else:
                        ema_values[sensor.id] = round(
                            smoothing_alpha * calibrated_temp
                            + (1 - smoothing_alpha) * ema_values[sensor.id],
                            1
                        )
                    temperature = ema_values[sensor.id]  # Presisi 1 angka di belakang koma

            except Exception as e:
                status = "ERROR"
                temperature = None
                notifikasi_info = f"Gagal membaca suhu: {e}"

            # temperature = round(sensor.get_temperature(), 2) + (temp_calibration or 0.0)  # Baca suhu dalam Celsius

            sensor_data = {
                "sensor_id": sensor.id,
                "device": f"Raspberry Pi 5|{device_name}",
                "device_kode": f"28-{sensor.id}",
                "device_id": int(sensor.id.strip(), 16),
                "action": "Monitoring",
                "sensor": "DS18B20",
                "temp": temperature,
                "ip_address": ip_address,
                "mac_address": mac_address,
                "timestamp": timestamp,
                "status": status
            }

            # Gabungkan data dengan setting_ds18b20.json
            sensor_data.update(settings)

            all_sensor_data.append(sensor_data)

            # Cek suhu apakah di luar batas, jika tidak normal kirim notifikasi
            if wa_number != None and (temperature < min_temp or temperature > max_temp) and status == "OK":
                now = datetime.now()
                if settings.get("notification_on", False):  # Cek notifikasi aktif/tidak
                    if last_temp_notification_time is None or (now - last_temp_notification_time) > notification_interval:
                        message = (
                            f"⚠️ *Suhu tidak normal!*\n"
                            f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"Lokasi: *{label} di {location}*\n"
                            f"Suhu sekarang: {temperature}°C\n"
                            f"Batas Suhu: {min_temp}°C - {max_temp}°C"
                        )
                        payload = {
                            "numberRecv": [wa_number],
                            "message": message
                        }
                        try:
                            response = requests.post(wa_api_url, json=payload, timeout=5)
                            # print("Notifikasi WA dikirim:", response.text)
                            sensor_data["notifikasi"] = response.text
                            last_temp_notification_time = now
                        except requests.RequestException as e:
                            # print("Gagal mengirim notifikasi WA:", e)
                            sensor_data['notifikasi'] = f"Gagal kirim notifikasi: {e}"  # Catat juga kalau gagal

        return all_sensor_data

    except RuntimeError as error:
        print(f"RuntimeError: {error}")
        return None

# Fungsi untuk mengirim data ke WebSocket
def send_data_to_websocket(data_list, ws):
    try:
        for data in data_list:
            ws.send(json.dumps(data))
            print(f"Sent data: {data}")
        print("All sensor data sent to WebSocket server!")
    except (websocket.WebSocketConnectionClosedException, Exception) as e:
        print(f"WebSocket connection error: {e}")
        reconnecting()

# Loop utama untuk membaca dan mengirim data
def loop_data(ws):
    try:
        while True:
            sensor_data_list = read_ds18b20()
            if sensor_data_list:
                send_data_to_websocket(sensor_data_list, ws)
            else:
                print("No data available")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Program dihentikan.")
    finally:
        print("Sensor DS18B20 dihentikan.")

# Fungsi untuk melakukan reconnect jika WebSocket terputus
def reconnecting():
    time.sleep(5)
    ws = websocket.create_connection(WEBSOCKET_URL)
    print("Reconnected to WebSocket server!")
    loop_data(ws)

# Baca data dari setting_ds18b20.json
def load_settings(sensor_id=None):
    try:
        with open(CONFIG_PATH, "r") as file:
            settings = json.load(file)
        # return settings

        # Ambil konfigurasi berdasarkan sensor_id atau gunakan default jika tidak ditemukan
        return settings.get(sensor_id, settings.get("default", {}))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    
# create setting_ds18b20.json 
def ensure_sensor_settings(sensor_id, device_id, default_settings=None):
    if default_settings is None:
        default_settings = {
            "device_id": str(int(sensor_id.strip(), 16)),
            "location": "Adm Instalasi Teknologi Komunikasi Dan Informasi",
            "label": "Ruangan Programmer ITKI",
            "calibration": False,
            "min_temp": None,
            "max_temp": None,
            "temp_calibration": None,
            "notification_on": False,
            "wa_number": None,
            "calibration_time": None,
            "user_calibrator": None
        }

    # Buat direktori jika belum ada
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    # Buat file JSON kosong jika belum ada
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            json.dump({}, f, indent=4)

    # Baca isi file
    with open(CONFIG_PATH, 'r') as f:
        settings_data = json.load(f)

    # Tambahkan sensor_id jika belum ada
    if sensor_id not in settings_data:
        settings_data[sensor_id] = default_settings
        with open(CONFIG_PATH, 'w') as f:
            json.dump(settings_data, f, indent=4)

# membaca pesan dari web socet
def listen_message_ws(ws):
    try:
        while True:
            try:
                ws.settimeout(5)  # Timeout 5 detik
                message = ws.recv()
                
                try:
                    message_data = json.loads(message)
                    change_setting (message_data)
                except json.JSONDecodeError:
                    print("Pesan bukan format JSON — diabaikan.")
                
                # Kirim data sensor setelah menerima pesan
                sensor_data = read_ds18b20()
                if sensor_data:
                    send_data_to_websocket(sensor_data, ws)
                    
            except websocket.WebSocketTimeoutException:
                print("Timeout - mengirim data sensor...")
                sensor_data = read_ds18b20()
                if sensor_data:
                    send_data_to_websocket(sensor_data, ws)
                continue
                
    except Exception as e:
        print(f"Error dalam listen message: {e}")
        raise

def change_setting (message_data):
    if (message_data.get("action") == "forwading"):
        target_device_id = message_data.get("id")

        print("Pesan forwarding diterima — memperbarui setting_ds18b20.json...")
        
        # Baca file setting_ds18b20.json
        with open(CONFIG_PATH, "r") as file:
            settings = json.load(file)
        
         # Cari sensor_id yang memiliki device_id yang cocok
        found_sensor_id = None
        for sensor_id, config in settings.items():
            if config.get("device_id") == target_device_id:
                found_sensor_id = sensor_id
                break

        if (found_sensor_id):
            sensor_settings = settings[found_sensor_id]

            # Update nilai yang dikirim kalau ada
            if "min_temp" in message_data:
                sensor_settings["min_temp"] = message_data["min_temp"]
            if "max_temp" in message_data:
                sensor_settings["max_temp"] = message_data["max_temp"]
            if "temp_calibration" in message_data:
                sensor_settings["temp_calibration"] = message_data["temp_calibration"]
            if "wa_number" in message_data:
                sensor_settings["wa_number"] = message_data["wa_number"]
            if "calibration_time" in message_data:
                sensor_settings["calibration_time"] = message_data["calibration_time"]
            if "location" in message_data:
                sensor_settings["location"] = message_data["location"]
            if "label" in message_data:
                sensor_settings["label"] = message_data["label"]
            if "notification_on" in message_data:
                sensor_settings["notification_on"] = message_data["notification_on"]
            if "user_calibrator" in message_data:
                sensor_settings["user_calibrator"] = message_data["user_calibrator"]
        
            settings[sensor_id] = sensor_settings  # Simpan kembali perubahan

            # Tulis kembali ke file setting_ds18b20.json
            with open(CONFIG_PATH, 'w') as file:
                json.dump(settings, file, indent=4)
            
            print("setting_ds18b20.json berhasil diperbarui.")
        else:
            print(f"[WARNING] Sensor ID '{sensor_id}' tidak ditemukan dalam setting_ds18b20.json.")
        

# Program utama
if __name__ == "__main__":
    generate_device_id()
    while True:
        try:
            print("Menghubungkan ke server WebSocket...")
            ws = websocket.create_connection(WEBSOCKET_URL)
            print("Connected to WebSocket server!")
            
            # loop_data(ws)

             # Jalankan loop data dan listen message dalam thread terpisah
            from threading import Thread
            
            data_thread = Thread(target=loop_data, args=(ws,))
            listen_thread = Thread(target=listen_message_ws, args=(ws,))
            
            data_thread.start()
            listen_thread.start()
            
            data_thread.join()
            listen_thread.join()
        # except (websocket.WebSocketConnectionClosedException, Exception) as e:
            # print(f"WebSocket connection error: {e}")
            # reconnecting()
        except Exception as e:
            print(f"Koneksi terputus: {e}")
            print("Mencoba menghubungkan kembali dalam 5 detik...")
            time.sleep(5)
            continue
