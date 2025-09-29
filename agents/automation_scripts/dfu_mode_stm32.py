#!/usr/bin/env python3
"""
STM32 DFU Mode Automation Script

Puts all detected STM32 devices into DFU (Device Firmware Update) mode
for programming with dfu-util or STM32CubeProgrammer.
"""

import sys
import time
import json
import argparse
import subprocess
from pathlib import Path

# Add parent directory to path to import hub_control
sys.path.append(str(Path(__file__).parent.parent))

from hub_control import HubController, load_config


def main():
    parser = argparse.ArgumentParser(description="Put STM32 devices in DFU mode")
    parser.add_argument("--ports", help="Specific ports (e.g., 1,2,5-8)")
    parser.add_argument("--group", help="Port group to use")
    parser.add_argument("--list-devices", action="store_true",
                       help="List DFU devices after entering mode")
    parser.add_argument("--verify", action="store_true",
                       help="Verify DFU mode entry")
    parser.add_argument("--config", default="../hub_config.yaml")

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Create hub controller
    hub = HubController(config=config)

    if not hub.connect():
        print("❌ Failed to connect to USBFlashHub")
        return 1

    try:
        # Find STM32 devices
        stm32_devices = find_stm32_devices(hub, args)

        if not stm32_devices:
            print("❌ No STM32 devices found")
            return 1

        print(f"🔍 Found {len(stm32_devices)} STM32 devices:")
        for device, port in stm32_devices:
            print(f"   Port {port}: {device.device_type} ({device.serial_number})")

        # Enter DFU mode for each device
        print(f"\n🔄 Entering DFU mode...")

        success_count = 0
        for device, port in stm32_devices:
            print(f"   Port {port}: ", end="")

            if enter_dfu_mode(hub, port, device.device_type):
                print("✅ SUCCESS")
                success_count += 1
            else:
                print("❌ FAILED")

        print(f"\n📊 Results: {success_count}/{len(stm32_devices)} devices in DFU mode")

        # Verify DFU devices if requested
        if args.verify or args.list_devices:
            time.sleep(2.0)  # Wait for USB re-enumeration
            print(f"\n🔍 Checking DFU devices...")
            list_dfu_devices()

        return 0 if success_count > 0 else 1

    except KeyboardInterrupt:
        print("\n⚠️  Operation interrupted")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        hub.disconnect()


def find_stm32_devices(hub, args):
    """Find STM32 devices based on criteria"""
    stm32_devices = []

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

    # Check each port for STM32 devices
    for port in target_ports:
        device = hub.device_db.get_device_by_port(port)
        if device and "STM32" in device.device_type.upper():
            stm32_devices.append((device, port))

    return stm32_devices


def enter_dfu_mode(hub, port, device_type):
    """Enter DFU mode for STM32 device"""
    try:
        # STM32 DFU sequence: BOOT0 high, then reset
        # BOOT0 high selects system memory (DFU bootloader)

        # Set BOOT0 pin high (connected to boot pin on hub)
        hub.set_boot_pin(True)
        time.sleep(0.1)

        # Reset the device to enter DFU mode
        hub.pulse_reset(100)

        # Keep BOOT0 high for a moment
        time.sleep(0.5)

        # Note: BOOT0 stays high to maintain DFU mode
        # It will be released when device is power cycled

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def list_dfu_devices():
    """List available DFU devices using dfu-util"""
    try:
        result = subprocess.run(
            ["dfu-util", "-l"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            dfu_devices = [line for line in lines if 'DFU' in line or '0483:df11' in line]

            if dfu_devices:
                print(f"   Found {len(dfu_devices)} DFU devices:")
                for device in dfu_devices:
                    print(f"     {device}")
            else:
                print("   No DFU devices detected")
        else:
            print(f"   dfu-util error: {result.stderr}")

    except FileNotFoundError:
        print("   ⚠️  dfu-util not found - install with: sudo apt install dfu-util")
    except subprocess.TimeoutExpired:
        print("   ⚠️  dfu-util timeout")
    except Exception as e:
        print(f"   ❌ Error listing DFU devices: {e}")


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