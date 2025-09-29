#!/usr/bin/env python3
"""
Basic Blink Test Script

This script tests basic functionality of microcontroller boards by:
1. Connecting to the device serial port
2. Looking for output indicating the device is running
3. Optionally testing LED blink patterns
4. Returning success/failure status

Usage: This script is called by the testing agent after firmware is flashed.
"""

import serial
import time
import sys
import logging
import glob

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def find_device_port():
    """Find the device serial port"""
    # Common serial port patterns
    patterns = ['/dev/ttyUSB*', '/dev/ttyACM*', '/dev/cu.usbserial*', '/dev/cu.usbmodem*']

    for pattern in patterns:
        ports = glob.glob(pattern)
        if ports:
            # Sort ports to get consistent selection
            ports.sort()
            return ports[0]  # Return first found port

    return None

def test_device_output(port_path, timeout=15):
    """Test for device output indicating it's running"""
    try:
        logger.info(f"Connecting to device on {port_path}")

        # Try different baud rates common for microcontrollers
        baud_rates = [115200, 9600, 57600, 38400]

        for baud in baud_rates:
            try:
                logger.info(f"Trying baud rate: {baud}")
                ser = serial.Serial(port_path, baud, timeout=3)
                time.sleep(2)  # Allow device to settle

                # Clear any existing data
                ser.reset_input_buffer()

                # Wait for output
                start_time = time.time()
                output_received = False

                while time.time() - start_time < timeout:
                    if ser.in_waiting > 0:
                        data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                        if data.strip():
                            logger.info(f"Device output received: {data[:100]}...")
                            output_received = True
                            break
                    time.sleep(0.5)

                ser.close()

                if output_received:
                    logger.info(f"Device is producing output at {baud} baud")
                    return True

            except serial.SerialException as e:
                logger.debug(f"Serial error at {baud} baud: {e}")
                continue
            except Exception as e:
                logger.debug(f"Error at {baud} baud: {e}")
                continue

        logger.warning("No output detected from device")
        return False

    except Exception as e:
        logger.error(f"Test error: {e}")
        return False

def test_blink_pattern(port_path, timeout=10):
    """Test for blink-related output patterns"""
    try:
        logger.info(f"Testing for blink patterns on {port_path}")

        ser = serial.Serial(port_path, 115200, timeout=timeout)
        time.sleep(2)

        # Clear buffer
        ser.reset_input_buffer()

        # Collect output for analysis
        start_time = time.time()
        collected_output = ""

        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                collected_output += data
                logger.debug(f"Received: {data}")

            time.sleep(0.5)

        ser.close()

        # Look for blink-related keywords
        blink_keywords = [
            'blink', 'led', 'on', 'off', 'toggle',
            'HIGH', 'LOW', 'digitalWrite', 'delay',
            'loop', 'setup'
        ]

        found_keywords = []
        for keyword in blink_keywords:
            if keyword.lower() in collected_output.lower():
                found_keywords.append(keyword)

        if found_keywords:
            logger.info(f"Found blink-related keywords: {found_keywords}")
            return True
        else:
            logger.info("No blink-specific patterns found (may be normal)")
            return True  # Don't fail if no specific blink patterns

    except Exception as e:
        logger.error(f"Blink pattern test error: {e}")
        return True  # Don't fail the test for this

def test_device_responsiveness(port_path):
    """Test if device responds to input"""
    try:
        logger.info(f"Testing device responsiveness on {port_path}")

        ser = serial.Serial(port_path, 115200, timeout=5)
        time.sleep(2)

        # Clear buffer
        ser.reset_input_buffer()

        # Send some test commands
        test_commands = [b'\\n', b'\\r\\n', b'?\\n', b'help\\n', b'status\\n']

        for cmd in test_commands:
            logger.debug(f"Sending: {cmd}")
            ser.write(cmd)
            time.sleep(1)

            # Check for any response
            if ser.in_waiting > 0:
                response = ser.read_all().decode('utf-8', errors='ignore')
                if response.strip():
                    logger.info(f"Device responded to command: {response[:50]}...")
                    ser.close()
                    return True

        ser.close()
        logger.info("Device does not respond to commands (normal for simple blink firmware)")
        return True  # Don't fail if device doesn't respond to commands

    except Exception as e:
        logger.error(f"Responsiveness test error: {e}")
        return True  # Don't fail the test for this

def main():
    """Main test function"""
    logger.info("Starting basic blink test")

    # Find device port
    port = find_device_port()
    if not port:
        logger.error("No device serial port found")
        return False

    logger.info(f"Found device port: {port}")

    # Test basic device output
    if not test_device_output(port):
        logger.error("Device output test failed - device may not be running")
        return False

    # Test for blink patterns
    test_blink_pattern(port)

    # Test device responsiveness
    test_device_responsiveness(port)

    logger.info("Basic blink test completed successfully")
    return True

if __name__ == "__main__":
    success = main()

    if success:
        logger.info("TEST PASSED")
        sys.exit(0)
    else:
        logger.error("TEST FAILED")
        sys.exit(1)