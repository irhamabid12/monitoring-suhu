import binascii

# mac1 = "0a:2a:aa:aa:a9:a6"
# hash1 = binascii.crc32(mac1.encode())

# # Untuk hasil unsigned 32-bit (seperti PHP)
# hash1_unsigned = hash1 & 0xffffffff

# print(hash1_unsigned)
serial = None
try:
    with open('/proc/cpuinfo', 'r') as f:
        for line in f:
            if line.startswith('Serial'):
                serial = line.strip().split(":")[1].strip()
except:
    serial = None

device_id = binascii.crc32(serial.encode()) & 0xffffffff
print(str(device_id))
