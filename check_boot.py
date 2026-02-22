#!/usr/bin/env python3
import serial
import time
import sys

port = '/dev/ttyACM0'
print(f"Opening {port}...")

try:
    ser = serial.Serial(port, 115200, timeout=0.5)
    time.sleep(0.5)

    print("Sending Ctrl+C to break any running loop...")
    ser.write(b'\x03')
    time.sleep(0.1)

    print("\nReading output for 5 seconds...")
    print("=" * 70)

    start = time.time()
    while time.time() - start < 5:
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            try:
                print(data.decode('utf-8', errors='replace'), end='', flush=True)
            except:
                print(data)

    print("\n" + "=" * 70)
    print("Done. If no output, device may be stuck in early boot or bootloop.")

except Exception as e:
    print(f"Error: {e}")
finally:
    if 'ser' in locals():
        ser.close()
