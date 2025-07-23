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

# Inisialisasi sensor DHT11 pada pin GPIO
dht_device = adafruit_dht.DHT11(board.D4)  # Gunakan GPIO 4

# inisiasi variable time interval notifikasi
last_notification_time = None
notification_interval = timedelta(seconds=10) # set delay selama 10 detik

# Pastikan zona waktu diatur ke Asia/Jakarta
os.environ['TZ'] = 'Asia/Jakarta'

# URL WebSocket server
WEBSOCKET_URL = "wss://e-mon.rsudrsoetomo.jatimprov.go.id/ws_monitoring_suhu/"  #URL server WebSocket

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
    global last_notification_time

    try:
        # Baca data dari DHT11
        temperature = dht_device.temperature
        humidity = dht_device.humidity

        # Pastikan data tidak kosong
        if temperature is not None and humidity is not None:
            # Ambil IP address perangkat
            ip_address = get_ip_from_eth0()
            
            # Ambil MAC address perangkat
            mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                                    for elements in range(0, 2*6, 2)][::-1])
            # # Set zona waktu ke WIB
            # time.tzset()
            # time.environ['TZ'] = 'Asia/Jakarta'

            # Ambil waktu saat ini
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Ambil hostname perangkat secara dinamis
            device_name = socket.gethostname()

            # Ambil data dari setting.json
            settings = load_settings()

            # ambil nilai parameter di file setting.json
            min_temp = settings.get("min_temp", 0)
            max_temp = settings.get("max_temp", 100)
            min_hum = settings.get("min_hum", 0)
            max_hum = settings.get("max_hum", 100)
            wa_number = settings.get("wa_number")
            wa_api_url = "http://10.1.1.140/api/monitoring_suhu/notification/sendnotification"
            
            # Kembalikan data
            data = {
                "device": f"Raspberry Pi 5|{device_name}",
                "device_kode": "Lumba-Lumba",
                "device_id": "202502120001",
                "action": "Monitoring",
                "sensor_id": "202502270005",
                "sensor": "DHT11",
                "temp": temperature,
                "hum": humidity,
                "ip_address": ip_address,
                "mac_address": mac_address,
                "timestamp": timestamp
            }

            # Gabungkan data dengan setting.json
            data.update(settings)

            # Cek suhu apakah di luar batas
            if temperature < min_temp or temperature > max_temp:
                now = datetime.now()
                if last_notification_time is None or (now - last_notification_time) > notification_interval:
                    message = (
                        f"⚠️ Suhu tidak normal!\n"
                        f"Suhu sekarang: {temperature}°C\n"
                        f"Batas: {min_temp}°C - {max_temp}°C"
                    )
                    payload = {
                        "numberRecv": [wa_number],
                        "message": message
                    }
                    try:
                        response = requests.post(wa_api_url, json=payload, timeout=5)
                        # print("Notifikasi WA dikirim:", response.text)
                        data["notifikasi"] = response.text
                        last_notification_time = now
                    except requests.RequestException as e:
                        # print("Gagal mengirim notifikasi WA:", e)
                        data['notifikasi'] = f"Gagal kirim notifikasi: {e}"  # Catat juga kalau gagal

            # Cek humidity apakah di luar batas
            if humidity < min_hum or humidity > max_hum:
                now = datetime.now()
                if last_notification_time is None or (now - last_notification_time) > notification_interval:
                    message = (
                        f"⚠️ Kelembaban tidak normal!\n"
                        f"Kelembaban sekarang: {humidity}%\n"
                        f"Batas: {min_hum}% - {max_hum}%"
                    )
                    payload = {
                        "numberRecv": [wa_number],
                        "message": message
                    }
                    try:
                        response = requests.post(wa_api_url, json=payload, timeout=5)
                        # print("Notifikasi WA dikirim:", response.text)
                        data["notifikasi"] = response.text
                        last_notification_time = now
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
        # Membuka koneksi WebSocket
        # ws = websocket.create_connection(WEBSOCKET_URL)
        # print("Connected to WebSocket server!")

        # Mengirim data ke WebSocket
        ws.send(json.dumps(data))
        print("Data sent to WebSocket server!")

        # Menutup koneksi WebSocket
        # ws.close()
        
    except (websocket.WebSocketConnectionClosedException, Exception) as e:
        reconecting()
        # print(f"WebSocket connection error: {e}")
        # Coba ulangi koneksi jika WebSocket terputus
        # print("Reconnecting to WebSocket...")
        # time.sleep(5)  # Tunggu 5 detik sebelum mencoba kembali
        # send_data_to_websocket(data, ws)

def loop_data(ws):
    # try:
    #     # Loop untuk membaca data
    #     while True:
    #         # Baca data dari DHT11
    #         sensor_data = read_dht11()

    #         # Jika data berhasil dibaca, kirim ke WebSocket
    #         if sensor_data:
    #             send_data_to_websocket(sensor_data,ws)
    #             print(f"Sent data: {sensor_data}")
    #         else:
    #             print("Data not available")

    #         # Tunggu 1 detik sebelum pembacaan berikutnya
    #         time.sleep(1)

    # except KeyboardInterrupt:
    #     print("Program dihentikan.")
    # finally:
    #     dht_device.exit()
        print("Sensor DHT11 dihentikan.")


def reconecting():
    ws = websocket.create_connection(WEBSOCKET_URL)
    print("Connected to WebSocket server!")
    # loop_data(ws)


# Baca data dari setting.json
def load_settings():
    try:
        with open("setting.json", "r") as file:
            settings = json.load(file)
        return settings
    except (FileNotFoundError, json.JSONDecodeError):
        return {}  # Jika gagal, kembalikan dictionary kosong
    
def listen_message_ws(ws):
    while True:
        ws.settimeout(2)  # timeout 2 detik
        message = ws.recv()
        print(f"Received message: {message}")

# Program utama
if __name__ == "__main__":
    while True:
        try:
            ws = websocket.create_connection(WEBSOCKET_URL)
            print("Connected to WebSocket server!")
            listen_message_ws(ws)
            # loop_data(ws)

            print(ws)
            
        except (websocket.WebSocketConnectionClosedException, Exception) as e:
            ws = websocket.create_connection(WEBSOCKET_URL)
            listen_message_ws(ws)
            # loop_data(ws)

            # subprocess.run(["pm2", "restart", "dht11.py"])
            # print(f"WebSocket connection error: {e}")
            # # Coba ulangi koneksi jika WebSocket terputus
            # print("Reconnecting to WebSocket...")
            time.sleep(10)

       

