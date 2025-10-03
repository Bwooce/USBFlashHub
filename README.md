# USBFlashHub

ESP32-S2/S3/C3 controller for USB hub management and microcontroller programming. Controls Jim Heaney's I2C USB Hub hardware with simplified static port numbering and direct pin control.

## Features

- **Multi-Board Support**: ESP32-S2, ESP32-S3, ESP32-C3, and original ESP32
- **Web Interface**: Real-time WebSocket control via browser
- **I2C Hub Control**: Manages up to 8 hubs (32 USB ports total)
- **Power Management**: Per-port power control (Off/100mA/500mA)
- **LED Control**: Status, activity, and error indication (RGB on S3)
- **Pin Control**: Direct boot/reset pin control for device programming
- **Activity Logging**: PSRAM-based circular buffer with up to 10,000 entries
- **Python Automation**: Testing agents and control scripts included
- **Robust I2C**: Automatic retry with exponential backoff for reliability
- **WiFi Configuration**: Over-the-air WiFi setup and mDNS hostname

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
{"cmd":"port","port":1,"power":"500mA"}
{"cmd":"port","port":5,"power":"off"}
{"cmd":"port","port":1,"power":"100mA"}
{"cmd":"port","port":3,"enable":true}
{"cmd":"port","port":3,"enable":false}
```

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
{"cmd":"hub","hub":1,"state":255}
{"cmd":"alloff"}
```

**LED Control:**
```json
{"cmd":"led","led":"status","action":"on"}
{"cmd":"led","led":"activity","action":"flash"}
{"cmd":"led","led":"error"}
```

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

## Credits

Based on Jim Heaney's I2C USB Hub hardware design.

## Documentation

- [CLAUDE.md](CLAUDE.md) - Detailed technical documentation and command reference
- [agents/README.md](agents/README.md) - Python automation guide
