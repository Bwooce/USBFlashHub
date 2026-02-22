import serial
import time
import sys
import os

port = '/dev/ttyACM0'
baud = 115200

def wait_for_port(port_path, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(port_path):
            return True
        time.sleep(0.1)
    return False

try:
    s = serial.Serial(port, baud, timeout=0.1)
    print(f"Opening {port}...")
    time.sleep(1)
    
    print("Sending reboot command...")
    s.write(b'{"cmd":"reboot"}\n')
    s.close()
    
    print("Waiting for device to reconnect...")
    time.sleep(1)
    if wait_for_port(port):
        print("Device reconnected. Capturing output...")
        time.sleep(0.5) # Wait for CDC to fully init
        s = serial.Serial(port, baud, timeout=0.1)
        start_time = time.time()
        while time.time() - start_time < 5:
            line = s.readline()
            if line:
                print(line.decode('utf-8', 'ignore').strip())
        s.close()
    else:
        print("Timeout waiting for device.")
        
except Exception as e:
    print(f"Error: {e}")
