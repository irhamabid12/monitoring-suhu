import os
import adafruit_dht
import board
import websocket
import json
import time
import socket
import uuid
from datetime import datetime, timedelta
import subprocess
import requests
import binascii

# Inisialisasi sensor DHT11 pada pin GPIO
dht_device = adafruit_dht.DHT11(board.D17)  # Gunakan GPIO 17

# inisiasi variable time interval notifikasi
last_temp_notification_time = None
last_hum_notification_time = None

notification_interval = timedelta(seconds=60) # set delay selama 60 detik

# Pastikan zona waktu diatur ke Asia/Jakarta
os.environ['TZ'] = 'Asia/Jakarta'

# URL WebSocket server
WEBSOCKET_URL = "wss://e-mon.rsudrsoetomo.jatimprov.go.id/ws_monitoring_suhu/"  #URL server WebSocket

device_id = None
mac_address = None

# Fungsi untuk generate device id
def generate_device_id():
    global device_id, mac_address
    serial = None

    # Ambil MAC address perangkat
    mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                            for elements in range(0, 2*6, 2)][::-1])
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    serial = line.strip().split(":")[1].strip()
    except:
        serial = None

    if serial and serial != "0000000000000000":
        device_id = str(binascii.crc32(serial.encode()) & 0xffffffff)
    else:
        device_id = str(binascii.crc32(mac_address.encode()) & 0xffffffff)
    
    # Baca file setting.json
    with open("setting.json", "r") as file:
        settingUpdate = json.load(file)

    # Update device_id
    settingUpdate["device_id"] = device_id

    # Simpan kembali ke file
    with open("setting.json", "w") as file:
        json.dump(settingUpdate, file, indent=4)

# Fungsi untuk mendapatkan IP address dari eth0
def get_ip_from_eth0():
    try:
        # Menjalankan perintah 'hostname -I' untuk mendapatkan IP address
        ip_address = subprocess.check_output("hostname -I", shell=True).decode("utf-8").strip()
        # Ambil IP address yang dimulai dengan 10
        ip_list = ip_address.split()
        for ip in ip_list:
            if ip.startswith("10."):
                return ip
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return None

# Fungsi untuk membaca data dari DHT11
def read_dht11():
    global last_temp_notification_time, last_hum_notification_time 

    try:
        # Ambil data dari setting.json
        settings = load_settings()

        temp_calibration = settings.get("temp_calibration")
        hum_calibration = settings.get("hum_calibration")

        # Baca data dari DHT11
        temperature = dht_device.temperature
        humidity = dht_device.humidity

        # Pastikan data tidak kosong
        if temperature is not None and humidity is not None:
            # tambah dengan nilai kalibrasi
            temperatureCal = (temperature + temp_calibration)
            humidityCal = (humidity + hum_calibration)

            # Ambil IP address perangkat
            ip_address = get_ip_from_eth0()

            # Ambil waktu saat ini
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Ambil hostname perangkat secara dinamis
            device_name = socket.gethostname()

            # ambil nilai parameter di file setting.json
            min_temp = settings.get("min_temp", 0)
            max_temp = settings.get("max_temp", 100)

            min_hum = settings.get("min_hum", 0)
            max_hum = settings.get("max_hum", 100)

            location = settings.get("location")
            label = settings.get("label")

            wa_number = settings.get("wa_number")
            wa_api_url = "http://10.1.1.140/api/monitoring_suhu/notification/sendnotification"
            
            # Kembalikan data
            data = {
                "device": f"Raspberry Pi 5|{device_name}",
                "device_kode": device_id, 
                "device_id": device_id,
                "action": "Monitoring",
                "sensor_id": None,
                "sensor": "DHT11",
                "temp": temperatureCal,
                "hum": humidityCal,
                "ip_address": ip_address,
                "mac_address": mac_address,
                "timestamp": timestamp
            }

            # Gabungkan data dengan setting.json
            data.update(settings)

            # Cek apakah suhu atau humidity di luar batas
            temp_not_normal = temperature < min_temp or temperature > max_temp
            hum_not_normal = humidity < min_hum or humidity > max_hum

            # Cek suhu apakah di luar batas
            if temp_not_normal or hum_not_normal:
                now = datetime.now()
                if settings.get("notification_on", False):  # Cek notifikasi aktif/tidak
                    if last_temp_notification_time is None or (now - last_temp_notification_time) > notification_interval:
                        
                        if temp_not_normal and not hum_not_normal:
                            parameter = "Suhu"
                        elif hum_not_normal and not temp_not_normal:
                            parameter = "Kelembaban"
                        elif temp_not_normal and hum_not_normal:
                            parameter = "Suhu & Kelembaban"
                        else:
                            parameter = ""

                        
                        message = (
                            f"⚠️ *{parameter} tidak normal!*\n"
                            f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"Lokasi: *{label} di {location}*\n"
                            f"Suhu sekarang: {temperature}°C\n"
                            f"Batas Suhu: {min_temp}°C - {max_temp}°C\n"
                            f"Kelembaban sekarang: {humidity}%\n"
                            f"Batas Kelembaban: {min_hum}% - {max_hum}%\n"
                        )

                        payload = {
                            "numberRecv": [wa_number],
                            "message": message
                        }

                        try:
                            response = requests.post(wa_api_url, json=payload, timeout=5)
                            # print("Notifikasi WA dikirim:", response.text)
                            data["notifikasi"] = response.text
                            last_temp_notification_time = now
                        except requests.RequestException as e:
                            # print("Gagal mengirim notifikasi WA:", e)
                            data['notifikasi'] = f"Gagal kirim notifikasi: {e}"  # Catat juga kalau gagal
            return data
        else:
            return None
    except RuntimeError as error:
        print(f"RuntimeError: {error}")
        return None

# Fungsi untuk mengirim data ke WebSocket
def send_data_to_websocket(data, ws):
    try:
        # Mengirim data ke WebSocket
        ws.send(json.dumps(data))
        print("Data terkirim ke server WebSocket!")
        
    except (websocket.WebSocketConnectionClosedException, Exception) as e:
        print(f"Error koneksi WebSocket: {e}")
        raise  # Re-raise exception untuk ditangani di fungsi pemanggil

def loop_data(ws):
    try:
        # Loop untuk membaca data
        while True:
            # Baca data dari DHT11
            sensor_data = read_dht11()

            # Jika data berhasil dibaca, kirim ke WebSocket
            if sensor_data:
                send_data_to_websocket(sensor_data, ws)
                print(f"Data terkirim: {sensor_data}")
            else:
                print("Data tidak tersedia")

            # Tunggu 1 detik sebelum pembacaan berikutnya
            time.sleep(1)

    except KeyboardInterrupt:
        print("Program dihentikan.")
        raise
    except Exception as e:
        print(f"Error dalam loop data: {e}")
        raise
    finally:
        dht_device.exit()
        print("Sensor DHT11 dihentikan.")

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
                sensor_data = read_dht11()
                if sensor_data:
                    send_data_to_websocket(sensor_data, ws)
                    
            except websocket.WebSocketTimeoutException:
                print("Timeout - mengirim data sensor...")
                sensor_data = read_dht11()
                if sensor_data:
                    send_data_to_websocket(sensor_data, ws)
                continue
                
    except Exception as e:
        print(f"Error dalam listen message: {e}")
        raise

def change_setting (message_data):
    if (message_data.get("action") == "forwading" and 
        message_data.get("id") == device_id):
        
        print("Pesan forwarding diterima — memperbarui setting.json...")
        
        # Baca file setting.json
        with open("setting.json", "r") as file:
            settings = json.load(file)
        
       # Update nilai yang dikirim kalau ada
        if "min_temp" in message_data:
            settings["min_temp"] = message_data["min_temp"]
        if "max_temp" in message_data:
            settings["max_temp"] = message_data["max_temp"]
        if "temp_calibration" in message_data:
            settings["temp_calibration"] = message_data["temp_calibration"]
        if "min_hum" in message_data:
            settings["min_hum"] = message_data["min_hum"]
        if "max_hum" in message_data:
            settings["max_hum"] = message_data["max_hum"]
        if "hum_calibration" in message_data:
            settings["hum_calibration"] = message_data["hum_calibration"]
        if "wa_number" in message_data:
            settings["wa_number"] = message_data["wa_number"]
        if "calibration_time" in message_data:
            settings["calibration_time"] = message_data["calibration_time"]
        if "location" in message_data:
            settings["location"] = message_data["location"]
        if "label" in message_data:
            settings["label"] = message_data["label"]
        if "notification_on" in message_data:
            settings["notification_on"] = message_data["notification_on"]
        if "user_calibrator" in message_data:
            settings["user_calibrator"] = message_data["user_calibrator"]
        
        # Tulis kembali ke file setting.json
        with open("setting.json", 'w') as file:
            json.dump(settings, file, indent=4)
        
        print("Setting.json berhasil diperbarui.")
        
# Baca data dari setting.json
def load_settings():
    try:
        with open("setting.json", "r") as file:
            settings = json.load(file)
        return settings
    except (FileNotFoundError, json.JSONDecodeError):
        return {}  # Jika gagal, kembalikan dictionary kosong

# Program utama
if __name__ == "__main__":
    generate_device_id() # Ini untuk generate device_id dan get mac_address
    while True:
        try:
            print("Menghubungkan ke server WebSocket...")
            ws = websocket.create_connection(WEBSOCKET_URL)
            print("Terhubung ke server WebSocket!")
            
            # Jalankan loop data dan listen message dalam thread terpisah
            from threading import Thread
            
            data_thread = Thread(target=loop_data, args=(ws,))
            listen_thread = Thread(target=listen_message_ws, args=(ws,))
            
            data_thread.start()
            listen_thread.start()
            
            data_thread.join()
            listen_thread.join()
            
        except Exception as e:
            print(f"Koneksi terputus: {e}")
            print("Mencoba menghubungkan kembali dalam 5 detik...")
            time.sleep(5)
            continue
