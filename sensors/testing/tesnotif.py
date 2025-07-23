import json
import requests
from datetime import datetime, timedelta
import time

print(requests.__version__)  # cek versi requests

wa_api_url = "http://10.1.1.140/api/monitoring_suhu/notification/sendnotification"

last_notification_time = None
notification_interval = timedelta(seconds=10)  # delay antar notifikasi

# Baca data dari setting.json sekali
with open("setting.json", "r") as file:
    settings = json.load(file)

min_temp = settings.get("min_temp", 0)
max_temp = settings.get("max_temp", 100)
wa_number = settings.get("wa_number")


while True:
    # Simulasi baca suhu (bisa diganti dengan sensor beneran)
    temperature = 25.3  # Ganti ini sesuai suhu dari sensor

    now = datetime.now()

    if temperature < min_temp or temperature > max_temp:
        if last_notification_time is None or (now - last_notification_time) > notification_interval:
            print("⚠️ Suhu tidak normal, kirim notifikasi WA...")

            message = (
                f"⚠️ Alert Suhu\n"
                f"Suhu sekarang: {temperature}°C\n"
                f"Batas: {min_temp}°C - {max_temp}°C"
            )
            payload = {
                "numberRecv": [wa_number],
                "message": message
            }

            try:
                response = requests.post(wa_api_url, json=payload, timeout=5)
                print("✅ Notifikasi WA dikirim:", response.text)
                last_notification_time = now
            except requests.RequestException as e:
                print("❌ Gagal mengirim notifikasi WA:", e)
        else:
            print("⏳ Menunggu interval pengiriman notifikasi berikutnya...")
    else:
        print("✅ Suhu normal:", temperature, "°C")

    time.sleep(5)  # delay loop 5 detik biar gak terlalu cepat
