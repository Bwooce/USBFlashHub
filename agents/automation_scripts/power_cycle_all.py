#!/usr/bin/env python3
"""
Power Cycle All Ports Automation Script

Safely power cycles all active ports with configurable timing.
"""

import sys
import time
import json
import argparse
from pathlib import Path

# Add parent directory to path to import hub_control
sys.path.append(str(Path(__file__).parent.parent))

from hub_control import HubController, load_config


def main():
    parser = argparse.ArgumentParser(description="Power cycle all ports")
    parser.add_argument("--off-time", type=float, default=2.0,
                       help="Time to keep ports off (seconds)")
    parser.add_argument("--delay", type=float, default=0.5,
                       help="Delay between port operations (seconds)")
    parser.add_argument("--ports", help="Specific ports to cycle (e.g., 1,2,5-8)")
    parser.add_argument("--group", help="Port group to cycle")
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
        # Determine which ports to cycle
        ports_to_cycle = []

        if args.ports:
            # Parse port specification
            ports_to_cycle = parse_port_list(args.ports)
        elif args.group:
            # Use port group from config
            group_config = config.get('port_groups', {}).get(args.group)
            if not group_config:
                print(f"❌ Unknown port group: {args.group}")
                return 1
            ports_to_cycle = group_config['ports']
        else:
            # All ports 1-32
            ports_to_cycle = list(range(1, 33))

        print(f"🔄 Power cycling ports: {ports_to_cycle}")
        print(f"   Off time: {args.off_time}s")
        print(f"   Port delay: {args.delay}s")

        # Phase 1: Turn off all specified ports
        print("\n📴 Turning off ports...")
        for port in ports_to_cycle:
            print(f"   Port {port}: OFF")
            hub.power_port(port, "off")
            time.sleep(args.delay)

        # Phase 2: Wait
        print(f"\n⏳ Waiting {args.off_time} seconds...")
        time.sleep(args.off_time)

        # Phase 3: Turn ports back on
        print("\n🔌 Turning on ports...")
        for port in ports_to_cycle:
            print(f"   Port {port}: 500mA")
            hub.power_port(port, "500mA")
            time.sleep(args.delay)

        print("\n✅ Power cycle completed successfully")

        # Show status
        print("\n📊 Current status:")
        for port in ports_to_cycle:
            status = hub.get_port_status(port)
            if status:
                print(f"   Port {port}: {status.power_state}")

        return 0

    except KeyboardInterrupt:
        print("\n⚠️  Operation interrupted")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        hub.disconnect()


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

    return sorted(set(ports))  # Remove duplicates and sort


if __name__ == "__main__":
    sys.exit(main())