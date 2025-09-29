#!/bin/bash
# USBFlashHub Testing Agent Installation Script

set -e

echo "Installing USBFlashHub Testing Agent dependencies..."

# Check if running on supported system
if ! command -v apt-get &> /dev/null; then
    echo "Warning: This script is designed for Ubuntu/Debian systems"
    echo "Please install dependencies manually:"
    echo "- Python 3.8+"
    echo "- pyudev"
    echo "- PyYAML"
    echo "- websocket-client"
    echo "- dfu-util (for STM32 support)"
    echo "- esptool (for ESP32 support)"
    exit 1
fi

# Update package list
echo "Updating package list..."
sudo apt-get update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y python3 python3-pip python3-pyudev dfu-util avrdude

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Install optional ESP32 tools
echo "Installing ESP32 tools..."
pip3 install esptool

# Set up permissions for USB access
echo "Setting up USB permissions..."
sudo usermod -a -G dialout $USER

# Make scripts executable
echo "Making test scripts executable..."
chmod +x test_scripts/*.py

# Create log directory
mkdir -p logs

echo ""
echo "Installation completed successfully!"
echo ""
echo "IMPORTANT: You need to log out and back in for USB permissions to take effect."
echo ""
echo "To test the installation:"
echo "1. Start your USBFlashHub device"
echo "2. Run: python3 testing_agent.py --config test_rules.yaml"
echo "3. Connect a USB device to test"
echo ""
echo "See README.md for detailed usage instructions."