#!/usr/bin/env python3
"""
Device Inventory Automation Script

Scans all ports, identifies connected devices, and updates the device database.
Useful for initial setup or periodic inventory updates.
"""

import sys
import time
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import hub_control
sys.path.append(str(Path(__file__).parent.parent))

from hub_control import HubController, load_config, DeviceRecord


def main():
    parser = argparse.ArgumentParser(description="Scan and inventory connected devices")
    parser.add_argument("--ports", help="Specific ports to scan (e.g., 1,2,5-8)")
    parser.add_argument("--group", help="Port group to scan")
    parser.add_argument("--power-on", action="store_true",
                       help="Power on ports before scanning")
    parser.add_argument("--power-level", default="high",
                       help="Power level for scanning (off/low/high)")
    parser.add_argument("--export", help="Export results to file (JSON/CSV)")
    parser.add_argument("--update-db", action="store_true",
                       help="Update device database")
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
        # Determine ports to scan
        target_ports = get_target_ports(args, config)

        print(f"🔍 Scanning ports: {target_ports}")

        # Power on ports if requested
        if args.power_on:
            print(f"🔌 Powering on ports ({args.power_level})...")
            for port in target_ports:
                hub.power_port(port, args.power_level)
                time.sleep(0.2)

            # Wait for devices to enumerate
            print("⏳ Waiting for device enumeration...")
            time.sleep(3.0)

        # Scan for devices
        print(f"\n📱 Scanning for devices...")
        inventory = scan_devices(target_ports)

        # Update database if requested
        if args.update_db:
            print(f"💾 Updating device database...")
            update_device_database(hub, inventory)

        # Display results
        display_inventory(inventory)

        # Export results if requested
        if args.export:
            export_inventory(inventory, args.export)

        return 0

    except KeyboardInterrupt:
        print("\n⚠️  Operation interrupted")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        hub.disconnect()


def get_target_ports(args, config):
    """Determine which ports to scan"""
    if args.ports:
        return parse_port_list(args.ports)
    elif args.group:
        group_config = config.get('port_groups', {}).get(args.group)
        if group_config:
            return group_config['ports']

    return list(range(1, 33))  # All ports


def scan_devices(ports):
    """Scan USB devices and correlate with ports"""
    inventory = {}

    print("🔍 Scanning USB devices...")

    # Get current USB device list
    usb_devices = get_usb_devices()

    print(f"   Found {len(usb_devices)} USB devices system-wide")

    # For each port, try to identify connected device
    for port in ports:
        print(f"   Port {port:2d}: ", end="")

        # In a real implementation, this would correlate USB topology
        # with physical ports. For now, we'll simulate this process.
        device = identify_device_on_port(port, usb_devices)

        if device:
            inventory[port] = device
            print(f"{device['device_type']} ({device['serial']})")
        else:
            inventory[port] = None
            print("No device detected")

    return inventory


def get_usb_devices():
    """Get list of USB devices from system"""
    devices = []

    try:
        # Use lsusb to get device list
        result = subprocess.run(
            ["lsusb", "-v"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            devices = parse_lsusb_output(result.stdout)

    except FileNotFoundError:
        print("   ⚠️  lsusb not found - using alternative method")
        devices = get_usb_devices_alternative()
    except subprocess.TimeoutExpired:
        print("   ⚠️  lsusb timeout")
    except Exception as e:
        print(f"   ❌ Error scanning USB: {e}")

    return devices


def get_usb_devices_alternative():
    """Alternative method to get USB devices"""
    devices = []

    try:
        # Read from /sys/bus/usb/devices
        usb_path = Path("/sys/bus/usb/devices")
        if usb_path.exists():
            for device_dir in usb_path.glob("*-*"):
                if device_dir.is_dir():
                    device_info = parse_sysfs_device(device_dir)
                    if device_info:
                        devices.append(device_info)

    except Exception as e:
        print(f"   ❌ Alternative USB scan error: {e}")

    return devices


def parse_lsusb_output(output):
    """Parse lsusb -v output"""
    devices = []
    current_device = {}

    for line in output.split('\n'):
        line = line.strip()

        if line.startswith('Bus ') and 'Device ' in line:
            # New device
            if current_device:
                devices.append(current_device)
            current_device = {}

            # Parse bus/device line: "Bus 001 Device 005: ID 303a:1001 Espressif ESP32-S2"
            parts = line.split()
            if len(parts) >= 6:
                vid_pid = parts[5].split(':')
                if len(vid_pid) == 2:
                    current_device['vendor_id'] = vid_pid[0]
                    current_device['product_id'] = vid_pid[1]

        elif line.startswith('idVendor'):
            # Extract vendor info
            parts = line.split(None, 2)
            if len(parts) >= 3:
                current_device['vendor_id'] = parts[1]
                current_device['manufacturer'] = parts[2]

        elif line.startswith('idProduct'):
            # Extract product info
            parts = line.split(None, 2)
            if len(parts) >= 3:
                current_device['product_id'] = parts[1]
                current_device['product_name'] = parts[2]

        elif line.startswith('iSerial') and 'Serial' in line:
            # Extract serial number
            parts = line.split()
            if len(parts) >= 3:
                current_device['serial'] = ' '.join(parts[2:])

    # Add last device
    if current_device:
        devices.append(current_device)

    return devices


def parse_sysfs_device(device_dir):
    """Parse device info from sysfs"""
    device_info = {}

    try:
        # Read basic device info
        vid_file = device_dir / "idVendor"
        pid_file = device_dir / "idProduct"
        serial_file = device_dir / "serial"
        manufacturer_file = device_dir / "manufacturer"
        product_file = device_dir / "product"

        if vid_file.exists():
            device_info['vendor_id'] = vid_file.read_text().strip()

        if pid_file.exists():
            device_info['product_id'] = pid_file.read_text().strip()

        if serial_file.exists():
            device_info['serial'] = serial_file.read_text().strip()

        if manufacturer_file.exists():
            device_info['manufacturer'] = manufacturer_file.read_text().strip()

        if product_file.exists():
            device_info['product_name'] = product_file.read_text().strip()

        if 'vendor_id' in device_info and 'product_id' in device_info:
            return device_info

    except Exception:
        pass

    return None


def identify_device_on_port(port, usb_devices):
    """Identify device connected to specific port"""
    # This is a simplified implementation
    # In reality, would need USB topology mapping

    # Known device type mappings
    device_types = {
        ('303a', '1001'): 'ESP32-S2',
        ('303a', '0002'): 'ESP32-S2',
        ('303a', '1000'): 'ESP32',
        ('303a', '80d4'): 'ESP32-C3',
        ('303a', '4001'): 'ESP32-S3',
        ('0483', 'df11'): 'STM32-DFU',
        ('0483', '5740'): 'STM32',
        ('2341', '0043'): 'Arduino-Uno',
        ('1a86', '7523'): 'CH340-Serial',
        ('0403', '6001'): 'FTDI-Serial',
    }

    # For simulation, just cycle through detected devices
    # Real implementation would map USB tree to physical ports
    if usb_devices and (port - 1) < len(usb_devices):
        device = usb_devices[port - 1]

        vendor_id = device.get('vendor_id', '').lower()
        product_id = device.get('product_id', '').lower()

        device_type = device_types.get((vendor_id, product_id), 'Unknown')

        return {
            'vendor_id': vendor_id,
            'product_id': product_id,
            'device_type': device_type,
            'serial': device.get('serial', 'Unknown'),
            'manufacturer': device.get('manufacturer', 'Unknown'),
            'product_name': device.get('product_name', 'Unknown'),
            'detected_time': datetime.now().isoformat()
        }

    return None


def update_device_database(hub, inventory):
    """Update device database with inventory results"""
    updated_count = 0

    for port, device_info in inventory.items():
        if device_info:
            device_record = DeviceRecord(
                vendor_id=device_info['vendor_id'],
                product_id=device_info['product_id'],
                device_type=device_info['device_type'],
                serial_number=device_info['serial'],
                manufacturer=device_info['manufacturer'],
                product_name=device_info['product_name'],
                port_number=port,
                last_seen=datetime.now()
            )

            try:
                device_id = hub.device_db.add_device(device_record)
                updated_count += 1
                print(f"   Updated device {device_id} on port {port}")

            except Exception as e:
                print(f"   ❌ Failed to update device on port {port}: {e}")

    print(f"✅ Updated {updated_count} devices in database")


def display_inventory(inventory):
    """Display inventory results"""
    print(f"\n📊 Device Inventory Results:")
    print("=" * 80)
    print(f"{'Port':<4} {'Device Type':<15} {'Serial Number':<20} {'Manufacturer':<15}")
    print("-" * 80)

    connected_count = 0
    for port in sorted(inventory.keys()):
        device = inventory[port]

        if device:
            print(f"{port:<4} {device['device_type']:<15} "
                  f"{device['serial'][:19]:<20} {device['manufacturer'][:14]:<15}")
            connected_count += 1
        else:
            print(f"{port:<4} {'No Device':<15} {'-':<20} {'-':<15}")

    print("-" * 80)
    print(f"Total ports scanned: {len(inventory)}")
    print(f"Devices connected: {connected_count}")
    print(f"Empty ports: {len(inventory) - connected_count}")


def export_inventory(inventory, export_file):
    """Export inventory to file"""
    export_path = Path(export_file)

    try:
        if export_path.suffix.lower() == '.json':
            export_json(inventory, export_path)
        elif export_path.suffix.lower() == '.csv':
            export_csv(inventory, export_path)
        else:
            print(f"❌ Unsupported export format: {export_path.suffix}")
            return

        print(f"📄 Exported inventory to {export_path}")

    except Exception as e:
        print(f"❌ Export failed: {e}")


def export_json(inventory, file_path):
    """Export inventory as JSON"""
    export_data = {
        'scan_time': datetime.now().isoformat(),
        'total_ports': len(inventory),
        'connected_devices': sum(1 for d in inventory.values() if d),
        'ports': inventory
    }

    with open(file_path, 'w') as f:
        json.dump(export_data, f, indent=2)


def export_csv(inventory, file_path):
    """Export inventory as CSV"""
    import csv

    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'Port', 'Device_Type', 'Vendor_ID', 'Product_ID',
            'Serial_Number', 'Manufacturer', 'Product_Name'
        ])

        # Data
        for port in sorted(inventory.keys()):
            device = inventory[port]
            if device:
                writer.writerow([
                    port,
                    device['device_type'],
                    device['vendor_id'],
                    device['product_id'],
                    device['serial'],
                    device['manufacturer'],
                    device['product_name']
                ])
            else:
                writer.writerow([port, '', '', '', '', '', ''])


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