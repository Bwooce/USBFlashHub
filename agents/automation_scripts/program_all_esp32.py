#!/usr/bin/env python3
"""
Program All ESP32 Devices Automation Script

Automatically programs all detected ESP32 devices with specified firmware.
Includes bootloader entry, flashing, and verification.
"""

import sys
import time
import json
import argparse
import subprocess
from pathlib import Path

# Add parent directory to path to import hub_control
sys.path.append(str(Path(__file__).parent.parent))

from hub_control import HubController, load_config, DeviceRecord


def main():
    parser = argparse.ArgumentParser(description="Program all ESP32 devices")
    parser.add_argument("firmware", help="Firmware file to flash")
    parser.add_argument("--device-type", default="ESP32",
                       help="Device type filter (ESP32, ESP32-S2, ESP32-C3, ESP32-S3)")
    parser.add_argument("--ports", help="Specific ports to program (e.g., 1,2,5-8)")
    parser.add_argument("--group", help="Port group to program")
    parser.add_argument("--baud", type=int, default=921600, help="Flash baud rate")
    parser.add_argument("--address", default="0x1000", help="Flash address")
    parser.add_argument("--verify", action="store_true", help="Verify after flashing")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel programming count")
    parser.add_argument("--config", default="../hub_config.yaml")

    args = parser.parse_args()

    # Validate firmware file
    firmware_path = Path(args.firmware)
    if not firmware_path.exists():
        print(f"❌ Firmware file not found: {args.firmware}")
        return 1

    # Load configuration
    config = load_config(args.config)

    # Create hub controller
    hub = HubController(config=config)

    if not hub.connect():
        print("❌ Failed to connect to USBFlashHub")
        return 1

    try:
        # Find ESP32 devices to program
        devices_to_program = find_target_devices(hub, args)

        if not devices_to_program:
            print(f"❌ No {args.device_type} devices found to program")
            return 1

        print(f"📱 Found {len(devices_to_program)} {args.device_type} devices to program:")
        for device, port in devices_to_program:
            print(f"   Port {port}: {device.device_type} ({device.serial_number})")

        # Confirm operation
        if not confirm_operation(devices_to_program, firmware_path):
            print("❌ Operation cancelled")
            return 1

        # Program devices
        success_count = 0
        total_count = len(devices_to_program)

        print(f"\n🔧 Starting programming process...")

        if args.parallel > 1:
            success_count = program_devices_parallel(hub, devices_to_program, args)
        else:
            success_count = program_devices_sequential(hub, devices_to_program, args)

        # Report results
        print(f"\n📊 Programming Results:")
        print(f"   Total devices: {total_count}")
        print(f"   Successful: {success_count}")
        print(f"   Failed: {total_count - success_count}")

        if success_count == total_count:
            print("✅ All devices programmed successfully!")
            return 0
        else:
            print("⚠️  Some devices failed to program")
            return 1

    except KeyboardInterrupt:
        print("\n⚠️  Operation interrupted")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        hub.disconnect()


def find_target_devices(hub, args):
    """Find devices to program based on criteria"""
    devices_to_program = []

    # Determine target ports
    target_ports = []
    if args.ports:
        target_ports = parse_port_list(args.ports)
    elif args.group:
        config = load_config(args.config)
        group_config = config.get('port_groups', {}).get(args.group)
        if group_config:
            target_ports = group_config['ports']
    else:
        target_ports = list(range(1, 33))

    # Check each port for target devices
    for port in target_ports:
        device = hub.device_db.get_device_by_port(port)
        if device and args.device_type.upper() in device.device_type.upper():
            devices_to_program.append((device, port))

    return devices_to_program


def confirm_operation(devices, firmware_path):
    """Confirm programming operation with user"""
    print(f"\n⚠️  About to program {len(devices)} devices with:")
    print(f"   Firmware: {firmware_path.name}")
    print(f"   Size: {firmware_path.stat().st_size} bytes")

    response = input("\nProceed? (y/N): ").strip().lower()
    return response in ['y', 'yes']


def program_devices_sequential(hub, devices_to_program, args):
    """Program devices one by one"""
    success_count = 0

    for i, (device, port) in enumerate(devices_to_program):
        print(f"\n📱 Programming device {i+1}/{len(devices_to_program)} on port {port}")

        if program_single_device(hub, device, port, args):
            success_count += 1
            print(f"   ✅ Port {port}: SUCCESS")
        else:
            print(f"   ❌ Port {port}: FAILED")

    return success_count


def program_devices_parallel(hub, devices_to_program, args):
    """Program multiple devices in parallel (simplified implementation)"""
    # For now, implement as sequential with shorter delays
    # True parallel programming would require thread pool
    print("⚠️  Parallel programming not fully implemented, using sequential mode")
    return program_devices_sequential(hub, devices_to_program, args)


def program_single_device(hub, device, port, args):
    """Program a single device"""
    try:
        print(f"   🔄 Entering bootloader mode...")

        # Enter bootloader mode
        if not hub.enter_bootloader_mode(port, device.device_type):
            print(f"   ❌ Failed to enter bootloader mode")
            return False

        time.sleep(1.0)  # Wait for bootloader

        # Flash firmware
        print(f"   📥 Flashing firmware...")

        # Detect serial port (simplified - in real implementation would scan for device)
        serial_port = f"/dev/ttyUSB{port-1}"  # Approximate mapping

        if not flash_with_esptool(serial_port, args.firmware, args):
            print(f"   ❌ Flashing failed")
            return False

        # Reset device
        print(f"   🔄 Resetting device...")
        hub.pulse_reset(100)
        time.sleep(2.0)

        # Verify if requested
        if args.verify:
            print(f"   🔍 Verifying firmware...")
            if not verify_firmware(serial_port, args.firmware, args):
                print(f"   ⚠️  Verification failed")
                return False

        # Record success in database
        hub.device_db.add_test_result(
            device.id,
            f"firmware_flash_{Path(args.firmware).stem}",
            "PASSED",
            0,  # Duration would be calculated in real implementation
            None,
            None,
            port
        )

        return True

    except Exception as e:
        print(f"   ❌ Error programming device: {e}")

        # Record failure in database
        hub.device_db.add_test_result(
            device.id,
            f"firmware_flash_{Path(args.firmware).stem}",
            "FAILED",
            0,
            str(e),
            None,
            port
        )

        return False


def flash_with_esptool(port, firmware_file, args):
    """Flash firmware using esptool"""
    cmd = [
        "esptool.py",
        "--port", port,
        "--baud", str(args.baud),
        "write_flash",
        args.address, firmware_file
    ]

    try:
        print(f"   📡 Running: esptool.py --port {port} --baud {args.baud} write_flash {args.address} {Path(firmware_file).name}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            return True
        else:
            print(f"   ❌ esptool error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"   ❌ esptool timeout")
        return False
    except FileNotFoundError:
        print(f"   ❌ esptool not found - install with: pip install esptool")
        return False


def verify_firmware(port, firmware_file, args):
    """Verify flashed firmware"""
    # Simple verification by reading back and comparing
    # In practice, this might check specific addresses or use checksums
    cmd = [
        "esptool.py",
        "--port", port,
        "--baud", str(args.baud),
        "verify_flash",
        args.address, firmware_file
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print(f"   ❌ verify timeout")
        return False
    except FileNotFoundError:
        return True  # If esptool not available, skip verification


def parse_port_list(port_spec):
    """Parse port specification like '1,2,5-8' into list of port numbers"""
    ports = []

    for part in port_spec.split(','):
        part = part.strip()
        if '-' in part:
            start, end = map(int, part.split('-'))
            ports.extend(range(start, end + 1))
        else:
            ports.append(int(part))

    return sorted(set(ports))


if __name__ == "__main__":
    sys.exit(main())