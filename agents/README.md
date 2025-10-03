# USBFlashHub Python Agents

A comprehensive Python-based system for the USBFlashHub that provides both automated testing and interactive control capabilities through two complementary agents.

## Quick Connect Guide

The USBFlashHub uses mDNS hostname `usbhub.local` (default). If mDNS doesn't work, use the IP address.

### Find Your Hub
```bash
# Try mDNS first
curl http://usbhub.local/

# If that fails, get IP from serial console
screen /dev/ttyACM0 115200
# Look for "IP: 192.168.x.x"

# Or scan your network
nmap -p 80 192.168.1.0/24 | grep -B2 "80/tcp open"
```

### Turn On All USB Ports with LEDs

**Smart Script (Recommended)** - Detects actual connected hubs:
```bash
# Automatically detects connected hubs and turns on ports with LEDs
python3 turn_on_all_ports.py

# Specific options
python3 turn_on_all_ports.py --power low        # Use low instead of high
python3 turn_on_all_ports.py --no-leds           # Don't turn on LEDs
python3 turn_on_all_ports.py --ports 1,2,3,4     # Only specific ports
python3 turn_on_all_ports.py --ports 1-4         # Port range
python3 turn_on_all_ports.py --host 192.168.1.100 # Use IP instead of mDNS
```

**One-Liner for All Possible Ports** (attempts all 32 ports with LEDs):
```bash
# Try all possible ports (1-32) and hubs (1-8) with LEDs
python3 -c "import websocket,json,time; ws=websocket.WebSocket(); ws.connect('ws://usbhub.local:81'); [ws.send(json.dumps({'cmd':'port','port':p,'power':'high'})) or time.sleep(0.02) for p in range(1,33)]; [ws.send(json.dumps({'cmd':'hub','hub':h,'led':True})) or time.sleep(0.02) for h in range(1,9)]; print('All ports attempted with LEDs')"
```

**Note**: The software supports up to 8 hubs (32 ports total). The script will attempt to control all possible ports - actual hardware will only respond for connected hubs.

## Overview

This system consists of two main Python agents:

1. **Testing Agent** (`testing_agent.py`) - Automated testing and workflow execution
2. **Hub Control Agent** (`hub_control.py`) - Interactive control, monitoring, and device database

## Features

### Testing Agent Features
- **Automated Testing**: Rule-based testing workflows for different device types
- **Device Detection**: Monitors USB devices using `pyudev` and automatically detects device types
- **Port Correlation**: Maps detected devices to specific hub port numbers
- **Multiple Protocols**: Supports esptool (ESP32), dfu-util (STM32), avrdude (Arduino), etc.
- **Comprehensive Logging**: Detailed logs and test reports with pass/fail tracking

### Hub Control Agent Features
- **Interactive CLI**: Command-line interface for manual hub control
- **Device Database**: SQLite database tracking devices, test history, and firmware versions
- **Status Dashboard**: Real-time terminal-based status display using Rich
- **Automation Scripts**: Pre-defined sequences for common tasks
- **REST API Server**: Optional web API for remote control and CI/CD integration
- **Port Grouping**: Organize ports into logical groups for batch operations

## Architecture

### Testing Agent Components

1. **USBHubController**: WebSocket communication with the USBFlashHub
2. **DeviceDetector**: Monitors USB device connections using pyudev
3. **DeviceRule**: Defines test workflows for specific device types
4. **TestingEngine**: Orchestrates the entire testing process

### Hub Control Agent Components

1. **HubController**: Core hub control functionality with WebSocket communication
2. **DeviceDatabase**: SQLite database for tracking devices and test history
3. **CLIInterface**: Interactive command-line interface using Python cmd module
4. **Dashboard**: Terminal-based status dashboard using Rich library
5. **RestAPIServer**: Optional Flask-based REST API for remote control
6. **Automation Scripts**: Pre-built scripts for common operations

## Installation

### Prerequisites

1. **System packages** (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install python3-pip dfu-util avrdude sqlite3
```

2. **Python dependencies**:
```bash
cd /home/bruce/Arduino/USBFlashHub/agents
pip3 install -r requirements.txt
```

3. **Optional dependencies**:
```bash
# For ESP32 support
pip3 install esptool

# For rich dashboard (recommended)
pip3 install rich

# For REST API server (optional)
pip3 install flask flask-cors
```

### Permissions

Add your user to the dialout group for serial port access:
```bash
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```

## Configuration

### Test Rules (test_rules.yaml)

The configuration file defines rules for different device types:

```yaml
rules:
  - name: "ESP32-S3 Complete Test"
    device_filter:
      device_type: "ESP32.*S3"  # Regex pattern
      vendor_id: "303a"         # Espressif VID
    steps:
      - action: "power_on"
        params:
          port: "auto"
          power_level: "high"
        timeout: 5.0

      - action: "enter_bootloader"
        params:
          method: "boot_reset"
        timeout: 5.0

      - action: "flash_firmware"
        params:
          file: "/path/to/firmware.bin"
          tool: "esptool"
        timeout: 60.0
```

### Supported Actions

- **power_on**: Turn on port power (off, low, high)
- **power_off**: Turn off port power
- **wait_for_device**: Wait for device to appear
- **enter_bootloader**: Enter bootloader mode (boot_reset, dfu)
- **flash_firmware**: Flash firmware using specified tool
- **reset_device**: Reset the device
- **run_test**: Execute test script

### Device Filters

Rules can match devices using regex patterns:
- `device_type`: Device type string (ESP32-S3, STM32-DFU, etc.)
- `vendor_id`: USB Vendor ID (303a for Espressif, 0483 for STM32)
- `product_id`: USB Product ID
- `manufacturer`: Manufacturer string
- `product`: Product string

## Usage

### Hub Control Agent Usage

The Hub Control Agent provides multiple operation modes for different use cases.

#### 1. Interactive CLI Mode (Default)
```bash
cd /home/bruce/Arduino/USBFlashHub/agents
python3 hub_control.py

# Or specify custom configuration
python3 hub_control.py --config hub_config.yaml
```

The interactive CLI provides commands for hub control:

```
USBHub> help
Available commands:

Power Control:
  power <port> <level>      - Set port power (off, low, high)
  power-cycle <port>        - Power cycle a port
  all-off                   - Emergency stop all ports
  bootloader <port> [type]  - Enter bootloader mode

Status & Monitoring:
  status                    - Show hub and port status
  devices [filter]          - List tracked devices
  test-history [device_id]  - Show test history

Automation:
  run-script <script>       - Run automation script

Connection:
  connect [host] [port]     - Connect to hub
  disconnect                - Disconnect from hub
  quit                      - Exit CLI
```

#### Example CLI Session
```
USBHub> connect localhost 81
✓ Connected to localhost:81

USBHub> status
Hub Status
┌─────┬─────────┬──────┬───────┬──────────────┐
│ Hub │ Address │ Port │ Power │ Device       │
├─────┼─────────┼──────┼───────┼──────────────┤
│ 1   │ 0x18    │ 1    │ high │ ESP32-S3     │
│     │         │ 2    │ off   │ None         │
│     │         │ 3    │ high │ STM32        │
│     │         │ 4    │ off   │ None         │
└─────┴─────────┴──────┴───────┴──────────────┘

USBHub> power 2 high
✓ Port 2 power set to high

USBHub> bootloader 3 STM32
✓ Entered bootloader mode for STM32 on port 3

USBHub> devices ESP32
Found 3 devices:
┌────┬───────────┬──────────────┬──────┬───────────┬───────┐
│ ID │ Type      │ Serial       │ Port │ Last Seen │ Tests │
├────┼───────────┼──────────────┼──────┼───────────┼───────┤
│ 5  │ ESP32-S3  │ 1234ABCD     │ 1    │ 12-29 14:30 │ 5 (PASSED) │
│ 8  │ ESP32-C3  │ 5678EFGH     │ 7    │ 12-28 16:22 │ 3 (FAILED) │
└────┴───────────┴──────────────┴──────┴───────────┴───────┘

USBHub> run-script power_cycle_all --ports 1,3,5-8
🔄 Power cycling ports: [1, 3, 5, 6, 7, 8]
📴 Turning off ports...
⏳ Waiting 2.0 seconds...
🔌 Turning on ports...
✅ Power cycle completed successfully
```

#### 2. Dashboard Mode
Real-time status monitoring with a rich terminal interface:

```bash
python3 hub_control.py --mode dashboard
```

The dashboard displays:
- Real-time hub and port status
- Recently connected devices
- System activity log
- Connection status

#### 3. REST API Mode
Start a REST API server for remote control:

```bash
python3 hub_control.py --mode api --api-port 5000
```

API endpoints include:
- `GET /api/status` - Get hub status
- `POST /api/port/<port>/power` - Set port power
- `POST /api/port/<port>/power-cycle` - Power cycle port
- `POST /api/bootloader` - Enter bootloader mode
- `POST /api/emergency-stop` - Emergency stop all ports
- `GET /api/devices` - Get tracked devices
- `GET /api/test-history` - Get test history

### Testing Agent Usage

For automated testing workflows:

1. **Start the USBFlashHub** (ensure it's running on localhost:81)

2. **Run the testing agent**:
```bash
cd /home/bruce/Arduino/USBFlashHub/agents
python3 testing_agent.py --config test_rules.yaml
```

3. **Connect devices** to the hub - the agent will automatically:
   - Detect new devices
   - Match them against rules
   - Execute appropriate test workflows
   - Generate reports

### Command Line Options

```bash
python3 testing_agent.py [options]

Options:
  --config FILE          Configuration file (default: test_rules.yaml)
  --host HOST           USBFlashHub host (default: localhost)
  --port PORT           USBFlashHub WebSocket port (default: 81)
  --report-interval SEC  Report interval in seconds (default: 300)
```

### Example Workflow

When an ESP32-S3 device is connected:

1. **Device Detection**: Agent detects USB device with VID:303a
2. **Rule Matching**: Matches "ESP32-S3 Complete Test" rule
3. **Test Execution**:
   - Powers on the port
   - Waits for device enumeration
   - Enters bootloader mode (boot pin + reset)
   - Flashes firmware using esptool
   - Resets device to run firmware
   - Executes test script
   - Powers off port
4. **Reporting**: Logs results and generates pass/fail report

## Automation Scripts

The Hub Control Agent includes several pre-built automation scripts:

### 1. Power Cycle All Ports
```bash
# Power cycle all ports
python3 automation_scripts/power_cycle_all.py

# Power cycle specific ports with custom timing
python3 automation_scripts/power_cycle_all.py --ports 1,2,5-8 --off-time 3.0

# Power cycle a port group
python3 automation_scripts/power_cycle_all.py --group esp32_dev
```

### 2. Program All ESP32 Devices
```bash
# Program all ESP32 devices with firmware
python3 automation_scripts/program_all_esp32.py firmware.bin

# Program specific device types
python3 automation_scripts/program_all_esp32.py firmware.bin --device-type ESP32-S3

# Program with verification
python3 automation_scripts/program_all_esp32.py firmware.bin --verify --baud 460800
```

### 3. STM32 DFU Mode Entry
```bash
# Put all STM32 devices in DFU mode
python3 automation_scripts/dfu_mode_stm32.py

# Target specific ports
python3 automation_scripts/dfu_mode_stm32.py --ports 5-8

# Verify DFU mode entry
python3 automation_scripts/dfu_mode_stm32.py --verify
```

### 4. Device Inventory
```bash
# Scan all ports and identify devices
python3 automation_scripts/device_inventory.py

# Power on ports before scanning
python3 automation_scripts/device_inventory.py --power-on

# Export results
python3 automation_scripts/device_inventory.py --export inventory.json --update-db
```

### Creating Custom Scripts

Automation scripts can use the hub controller:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from hub_control import HubController, load_config

def main():
    config = load_config("../hub_config.yaml")
    hub = HubController(config=config)

    if not hub.connect():
        return 1

    # Your automation logic here
    hub.power_port(1, "high")
    hub.enter_bootloader_mode(1, "ESP32")

    hub.disconnect()
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

## Device Database

The Hub Control Agent automatically maintains a SQLite database (`devices.db`) that tracks:

### Device Information
- Device types, VID/PID, serial numbers
- Manufacturers and product names
- Port connection history
- First and last seen timestamps

### Test History
- Test results from both agents
- Test duration and error messages
- Firmware versions tested
- Timestamps and port correlations

### Database Queries
```bash
# View database directly
sqlite3 devices.db "SELECT * FROM devices ORDER BY last_seen DESC LIMIT 10;"

# Export test history
sqlite3 -header -csv devices.db "SELECT * FROM test_history;" > test_results.csv
```

### Database Schema
```sql
-- Device tracking
CREATE TABLE devices (
    id INTEGER PRIMARY KEY,
    vendor_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    device_type TEXT,
    serial_number TEXT,
    port_number INTEGER,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    firmware_version TEXT,
    test_count INTEGER DEFAULT 0
);

-- Test history
CREATE TABLE test_history (
    id INTEGER PRIMARY KEY,
    device_id INTEGER,
    test_name TEXT NOT NULL,
    test_result TEXT NOT NULL,
    test_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_seconds REAL,
    firmware_version TEXT,
    port_number INTEGER,
    FOREIGN KEY (device_id) REFERENCES devices (id)
);
```

## Directory Structure

```
agents/
├── hub_control.py           # Hub control agent (NEW)
├── hub_config.yaml          # Hub control configuration (NEW)
├── testing_agent.py         # Testing automation agent
├── test_rules.yaml          # Testing rules configuration
├── requirements.txt         # Python dependencies
├── README.md               # This file
├── devices.db              # Device database (created automatically)
├── hub_control.log         # Hub control log (created when running)
├── testing_agent.log       # Testing agent log (created when running)
├── automation_scripts/     # Automation scripts directory (NEW)
│   ├── power_cycle_all.py  # Power cycle automation
│   ├── program_all_esp32.py # ESP32 programming
│   ├── dfu_mode_stm32.py   # STM32 DFU mode
│   └── device_inventory.py # Device scanning
├── test_firmware/          # Test firmware directory
│   ├── esp32s3_test.bin
│   ├── esp32s2_blink.bin
│   └── stm32_test.bin
└── test_scripts/           # Test scripts directory
    ├── esp32_wifi_test.py
    ├── blink_test.py
    └── arduino_test.py
```

## Creating Test Firmware

### ESP32 Example
```bash
# In your ESP32 project directory
arduino-cli compile --fqbn esp32:esp32:esp32s3 your_project.ino
cp build/esp32.esp32.esp32s3/your_project.ino.bin ../USBFlashHub/agents/test_firmware/esp32s3_test.bin
```

### STM32 Example
```bash
# Build with STM32CubeIDE or similar
cp build/your_project.bin ../USBFlashHub/agents/test_firmware/stm32_test.bin
```

## Creating Test Scripts

Test scripts should exit with code 0 for success, non-zero for failure:

```python
#!/usr/bin/env python3
# test_scripts/esp32_wifi_test.py

import serial
import time
import sys

def test_wifi_connection():
    try:
        # Connect to ESP32 serial port
        ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=10)

        # Send test command
        ser.write(b'test_wifi\\n')

        # Read response
        response = ser.readline().decode().strip()

        # Check for success
        if 'WiFi OK' in response:
            print("WiFi test passed")
            return True
        else:
            print(f"WiFi test failed: {response}")
            return False

    except Exception as e:
        print(f"Test error: {e}")
        return False
    finally:
        if 'ser' in locals():
            ser.close()

if __name__ == "__main__":
    success = test_wifi_connection()
    sys.exit(0 if success else 1)
```

## Supported Device Types

The agent recognizes these device types automatically:

| Device Type | VID:PID | Description |
|-------------|---------|-------------|
| ESP32-S2 | 303a:1001, 303a:0002 | ESP32-S2 boards |
| ESP32-S3 | 303a:1000 | ESP32-S3 boards |
| ESP32-C3 | 303a:80d4 | ESP32-C3 boards |
| ESP32 | 303a:1000 | Original ESP32 |
| STM32-DFU | 0483:df11 | STM32 in DFU mode |
| STM32 | 0483:5740 | STM32 normal mode |
| Arduino-Uno | 2341:0043, 2341:0001 | Arduino Uno |

## Integration Between Agents

The Testing Agent and Hub Control Agent can work together:

### Shared Database
Both agents can share the same device database for unified device tracking:

```yaml
# In hub_config.yaml
testing_agent:
  enabled: true
  share_database: true
  sync_device_info: true
```

### Workflow Integration
1. Use Hub Control Agent to manually set up test conditions
2. Run Testing Agent for automated workflows
3. View consolidated results in Hub Control Agent database

### API Integration
The REST API can trigger Testing Agent workflows:

```bash
# Start hub control API
python3 hub_control.py --mode api &

# Start testing agent
python3 testing_agent.py &

# Control via API
curl -X POST http://localhost:5000/api/port/1/power -d '{"level":"high"}'
```

## Troubleshooting

### Common Issues

1. **Permission denied accessing USB devices**:
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and back in
   ```

2. **Missing Python dependencies**:
   ```bash
   pip3 install -r requirements.txt
   pip3 install rich flask flask-cors  # Optional components
   ```

3. **pyudev import error**:
   ```bash
   sudo apt install python3-pyudev
   # or
   pip3 install pyudev
   ```

4. **WebSocket connection failed**:
   - Ensure USBFlashHub is running on port 81
   - Check host/port settings in configuration
   - Verify firewall settings
   - Test with: `telnet localhost 81`

5. **Device not detected**:
   - Check USB cable connection
   - Verify device appears in `lsusb`
   - Check udev rules
   - Try different USB port

6. **Database errors**:
   ```bash
   # Check database integrity
   sqlite3 devices.db "PRAGMA integrity_check;"

   # Backup and recreate if corrupted
   cp devices.db devices.db.backup
   rm devices.db  # Will recreate automatically
   ```

7. **Flashing failed**:
   - Ensure correct firmware file path
   - Check device is in bootloader mode
   - Verify tool installation (esptool, dfu-util)
   - Check serial port permissions

8. **Rich display issues**:
   ```bash
   # Install rich for better displays
   pip3 install rich

   # Use plain text mode if Rich unavailable
   python3 hub_control.py --no-rich
   ```

### Debug Mode

Enable debug logging by modifying the script:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

### Manual Testing

Test individual components:

```python
# Test USB device detection
from testing_agent import DeviceDetector
detector = DeviceDetector()
detector.start_monitoring()
print(detector.get_all_devices())

# Test hub connection
from testing_agent import USBHubController
hub = USBHubController()
hub.connect()
hub.get_status()
```

## Quick Start Examples

### 1. Basic Hub Control
```bash
# Start interactive CLI
python3 hub_control.py

# Power on a device and enter bootloader mode
USBHub> power 5 high
USBHub> bootloader 5 ESP32

# Check status
USBHub> status
USBHub> devices ESP32
```

### 2. Automation Example
```bash
# Power cycle development ports
python3 automation_scripts/power_cycle_all.py --group esp32_dev

# Program all ESP32 devices
python3 automation_scripts/program_all_esp32.py firmware.bin --verify

# Scan and inventory all connected devices
python3 automation_scripts/device_inventory.py --power-on --update-db
```

### 3. Dashboard Monitoring
```bash
# Real-time status dashboard
python3 hub_control.py --mode dashboard

# REST API for remote access
python3 hub_control.py --mode api --api-port 5000
```

### 4. Integration with Testing Agent
```bash
# Terminal 1: Start hub control API
python3 hub_control.py --mode api

# Terminal 2: Run automated testing
python3 testing_agent.py --config test_rules.yaml

# Terminal 3: Monitor with dashboard
python3 hub_control.py --mode dashboard --no-connect
```

## Contributing

### Adding New Device Types

1. **Update device recognition**:
   - Add VID:PID mapping in `hub_control.py` and `testing_agent.py`
   - Update `hub_config.yaml` device_types section

2. **Add bootloader sequences**:
   - Define bootloader sequence in `hub_config.yaml`
   - Test with actual hardware

3. **Create automation scripts**:
   - Add device-specific automation scripts
   - Update documentation

4. **Add test rules**:
   - Create appropriate rule in `test_rules.yaml`
   - Add flashing tool support if needed

### Adding New Automation Scripts

1. Create script in `automation_scripts/` directory
2. Use `HubController` class for hub communication
3. Follow existing script patterns for argument parsing
4. Add documentation and usage examples

## License

These Python agents are part of the USBFlashHub project.