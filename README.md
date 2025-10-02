# USBFlashHub

ESP32-S2/S3/C3 controller for USB hub management and microcontroller programming. Controls Jim Heaney's I2C USB Hub hardware with simplified static port numbering and direct pin control.

## Features

- **Multi-Board Support**: ESP32-S2, ESP32-S3, ESP32-C3, and original ESP32
- **Web Interface**: Real-time WebSocket control via browser
- **I2C Hub Control**: Manages up to 8 hubs (32 USB ports total)
- **Power Management**: Per-port power control (Off/100mA/500mA)
- **LED Control**: Status, activity, and error indication (RGB on S3)
- **Pin Control**: Direct boot/reset pin control for device programming
- **Activity Logging**: PSRAM-based circular buffer with 5000+ entries
- **Python Automation**: Testing agents and control scripts included

## Hardware Support

### Supported Boards
- **ESP32-S2** (Wemos S2 Mini)
- **ESP32-S3** (S3 Zero with RGB LED)
- **ESP32-C3** (C3 Zero/Mini)
- **ESP32** (Original)

### Hub Hardware
Compatible with Jim Heaney's I2C-controlled USB Hub using PCA9557PW I/O expanders at addresses 0x18-0x1F.

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
```

**ESP32-C3:**
```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc USBFlashHub.ino
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
{"cmd":"port","port":1,"power":"500mA"}
{"cmd":"port","port":5,"power":"off"}
```

**Pin Control:**
```json
{"cmd":"boot","state":true}
{"cmd":"reset","state":false}
{"cmd":"reset","pulse":100}
```

**Hub Control:**
```json
{"cmd":"hub","hub":1,"led":true}
{"cmd":"alloff"}
```

**Status:**
```json
{"cmd":"status"}
{"cmd":"log"}
```

## Port Numbering

Ports are numbered sequentially across hubs:
- Hub 1 (0x18): Ports 1-4
- Hub 2 (0x19): Ports 5-8
- Hub 3 (0x1A): Ports 9-12
- Hub 4 (0x1B): Ports 13-16
- Hub 5 (0x1C): Ports 17-20
- Hub 6 (0x1D): Ports 21-24
- Hub 7 (0x1E): Ports 25-28
- Hub 8 (0x1F): Ports 29-32

## Pin Assignments

Varies by board - see [CLAUDE.md](CLAUDE.md) for complete pin mappings.

## Python Automation

The `agents/` directory contains:
- `turn_on_all_ports.py` - Smart port detection and activation
- `hub_control.py` - Interactive CLI and dashboard
- `testing_agent.py` - Automated device testing with YAML rules
- `automation_scripts/` - Batch programming and power cycling

See [agents/README.md](agents/README.md) for details.

## Activity Logging

The system maintains a circular buffer activity log:
- 5000+ entries in PSRAM (if available)
- 100 entries in regular RAM (fallback)
- **Note**: Log is volatile and cleared on reboot
- Accessible via web interface or `{"cmd":"log"}` command

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

Based on Jim Heaney's I2C USB Hub hardware design.

## Documentation

- [CLAUDE.md](CLAUDE.md) - Detailed technical documentation
- [agents/README.md](agents/README.md) - Python automation guide
