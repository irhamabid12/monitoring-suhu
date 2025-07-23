import time
import board
import adafruit_dht

# Inisialisasi sensor DHT11 di GPIO17
dht_device = adafruit_dht.DHT11(board.D17)

print("Mulai membaca data dari DHT11... (Tekan Ctrl+C untuk berhenti)")

try:
    while True:
        try:
            temperature = dht_device.temperature
            humidity = dht_device.humidity

            if temperature is not None and humidity is not None:
                print(f"Suhu: {temperature}°C  |  Kelembaban: {humidity}%")
            else:
                print("Gagal membaca data dari sensor.")
            
        except RuntimeError as e:
            print(f"Runtime error: {e}")
        
        time.sleep(2)

except KeyboardInterrupt:
    print("Pengujian dihentikan oleh pengguna.")
finally:
    dht_device.exit()
    print("Sensor dimatikan.")
