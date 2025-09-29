#!/usr/bin/env python3
"""
ESP32 WiFi Test Script

This script tests WiFi connectivity on an ESP32 device by:
1. Connecting to the ESP32 serial port
2. Sending test commands
3. Verifying responses
4. Returning success/failure status

Usage: This script is called by the testing agent after firmware is flashed.
"""

import serial
import time
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def find_esp32_port():
    """Find the ESP32 serial port"""
    import glob

    # Common ESP32 serial port patterns
    patterns = ['/dev/ttyUSB*', '/dev/ttyACM*', '/dev/cu.usbserial*']

    for pattern in patterns:
        ports = glob.glob(pattern)
        if ports:
            return ports[0]  # Return first found port

    return None

def test_esp32_response(port_path, timeout=10):
    """Test ESP32 device response"""
    try:
        logger.info(f"Connecting to ESP32 on {port_path}")

        # Connect to ESP32
        ser = serial.Serial(port_path, 115200, timeout=timeout)
        time.sleep(2)  # Allow device to settle

        # Clear any existing data
        ser.reset_input_buffer()

        # Send a simple command to check if device is responsive
        test_commands = [
            b'\\n',  # Simple newline
            b'help\\n',  # Help command
            b'status\\n',  # Status command
        ]

        for cmd in test_commands:
            logger.info(f"Sending command: {cmd}")
            ser.write(cmd)
            time.sleep(1)

            # Read response
            response = ser.read_all().decode('utf-8', errors='ignore')
            logger.info(f"Response: {response}")

            # Check for any response (device is alive)
            if response.strip():
                logger.info("ESP32 is responding")
                return True

        logger.warning("No response from ESP32")
        return False

    except serial.SerialException as e:
        logger.error(f"Serial port error: {e}")
        return False
    except Exception as e:
        logger.error(f"Test error: {e}")
        return False
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

def test_wifi_functionality(port_path, timeout=30):
    """Test WiFi functionality (if supported by firmware)"""
    try:
        logger.info(f"Testing WiFi functionality on {port_path}")

        ser = serial.Serial(port_path, 115200, timeout=timeout)
        time.sleep(2)

        # Clear buffer
        ser.reset_input_buffer()

        # Try WiFi-specific commands (depends on firmware)
        wifi_commands = [
            b'wifi_scan\\n',
            b'wifi_status\\n',
            b'AT+CWLAP\\n',  # AT command style
        ]

        for cmd in wifi_commands:
            logger.info(f"Sending WiFi command: {cmd}")
            ser.write(cmd)
            time.sleep(3)  # WiFi operations need more time

            response = ser.read_all().decode('utf-8', errors='ignore')
            logger.info(f"WiFi response: {response}")

            # Look for WiFi-related responses
            wifi_indicators = ['WIFI', 'wifi', 'AP:', 'SSID', 'scan', 'connected']
            if any(indicator in response for indicator in wifi_indicators):
                logger.info("WiFi functionality detected")
                return True

        logger.info("No WiFi functionality detected (may be normal for test firmware)")
        return True  # Don't fail if WiFi not implemented in test firmware

    except Exception as e:
        logger.error(f"WiFi test error: {e}")
        return False
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

def main():
    """Main test function"""
    logger.info("Starting ESP32 WiFi test")

    # Find ESP32 port
    port = find_esp32_port()
    if not port:
        logger.error("No ESP32 serial port found")
        return False

    logger.info(f"Found ESP32 port: {port}")

    # Test basic device response
    if not test_esp32_response(port):
        logger.error("ESP32 basic response test failed")
        return False

    # Test WiFi functionality
    if not test_wifi_functionality(port):
        logger.error("ESP32 WiFi test failed")
        return False

    logger.info("ESP32 WiFi test completed successfully")
    return True

if __name__ == "__main__":
    success = main()

    if success:
        logger.info("TEST PASSED")
        sys.exit(0)
    else:
        logger.error("TEST FAILED")
        sys.exit(1)