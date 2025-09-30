# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
USBFlashHub - ESP32-S2 controller for USB hub management and microcontroller programming. Controls Jim Heaney's I2C USB Hub hardware with simplified static port numbering and direct pin control.

## Build Instructions
- Supported Boards:
  - ESP32-S2 (Wemos S2 Mini)
  - ESP32-C3 (C3 Zero/Mini)
  - ESP32-S3 (S3 Zero with onboard RGB LED)
  - ESP32 (Original)
- Required libraries:
  - ArduinoJson (via Library Manager)
  - WebSockets by Markus Sattler
  - Adafruit NeoPixel (for S3-Zero RGB LED)
- Serial: 115200 baud
- Compile with Arduino IDE or arduino-cli
- Auto-detects board type at compile time

## Key Simplifications from Original
- **Static Port Numbering**: Ports 1-32 mapped sequentially across hubs
- **Direct Pin Control**: Boot/Reset pins just HIGH/LOW (no per-board config)
- **Hardcoded Hub Addresses**: Up to 8 hubs at 0x18-0x1F (configurable via MAX_HUBS)
- **Power Level Control**: Off/100mA/500mA per USB spec
- **LED Management**: Dedicated LED controller class

## Architecture

### Port Numbering
```
Hub 1 (0x18): Ports 1-4
Hub 2 (0x19): Ports 5-8
Hub 3 (0x1A): Ports 9-12
Hub 4 (0x1B): Ports 13-16
Hub 5 (0x1C): Ports 17-20
Hub 6 (0x1D): Ports 21-24
Hub 7 (0x1E): Ports 25-28
Hub 8 (0x1F): Ports 29-32
```

### Hardware Pins (Board-Specific)

**ESP32-S2 (Wemos S2 Mini):**
```
I2C_SDA: GPIO 33
I2C_SCL: GPIO 35
BOOT_PIN: GPIO 11
RESET_PIN: GPIO 12 (active LOW)
STATUS_LED: GPIO 15
ACTIVITY_LED: GPIO 13
EMERGENCY_BTN: GPIO 0
```

**ESP32-C3 (C3 Zero/Mini):**
```
I2C_SDA: GPIO 4
I2C_SCL: GPIO 5
BOOT_PIN: GPIO 6
RESET_PIN: GPIO 7 (active LOW)
STATUS_LED: GPIO 8
ACTIVITY_LED: GPIO 10
EMERGENCY_BTN: GPIO 9
```

**ESP32-S3 (S3 Zero/Mini):**
```
I2C_SDA: GPIO 2
I2C_SCL: GPIO 1
BOOT_PIN: GPIO 3
RESET_PIN: GPIO 4 (active LOW)
RGB_LED: GPIO 21 (onboard WS2812)
EMERGENCY_BTN: GPIO 0

LED Colors:
- Green: Status OK
- Blue: Activity flash
- Red: Error pattern
```

**ESP32 (Original):**
```
I2C_SDA: GPIO 21
I2C_SCL: GPIO 22
BOOT_PIN: GPIO 13
RESET_PIN: GPIO 12 (active LOW)
STATUS_LED: GPIO 2
ACTIVITY_LED: GPIO 4
EMERGENCY_BTN: GPIO 0
```

### Power Levels
```
POWER_OFF: 0x00 (disabled)
POWER_100MA: 0x01 (USB 2.0 low power)
POWER_500MA: 0x03 (USB 2.0 high power, default)
```

## Activity Logging

**Important Note on Persistence:**
- The activity log uses PSRAM for large buffer capacity
- **PSRAM is volatile memory** - it loses contents on ANY reset (power cycle, software reset, watchdog, etc.)
- PSRAM is only preserved during deep sleep, not during normal reboots
- The log is **not persistent across reboots** by design for performance
- For persistent logging, logs should be retrieved via WebSocket before rebooting
- Future enhancement: Optional flash storage (LittleFS) for persistent logs

## Command Interface

### Important Hardware Notes

**Hardware Configuration:**
- Software supports up to 8 hubs (32 ports total: 8 hubs × 4 ports each)
- Actual connected hardware varies by build
- LEDs are controlled per-hub, not per-port
- Always turn on LEDs when activating ports for visual feedback

**Quick Turn On All Ports:**
```bash
# Smart script that detects actual hardware
cd agents
python3 turn_on_all_ports.py

# One-liner to attempt all possible ports and hubs with LEDs
python3 -c "import websocket,json,time; ws=websocket.WebSocket(); ws.connect('ws://usbhub.local:81'); [ws.send(json.dumps({'cmd':'port','port':p,'power':'500mA'})) or time.sleep(0.02) for p in range(1,33)]; [ws.send(json.dumps({'cmd':'hub','hub':h,'led':True})) for h in range(1,9)]; print('Done')"
```

### Port Control
```json
{"cmd":"port","port":1,"power":"500mA"}    // Set power level
{"cmd":"port","port":5,"power":"off"}      // Turn off port
{"cmd":"port","port":3,"enable":true}      // Legacy enable/disable
```

### Hub Control
```json
{"cmd":"hub","hub":1,"state":255}          // Set raw hub state
{"cmd":"alloff"}                            // Emergency stop all
```

### Pin Control (Direct HIGH/LOW)
```json
{"cmd":"boot","state":true}                // Boot pin HIGH
{"cmd":"boot","state":false}               // Boot pin LOW
{"cmd":"reset","state":true}               // Assert reset (pin goes LOW)
{"cmd":"reset","state":false}              // Release reset (pin goes HIGH)
{"cmd":"reset","pulse":100}                // Pulse reset for 100ms
```

### LED Control
```json
{"cmd":"led","led":"status","action":"on"}
{"cmd":"led","led":"activity","action":"flash"}
{"cmd":"led","led":"error"}                // Error pattern
```

### Status
```json
{"cmd":"status"}                            // Full system status
{"cmd":"ping"}                              // Connectivity check
{"cmd":"help"}                              // Command reference
```

## Programming Different Boards

Since boot/reset pin meanings vary by target:
- **ESP32**: Boot=LOW for bootloader, Reset=active LOW
- **STM32**: Boot=HIGH for DFU mode, Reset=active LOW
- User must set appropriate pin states for their target device

## USB Device Identification

The ESP32-S2/S3 appears as a custom USB device with:
- **Manufacturer**: "USBFlashHub Project"
- **Product**: "Hub Controller"
- **Serial Number**: Unique ID based on MAC (e.g., "HUBCTL_507817F0F4")

To customize, edit these defines in USBFlashHub.ino:
```cpp
#define USB_MANUFACTURER_NAME "USBFlashHub Project"
#define USB_PRODUCT_NAME      "Hub Controller"
#define USB_SERIAL_PREFIX     "HUBCTL_"
```

## Python Automation Agents

### Testing Agent (agents/testing_agent.py)
Automated device testing with rules engine:
```bash
cd agents
./install.sh  # First time only
python3 testing_agent.py --config test_rules.yaml
```

Features:
- USB device detection and port correlation
- YAML-based test workflows
- Support for ESP32, STM32, Arduino devices
- Automatic firmware flashing and testing

Example rule in test_rules.yaml:
```yaml
- name: "ESP32-S3 Test"
  device_match:
    vid_pid: "303a:1001"  # ESP32-S3
  steps:
    - action: power_on
      port: auto
      power: 500mA
    - action: enter_bootloader
      method: boot_reset
    - action: flash_firmware
      file: "firmware.bin"
      tool: esptool
```

### Hub Control Agent (agents/hub_control.py)
Interactive control and monitoring:
```bash
python3 hub_control.py --mode cli     # Interactive CLI
python3 hub_control.py --mode dashboard  # Real-time dashboard
python3 hub_control.py --mode api     # REST API server
```

CLI Commands:
- `power <port> <off|100mA|500mA>` - Control port power
- `bootloader <port> <device_type>` - Enter bootloader mode
- `status` - Show hub status
- `inventory` - List all known devices
- `all-off` - Emergency stop

### Automation Scripts
Ready-to-use scripts in agents/automation_scripts/:
- `power_cycle_all.py` - Power cycle all/specific ports
- `program_all_esp32.py` - Batch program ESP32 devices
- `dfu_mode_stm32.py` - Put STM32s in DFU mode
- `device_inventory.py` - Scan and catalog devices

Example usage:
```bash
# Program all ESP32s with new firmware
./automation_scripts/program_all_esp32.py firmware.bin

# Power cycle specific ports
./automation_scripts/power_cycle_all.py --ports 1,2,3 --delay 2

# Scan all ports and update device database
./automation_scripts/device_inventory.py
```

### Database Queries
Hub Control agent maintains SQLite database of devices:
```sql
-- Find all ESP32 devices
SELECT * FROM devices WHERE product_name LIKE '%ESP32%';

-- Get test history for a device
SELECT * FROM test_runs WHERE device_serial = 'ABC123' ORDER BY timestamp DESC;

-- Find which port a device was last connected to
SELECT * FROM port_history WHERE device_serial = 'ABC123' ORDER BY timestamp DESC LIMIT 1;
```

## Compile Commands

**ESP32-S2:**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32s2:CDCOnBoot=cdc,PSRAM=enabled USBFlashHub.ino
```

**ESP32-C3:**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc USBFlashHub.ino
```

**ESP32-S3:**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc,PSRAM=enabled USBFlashHub.ino
```

**ESP32 (Original):**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32 USBFlashHub.ino
```