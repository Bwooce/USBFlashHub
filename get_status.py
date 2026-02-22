#!/usr/bin/env python3
import serial
import json
import time

port = '/dev/ttyACM0'
ser = serial.Serial(port, 115200, timeout=2)
time.sleep(0.3)

# Clear any pending data
ser.reset_input_buffer()

# Send status command
print("Sending status command...")
ser.write(b'{"cmd":"status"}\n')
time.sleep(0.5)

# Read response
print("\nResponse:")
print("=" * 70)
found_json = False
while ser.in_waiting:
    line = ser.readline().decode('utf-8', errors='ignore').strip()
    if line:
        if line.startswith('{'):
            try:
                data = json.loads(line)
                print(json.dumps(data, indent=2))
                found_json = True
            except:
                print(line)
        else:
            print(line)

if not found_json:
    print("No JSON response received")

ser.close()
