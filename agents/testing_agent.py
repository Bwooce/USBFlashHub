#!/usr/bin/env python3
"""
USBFlashHub Testing Automation Agent

A comprehensive testing automation system for the USBFlashHub that:
- Monitors USB device connections and correlates them with hub ports
- Executes configurable test workflows for different device types
- Controls hub power, boot/reset pins via WebSocket
- Supports multiple programming protocols (esptool, dfu-util, etc.)
- Provides detailed logging and test reporting

Author: Testing automation for USBFlashHub
"""

import asyncio
import json
import logging
import time
import subprocess
import signal
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import yaml
import pyudev
import websocket
import threading
from datetime import datetime
import re


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/bruce/Arduino/USBFlashHub/agents/testing_agent.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Information about a detected USB device"""
    vendor_id: str
    product_id: str
    device_path: str
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    product: Optional[str] = None
    device_type: Optional[str] = None
    port_number: Optional[int] = None
    first_seen: datetime = field(default_factory=datetime.now)


@dataclass
class TestStep:
    """A single step in a test workflow"""
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0
    retry_count: int = 0
    success_criteria: Optional[str] = None


@dataclass
class TestResult:
    """Result of a test execution"""
    device_info: DeviceInfo
    rule_name: str
    steps_executed: List[str]
    success: bool
    start_time: datetime
    end_time: datetime
    error_message: Optional[str] = None
    logs: List[str] = field(default_factory=list)


class DeviceRule:
    """Defines a test workflow for a specific device type"""

    def __init__(self, name: str, device_filter: Dict[str, str], steps: List[TestStep]):
        self.name = name
        self.device_filter = device_filter
        self.steps = steps

    def matches_device(self, device: DeviceInfo) -> bool:
        """Check if this rule applies to the given device"""
        for key, pattern in self.device_filter.items():
            device_value = getattr(device, key, None)
            if device_value is None:
                return False
            if not re.match(pattern, str(device_value), re.IGNORECASE):
                return False
        return True

    @classmethod
    def from_dict(cls, rule_dict: Dict[str, Any]) -> 'DeviceRule':
        """Create a DeviceRule from a dictionary (loaded from YAML)"""
        steps = []
        for step_dict in rule_dict.get('steps', []):
            step = TestStep(
                action=step_dict['action'],
                params=step_dict.get('params', {}),
                timeout=step_dict.get('timeout', 30.0),
                retry_count=step_dict.get('retry_count', 0),
                success_criteria=step_dict.get('success_criteria')
            )
            steps.append(step)

        return cls(
            name=rule_dict['name'],
            device_filter=rule_dict['device_filter'],
            steps=steps
        )


class USBHubController:
    """WebSocket controller for USBFlashHub communication"""

    def __init__(self, host: str = "usbhub.local", port: int = 81):
        self.host = host
        self.port = port
        self.ws = None
        self.connected = False
        self.response_queue = asyncio.Queue()
        self.logger = logging.getLogger(f"{__name__}.USBHubController")

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
            # Put message in queue for processing
            asyncio.run_coroutine_threadsafe(
                self.response_queue.put(message),
                asyncio.get_event_loop()
            )
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    def _on_error(self, ws, error):
        """WebSocket error handler"""
        self.logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket connection closed"""
        self.connected = False
        self.logger.info("Disconnected from USBFlashHub")

    def send_command(self, command: Dict[str, Any], wait_for_response: bool = True) -> Optional[Dict[str, Any]]:
        """Send command to USBFlashHub and optionally wait for response"""
        if not self.connected:
            self.logger.error("Not connected to USBFlashHub")
            return None

        try:
            cmd_json = json.dumps(command)
            self.logger.debug(f"Sending command: {cmd_json}")
            self.ws.send(cmd_json)

            if wait_for_response:
                # Wait for response (simple implementation)
                time.sleep(0.1)  # Give time for response
                try:
                    response = asyncio.run_coroutine_threadsafe(
                        asyncio.wait_for(self.response_queue.get(), timeout=5.0),
                        asyncio.get_event_loop()
                    ).result()
                    return json.loads(response)
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    pass

            return {"status": "sent"}

        except Exception as e:
            self.logger.error(f"Failed to send command: {e}")
            return None

    def power_port(self, port: int, power_level: str = "high") -> bool:
        """Control power to a specific port"""
        command = {"cmd": "port", "port": port, "power": power_level}
        response = self.send_command(command)
        return response is not None

    def set_boot_pin(self, state: bool) -> bool:
        """Control boot pin state"""
        command = {"cmd": "boot", "state": state}
        response = self.send_command(command)
        return response is not None

    def set_reset_pin(self, state: bool) -> bool:
        """Control reset pin state"""
        command = {"cmd": "reset", "state": state}
        response = self.send_command(command)
        return response is not None

    def pulse_reset(self, duration_ms: int = 100) -> bool:
        """Pulse reset pin for specified duration"""
        command = {"cmd": "reset", "pulse": duration_ms}
        response = self.send_command(command)
        return response is not None

    def emergency_stop(self) -> bool:
        """Emergency stop - turn off all ports"""
        command = {"cmd": "alloff"}
        response = self.send_command(command)
        return response is not None

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Get hub status"""
        command = {"cmd": "status"}
        return self.send_command(command)


class DeviceDetector:
    """USB device detection and monitoring using pyudev"""

    # Known device types based on VID/PID
    DEVICE_TYPES = {
        ('303a', '1001'): 'ESP32-S2',
        ('303a', '0002'): 'ESP32-S2',
        ('303a', '1000'): 'ESP32',
        ('303a', '80d4'): 'ESP32-C3',
        ('303a', '1000'): 'ESP32-S3',
        ('0483', 'df11'): 'STM32-DFU',
        ('0483', '5740'): 'STM32',
        ('2341', '0043'): 'Arduino-Uno',
        ('2341', '0001'): 'Arduino-Uno',
        ('1a86', '7523'): 'CH340-Serial',
        ('0403', '6001'): 'FTDI-Serial',
    }

    def __init__(self):
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='usb')
        self.devices = {}  # device_path -> DeviceInfo
        self.port_mapping = {}  # port_number -> device_path
        self.logger = logging.getLogger(f"{__name__}.DeviceDetector")
        self.observer = None
        self.device_callbacks = []  # List of callbacks for device events

    def add_device_callback(self, callback: Callable[[str, DeviceInfo], None]):
        """Add a callback for device events. Callback signature: (action, device_info)"""
        self.device_callbacks.append(callback)

    def start_monitoring(self):
        """Start monitoring USB device events"""
        self.logger.info("Starting USB device monitoring")

        # Initial scan for existing devices
        self._scan_existing_devices()

        # Start monitoring for new events
        self.observer = pyudev.MonitorObserver(self.monitor, self._handle_device_event)
        self.observer.start()

    def stop_monitoring(self):
        """Stop monitoring USB device events"""
        if self.observer:
            self.observer.stop()
            self.logger.info("Stopped USB device monitoring")

    def _scan_existing_devices(self):
        """Scan for currently connected USB devices"""
        self.logger.info("Scanning for existing USB devices")

        for device in self.context.list_devices(subsystem='usb', DEVTYPE='usb_device'):
            device_info = self._create_device_info(device)
            if device_info:
                self.devices[device_info.device_path] = device_info
                self.logger.info(f"Found existing device: {device_info.device_type} at {device_info.device_path}")

                # Notify callbacks
                for callback in self.device_callbacks:
                    try:
                        callback('add', device_info)
                    except Exception as e:
                        self.logger.error(f"Error in device callback: {e}")

    def _handle_device_event(self, device):
        """Handle pyudev device events"""
        action = device.action

        if action in ['add', 'remove']:
            device_info = self._create_device_info(device)
            if device_info:
                if action == 'add':
                    self.devices[device_info.device_path] = device_info
                    self.logger.info(f"Device connected: {device_info.device_type} at {device_info.device_path}")
                elif action == 'remove':
                    if device_info.device_path in self.devices:
                        del self.devices[device_info.device_path]
                        self.logger.info(f"Device disconnected: {device_info.device_path}")

                # Notify callbacks
                for callback in self.device_callbacks:
                    try:
                        callback(action, device_info)
                    except Exception as e:
                        self.logger.error(f"Error in device callback: {e}")

    def _create_device_info(self, device) -> Optional[DeviceInfo]:
        """Create DeviceInfo from pyudev device"""
        try:
            vendor_id = device.get('ID_VENDOR_ID', '').lower()
            product_id = device.get('ID_PRODUCT_ID', '').lower()

            if not vendor_id or not product_id:
                return None

            device_type = self.DEVICE_TYPES.get((vendor_id, product_id), 'Unknown')

            return DeviceInfo(
                vendor_id=vendor_id,
                product_id=product_id,
                device_path=device.device_path,
                serial_number=device.get('ID_SERIAL_SHORT'),
                manufacturer=device.get('ID_VENDOR'),
                product=device.get('ID_MODEL'),
                device_type=device_type
            )

        except Exception as e:
            self.logger.error(f"Error creating device info: {e}")
            return None

    def correlate_device_with_port(self, device_path: str, port_number: int):
        """Correlate a device with a hub port number"""
        if device_path in self.devices:
            self.devices[device_path].port_number = port_number
            self.port_mapping[port_number] = device_path
            self.logger.info(f"Correlated device {device_path} with port {port_number}")

    def get_device_by_port(self, port_number: int) -> Optional[DeviceInfo]:
        """Get device information for a specific port"""
        device_path = self.port_mapping.get(port_number)
        if device_path and device_path in self.devices:
            return self.devices[device_path]
        return None

    def get_all_devices(self) -> List[DeviceInfo]:
        """Get all currently detected devices"""
        return list(self.devices.values())


class TestingEngine:
    """Main testing engine that orchestrates device detection, rule matching, and test execution"""

    def __init__(self, config_file: str = None):
        self.hub_controller = USBHubController()
        self.device_detector = DeviceDetector()
        self.rules = []
        self.test_results = []
        self.running = False
        self.logger = logging.getLogger(f"{__name__}.TestingEngine")

        # Load configuration
        if config_file:
            self.load_config(config_file)

        # Set up device detection callback
        self.device_detector.add_device_callback(self._on_device_event)

    def load_config(self, config_file: str):
        """Load test rules from configuration file"""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            self.rules = []
            for rule_dict in config.get('rules', []):
                rule = DeviceRule.from_dict(rule_dict)
                self.rules.append(rule)
                self.logger.info(f"Loaded rule: {rule.name}")

        except Exception as e:
            self.logger.error(f"Failed to load config from {config_file}: {e}")

    def start(self) -> bool:
        """Start the testing engine"""
        self.logger.info("Starting testing engine")

        # Connect to hub
        if not self.hub_controller.connect():
            self.logger.error("Failed to connect to USBFlashHub")
            return False

        # Start device monitoring
        self.device_detector.start_monitoring()

        self.running = True
        return True

    def stop(self):
        """Stop the testing engine"""
        self.logger.info("Stopping testing engine")
        self.running = False

        self.device_detector.stop_monitoring()
        self.hub_controller.disconnect()

    def _on_device_event(self, action: str, device_info: DeviceInfo):
        """Handle device connection/disconnection events"""
        if action == 'add' and self.running:
            # Try to match device with rules and execute tests
            self._process_new_device(device_info)

    def _process_new_device(self, device_info: DeviceInfo):
        """Process a newly detected device and run applicable tests"""
        self.logger.info(f"Processing new device: {device_info.device_type}")

        # Find matching rules
        matching_rules = [rule for rule in self.rules if rule.matches_device(device_info)]

        if not matching_rules:
            self.logger.info(f"No rules match device {device_info.device_type}")
            return

        # Execute each matching rule
        for rule in matching_rules:
            self.logger.info(f"Executing rule {rule.name} for device {device_info.device_type}")
            result = self._execute_rule(rule, device_info)
            self.test_results.append(result)

    def _execute_rule(self, rule: DeviceRule, device_info: DeviceInfo) -> TestResult:
        """Execute a test rule for a specific device"""
        start_time = datetime.now()
        steps_executed = []
        logs = []
        success = True
        error_message = None

        try:
            for step in rule.steps:
                self.logger.info(f"Executing step: {step.action}")
                logs.append(f"Executing step: {step.action}")

                step_success = self._execute_step(step, device_info, logs)
                steps_executed.append(step.action)

                if not step_success:
                    success = False
                    error_message = f"Step {step.action} failed"
                    break

        except Exception as e:
            success = False
            error_message = f"Exception during rule execution: {e}"
            self.logger.error(error_message)
            logs.append(error_message)

        end_time = datetime.now()

        result = TestResult(
            device_info=device_info,
            rule_name=rule.name,
            steps_executed=steps_executed,
            success=success,
            start_time=start_time,
            end_time=end_time,
            error_message=error_message,
            logs=logs
        )

        # Log result
        status = "PASSED" if success else "FAILED"
        self.logger.info(f"Rule {rule.name} {status} for device {device_info.device_type}")

        return result

    def _execute_step(self, step: TestStep, device_info: DeviceInfo, logs: List[str]) -> bool:
        """Execute a single test step"""
        try:
            action = step.action
            params = step.params

            if action == "power_on":
                port = params.get("port", "auto")
                if port == "auto":
                    # Auto-detect port (simplified - would need proper correlation logic)
                    port = 1  # Default to port 1 for now
                power_level = params.get("power_level", "high")
                return self.hub_controller.power_port(port, power_level)

            elif action == "power_off":
                port = params.get("port", device_info.port_number or 1)
                return self.hub_controller.power_port(port, "off")

            elif action == "wait_for_device":
                timeout = params.get("timeout", 5)
                return self._wait_for_device(device_info, timeout, logs)

            elif action == "enter_bootloader":
                method = params.get("method", "boot_reset")
                return self._enter_bootloader(method, logs)

            elif action == "flash_firmware":
                return self._flash_firmware(step, device_info, logs)

            elif action == "reset_device":
                return self._reset_device(logs)

            elif action == "run_test":
                return self._run_test(step, device_info, logs)

            else:
                logs.append(f"Unknown action: {action}")
                return False

        except Exception as e:
            logs.append(f"Error executing step {step.action}: {e}")
            return False

    def _wait_for_device(self, device_info: DeviceInfo, timeout: float, logs: List[str]) -> bool:
        """Wait for device to appear"""
        logs.append(f"Waiting for device {device_info.device_type} (timeout: {timeout}s)")

        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if device is still present
            if device_info.device_path in self.device_detector.devices:
                logs.append("Device detected")
                return True
            time.sleep(0.5)

        logs.append("Timeout waiting for device")
        return False

    def _enter_bootloader(self, method: str, logs: List[str]) -> bool:
        """Enter bootloader mode using specified method"""
        logs.append(f"Entering bootloader mode using method: {method}")

        if method == "boot_reset":
            # Standard ESP32 bootloader entry
            self.hub_controller.set_boot_pin(True)   # Boot pin HIGH
            time.sleep(0.1)
            self.hub_controller.pulse_reset(100)     # Pulse reset
            time.sleep(0.5)
            self.hub_controller.set_boot_pin(False)  # Release boot pin
            logs.append("Boot/reset sequence completed")
            return True

        elif method == "dfu":
            # STM32 DFU mode entry
            self.hub_controller.set_boot_pin(True)   # Boot0 HIGH for DFU
            self.hub_controller.pulse_reset(100)     # Reset to enter DFU
            logs.append("DFU mode entry sequence completed")
            return True

        else:
            logs.append(f"Unknown bootloader method: {method}")
            return False

    def _flash_firmware(self, step: TestStep, device_info: DeviceInfo, logs: List[str]) -> bool:
        """Flash firmware to device"""
        params = step.params
        firmware_file = params.get("file")
        tool = params.get("tool", "auto")

        if not firmware_file:
            logs.append("No firmware file specified")
            return False

        if not Path(firmware_file).exists():
            logs.append(f"Firmware file not found: {firmware_file}")
            return False

        # Auto-detect tool based on device type
        if tool == "auto":
            if "ESP32" in device_info.device_type:
                tool = "esptool"
            elif "STM32" in device_info.device_type:
                tool = "dfu-util"
            else:
                logs.append(f"Cannot auto-detect tool for device type: {device_info.device_type}")
                return False

        logs.append(f"Flashing {firmware_file} using {tool}")

        try:
            if tool == "esptool":
                return self._flash_with_esptool(firmware_file, device_info, logs)
            elif tool == "dfu-util":
                return self._flash_with_dfu_util(firmware_file, device_info, logs)
            else:
                logs.append(f"Unsupported flashing tool: {tool}")
                return False

        except Exception as e:
            logs.append(f"Flashing failed: {e}")
            return False

    def _flash_with_esptool(self, firmware_file: str, device_info: DeviceInfo, logs: List[str]) -> bool:
        """Flash firmware using esptool"""
        # Find serial port for device (simplified)
        port = "/dev/ttyUSB0"  # Would need proper port detection

        cmd = [
            "esptool.py",
            "--port", port,
            "--baud", "921600",
            "write_flash",
            "0x1000", firmware_file
        ]

        logs.append(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            logs.append(f"esptool stdout: {result.stdout}")
            if result.stderr:
                logs.append(f"esptool stderr: {result.stderr}")

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logs.append("esptool timeout")
            return False

    def _flash_with_dfu_util(self, firmware_file: str, device_info: DeviceInfo, logs: List[str]) -> bool:
        """Flash firmware using dfu-util"""
        cmd = [
            "dfu-util",
            "-a", "0",
            "-D", firmware_file
        ]

        logs.append(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            logs.append(f"dfu-util stdout: {result.stdout}")
            if result.stderr:
                logs.append(f"dfu-util stderr: {result.stderr}")

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logs.append("dfu-util timeout")
            return False

    def _reset_device(self, logs: List[str]) -> bool:
        """Reset the device"""
        logs.append("Resetting device")
        return self.hub_controller.pulse_reset(100)

    def _run_test(self, step: TestStep, device_info: DeviceInfo, logs: List[str]) -> bool:
        """Run a test script"""
        params = step.params
        script = params.get("script")

        if not script:
            logs.append("No test script specified")
            return False

        if not Path(script).exists():
            logs.append(f"Test script not found: {script}")
            return False

        logs.append(f"Running test script: {script}")

        try:
            result = subprocess.run([script], capture_output=True, text=True, timeout=step.timeout)
            logs.append(f"Test stdout: {result.stdout}")
            if result.stderr:
                logs.append(f"Test stderr: {result.stderr}")

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logs.append(f"Test script timeout after {step.timeout}s")
            return False
        except Exception as e:
            logs.append(f"Error running test script: {e}")
            return False

    def get_test_results(self) -> List[TestResult]:
        """Get all test results"""
        return self.test_results.copy()

    def generate_report(self) -> str:
        """Generate a summary report of all test results"""
        if not self.test_results:
            return "No test results available"

        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.success)
        failed_tests = total_tests - passed_tests

        report = []
        report.append("=" * 60)
        report.append("USBFlashHub Testing Report")
        report.append("=" * 60)
        report.append(f"Total Tests: {total_tests}")
        report.append(f"Passed: {passed_tests}")
        report.append(f"Failed: {failed_tests}")
        report.append(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        report.append("")

        for result in self.test_results:
            status = "PASSED" if result.success else "FAILED"
            duration = (result.end_time - result.start_time).total_seconds()

            report.append(f"[{status}] {result.rule_name} - {result.device_info.device_type}")
            report.append(f"  Duration: {duration:.2f}s")
            report.append(f"  Steps: {', '.join(result.steps_executed)}")
            if result.error_message:
                report.append(f"  Error: {result.error_message}")
            report.append("")

        return "\n".join(report)


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info("Received interrupt signal, shutting down...")
    if hasattr(signal_handler, 'engine'):
        signal_handler.engine.stop()
    sys.exit(0)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="USBFlashHub Testing Automation Agent")
    parser.add_argument("--config", default="test_rules.yaml", help="Configuration file")
    parser.add_argument("--host", default="usbhub.local", help="USBFlashHub host (mDNS hostname or IP)")
    parser.add_argument("--port", type=int, default=81, help="USBFlashHub WebSocket port")
    parser.add_argument("--report-interval", type=int, default=300, help="Report interval in seconds")

    args = parser.parse_args()

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Create and start testing engine
    engine = TestingEngine(args.config)
    engine.hub_controller.host = args.host
    engine.hub_controller.port = args.port

    # Store engine reference for signal handler
    signal_handler.engine = engine

    if not engine.start():
        logger.error("Failed to start testing engine")
        return 1

    logger.info("Testing engine started. Press Ctrl+C to stop.")

    try:
        # Main loop - periodically generate reports
        last_report = time.time()

        while engine.running:
            time.sleep(1)

            # Generate periodic reports
            if time.time() - last_report >= args.report_interval:
                report = engine.generate_report()
                logger.info(f"Periodic Report:\n{report}")
                last_report = time.time()

    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()

    # Final report
    logger.info("Final Report:")
    logger.info(engine.generate_report())

    return 0


if __name__ == "__main__":
    sys.exit(main())