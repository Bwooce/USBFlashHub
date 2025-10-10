#!/usr/bin/env python3
"""
Monitor serial output for watchdog timeout debugging.
Logs all output and highlights warnings about loop blocking.
"""
import serial
import time
import sys
from datetime import datetime

def monitor_serial(port='/dev/ttyACM0', baudrate=115200):
    """Monitor serial output with timestamp logging."""
    print(f"Connecting to {port} at {baudrate} baud...")
    print("Watching for watchdog-related messages...")
    print("=" * 70)
    
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)  # Wait for connection
        
        while True:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    
                    # Highlight important messages
                    if any(kw in line.lower() for kw in ['watchdog', 'wdt', 'blocked', 'warning', 'error', 'panic']):
                        print(f"\033[1;31m[{timestamp}] {line}\033[0m")  # Red bold
                    elif 'health:' in line.lower():
                        print(f"\033[1;32m[{timestamp}] {line}\033[0m")  # Green bold
                    else:
                        print(f"[{timestamp}] {line}")
                    
                    sys.stdout.flush()
                    
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == '__main__':
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'
    monitor_serial(port)
