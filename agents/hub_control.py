#!/usr/bin/env python3
"""
USBFlashHub Control Agent

A comprehensive control and monitoring system for the USBFlashHub that provides:
- Interactive command-line interface for manual hub control
- Device database with SQLite for tracking devices and test history
- Automation scripts for common tasks
- Terminal-based status dashboard
- Optional REST API server
- Integration with testing_agent

Author: USBFlashHub Control System
"""

import asyncio
import json
import logging
import sqlite3
import time
import subprocess
import signal
import sys
import threading
import argparse
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import yaml
import websocket
import cmd
from contextlib import contextmanager
import re
import os

try:
    from rich.console import Console
    from rich.table import Table
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from rich.progress import Progress, TaskID
    from rich.prompt import Prompt, Confirm
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Rich library not available. Install with: pip install rich")

try:
    import flask
    from flask import Flask, jsonify, request
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/bruce/Arduino/USBFlashHub/agents/hub_control.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DeviceRecord:
    """Database record for a tracked device"""
    id: Optional[int] = None
    vendor_id: str = ""
    product_id: str = ""
    device_type: str = ""
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    product_name: Optional[str] = None
    port_number: Optional[int] = None
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    firmware_version: Optional[str] = None
    test_count: int = 0
    last_test_result: Optional[str] = None
    last_test_time: Optional[datetime] = None
    notes: Optional[str] = None


@dataclass
class PortStatus:
    """Status information for a hub port"""
    port_number: int
    power_state: str = "unknown"  # off, low, high, unknown
    device_connected: bool = False
    device_info: Optional[DeviceRecord] = None
    last_activity: Optional[datetime] = None


@dataclass
class HubStatus:
    """Status information for a hub"""
    hub_number: int
    address: int
    connected: bool = False
    ports: List[PortStatus] = field(default_factory=list)
    last_communication: Optional[datetime] = None


class DeviceDatabase:
    """SQLite database for tracking devices and test history"""

    def __init__(self, db_path: str = "/home/bruce/Arduino/USBFlashHub/agents/devices.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(f"{__name__}.DeviceDatabase")
        self._init_database()

    def _init_database(self):
        """Initialize the SQLite database with required tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS devices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        vendor_id TEXT NOT NULL,
                        product_id TEXT NOT NULL,
                        device_type TEXT,
                        serial_number TEXT,
                        manufacturer TEXT,
                        product_name TEXT,
                        port_number INTEGER,
                        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        firmware_version TEXT,
                        test_count INTEGER DEFAULT 0,
                        last_test_result TEXT,
                        last_test_time TIMESTAMP,
                        notes TEXT,
                        UNIQUE(vendor_id, product_id, serial_number)
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS test_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id INTEGER,
                        test_name TEXT NOT NULL,
                        test_result TEXT NOT NULL,
                        test_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        duration_seconds REAL,
                        error_message TEXT,
                        firmware_version TEXT,
                        port_number INTEGER,
                        FOREIGN KEY (device_id) REFERENCES devices (id)
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS port_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        port_number INTEGER NOT NULL,
                        device_id INTEGER,
                        connected_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        disconnected_time TIMESTAMP,
                        duration_seconds REAL,
                        FOREIGN KEY (device_id) REFERENCES devices (id)
                    )
                """)

                conn.commit()
                self.logger.info("Database initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Get a database connection with automatic cleanup"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def add_device(self, device: DeviceRecord) -> int:
        """Add or update a device record, return device ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if device already exists
                cursor.execute("""
                    SELECT id FROM devices
                    WHERE vendor_id = ? AND product_id = ? AND serial_number = ?
                """, (device.vendor_id, device.product_id, device.serial_number))

                existing = cursor.fetchone()

                if existing:
                    # Update existing device
                    device_id = existing['id']
                    cursor.execute("""
                        UPDATE devices SET
                            last_seen = ?, port_number = ?, device_type = ?,
                            manufacturer = ?, product_name = ?
                        WHERE id = ?
                    """, (
                        device.last_seen, device.port_number, device.device_type,
                        device.manufacturer, device.product_name, device_id
                    ))
                else:
                    # Insert new device
                    cursor.execute("""
                        INSERT INTO devices
                        (vendor_id, product_id, device_type, serial_number, manufacturer,
                         product_name, port_number, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        device.vendor_id, device.product_id, device.device_type,
                        device.serial_number, device.manufacturer, device.product_name,
                        device.port_number, device.first_seen, device.last_seen
                    ))
                    device_id = cursor.lastrowid

                conn.commit()
                self.logger.debug(f"Added/updated device {device_id}: {device.device_type}")
                return device_id

        except Exception as e:
            self.logger.error(f"Failed to add device: {e}")
            raise

    def get_device_by_serial(self, serial_number: str) -> Optional[DeviceRecord]:
        """Get device by serial number"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM devices WHERE serial_number = ?", (serial_number,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_device_record(row)
                return None

        except Exception as e:
            self.logger.error(f"Failed to get device by serial: {e}")
            return None

    def get_devices_by_type(self, device_type: str) -> List[DeviceRecord]:
        """Get all devices of a specific type"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM devices WHERE device_type LIKE ? ORDER BY last_seen DESC",
                             (f"%{device_type}%",))
                rows = cursor.fetchall()

                return [self._row_to_device_record(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Failed to get devices by type: {e}")
            return []

    def get_device_by_port(self, port_number: int) -> Optional[DeviceRecord]:
        """Get device currently connected to a port"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM devices
                    WHERE port_number = ?
                    ORDER BY last_seen DESC LIMIT 1
                """, (port_number,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_device_record(row)
                return None

        except Exception as e:
            self.logger.error(f"Failed to get device by port: {e}")
            return None

    def add_test_result(self, device_id: int, test_name: str, result: str,
                       duration: float = 0, error_message: str = None,
                       firmware_version: str = None, port_number: int = None):
        """Add a test result to the database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Add test history record
                cursor.execute("""
                    INSERT INTO test_history
                    (device_id, test_name, test_result, duration_seconds, error_message,
                     firmware_version, port_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (device_id, test_name, result, duration, error_message,
                     firmware_version, port_number))

                # Update device test statistics
                cursor.execute("""
                    UPDATE devices SET
                        test_count = test_count + 1,
                        last_test_result = ?,
                        last_test_time = ?
                    WHERE id = ?
                """, (result, datetime.now(), device_id))

                conn.commit()
                self.logger.debug(f"Added test result for device {device_id}: {test_name} = {result}")

        except Exception as e:
            self.logger.error(f"Failed to add test result: {e}")
            raise

    def get_test_history(self, device_id: Optional[int] = None, limit: int = 100) -> List[Dict]:
        """Get test history, optionally filtered by device"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                if device_id:
                    cursor.execute("""
                        SELECT th.*, d.device_type, d.serial_number
                        FROM test_history th
                        JOIN devices d ON th.device_id = d.id
                        WHERE th.device_id = ?
                        ORDER BY th.test_time DESC LIMIT ?
                    """, (device_id, limit))
                else:
                    cursor.execute("""
                        SELECT th.*, d.device_type, d.serial_number
                        FROM test_history th
                        JOIN devices d ON th.device_id = d.id
                        ORDER BY th.test_time DESC LIMIT ?
                    """, (limit,))

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Failed to get test history: {e}")
            return []

    def _row_to_device_record(self, row: sqlite3.Row) -> DeviceRecord:
        """Convert database row to DeviceRecord"""
        return DeviceRecord(
            id=row['id'],
            vendor_id=row['vendor_id'],
            product_id=row['product_id'],
            device_type=row['device_type'],
            serial_number=row['serial_number'],
            manufacturer=row['manufacturer'],
            product_name=row['product_name'],
            port_number=row['port_number'],
            first_seen=datetime.fromisoformat(row['first_seen']) if row['first_seen'] else datetime.now(),
            last_seen=datetime.fromisoformat(row['last_seen']) if row['last_seen'] else datetime.now(),
            firmware_version=row['firmware_version'],
            test_count=row['test_count'],
            last_test_result=row['last_test_result'],
            last_test_time=datetime.fromisoformat(row['last_test_time']) if row['last_test_time'] else None,
            notes=row['notes']
        )

    def search_devices(self, query: str) -> List[DeviceRecord]:
        """Search devices by various criteria"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Search across multiple fields
                search_pattern = f"%{query}%"
                cursor.execute("""
                    SELECT * FROM devices
                    WHERE device_type LIKE ? OR
                          manufacturer LIKE ? OR
                          product_name LIKE ? OR
                          serial_number LIKE ? OR
                          notes LIKE ?
                    ORDER BY last_seen DESC
                """, (search_pattern, search_pattern, search_pattern, search_pattern, search_pattern))

                return [self._row_to_device_record(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Failed to search devices: {e}")
            return []


class HubController:
    """Core hub control functionality with WebSocket communication"""

    def __init__(self, host: str = "usbhub.local", port: int = 81, config: Dict = None):
        self.host = host
        self.port = port
        self.config = config or {}
        self.ws = None
        self.connected = False
        self.response_queue = asyncio.Queue()
        self.hub_status = {}
        self.device_db = DeviceDatabase()
        self.logger = logging.getLogger(f"{__name__}.HubController")
        self.callbacks = []

        # Initialize hub status
        max_hubs = self.config.get('max_hubs', 8)
        for hub_num in range(1, max_hubs + 1):
            self.hub_status[hub_num] = HubStatus(
                hub_number=hub_num,
                address=0x17 + hub_num,  # 0x18-0x1F
                ports=[PortStatus(port_number=hub_num * 4 - 4 + i + 1) for i in range(4)]
            )

    def add_callback(self, callback: Callable):
        """Add a callback for hub events"""
        self.callbacks.append(callback)

    def connect(self) -> bool:
        """Connect to USBFlashHub WebSocket"""
        try:
            url = f"ws://{self.host}:{self.port}/"
            self.logger.info(f"Connecting to USBFlashHub at {url}")

            self.ws = websocket.WebSocketApp(
                url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )

            # Start WebSocket in a separate thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()

            # Wait for connection
            for _ in range(50):  # 5 second timeout
                if self.connected:
                    self._refresh_status()
                    return True
                time.sleep(0.1)

            return False

        except Exception as e:
            self.logger.error(f"Failed to connect to USBFlashHub: {e}")
            return False

    def disconnect(self):
        """Disconnect from USBFlashHub"""
        if self.ws:
            self.ws.close()
            self.connected = False

    def _on_open(self, ws):
        """WebSocket connection opened"""
        self.connected = True
        self.logger.info("Connected to USBFlashHub")

    def _on_message(self, ws, message):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            self.logger.debug(f"Received: {message}")

            # Update internal state based on message
            self._process_status_update(data)

            # Notify callbacks
            for callback in self.callbacks:
                try:
                    callback('message', data)
                except Exception as e:
                    self.logger.error(f"Error in callback: {e}")

        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    def _on_error(self, ws, error):
        """WebSocket error handler"""
        self.logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket connection closed"""
        self.connected = False
        self.logger.info("Disconnected from USBFlashHub")

    def send_command(self, command: Dict[str, Any], wait_for_response: bool = False) -> Optional[Dict[str, Any]]:
        """Send command to USBFlashHub"""
        if not self.connected:
            self.logger.error("Not connected to USBFlashHub")
            return None

        try:
            cmd_json = json.dumps(command)
            self.logger.debug(f"Sending command: {cmd_json}")
            self.ws.send(cmd_json)

            if wait_for_response:
                time.sleep(0.2)  # Give time for response

            return {"status": "sent"}

        except Exception as e:
            self.logger.error(f"Failed to send command: {e}")
            return None

    def _process_status_update(self, data: Dict):
        """Process status updates from hub"""
        # Update hub and port status based on received data
        # This would be expanded based on actual hub response format
        pass

    def _refresh_status(self):
        """Refresh hub status"""
        self.send_command({"cmd": "status"})

    # Port control methods
    def power_port(self, port: int, power_level: str = "high") -> bool:
        """Control power to a specific port"""
        command = {"cmd": "port", "port": port, "power": power_level}
        success = self.send_command(command) is not None

        if success:
            # Update local status
            hub_num = ((port - 1) // 4) + 1
            port_idx = (port - 1) % 4
            if hub_num in self.hub_status:
                self.hub_status[hub_num].ports[port_idx].power_state = power_level
                self.hub_status[hub_num].ports[port_idx].last_activity = datetime.now()

        return success

    def power_cycle_port(self, port: int, off_time: float = 1.0) -> bool:
        """Power cycle a port (off -> wait -> on)"""
        self.logger.info(f"Power cycling port {port}")

        # Turn off
        if not self.power_port(port, "off"):
            return False

        # Wait
        time.sleep(off_time)

        # Turn back on
        return self.power_port(port, "high")

    def all_ports_off(self) -> bool:
        """Turn off all ports (emergency stop)"""
        command = {"cmd": "alloff"}
        return self.send_command(command) is not None

    def set_boot_pin(self, state: bool) -> bool:
        """Control boot pin state"""
        command = {"cmd": "boot", "state": state}
        return self.send_command(command) is not None

    def set_reset_pin(self, state: bool) -> bool:
        """Control reset pin state"""
        command = {"cmd": "reset", "state": state}
        return self.send_command(command) is not None

    def pulse_reset(self, duration_ms: int = 100) -> bool:
        """Pulse reset pin for specified duration"""
        command = {"cmd": "reset", "pulse": duration_ms}
        return self.send_command(command) is not None

    def enter_bootloader_mode(self, port: int, device_type: str = "ESP32") -> bool:
        """Put device on port into bootloader mode"""
        self.logger.info(f"Entering bootloader mode for {device_type} on port {port}")

        if device_type.upper().startswith("ESP32"):
            # ESP32 bootloader sequence
            self.set_boot_pin(True)
            time.sleep(0.1)
            self.pulse_reset(100)
            time.sleep(0.5)
            self.set_boot_pin(False)
            return True
        elif device_type.upper().startswith("STM32"):
            # STM32 DFU mode
            self.set_boot_pin(True)  # BOOT0 high for DFU
            self.pulse_reset(100)
            return True
        else:
            self.logger.warning(f"Unknown device type for bootloader: {device_type}")
            return False

    def get_hub_status(self) -> Dict[int, HubStatus]:
        """Get current hub status"""
        return self.hub_status.copy()

    def get_port_status(self, port: int) -> Optional[PortStatus]:
        """Get status for a specific port"""
        hub_num = ((port - 1) // 4) + 1
        port_idx = (port - 1) % 4

        if hub_num in self.hub_status:
            return self.hub_status[hub_num].ports[port_idx]

        return None


class CLIInterface(cmd.Cmd):
    """Interactive command-line interface"""

    intro = '''
╔══════════════════════════════════════════════════════════════╗
║                  USBFlashHub Control Agent                  ║
║            Interactive Command Line Interface               ║
╚══════════════════════════════════════════════════════════════╝

Type 'help' for available commands or 'quit' to exit.
    '''

    prompt = "USBHub> "

    def __init__(self, hub_controller: HubController):
        super().__init__()
        self.hub = hub_controller
        self.logger = logging.getLogger(f"{__name__}.CLIInterface")

    # Power control commands
    def do_power(self, args):
        """Power control: power <port> <level>
        Examples: power 5 high, power 3 off, power 1 low"""
        try:
            parts = args.split()
            if len(parts) != 2:
                print("Usage: power <port> <level>")
                print("Levels: off, low, high")
                return

            port = int(parts[0])
            level = parts[1]

            if self.hub.power_port(port, level):
                print(f"✓ Port {port} power set to {level}")
            else:
                print(f"✗ Failed to set port {port} power")

        except ValueError:
            print("Invalid port number")
        except Exception as e:
            print(f"Error: {e}")

    def do_power_cycle(self, args):
        """Power cycle a port: power-cycle <port> [off_time]
        Example: power-cycle 5, power-cycle 3 2.0"""
        try:
            parts = args.split()
            if len(parts) < 1:
                print("Usage: power-cycle <port> [off_time_seconds]")
                return

            port = int(parts[0])
            off_time = float(parts[1]) if len(parts) > 1 else 1.0

            if self.hub.power_cycle_port(port, off_time):
                print(f"✓ Power cycled port {port}")
            else:
                print(f"✗ Failed to power cycle port {port}")

        except ValueError:
            print("Invalid port number or off time")
        except Exception as e:
            print(f"Error: {e}")

    def do_all_off(self, args):
        """Emergency stop - turn off all ports"""
        if self.hub.all_ports_off():
            print("✓ All ports turned off")
        else:
            print("✗ Failed to turn off all ports")

    def do_bootloader(self, args):
        """Enter bootloader mode: bootloader <port> [device_type]
        Examples: bootloader 5, bootloader 3 STM32"""
        try:
            parts = args.split()
            if len(parts) < 1:
                print("Usage: bootloader <port> [device_type]")
                return

            port = int(parts[0])
            device_type = parts[1] if len(parts) > 1 else "ESP32"

            if self.hub.enter_bootloader_mode(port, device_type):
                print(f"✓ Entered bootloader mode for {device_type} on port {port}")
            else:
                print(f"✗ Failed to enter bootloader mode on port {port}")

        except ValueError:
            print("Invalid port number")
        except Exception as e:
            print(f"Error: {e}")

    # Status and monitoring commands
    def do_status(self, args):
        """Show hub and port status"""
        if not RICH_AVAILABLE:
            self._status_plain()
        else:
            self._status_rich()

    def _status_plain(self):
        """Plain text status display"""
        print("\n" + "="*60)
        print("USBFlashHub Status")
        print("="*60)

        hub_status = self.hub.get_hub_status()
        for hub_num, hub in hub_status.items():
            print(f"\nHub {hub_num} (0x{hub.address:02X}):")
            print(f"  Connected: {'Yes' if hub.connected else 'No'}")

            for port in hub.ports:
                device_info = ""
                if port.device_connected and port.device_info:
                    device_info = f" - {port.device_info.device_type}"

                print(f"  Port {port.port_number}: {port.power_state}{device_info}")

    def _status_rich(self):
        """Rich formatted status display"""
        console = Console()

        table = Table(title="USBFlashHub Status")
        table.add_column("Hub", style="cyan", no_wrap=True)
        table.add_column("Address", style="magenta")
        table.add_column("Port", style="green")
        table.add_column("Power", style="yellow")
        table.add_column("Device", style="blue")

        hub_status = self.hub.get_hub_status()
        for hub_num, hub in hub_status.items():
            for i, port in enumerate(hub.ports):
                hub_display = f"Hub {hub_num}" if i == 0 else ""
                addr_display = f"0x{hub.address:02X}" if i == 0 else ""
                device_display = port.device_info.device_type if port.device_info else "None"

                table.add_row(
                    hub_display,
                    addr_display,
                    str(port.port_number),
                    port.power_state,
                    device_display
                )

        console.print(table)

    def do_devices(self, args):
        """List tracked devices: devices [filter]
        Examples: devices, devices ESP32, devices port:5"""
        devices = []

        if not args:
            # Get all recent devices
            devices = self.hub.device_db.search_devices("")
        elif args.startswith("port:"):
            port_num = int(args[5:])
            device = self.hub.device_db.get_device_by_port(port_num)
            if device:
                devices = [device]
        else:
            devices = self.hub.device_db.search_devices(args)

        if not devices:
            print("No devices found")
            return

        if RICH_AVAILABLE:
            self._devices_rich(devices)
        else:
            self._devices_plain(devices)

    def _devices_plain(self, devices: List[DeviceRecord]):
        """Plain text device listing"""
        print(f"\nFound {len(devices)} devices:")
        print("-" * 80)
        for device in devices[:20]:  # Limit to 20 devices
            print(f"ID: {device.id}")
            print(f"  Type: {device.device_type}")
            print(f"  Serial: {device.serial_number}")
            print(f"  Port: {device.port_number}")
            print(f"  Last seen: {device.last_seen}")
            print(f"  Tests: {device.test_count} (last: {device.last_test_result})")
            print()

    def _devices_rich(self, devices: List[DeviceRecord]):
        """Rich formatted device listing"""
        console = Console()

        table = Table(title=f"Tracked Devices ({len(devices)} found)")
        table.add_column("ID", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Serial", style="yellow")
        table.add_column("Port", style="magenta")
        table.add_column("Last Seen", style="blue")
        table.add_column("Tests", style="white")

        for device in devices[:20]:  # Limit to 20 devices
            last_seen = device.last_seen.strftime("%m-%d %H:%M") if device.last_seen else "Unknown"
            test_info = f"{device.test_count} ({device.last_test_result})" if device.test_count > 0 else "0"

            table.add_row(
                str(device.id),
                device.device_type or "Unknown",
                device.serial_number or "N/A",
                str(device.port_number) if device.port_number else "N/A",
                last_seen,
                test_info
            )

        console.print(table)

    def do_test_history(self, args):
        """Show test history: test-history [device_id] [limit]"""
        try:
            parts = args.split()
            device_id = int(parts[0]) if parts else None
            limit = int(parts[1]) if len(parts) > 1 else 20

            history = self.hub.device_db.get_test_history(device_id, limit)

            if not history:
                print("No test history found")
                return

            if RICH_AVAILABLE:
                self._test_history_rich(history)
            else:
                self._test_history_plain(history)

        except ValueError:
            print("Invalid device ID or limit")
        except Exception as e:
            print(f"Error: {e}")

    def _test_history_plain(self, history: List[Dict]):
        """Plain text test history"""
        print(f"\nTest History ({len(history)} entries):")
        print("-" * 80)
        for test in history:
            print(f"Device: {test['device_type']} ({test['serial_number']})")
            print(f"  Test: {test['test_name']} - {test['test_result']}")
            print(f"  Time: {test['test_time']}")
            if test['duration_seconds']:
                print(f"  Duration: {test['duration_seconds']:.1f}s")
            if test['error_message']:
                print(f"  Error: {test['error_message']}")
            print()

    def _test_history_rich(self, history: List[Dict]):
        """Rich formatted test history"""
        console = Console()

        table = Table(title=f"Test History ({len(history)} entries)")
        table.add_column("Device", style="green")
        table.add_column("Test", style="blue")
        table.add_column("Result", style="yellow")
        table.add_column("Time", style="cyan")
        table.add_column("Duration", style="magenta")

        for test in history:
            duration = f"{test['duration_seconds']:.1f}s" if test['duration_seconds'] else "N/A"

            result_style = "green" if test['test_result'].upper() == "PASSED" else "red"

            table.add_row(
                f"{test['device_type']} ({test['serial_number']})",
                test['test_name'],
                Text(test['test_result'], style=result_style),
                test['test_time'][:16],  # Truncate timestamp
                duration
            )

        console.print(table)

    # Automation commands
    def do_run_script(self, args):
        """Run automation script: run-script <script_name> [args]"""
        if not args:
            self._list_scripts()
            return

        parts = args.split()
        script_name = parts[0]
        script_args = parts[1:] if len(parts) > 1 else []

        script_path = Path("/home/bruce/Arduino/USBFlashHub/agents/automation_scripts") / f"{script_name}.py"

        if not script_path.exists():
            print(f"Script not found: {script_name}")
            self._list_scripts()
            return

        try:
            cmd = [sys.executable, str(script_path)] + script_args
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            print(f"Script output:")
            print(result.stdout)
            if result.stderr:
                print(f"Errors:")
                print(result.stderr)

            if result.returncode == 0:
                print("✓ Script completed successfully")
            else:
                print(f"✗ Script failed with exit code {result.returncode}")

        except subprocess.TimeoutExpired:
            print("✗ Script timed out")
        except Exception as e:
            print(f"Error running script: {e}")

    def _list_scripts(self):
        """List available automation scripts"""
        script_dir = Path("/home/bruce/Arduino/USBFlashHub/agents/automation_scripts")

        if not script_dir.exists():
            print("No automation scripts directory found")
            return

        scripts = list(script_dir.glob("*.py"))

        if not scripts:
            print("No automation scripts found")
            return

        print("\nAvailable automation scripts:")
        for script in scripts:
            print(f"  {script.stem}")

    # Control flow commands
    def do_connect(self, args):
        """Connect to hub: connect [host] [port]"""
        parts = args.split()
        host = parts[0] if parts else "localhost"
        port = int(parts[1]) if len(parts) > 1 else 81

        self.hub.host = host
        self.hub.port = port

        if self.hub.connect():
            print(f"✓ Connected to {host}:{port}")
        else:
            print(f"✗ Failed to connect to {host}:{port}")

    def do_disconnect(self, args):
        """Disconnect from hub"""
        self.hub.disconnect()
        print("Disconnected from hub")

    def do_quit(self, args):
        """Exit the CLI"""
        self.hub.disconnect()
        print("Goodbye!")
        return True

    def do_exit(self, args):
        """Exit the CLI"""
        return self.do_quit(args)


class Dashboard:
    """Terminal-based status dashboard using Rich"""

    def __init__(self, hub_controller: HubController):
        self.hub = hub_controller
        self.running = False
        self.logger = logging.getLogger(f"{__name__}.Dashboard")

    def start(self):
        """Start the live dashboard"""
        if not RICH_AVAILABLE:
            self.logger.error("Rich library required for dashboard")
            return

        self.running = True
        console = Console()

        with Live(self._generate_layout(), refresh_per_second=1, console=console) as live:
            try:
                while self.running:
                    live.update(self._generate_layout())
                    time.sleep(1)
            except KeyboardInterrupt:
                self.running = False

    def stop(self):
        """Stop the dashboard"""
        self.running = False

    def _generate_layout(self):
        """Generate the dashboard layout"""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        # Header
        layout["header"].update(Panel(
            f"USBFlashHub Control Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            style="bold blue"
        ))

        # Hub status table
        layout["left"].update(self._create_hub_status_panel())

        # Device list
        layout["right"].update(self._create_device_panel())

        # Footer
        layout["footer"].update(Panel(
            "Press Ctrl+C to exit | Connection: " + ("Connected" if self.hub.connected else "Disconnected"),
            style="dim"
        ))

        return layout

    def _create_hub_status_panel(self):
        """Create hub status panel"""
        table = Table(title="Hub Status")
        table.add_column("Hub", style="cyan")
        table.add_column("Port", style="green")
        table.add_column("Power", style="yellow")
        table.add_column("Device", style="blue")
        table.add_column("Last Activity", style="dim")

        hub_status = self.hub.get_hub_status()
        for hub_num, hub in hub_status.items():
            for i, port in enumerate(hub.ports):
                hub_display = f"Hub {hub_num}" if i == 0 else ""
                device_display = port.device_info.device_type if port.device_info else "-"
                activity = port.last_activity.strftime("%H:%M:%S") if port.last_activity else "-"

                # Color code power state
                power_color = "green" if port.power_state != "off" else "red"

                table.add_row(
                    hub_display,
                    str(port.port_number),
                    Text(port.power_state, style=power_color),
                    device_display,
                    activity
                )

        return Panel(table, title="Hub Status", border_style="blue")

    def _create_device_panel(self):
        """Create device panel"""
        devices = self.hub.device_db.search_devices("")[:10]  # Last 10 devices

        if not devices:
            return Panel("No devices tracked", title="Recent Devices", border_style="green")

        table = Table()
        table.add_column("Device", style="green")
        table.add_column("Port", style="cyan")
        table.add_column("Last Seen", style="yellow")
        table.add_column("Tests", style="blue")

        for device in devices:
            last_seen = device.last_seen.strftime("%m-%d %H:%M") if device.last_seen else "Unknown"
            port_display = str(device.port_number) if device.port_number else "-"

            table.add_row(
                device.device_type or "Unknown",
                port_display,
                last_seen,
                str(device.test_count)
            )

        return Panel(table, title="Recent Devices", border_style="green")


class RestAPIServer:
    """Optional REST API server for remote control"""

    def __init__(self, hub_controller: HubController, port: int = 5000):
        if not FLASK_AVAILABLE:
            raise ImportError("Flask required for REST API server")

        self.hub = hub_controller
        self.port = port
        self.app = Flask(__name__)
        CORS(self.app)
        self.logger = logging.getLogger(f"{__name__}.RestAPIServer")

        self._setup_routes()

    def _setup_routes(self):
        """Set up API routes"""

        @self.app.route('/api/status', methods=['GET'])
        def get_status():
            """Get hub status"""
            hub_status = self.hub.get_hub_status()
            return jsonify({
                "connected": self.hub.connected,
                "hubs": {str(k): asdict(v) for k, v in hub_status.items()}
            })

        @self.app.route('/api/port/<int:port>/power', methods=['POST'])
        def set_port_power(port):
            """Set port power level"""
            data = request.json
            power_level = data.get('level', 'high')

            success = self.hub.power_port(port, power_level)
            return jsonify({"success": success, "port": port, "power": power_level})

        @self.app.route('/api/port/<int:port>/power-cycle', methods=['POST'])
        def power_cycle_port(port):
            """Power cycle a port"""
            data = request.json
            off_time = data.get('off_time', 1.0)

            success = self.hub.power_cycle_port(port, off_time)
            return jsonify({"success": success, "port": port})

        @self.app.route('/api/bootloader', methods=['POST'])
        def enter_bootloader():
            """Enter bootloader mode"""
            data = request.json
            port = data.get('port')
            device_type = data.get('device_type', 'ESP32')

            if not port:
                return jsonify({"error": "Port required"}), 400

            success = self.hub.enter_bootloader_mode(port, device_type)
            return jsonify({"success": success, "port": port, "device_type": device_type})

        @self.app.route('/api/emergency-stop', methods=['POST'])
        def emergency_stop():
            """Emergency stop all ports"""
            success = self.hub.all_ports_off()
            return jsonify({"success": success})

        @self.app.route('/api/devices', methods=['GET'])
        def get_devices():
            """Get tracked devices"""
            query = request.args.get('q', '')
            limit = int(request.args.get('limit', 50))

            devices = self.hub.device_db.search_devices(query)[:limit]
            return jsonify([asdict(device) for device in devices])

        @self.app.route('/api/test-history', methods=['GET'])
        def get_test_history():
            """Get test history"""
            device_id = request.args.get('device_id')
            limit = int(request.args.get('limit', 100))

            device_id = int(device_id) if device_id else None
            history = self.hub.device_db.get_test_history(device_id, limit)
            return jsonify(history)

    def start(self):
        """Start the API server"""
        self.logger.info(f"Starting REST API server on port {self.port}")
        self.app.run(host='0.0.0.0', port=self.port, debug=False)


def load_config(config_path: str) -> Dict:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info("Received interrupt signal, shutting down...")
    if hasattr(signal_handler, 'hub'):
        signal_handler.hub.disconnect()
    sys.exit(0)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="USBFlashHub Control Agent")
    parser.add_argument("--config", default="/home/bruce/Arduino/USBFlashHub/agents/hub_config.yaml",
                       help="Configuration file")
    parser.add_argument("--host", default="usbhub.local", help="Hub host (mDNS hostname or IP)")
    parser.add_argument("--port", type=int, default=81, help="Hub WebSocket port")
    parser.add_argument("--mode", choices=["cli", "dashboard", "api"], default="cli",
                       help="Operation mode")
    parser.add_argument("--api-port", type=int, default=5000, help="REST API port")
    parser.add_argument("--no-connect", action="store_true", help="Don't auto-connect to hub")

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Create hub controller
    hub = HubController(args.host, args.port, config)
    signal_handler.hub = hub

    # Connect to hub unless disabled
    if not args.no_connect:
        if not hub.connect():
            logger.error("Failed to connect to USBFlashHub")
            if args.mode != "cli":
                return 1

    try:
        if args.mode == "cli":
            # Interactive CLI mode
            cli = CLIInterface(hub)
            cli.cmdloop()

        elif args.mode == "dashboard":
            # Live dashboard mode
            if not RICH_AVAILABLE:
                logger.error("Rich library required for dashboard mode")
                return 1

            dashboard = Dashboard(hub)
            logger.info("Starting dashboard. Press Ctrl+C to exit.")
            dashboard.start()

        elif args.mode == "api":
            # REST API server mode
            if not FLASK_AVAILABLE:
                logger.error("Flask required for API server mode")
                return 1

            api_server = RestAPIServer(hub, args.api_port)
            api_server.start()

    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1
    finally:
        hub.disconnect()

    logger.info("Hub control agent stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())