#!/usr/bin/env python3
"""
Turn on all detected USB ports with LEDs.
Automatically detects the actual number of connected hubs/ports.
"""

import websocket
import json
import time
import argparse


def detect_and_activate_ports(host="usbhub.local", power="500mA", with_leds=True):
    """Detect connected hubs/ports and turn them on with LEDs."""

    try:
        # Connect to hub
        ws = websocket.WebSocket()
        ws.connect(f'ws://{host}:81')
        print(f'Connected to USBFlashHub at {host}')

        # Request status to detect actual connected hubs
        print('Detecting connected hubs...')
        cmd = {'cmd': 'status'}
        ws.send(json.dumps(cmd))

        # Wait for responses (first is connection confirm, second is actual status)
        ws.settimeout(1.0)

        # Skip the connection confirmation
        try:
            ws.recv()  # Discard "connected" message
        except:
            pass

        # Get the actual status
        try:
            response = ws.recv()
            status = json.loads(response)
        except Exception as e:
            print(f'Could not get status: {e}')
            # Fallback to trying all ports
            status = None

        active_hubs = []
        active_ports = []

        if status and 'hubs' in status:
            # Parse the actual connected hubs from status
            for hub in status['hubs']:
                hub_num = hub['num']
                active_hubs.append(hub_num)

                # Get the ports for this hub
                if 'ports' in hub:
                    for port in hub['ports']:
                        port_num = port['num']
                        # Adjust for absolute port numbering
                        absolute_port = (hub_num - 1) * 4 + port_num
                        active_ports.append(absolute_port)
                else:
                    # If no port details, assume all 4 ports
                    for i in range(4):
                        active_ports.append((hub_num - 1) * 4 + i + 1)

                hub_start = (hub_num - 1) * 4 + 1
                hub_end = hub_num * 4
                print(f'  Hub {hub_num} (0x{hub["addr"]:02X}): Ports {hub_start}-{hub_end} ✓')

        else:
            # Fallback: try all possible ports
            print('Could not detect hubs from status, trying all possible ports...')
            active_hubs = list(range(1, 9))
            active_ports = list(range(1, 33))

        print(f'\nDetected {len(active_hubs)} hub(s) with {len(active_ports)} total port(s)')

        # Turn on all detected ports
        print(f'\nTurning on all ports at {power}...')
        for port in active_ports:
            cmd = {'cmd': 'port', 'port': port, 'power': power}
            ws.send(json.dumps(cmd))
            print(f'  Port {port}: ON ({power})')
            time.sleep(0.02)  # Small delay to avoid overwhelming

        # Turn on LEDs for all active hubs
        if with_leds:
            print('\nTurning on hub LEDs...')
            for hub in active_hubs:
                cmd = {'cmd': 'hub', 'hub': hub, 'led': True}
                ws.send(json.dumps(cmd))
                print(f'  Hub {hub} LED: ON')
                time.sleep(0.02)

        ws.close()

        print(f'\n✓ Successfully activated {len(active_ports)} ports')
        if with_leds:
            print(f'✓ LEDs enabled on {len(active_hubs)} hubs')

        return active_ports, active_hubs

    except Exception as e:
        print(f'Error: {e}')
        print('\nTroubleshooting:')
        print('1. Check if hub is powered on')
        print('2. Verify network connection')
        print('3. Try using IP address instead of mDNS:')
        print('   python3 turn_on_all_ports.py --host 192.168.1.100')
        return [], []


def main():
    parser = argparse.ArgumentParser(description='Turn on all USBFlashHub ports')
    parser.add_argument('--host', default='usbhub.local',
                       help='Hub hostname or IP (default: usbhub.local)')
    parser.add_argument('--power', choices=['off', '100mA', '500mA'],
                       default='500mA', help='Power level (default: 500mA)')
    parser.add_argument('--no-leds', action='store_true',
                       help='Do not turn on LEDs')
    parser.add_argument('--ports', type=str,
                       help='Specific ports to turn on (e.g., "1,2,3" or "1-4")')

    args = parser.parse_args()

    if args.ports:
        # Parse specific ports
        ports = []
        for part in args.ports.split(','):
            if '-' in part:
                start, end = map(int, part.split('-'))
                ports.extend(range(start, end + 1))
            else:
                ports.append(int(part))

        print(f'Turning on specific ports: {ports}')
        try:
            ws = websocket.WebSocket()
            ws.connect(f'ws://{args.host}:81')

            for port in ports:
                cmd = {'cmd': 'port', 'port': port, 'power': args.power}
                ws.send(json.dumps(cmd))
                print(f'  Port {port}: {args.power}')

            if not args.no_leds:
                # Determine which hubs these ports belong to
                hubs = set((p - 1) // 4 + 1 for p in ports)
                for hub in hubs:
                    cmd = {'cmd': 'hub', 'hub': hub, 'led': True}
                    ws.send(json.dumps(cmd))
                    print(f'  Hub {hub} LED: ON')

            ws.close()
            print('✓ Done')

        except Exception as e:
            print(f'Error: {e}')
    else:
        # Turn on all detected ports
        detect_and_activate_ports(
            host=args.host,
            power=args.power,
            with_leds=not args.no_leds
        )


if __name__ == '__main__':
    main()