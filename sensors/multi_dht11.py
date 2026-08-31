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
from threading import Thread

# ============================================================
# Konfigurasi sensor DHT11 — tambah/kurangi entry sesuai hardware
# ============================================================
SENSOR_CONFIGS = [
    {"pin": board.D17, "config_file": "setting_dht11.json",    "id_offset": 0},
    {"pin": board.D27, "config_file": "setting_dht11_p2.json", "id_offset": 1},
    {"pin": board.D21, "config_file": "setting_dht11_p3.json", "id_offset": 2},
    {"pin": board.D23, "config_file": "setting_dht11_p4.json", "id_offset": 3},
]

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")

# URL WebSocket server
WEBSOCKET_URL = "wss://e-mon.rsudrsoetomo.jatimprov.go.id/ws_monitoring_suhu/"

# Interval minimum antar notifikasi WA
notification_interval = timedelta(seconds=60)

# Pastikan zona waktu Asia/Jakarta
os.environ['TZ'] = 'Asia/Jakarta'

# ============================================================
# Global device info (shared across all sensors)
# ============================================================
base_id = None
mac_address = None


def generate_device_id():
    """Generate base_id dari serial CPU atau MAC address."""
    global base_id, mac_address
    serial = None

    mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                            for elements in range(0, 2*6, 2)][::-1])
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    serial = line.strip().split(":")[1].strip()
    except Exception:
        serial = None

    if serial and serial != "0000000000000000":
        base_id = binascii.crc32(serial.encode()) & 0xffffffff
    else:
        base_id = binascii.crc32(mac_address.encode()) & 0xffffffff


# ============================================================
# Per-sensor state
# ============================================================
def create_sensor_state(cfg):
    """Buat state awal untuk satu sensor."""
    config_path = os.path.join(CONFIG_DIR, cfg["config_file"])
    return {
        "pin":             cfg["pin"],
        "id_offset":       cfg["id_offset"],
        "config_path":     config_path,
        "device_id":       None,
        "dht_device":      adafruit_dht.DHT11(cfg["pin"]),
        "last_notif_time": None,
    }


def reinit_dht(state):
    """Reinisialisasi objek DHT11 jika terjadi OSError."""
    try:
        state["dht_device"].exit()
    except Exception:
        pass
    time.sleep(0.5)
    state["dht_device"] = adafruit_dht.DHT11(state["pin"])


# ============================================================
# Config helpers
# ============================================================
def ensure_setting(config_path, device_id):
    """Buat file config JSON dengan nilai default jika belum ada."""
    default_settings = {
        "device_id": str(device_id),
        "location": "Adm Instalasi Teknologi Komunikasi Dan Informasi",
        "label": "Ruangan Programmer ITKI",
        "calibration": False,
        "min_temp": 0,
        "max_temp": 0,
        "temp_calibration": 0,
        "min_hum": 0,
        "max_hum": 0,
        "hum_calibration": 0,
        "notification_on": 0,
        "wa_number": None,
        "calibration_time": None,
        "user_calibrator": None,
    }
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump(default_settings, f, indent=4)


def load_settings(config_path):
    """Baca file config JSON."""
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_device_id_in_file(config_path, device_id):
    """Update nilai device_id di file config."""
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        data["device_id"] = str(device_id)
        with open(config_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Gagal update device_id di {config_path}: {e}")


# ============================================================
# Helpers
# ============================================================
def get_ip_from_eth0():
    """Ambil IP address lokal yang diawali '10.'"""
    try:
        ip_address = subprocess.check_output("hostname -I", shell=True).decode("utf-8").strip()
        for ip in ip_address.split():
            if ip.startswith("10."):
                return ip
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error get IP: {e}")
        return None


# ============================================================
# Baca satu sensor
# ============================================================
def read_single_sensor(state):
    """
    Baca satu sensor DHT11 dan kembalikan dict data atau None.
    OSError  -> reinit sensor -> return None (skip siklus ini).
    RuntimeError -> return None (sinyal tidak sempurna, normal pada DHT11).
    """
    config_path = state["config_path"]
    device_id   = state["device_id"]

    ensure_setting(config_path, device_id)
    settings = load_settings(config_path)

    temp_calibration = settings.get("temp_calibration") or 0
    hum_calibration  = settings.get("hum_calibration")  or 0

    try:
        temperature = state["dht_device"].temperature
        humidity    = state["dht_device"].humidity
    except OSError as e:
        print(f"OSError sensor {device_id} (reinisialisasi): {e}")
        reinit_dht(state)
        return None
    except RuntimeError as e:
        print(f"RuntimeError sensor {device_id}: {e}")
        return None

    if temperature is None or humidity is None:
        return None

    temperatureCal = temperature + temp_calibration
    humidityCal    = humidity    + hum_calibration

    ip_address  = get_ip_from_eth0()
    timestamp   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    device_name = socket.gethostname()

    min_temp  = settings.get("min_temp", 0)
    max_temp  = settings.get("max_temp", 0)
    min_hum   = settings.get("min_hum", 0)
    max_hum   = settings.get("max_hum", 0)
    location  = settings.get("location")
    label     = settings.get("label")
    wa_number = settings.get("wa_number")
    wa_api_url = "http://10.1.1.140/api/monitoring_suhu/notification/sendnotification"

    data = {
        "device":      f"Raspberry Pi 5|{device_name}",
        "device_kode": str(device_id),
        "device_id":   str(device_id),
        "action":      "Monitoring",
        "sensor_id":   None,
        "sensor":      "DHT11",
        "temp":        temperatureCal,
        "hum":         humidityCal,
        "ip_address":  ip_address,
        "mac_address": mac_address,
        "timestamp":   timestamp,
    }
    data.update(settings)

    # Notifikasi WA jika suhu/humidity di luar batas (hanya jika batas dikonfigurasi)
    temp_not_normal = max_temp > 0 and (temperatureCal < min_temp or temperatureCal > max_temp)
    hum_not_normal  = max_hum  > 0 and (humidityCal   < min_hum  or humidityCal   > max_hum)

    if wa_number and (temp_not_normal or hum_not_normal) and settings.get("notification_on", False):
        now = datetime.now()
        if state["last_notif_time"] is None or (now - state["last_notif_time"]) > notification_interval:
            if   temp_not_normal and not hum_not_normal: parameter = "Suhu"
            elif hum_not_normal  and not temp_not_normal: parameter = "Kelembaban"
            else:                                          parameter = "Suhu & Kelembaban"

            message = (
                f"⚠️ *{parameter} tidak normal!*\n"
                f"Waktu: {timestamp}\n"
                f"Lokasi: *{label} di {location}*\n"
                f"Suhu sekarang: {temperatureCal}°C\n"
                f"Batas Suhu: {min_temp}°C - {max_temp}°C\n"
                f"Kelembaban sekarang: {humidityCal}%\n"
                f"Batas Kelembaban: {min_hum}% - {max_hum}%\n"
            )
            payload = {"numberRecv": [wa_number], "message": message}
            try:
                response = requests.post(wa_api_url, json=payload, timeout=5)
                data["notifikasi"] = response.text
                state["last_notif_time"] = now
            except requests.RequestException as e:
                data["notifikasi"] = f"Gagal kirim notifikasi: {e}"

    return data


# ============================================================
# WebSocket helpers
# ============================================================
def send_data_to_websocket(data, ws):
    ws.send(json.dumps(data))
    print(f"Data terkirim: {data}")


def read_and_send_all(states, ws):
    """Baca semua sensor secara sequential dan kirim ke WebSocket."""
    for state in states:
        try:
            sensor_data = read_single_sensor(state)
            if sensor_data:
                send_data_to_websocket(sensor_data, ws)
            else:
                print(f"Sensor device_id={state['device_id']}: data tidak tersedia")
        except (websocket.WebSocketConnectionClosedException,
                websocket.WebSocketException) as e:
            print(f"WebSocket error saat kirim sensor {state['device_id']}: {e}")
            raise   # Biarkan thread utama tangani reconnect
        except Exception as e:
            print(f"Error sensor {state['device_id']}: {e}")


# ============================================================
# Thread: loop kirim data setiap 1 detik
# ============================================================
def loop_data(ws, states):
    try:
        while True:
            read_and_send_all(states, ws)
            time.sleep(1)
    except KeyboardInterrupt:
        print("Program dihentikan.")
        raise
    except Exception as e:
        print(f"Error dalam loop data: {e}")
        raise
    finally:
        for state in states:
            try:
                state["dht_device"].exit()
            except Exception:
                pass
        print("Semua sensor DHT11 dihentikan.")


# ============================================================
# Thread: listen pesan dari WebSocket
# ============================================================
def listen_message_ws(ws, states):
    try:
        while True:
            try:
                ws.settimeout(5)
                message = ws.recv()
                try:
                    message_data = json.loads(message)
                    change_setting(message_data, states)
                except json.JSONDecodeError:
                    print("Pesan bukan format JSON — diabaikan.")
                read_and_send_all(states, ws)

            except websocket.WebSocketTimeoutException:
                print("Timeout - mengirim data sensor...")
                read_and_send_all(states, ws)
                continue

    except Exception as e:
        print(f"Error dalam listen message: {e}")
        raise


# ============================================================
# Handler update setting via pesan WebSocket
# ============================================================
def change_setting(message_data, states):
    """Update file config sensor berdasarkan device_id dari pesan server."""
    if message_data.get("action") != "forwading":
        return

    target_device_id = str(message_data.get("id", ""))

    # Cari sensor yang device_id-nya cocok
    target_state = None
    for state in states:
        if str(state["device_id"]) == target_device_id:
            target_state = state
            break

    if not target_state:
        print(f"[WARNING] device_id '{target_device_id}' tidak ditemukan di sensor manapun.")
        return

    config_path = target_state["config_path"]
    config_name = os.path.basename(config_path)
    print(f"Pesan forwarding diterima untuk device_id {target_device_id} — memperbarui {config_name}...")

    try:
        with open(config_path, "r") as f:
            settings = json.load(f)
    except Exception as e:
        print(f"Gagal membaca {config_name}: {e}")
        return

    updatable_keys = [
        "min_temp", "max_temp", "temp_calibration",
        "min_hum", "max_hum", "hum_calibration",
        "wa_number", "calibration_time", "location",
        "label", "notification_on", "user_calibrator",
    ]
    for key in updatable_keys:
        if key in message_data:
            settings[key] = message_data[key]

    try:
        with open(config_path, "w") as f:
            json.dump(settings, f, indent=4)
        print(f"{config_name} berhasil diperbarui.")
    except Exception as e:
        print(f"Gagal menyimpan {config_name}: {e}")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    generate_device_id()

    # Inisialisasi state semua sensor
    states = []
    for cfg in SENSOR_CONFIGS:
        state = create_sensor_state(cfg)
        state["device_id"] = str(base_id + cfg["id_offset"])
        ensure_setting(state["config_path"], state["device_id"])
        update_device_id_in_file(state["config_path"], state["device_id"])
        states.append(state)
        print(f"Sensor GPIO {cfg['pin']} -> device_id={state['device_id']}, config={cfg['config_file']}")

    # Loop utama dengan auto-reconnect
    while True:
        try:
            print("Menghubungkan ke server WebSocket...")
            ws = websocket.create_connection(WEBSOCKET_URL)
            print("Terhubung ke server WebSocket!")

            data_thread   = Thread(target=loop_data,         args=(ws, states), daemon=True)
            listen_thread = Thread(target=listen_message_ws, args=(ws, states), daemon=True)

            data_thread.start()
            listen_thread.start()

            data_thread.join()
            listen_thread.join()

        except Exception as e:
            print(f"Koneksi terputus: {e}")
            print("Mencoba menghubungkan kembali dalam 5 detik...")
            time.sleep(5)
            continue
