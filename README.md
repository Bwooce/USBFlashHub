# USBFlashHub

ESP32-S2/S3/C3 controller for USB hub management and microcontroller programming.

**Hardware-Specific:** This firmware is designed exclusively for [Jim Heaney's I2C-Controlled USB Hub](https://github.com/JimHeaney/i2c-usb-hub) hardware. It will not work with other USB hubs.

Provides simplified static port numbering and direct pin control for the I2C USB Hub hardware.

## Features

- **Multi-Board Support**: ESP32-S2, ESP32-S3, ESP32-C3, and original ESP32
- **Web Interface**: Real-time WebSocket control via browser with editable system name
- **I2C Hub Control**: Manages up to 8 hubs (32 USB ports total)
- **Power Management**: Per-port power control (Off/Low/High - actual mA values depend on resistor configuration)
- **Port Naming**: Assign persistent names to ports (max 10 chars, stored in NVS)
- **System Name**: Customizable system name for UI and mDNS hostname (max 15 chars)
- **LED Control**: Status, activity, and error indication (RGB on S3)
- **Pin Control**: Direct boot/reset pin control for device programming
- **Relay Control**: External 5V power control via High Level Trigger SSR
- **Activity Logging**: PSRAM-based circular buffer with up to 10,000 entries
- **Python Automation**: Testing agents and control scripts included
- **Robust I2C**: Automatic retry with exponential backoff for reliability
- **WiFi Configuration**: Over-the-air WiFi setup and mDNS hostname

## Hardware Support

### Hub PCA9557 Bit Mapping
| Bit | Function | Hardware Designator |
|-----|----------|---------------------|
| 0 | Current Limit Toggle | P0 |
| 1 | USB-C VBUS Path (Switch) | U7 / Q5 |
| 3 | Status LEDs | LED1-4 |
| 4 | USB-A Port 1 | U3 / Q1 |
| 5 | USB-A Port 2 | U4 / Q2 |
| 6 | USB-A Port 3 | U5 / Q3 |
| 7 | USB-A Port 4 | U6 / Q4 |

**Hardware Reasoning:**
- **USB-C VBUS Path**: Bit 1 (U7 / Q5) enables the power path between the USB-C VBUS and the main 5V rail. This allows the hub to be powered via USB-C or to provide 5V power to the USB-C port.
- **Current Alignment**: The current limit (Bit 0) is shared across all load switches (U3-U7), ensuring that USB-C side current configuration is always aligned with the overall high/low current setting.
- **Warning**: Avoid cross-connecting 5V from the header pin and 5V from the USB-C port unless intended. Bit 1 connects these rails directly.

### Supported Boards
- **ESP32-S2** (Wemos S2 Mini)
- **ESP32-S3** (S3 Zero with RGB LED)
- **ESP32-C3** (C3 Zero/Mini)
- **ESP32** (Original)

### Hub Hardware

**This firmware is designed exclusively for [Jim Heaney's I2C-Controlled USB Hub](https://github.com/JimHeaney/i2c-usb-hub).**

- Uses PCA9557PW I2C GPIO expanders at addresses 0x18-0x1F
- MT9700 load switches for per-port current limiting
- For complete hardware specifications, schematics, and BOM, see the [hardware repository](https://github.com/JimHeaney/i2c-usb-hub)

## Quick Start

### Prerequisites
- Arduino IDE or arduino-cli
- ESP32 board support package
- Required libraries:
  - ArduinoJson
  - WebSockets by Markus Sattler
  - Adafruit NeoPixel (for ESP32-S3 only)

### Compilation

**ESP32-S3:**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc,PSRAM=enabled USBFlashHub.ino
arduino-cli upload --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc,PSRAM=enabled -p /dev/ttyACM0 USBFlashHub.ino
```

**ESP32-S2:**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32s2:CDCOnBoot=cdc,PSRAM=enabled USBFlashHub.ino
arduino-cli upload --fqbn esp32:esp32:esp32s2:CDCOnBoot=cdc,PSRAM=enabled -p /dev/ttyACM0 USBFlashHub.ino
```

**ESP32-C3:**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc USBFlashHub.ino
arduino-cli upload --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc -p /dev/ttyACM0 USBFlashHub.ino
```

**ESP32 (Original):**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32 USBFlashHub.ino
arduino-cli upload --fqbn esp32:esp32:esp32 -p /dev/ttyUSB0 USBFlashHub.ino
```

### Upload Web Interface
```bash
python3 upload_data.py
```

## Usage

### Web Interface
Connect to `http://usbhub.local` (or device IP address) for browser-based control.

### Python Agents

**Turn on all ports:**
```bash
cd agents
python3 turn_on_all_ports.py
```

**Interactive control:**
```bash
python3 hub_control.py --mode cli
```

**Automated testing:**
```bash
python3 testing_agent.py --config test_rules.yaml
```

### WebSocket Commands

**Port Control:**
```json
{"cmd":"port","port":1,"power":"high"}
{"cmd":"port","port":5,"power":"off"}
{"cmd":"port","port":1,"power":"low"}
{"cmd":"port","port":3,"enable":true}
{"cmd":"port","port":3,"enable":false}
```

**Port Naming:**
```json
{"cmd":"portname","port":5,"name":"ESP32-Dev"}
{"cmd":"portname","port":5,"name":""}
```
*Names: max 10 characters, alphanumeric, underscore, and hyphen only. Stored in NVS (persistent across reboots).*

**System Name:**
```json
{"cmd":"systemname","name":"MyHub"}
```
*System name: max 15 characters, alphanumeric, underscore, and hyphen only (no spaces). Used for UI title and mDNS hostname. Stored in NVS.*

**Pin Control:**
```json
{"cmd":"boot","state":true}
{"cmd":"boot","state":false}
{"cmd":"reset","state":true}
{"cmd":"reset","state":false}
{"cmd":"reset","pulse":100}
```

**Hub Control:**
```json
{"cmd":"hub","hub":1,"led":true}
{"cmd":"hub","hub":1,"led":false}
{"cmd":"hub","hub":1,"usbc":true}
{"cmd":"hub","hub":1,"usbc":false}
{"cmd":"hub","hub":1,"state":255}
{"cmd":"alloff"}
```

**LED Control:**
```json
{"cmd":"led","led":"status","action":"on"}
{"cmd":"led","led":"activity","action":"flash"}
{"cmd":"led","led":"error"}
```

**Relay Control:**
```json
{"cmd":"relay","state":true}
{"cmd":"relay","state":false}
{"cmd":"relay","default":true}
```
*Controls external 5V power via High Level Trigger SSR. Integrated with emergency stop. Default: ON on boot (configurable).*

**System Commands:**
```json
{"cmd":"status"}
{"cmd":"log"}
{"cmd":"ping"}
{"cmd":"help"}
```

**WiFi Configuration:**
```json
{"cmd":"config","wifi":{"ssid":"MyNetwork","pass":"password"}}
{"cmd":"config","wifi":{"enable":false}}
{"cmd":"config","mdns":"usbhub"}
{"cmd":"config"}
```

## Power Levels

The hub supports three power levels: **off**, **low**, and **high**.

**Important:** The actual current values depend on the resistor configuration in your specific hardware build:
- Current limiting is performed by **MT9700 load switch chips** with series-switched resistor ladder on SET pin
- **MT9700 formula:** I_LIMIT = 6.8kΩ / R_SET
- **Current BOM values:** Two 30kΩ resistors in series-switched configuration
  - High power: ~227mA (one 30kΩ resistor)
  - Low power: ~113mA (both 30kΩ resistors in series = 60kΩ)
- **Hardware configurable** - resistor values can be changed to adjust current limits
- For resistor selection and schematic details, see [Jim Heaney's hardware repository](https://github.com/JimHeaney/i2c-usb-hub)

## Pin Assignments

Varies by board - see [CLAUDE.md](CLAUDE.md) for complete pin mappings.

## Python Automation

The `agents/` directory contains:
- `turn_on_all_ports.py` - Smart port detection and activation with LED control
- `hub_control.py` - Interactive CLI, dashboard, and REST API
- `testing_agent.py` - Automated device testing with YAML rules
- `automation_scripts/` - Batch programming, power cycling, and inventory

See [agents/README.md](agents/README.md) for details.

## Activity Logging

The system maintains a circular buffer activity log:
- **Up to 10,000 entries** in PSRAM (dynamically sized to 75% of available PSRAM)
- **100 entries** in regular RAM (fallback when PSRAM unavailable)
- **Note**: Log is volatile and cleared on reboot
- Accessible via web interface or `{"cmd":"log"}` command
- Real-time log entries broadcast via WebSocket

## Reliability Features

### I2C Error Recovery
- **Automatic retry** with exponential backoff (3 attempts: 10ms, 20ms, 30ms delays)
- Prevents hub lockups from transient I2C errors (EMI, loose connections)
- Applied to all hub control operations

### Watchdog Protection
- **10-second watchdog timer** with automatic feeding
- Log serialization protected with timeout (5 seconds max)
- Supports continuous operation with large PSRAM logs

### Memory Management
- **No heap fragmentation**: Stack-based buffers for stats logging
- **Leak prevention**: Automatic cleanup on re-initialization
- **PSRAM tracking**: Separate monitoring of SRAM and PSRAM usage

### Long-Term Stability
- **Millis() rollover handling**: Continues operation after 49.7 days uptime
- **WebSocket buffer validation**: Prevents buffer overflow attacks
- **Non-blocking operations**: Emergency stop and reset sequences don't block main loop

## WiFi Configuration

### Default Settings
- **SSID**: Configure via web interface or serial command
- **mDNS hostname**: `usbhub.local` (customizable)
- **Web server**: Port 80
- **WebSocket**: Port 81

### First-Time Setup
1. Connect to device via USB serial (115200 baud)
2. Send WiFi config command:
   ```json
   {"cmd":"config","wifi":{"ssid":"YourNetwork","pass":"YourPassword"}}
   ```
3. Device will restart and connect to WiFi
4. Access via `http://usbhub.local`

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Hardware Design

This firmware is designed exclusively for **Jim Heaney's I2C-Controlled USB Hub** hardware.

**Hardware Repository:** https://github.com/JimHeaney/i2c-usb-hub

The hardware design includes:
- Detailed schematics and PCB layouts
- Bill of Materials (BOM)
- Design notes and assembly instructions
- Current limiting resistor configurations

**Important:** This software will not work with other USB hubs. Consult the hardware repository for build instructions, component specifications, and design documentation.

## Documentation

- [CLAUDE.md](CLAUDE.md) - Detailed technical documentation and command reference
- [agents/README.md](agents/README.md) - Python automation guide
