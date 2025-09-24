# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
USBFlashHub - ESP32-S2 controller for USB hub management and microcontroller programming. Controls Jim Heaney's I2C USB Hub hardware with simplified static port numbering and direct pin control.

## Build Instructions
- Board: ESP32S2 Dev Module or Wemos S2 Mini
- Required library: ArduinoJson (via Library Manager)
- Serial: 115200 baud
- Compile with Arduino IDE or arduino-cli

## Key Simplifications from Original
- **Static Port Numbering**: Ports 1-16 mapped sequentially across hubs
- **Direct Pin Control**: Boot/Reset pins just HIGH/LOW (no per-board config)
- **Hardcoded Hub Addresses**: Up to 4 hubs at 0x44-0x47 (configurable via MAX_HUBS)
- **Power Level Control**: Off/100mA/500mA per USB spec
- **LED Management**: Dedicated LED controller class

## Architecture

### Port Numbering
```
Hub 1 (0x44): Ports 1-4
Hub 2 (0x45): Ports 5-8
Hub 3 (0x46): Ports 9-12
Hub 4 (0x47): Ports 13-16
```

### Hardware Pins
```
I2C_SDA: GPIO 33
I2C_SCL: GPIO 35
BOOT_PIN: GPIO 11
RESET_PIN: GPIO 12 (active LOW)
STATUS_LED: GPIO 15
ACTIVITY_LED: GPIO 13
EMERGENCY_BTN: GPIO 0
```

### Power Levels
```
POWER_OFF: 0x00 (disabled)
POWER_100MA: 0x01 (USB 2.0 low power)
POWER_500MA: 0x03 (USB 2.0 high power, default)
```

## Command Interface

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