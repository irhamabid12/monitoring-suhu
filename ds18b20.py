import time
import json
import socket
import uuid
import websocket
import subprocess
from datetime import datetime
from w1thermsensor import W1ThermSensor

# Inisialisasi sensor DS18B20
sensor = W1ThermSensor()

# URL WebSocket server
WEBSOCKET_URL = "wss://e-mon.rsudrsoetomo.jatimprov.go.id/ws_monitoring_suhu/"

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

# Fungsi untuk membaca suhu dari DS18B20
def read_ds18b20():
    try:
        temperature = sensor.get_temperature()  # Baca suhu dalam Celsius

        if temperature is not None:
            ip_address = get_ip_from_eth0()
            mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                                    for elements in range(0, 2*6, 2)][::-1])
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            device_name = socket.gethostname()

            # Ambil data dari setting.json
            settings = load_settings()

            data = {
                "device": f"Raspberry Pi 5|{device_name}",
                "device_kode": "Lumba-Lumba",
                "device_id": "202502120002",
                "action": "Monitoring",
                "sensor": "DS18B20",
                "temp": temperature,
		        "hum": 0,
                "ip_address": ip_address,
                "mac_address": mac_address,
                "timestamp": timestamp
            }

            # Gabungkan data dengan setting.json
            data.update(settings)

            return data
        else:
            return None
    except RuntimeError as error:
        print(f"RuntimeError: {error}")
        return None

# Fungsi untuk mengirim data ke WebSocket
def send_data_to_websocket(data, ws):
    try:
        ws.send(json.dumps(data))
        print("Data sent to WebSocket server!")
    except (websocket.WebSocketConnectionClosedException, Exception) as e:
        print(f"WebSocket connection error: {e}")
        reconnecting()

# Loop utama untuk membaca dan mengirim data
def loop_data(ws):
    try:
        while True:
            sensor_data = read_ds18b20()
            if sensor_data:
                send_data_to_websocket(sensor_data, ws)
                print(f"Sent data: {sensor_data}")
            else:
                print("Data not available")
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

# Baca data dari setting.json
def load_settings():
    try:
        with open("setting.json", "r") as file:
            settings = json.load(file)
        return settings
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Program utama
if __name__ == "__main__":
    while True:
        try:
            ws = websocket.create_connection(WEBSOCKET_URL)
            print("Connected to WebSocket server!")
            loop_data(ws)
        except (websocket.WebSocketConnectionClosedException, Exception) as e:
            print(f"WebSocket connection error: {e}")
            reconnecting()

