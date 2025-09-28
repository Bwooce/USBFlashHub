#!/usr/bin/env python3
"""
Upload data folder to ESP32 LittleFS filesystem
Usage: python3 upload_data.py [port]
"""

import os
import sys
import subprocess
import tempfile
import shutil

# Configuration
BOARD = "esp32:esp32:esp32s3"  # Change this to match your board
UPLOAD_SPEED = "921600"
PARTITION_SCHEME = "default"  # or "minimal" for more space

def find_mklittlefs():
    """Find the mklittlefs tool"""
    # Common locations
    paths = [
        os.path.expanduser("~/.arduino15/packages/esp32/tools/mklittlefs/"),
        "/usr/local/bin/",
        "/usr/bin/",
    ]

    for path in paths:
        for root, dirs, files in os.walk(path):
            if "mklittlefs" in files:
                return os.path.join(root, "mklittlefs")
    return None

def create_littlefs_image(data_dir, image_file, size="1441792"):
    """Create a LittleFS image from data directory"""
    mklittlefs = find_mklittlefs()
    if not mklittlefs:
        print("Error: mklittlefs tool not found!")
        print("Install ESP32 board package in Arduino IDE first")
        return False

    cmd = [
        mklittlefs,
        "-c", data_dir,
        "-s", size,
        image_file
    ]

    print(f"Creating LittleFS image from {data_dir}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False

    print("LittleFS image created successfully")
    return True

def upload_image(image_file, port):
    """Upload the LittleFS image to ESP32"""
    # Find esptool
    esptool_paths = [
        os.path.expanduser("~/.arduino15/packages/esp32/tools/esptool_py/"),
        "/usr/local/bin/",
        "/usr/bin/",
    ]

    esptool = None
    for path in esptool_paths:
        for root, dirs, files in os.walk(path):
            if "esptool.py" in files or "esptool" in files:
                esptool = os.path.join(root, "esptool.py" if "esptool.py" in files else "esptool")
                break

    if not esptool:
        print("Error: esptool not found!")
        return False

    # Upload command for ESP32-S3
    # LittleFS partition typically starts at 0x290000 for 4MB flash
    # Check if esptool is binary or python script
    if esptool.endswith(".py"):
        cmd = ["python3", esptool]
    else:
        cmd = [esptool]

    cmd.extend([
        "--chip", "esp32s3",
        "--port", port,
        "--baud", UPLOAD_SPEED,
        "write_flash",
        "0x290000",  # LittleFS partition offset (adjust if needed)
        image_file
    ])

    print(f"Uploading to {port}...")
    print(" ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode == 0

def main():
    # Check if data directory exists
    if not os.path.exists("data"):
        print("Error: 'data' directory not found!")
        print("Create a 'data' directory and put index.html in it")
        return 1

    # Get port from arguments or use default
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"

    # Create temporary image file
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        image_file = tmp.name

    try:
        # Create LittleFS image
        if not create_littlefs_image("data", image_file):
            return 1

        # Upload to ESP32
        if not upload_image(image_file, port):
            print("Upload failed!")
            return 1

        print("Upload successful!")
        return 0

    finally:
        # Clean up
        if os.path.exists(image_file):
            os.remove(image_file)

if __name__ == "__main__":
    sys.exit(main())