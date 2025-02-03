import adafruit_dht
import board
import websocket
import json
import time
import socket
import uuid
from datetime import datetime
import subprocess

# Inisialisasi sensor DHT11 pada pin GPIO
dht_device = adafruit_dht.DHT11(board.D4)  # Gunakan GPIO 4

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
            
            # Ambil waktu saat ini
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Ambil hostname perangkat secara dinamis
            device_name = socket.gethostname()
            
            # Kembalikan data
            return {
                "device": f"Raspberry Pi 5|{device_name}",
                "device_kode": "Lumba-Lumba",
                "action": "Monitoring",
                "sensor": "DHT11",
                "temp": temperature,
                "hum": humidity,
                "ip_address": ip_address,
                "mac_address": mac_address,
                "timestamp": timestamp
            }
        else:
            return None
    except RuntimeError as error:
        print(f"RuntimeError: {error}")
        return None

# Fungsi untuk mengirim data ke WebSocket
def send_data_to_websocket(data):
    try:
        # Membuka koneksi WebSocket
        ws = websocket.create_connection(WEBSOCKET_URL)
        print("Connected to WebSocket server!")

        # Mengirim data ke WebSocket
        ws.send(json.dumps(data))
        print("Data sent to WebSocket server!")

        # Menutup koneksi WebSocket
        ws.close()
        
    except (websocket.WebSocketConnectionClosedException, Exception) as e:
        print(f"WebSocket connection error: {e}")
        # Coba ulangi koneksi jika WebSocket terputus
        print("Reconnecting to WebSocket...")
        time.sleep(5)  # Tunggu 5 detik sebelum mencoba kembali
        send_data_to_websocket(data)

def loop_data():
    try:
        # Loop untuk membaca data
        while True:
            # Baca data dari DHT11
            sensor_data = read_dht11()

            # Jika data berhasil dibaca, kirim ke WebSocket
            if sensor_data:
                send_data_to_websocket(sensor_data)
                print(f"Sent data: {sensor_data}")
            else:
                print("Data not available")

            # Tunggu 1 detik sebelum pembacaan berikutnya
            time.sleep(1)

    except KeyboardInterrupt:
        print("Program dihentikan.")
    finally:
        dht_device.exit()
        print("Sensor DHT11 dihentikan.")

# Program utama
if __name__ == "__main__":
    loop_data()
