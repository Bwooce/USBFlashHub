// USBFlashHub.ino
// Target Board: ESP32-S2 Mini (Wemos S2 Mini or similar)
// Purpose: USB hub control and microcontroller programming interface
// Features: Static port numbering, simplified pin control, LED management
// Controls the USB i2c hub(s) from Jim Heaney (https://github.com/JimHeaney/i2c-usb-hub)
//
// ============================================
// COMMAND FORMAT REFERENCE
// ============================================
// Port Control:
//   {"cmd":"port","port":1,"power":"500mA"}    // Set power level (off/100mA/500mA)
//   {"cmd":"port","port":5,"power":"off"}      // Turn off port
//
// Hub Control:
//   {"cmd":"hub","hub":1,"state":255}          // Set raw hub state (8-bit value)
//   {"cmd":"hub","hub":1}                      // Query hub state
//   {"cmd":"alloff"}                            // Emergency stop all ports
//
// Pin Control (Direct HIGH/LOW):
//   {"cmd":"boot","state":true}                // Boot pin HIGH
//   {"cmd":"boot","state":false}               // Boot pin LOW
//   {"cmd":"reset","state":true}               // Assert reset (pin goes LOW)
//   {"cmd":"reset","state":false}              // Release reset (pin goes HIGH)
//   {"cmd":"reset","pulse":100}                // Pulse reset LOW for 100ms then back HIGH
//
// LED Control:
//   {"cmd":"led","led":"status","action":"on"}      // on/off/blink
//   {"cmd":"led","led":"activity","action":"flash"} // flash/on/off
//   {"cmd":"led","led":"error"}                     // Error pattern
//
// Status:
//   {"cmd":"status"}                            // Full system status
//   {"cmd":"ping"}                              // Connectivity check
//   {"cmd":"help"}                              // Command reference
//   {"cmd":"log"}                               // Get activity log (last 100 events)
//
// Configuration:
//   {"cmd":"config","wifi":{"ssid":"MyNetwork","pass":"password"}}  // Set WiFi
//   {"cmd":"config","wifi":{"enable":false}}                        // Disable WiFi
//   {"cmd":"config","mdns":"usbhub"}                                // Set mDNS name
//   {"cmd":"config"}                                                 // Get config
//
// Port Numbering:
//   Hub 1 (0x44): Ports 1-4
//   Hub 2 (0x45): Ports 5-8
//   Hub 3 (0x46): Ports 9-12
//   Hub 4 (0x47): Ports 13-16
//
// ============================================
// RESPONSE FORMATS
// ============================================
// Success Response:
//   {"status":"ok","msg":"Description of action"}
//   {"status":"ok","port":1,"power":"500mA"}
//
// Error Response:
//   {"status":"error","msg":"Error description","detail":"Optional details"}
//
// Status Response:
//   {
//     "status":"ok",
//     "device":"USBFlashHub",
//     "version":"2.0",
//     "uptime":12345,
//     "commands":10,
//     "pins":{"boot":"LOW","reset":"released"},
//     "hubs":[
//       {
//         "num":1,"addr":68,"state":255,
//         "ports":[
//           {"num":1,"power":"500mA"},
//           {"num":2,"power":"off"},
//           {"num":3,"power":"100mA"},
//           {"num":4,"power":"500mA"}
//         ]
//       }
//     ]
//   }
//
// SERIAL PORT: 115200 baud, 8N1
// ============================================

#include <Wire.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <time.h>
#include <esp_task_wdt.h>
#include <WebServer.h>
#include <WebSocketsServer.h>
#include <LittleFS.h>

// RGB LED support for S3-Zero
#if defined(CONFIG_IDF_TARGET_ESP32S3)
  #include <Adafruit_NeoPixel.h>
#endif

// ============================================
// Board Detection and Pin Assignments
// ============================================

// Detect which ESP32 variant we're compiling for
#if defined(CONFIG_IDF_TARGET_ESP32S2)
  #define BOARD_TYPE "ESP32-S2"
  #pragma message("Compiling for ESP32-S2")
  // ESP32-S2 Mini / Wemos S2 Mini Pin Assignments
  // I2C for USB Hub control
  #define I2C_SDA 33
  #define I2C_SCL 35
  // Programming control pins
  #define BOOT_PIN 11
  #define RESET_PIN 12  // Active LOW
  // Status LEDs
  #define STATUS_LED 15
  #define ACTIVITY_LED 13
  // Emergency stop (optional)
  #define EMERGENCY_BTN 0  // Built-in button on GPIO0

#elif defined(CONFIG_IDF_TARGET_ESP32C3)
  #define BOARD_TYPE "ESP32-C3"
  #pragma message("Compiling for ESP32-C3")
  // ESP32-C3 Zero / C3 Mini Pin Assignments
  // I2C for USB Hub control
  #define I2C_SDA 4
  #define I2C_SCL 5
  // Programming control pins
  #define BOOT_PIN 6
  #define RESET_PIN 7  // Active LOW
  // Status LEDs
  #define STATUS_LED 8
  #define ACTIVITY_LED 10
  // Emergency stop (optional)
  #define EMERGENCY_BTN 9  // Boot button on C3 Zero

#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  #define BOARD_TYPE "ESP32-S3"
  #pragma message("Compiling for ESP32-S3")
  // ESP32-S3 Zero/Mini Pin Assignments
  // I2C for USB Hub control
  #define I2C_SDA 1
  #define I2C_SCL 2
  // Programming control pins
  #define BOOT_PIN 3
  #define RESET_PIN 4  // Active LOW
  // S3-Zero has onboard WS2812 RGB LED
  #define RGB_LED_PIN 21
  #define RGB_LED_COUNT 1
  #define RGB_LED_BRIGHTNESS 50
  #define USE_RGB_LED
  // Dummy pins for compatibility (not used with RGB LED)
  #define STATUS_LED 255
  #define ACTIVITY_LED 255
  // Emergency stop (optional)
  #define EMERGENCY_BTN 0  // Built-in button on GPIO0

#elif defined(CONFIG_IDF_TARGET_ESP32)
  #define BOARD_TYPE "ESP32"
  #pragma message("Compiling for ESP32")
  // Original ESP32 Pin Assignments
  // I2C for USB Hub control
  #define I2C_SDA 21
  #define I2C_SCL 22
  // Programming control pins
  #define BOOT_PIN 13
  #define RESET_PIN 12  // Active LOW
  // Status LEDs
  #define STATUS_LED 2
  #define ACTIVITY_LED 4
  // Emergency stop (optional)
  #define EMERGENCY_BTN 0  // Built-in button on GPIO0

#else
  #error "Unsupported ESP32 variant. Please use ESP32, ESP32-S2, ESP32-S3, or ESP32-C3"
#endif

// NTP Configuration
#define NTP_SERVER "pool.ntp.org"
#define GMT_OFFSET_SEC 0
#define DAYLIGHT_OFFSET_SEC 0

// Timing Configuration
#define WDT_TIMEOUT         10    // 10 seconds watchdog timeout
#define ACTIVITY_FLASH_MS   50    // Activity LED flash duration
#define ERROR_FLASH_MS      100   // Error pattern flash duration
#define RESET_PULSE_MS      100   // Default reset pulse duration
#define RECONNECT_DELAY_MS  30000 // WiFi reconnect delay
#define HEARTBEAT_INTERVAL  5000  // Status LED heartbeat interval
#define BROADCAST_INTERVAL  2000  // WebSocket broadcast interval

// ============================================
// USB HUB CONFIGURATION
// ============================================
// Hardcoded hub addresses for consistent port numbering
// Port numbering: Hub 1 = ports 1-4, Hub 2 = ports 5-8, etc.
#define MAX_HUBS          8   // Number of USB hubs in the system
#define PORTS_PER_HUB     4   // Each hub controls 4 ports
#define TOTAL_PORTS       (MAX_HUBS * PORTS_PER_HUB)  // Calculate total ports

const uint8_t HUB_ADDRESSES[MAX_HUBS] = {
  0x18,  // Hub 1: ports 1-4
  0x19,  // Hub 2: ports 5-8
  0x1A,  // Hub 3: ports 9-12
  0x1B,  // Hub 4: ports 13-16
  0x1C,  // Hub 5: ports 17-20
  0x1D,  // Hub 6: ports 21-24
  0x1E,  // Hub 7: ports 25-28
  0x1F   // Hub 8: ports 29-32
};

// USB Power levels per USB spec
// Bit patterns for power control:
// Bits [1:0] control power level:
#define POWER_OFF     0x00  // Port disabled
#define POWER_100MA   0x01  // USB 2.0 low power (100mA)
#define POWER_500MA   0x03  // USB 2.0 high power (500mA)
#define POWER_DEFAULT POWER_500MA

// ============================================
// HUB CONTROLLER CLASS
// ============================================
class HubController {
private:
  TwoWire* wire;
  uint8_t hubStates[MAX_HUBS];  // Bit 0: current, Bit 3: LED, Bits 4-7: ports
  uint8_t portPowerStates[TOTAL_PORTS];  // Track desired power level per port
  uint8_t connectedHubs[MAX_HUBS];  // Track which hubs are actually connected
  uint8_t numConnected;
  uint32_t lastActivity;

public:
  HubController(TwoWire* i2c) : wire(i2c), lastActivity(0), numConnected(0) {
    memset(hubStates, 0x01, sizeof(hubStates));  // Start with 100mA limit (bit 0 set)
    memset(portPowerStates, POWER_OFF, sizeof(portPowerStates));
    memset(connectedHubs, 0, sizeof(connectedHubs));
  }

  bool begin() {
    numConnected = 0;
    Serial.println(F("========================================"));
    Serial.println(F("I2C Hub Scanner Starting"));
    Serial.print(F("I2C SDA Pin: GPIO"));
    Serial.println(I2C_SDA);
    Serial.print(F("I2C SCL Pin: GPIO"));
    Serial.println(I2C_SCL);
    Serial.println(F("Scanning I2C bus for all devices..."));

    // First do a complete I2C bus scan
    uint8_t deviceCount = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
      wire->beginTransmission(addr);
      uint8_t error = wire->endTransmission();
      if (error == 0) {
        Serial.print(F("  Found device at 0x"));
        if (addr < 16) Serial.print("0");
        Serial.println(addr, HEX);
        deviceCount++;
      }
    }
    Serial.print(F("Total I2C devices found: "));
    Serial.println(deviceCount);

    Serial.println(F("----------------------------------------"));
    Serial.println(F("Checking for USB hubs at expected addresses:"));

    for (uint8_t i = 0; i < MAX_HUBS; i++) {
      Serial.print(F("  Testing hub "));
      Serial.print(i + 1);
      Serial.print(F(" at 0x"));
      Serial.print(HUB_ADDRESSES[i], HEX);
      Serial.print(F("... "));

      // Test if hub exists
      wire->beginTransmission(HUB_ADDRESSES[i]);
      uint8_t error = wire->endTransmission();

      if (error == 0) {
        // Initialize the hub with proper configuration
        if (initializeHub(i)) {
          connectedHubs[i] = 1;
          numConnected++;
          Serial.print(F("FOUND and initialized! (ports "));
          Serial.print(i * PORTS_PER_HUB + 1);
          Serial.print(F("-"));
          Serial.print(i * PORTS_PER_HUB + PORTS_PER_HUB);
          Serial.println(F(")"));
        } else {
          Serial.println(F("Found but init failed!"));
        }
      } else {
        Serial.print(F("Not found (error="));
        Serial.print(error);
        Serial.println(F(")"));
      }
    }

    Serial.print(F("Found "));
    Serial.print(numConnected);
    Serial.print(F(" of "));
    Serial.print(MAX_HUBS);
    Serial.println(F(" configured hubs"));

    return numConnected > 0;
  }

  // Initialize a single hub with proper configuration
  bool initializeHub(uint8_t hubIndex) {
    if (hubIndex >= MAX_HUBS) return false;

    uint8_t addr = HUB_ADDRESSES[hubIndex];

    // Set Configuration Register (all pins as outputs)
    wire->beginTransmission(addr);
    wire->write(0x03);  // Configuration register address
    wire->write(0x00);  // Sets all pins as outputs
    uint8_t error = wire->endTransmission();
    if (error != 0) return false;

    // Set Polarity Inversion Register (disable inversion)
    wire->beginTransmission(addr);
    wire->write(0x02);  // Polarity Inversion Register
    wire->write(0x00);  // Disable inversion on all pins
    wire->endTransmission();

    // Set Output Control Register with initial state
    // Bit 0: Current limit (1=100mA, 0=500mA) - start with 100mA
    // Bit 3: LED control (0=off)
    // Bits 4-7: Port control (0=all ports off)
    hubStates[hubIndex] = 0x01;  // Bit 0 set for 100mA, all else off
    wire->beginTransmission(addr);
    wire->write(0x01);  // Output Control Register
    wire->write(hubStates[hubIndex]);
    wire->endTransmission();

    // Port 4 defaults to on for some reason, make sure it's off
    setPort(hubIndex, 3, false);  // Port 4 is index 3

    // LEDs are controlled by bit 3, already off

    return true;
  }

  // Set individual port on/off (internal helper)
  void setPort(uint8_t hubIndex, uint8_t portIndex, bool enable) {
    if (hubIndex >= MAX_HUBS || !connectedHubs[hubIndex]) return;
    if (portIndex >= PORTS_PER_HUB) return;

    // Ports are controlled by bits 4-7
    uint8_t portBit = 4 + portIndex;
    if (enable) {
      hubStates[hubIndex] |= (1 << portBit);
    } else {
      hubStates[hubIndex] &= ~(1 << portBit);
    }
    updateHub(hubIndex);
  }

  // Set port by absolute port number (1-32)
  bool setPortByNumber(uint8_t portNum, uint8_t powerLevel) {
    if (portNum < 1 || portNum > TOTAL_PORTS) return false;

    // Calculate hub and port from absolute port number
    uint8_t hubIndex = (portNum - 1) / PORTS_PER_HUB;
    uint8_t portIndex = (portNum - 1) % PORTS_PER_HUB;

    if (!connectedHubs[hubIndex]) {
      Serial.print(F("Hub "));
      Serial.print(hubIndex + 1);
      Serial.println(F(" not connected"));
      return false;
    }

    // For this hardware, ports are either on or off
    // Power level is controlled per-hub via bit 0
    setPort(hubIndex, portIndex, powerLevel != POWER_OFF);
    portPowerStates[portNum - 1] = powerLevel;  // Track desired power level

    return true;
  }

  // Set all ports on a hub
  bool setHub(uint8_t hubNum, uint8_t state) {
    if (hubNum < 1 || hubNum > MAX_HUBS) return false;
    uint8_t hubIndex = hubNum - 1;

    if (!connectedHubs[hubIndex]) {
      Serial.print(F("Hub "));
      Serial.print(hubNum);
      Serial.println(F(" not connected"));
      return false;
    }

    hubStates[hubIndex] = state;
    return updateHub(hubIndex);
  }

  // Turn all ports and leds off, and go to 100mA
  void allOff() {
    for (uint8_t i = 0; i < MAX_HUBS; i++) {
      if (connectedHubs[i]) {
        hubStates[i] = 0x01;  // Bit 0 set for 100mA, all ports/LED off
        updateHub(i);
      }
    }
    memset(portPowerStates, POWER_OFF, sizeof(portPowerStates));
  }

  // Get hub state
  uint8_t getHubState(uint8_t hubNum) {
    if (hubNum < 1 || hubNum > MAX_HUBS) return 0;
    return hubStates[hubNum - 1];
  }

  // Get port power level by absolute port number
  uint8_t getPortPower(uint8_t portNum) {
    if (portNum < 1 || portNum > TOTAL_PORTS) return 0;
    return portPowerStates[portNum - 1];
  }

  // Check if port is enabled
  bool isPortEnabled(uint8_t hubIndex, uint8_t portIndex) {
    if (hubIndex >= MAX_HUBS || !connectedHubs[hubIndex]) return false;
    uint8_t portBit = 4 + portIndex;
    return (hubStates[hubIndex] & (1 << portBit)) != 0;
  }

  uint32_t getLastActivity() { return lastActivity; }
  uint8_t getNumConnected() { return numConnected; }

  // Convert absolute port number to hub and port indices
  bool getHubAndPort(uint8_t portNum, uint8_t& hubIndex, uint8_t& portIndex) {
    if (portNum < 1 || portNum > TOTAL_PORTS) return false;
    hubIndex = (portNum - 1) / PORTS_PER_HUB;
    portIndex = (portNum - 1) % PORTS_PER_HUB;
    return connectedHubs[hubIndex];
  }

  // Get LED state of a specific hub (bit 3 is LED control)
  bool getHubLEDState(uint8_t hubIndex) {
    if (hubIndex >= MAX_HUBS) return false;
    return (hubStates[hubIndex] & 0x08) != 0;  // Bit 3
  }

  // Get power setting of a specific hub (bit 0 is power control)
  bool getHubPowerHigh(uint8_t hubIndex) {
    if (hubIndex >= MAX_HUBS) return false;
    // Bit 0: 0=500mA (high), 1=100mA (low) - inverted logic
    return !(hubStates[hubIndex] & 0x01);
  }

  // Get status of all ports
  void getStatus(JsonDocument& status) {
    JsonArray hubs = status.createNestedArray("hubs");

    for (uint8_t i = 0; i < MAX_HUBS; i++) {
      if (connectedHubs[i]) {
        JsonObject hub = hubs.createNestedObject();
        hub["num"] = i + 1;
        hub["addr"] = HUB_ADDRESSES[i];
        hub["state"] = hubStates[i];

        // Add hub-level LED and power status
        hub["led"] = getHubLEDState(i);
        hub["power"] = getHubPowerHigh(i) ? "500mA" : "100mA";

        JsonArray ports = hub.createNestedArray("ports");
        for (uint8_t p = 0; p < PORTS_PER_HUB; p++) {
          JsonObject port = ports.createNestedObject();
          uint8_t portNum = i * PORTS_PER_HUB + p + 1;
          port["num"] = portNum;
          port["enabled"] = isPortEnabled(i, p);
          port["power"] = getPowerString(getPortPower(portNum));
        }
      }
    }
  }

  // Control LED for a hub on/off
  void updateHubLED(uint8_t hubIndex, bool on) {
    if (hubIndex >= MAX_HUBS || !connectedHubs[hubIndex]) return;

    // Bit 3 controls LED
    if (on) {
      hubStates[hubIndex] |= 0x08;  // Set bit 3
    } else {
      hubStates[hubIndex] &= ~0x08;  // Clear bit 3
    }
    updateHub(hubIndex);
  }

  // Control Power level per Hub (100mA vs 500mA)
  void updateHubPower(uint8_t hubIndex, bool high) {
    if (hubIndex >= MAX_HUBS || !connectedHubs[hubIndex]) return;

    // Bit 0 controls current limit: 0 = 500mA, 1 = 100mA (inverted logic)
    if (high) {
      hubStates[hubIndex] &= ~0x01;  // Clear bit 0 for 500mA
    } else {
      hubStates[hubIndex] |= 0x01;  // Set bit 0 for 100mA
    }
    updateHub(hubIndex);
  }

private:
  bool updateHub(uint8_t hubIndex) {
    if (hubIndex >= MAX_HUBS || !connectedHubs[hubIndex]) return false;

    wire->beginTransmission(HUB_ADDRESSES[hubIndex]);
    wire->write(0b00000001); // Output port register
    wire->write(hubStates[hubIndex]);
    uint8_t error = wire->endTransmission();

    if (error == 0) {
      lastActivity = millis();
      return true;
    }
    return false;
  }

  const char* getPowerString(uint8_t level) {
    switch(level) {
      case POWER_OFF: return "off";
      case POWER_100MA: return "100mA";
      case POWER_500MA: return "500mA";
      default: return "unknown";
    }
  }
};

// ============================================
// CONFIGURATION MANAGER CLASS
// ============================================
class ConfigManager {
private:
  Preferences prefs;
  struct {
    char wifiSSID[32];
    char wifiPass[64];
    char mdnsName[32];
    bool wifiEnabled;
  } config;

public:
  ConfigManager() {
    strcpy(config.mdnsName, "usbhub");  // Default
    config.wifiEnabled = false;
  }

  void begin() {
    prefs.begin("usbflashhub", false);
    loadConfig();
  }

  void loadConfig() {
    prefs.getString("ssid", config.wifiSSID, sizeof(config.wifiSSID));
    prefs.getString("pass", config.wifiPass, sizeof(config.wifiPass));
    prefs.getString("mdns", config.mdnsName, sizeof(config.mdnsName));
    config.wifiEnabled = prefs.getBool("wifi_en", false);

    if (strlen(config.mdnsName) == 0) {
      strcpy(config.mdnsName, "usbhub");
    }
  }

  void saveConfig() {
    prefs.putString("ssid", config.wifiSSID);
    prefs.putString("pass", config.wifiPass);
    prefs.putString("mdns", config.mdnsName);
    prefs.putBool("wifi_en", config.wifiEnabled);
  }

  void setWiFi(const char* ssid, const char* pass, bool enable) {
    if (ssid) strlcpy(config.wifiSSID, ssid, sizeof(config.wifiSSID));
    if (pass) strlcpy(config.wifiPass, pass, sizeof(config.wifiPass));
    config.wifiEnabled = enable;
    saveConfig();
  }

  void setMDNS(const char* name) {
    strlcpy(config.mdnsName, name, sizeof(config.mdnsName));
    saveConfig();
  }

  const char* getSSID() { return config.wifiSSID; }
  const char* getPass() { return config.wifiPass; }
  const char* getMDNS() { return config.mdnsName; }
  bool isWiFiEnabled() { return config.wifiEnabled; }

  void getConfig(JsonDocument& doc) {
    doc["wifi"]["ssid"] = config.wifiSSID;
    doc["wifi"]["enabled"] = config.wifiEnabled;
    doc["mdns"] = config.mdnsName;
  }
};

// ============================================
// ACTIVITY LOGGER CLASS
// ============================================
class ActivityLogger {
private:
  static const uint16_t MAX_ENTRIES = 100;

  struct LogEntry {
    time_t timestamp;
    char action[24];
    uint8_t target;
    char detail[32];
  };

  LogEntry* entries;
  uint16_t writeIndex;
  uint16_t count;
  bool usePSRAM;

public:
  ActivityLogger() : writeIndex(0), count(0), usePSRAM(false), entries(nullptr) {}

  void begin() {
    // Check for PSRAM and allocate buffer
    if (psramFound()) {
      entries = (LogEntry*)ps_malloc(sizeof(LogEntry) * MAX_ENTRIES);
      if (entries) {
        usePSRAM = true;
        Serial.println(F("Activity log using PSRAM"));
      }
    }

    if (!entries) {
      entries = new LogEntry[MAX_ENTRIES];
      Serial.println(F("Activity log using regular RAM"));
    }

    memset(entries, 0, sizeof(LogEntry) * MAX_ENTRIES);
  }

  void log(const char* action, uint8_t target = 0, const char* detail = nullptr) {
    if (!entries) return;

    LogEntry& entry = entries[writeIndex];
    entry.timestamp = time(nullptr);
    strlcpy(entry.action, action, sizeof(entry.action));
    entry.target = target;
    if (detail) {
      strlcpy(entry.detail, detail, sizeof(entry.detail));
    } else {
      entry.detail[0] = 0;
    }

    writeIndex = (writeIndex + 1) % MAX_ENTRIES;
    if (count < MAX_ENTRIES) count++;
  }

  void getLog(JsonDocument& doc) {
    JsonArray logs = doc.createNestedArray("log");

    uint16_t start = (count < MAX_ENTRIES) ? 0 : writeIndex;
    for (uint16_t i = 0; i < count; i++) {
      // Feed watchdog every 10 entries during log serialization
      if (i % 10 == 0) {
        esp_task_wdt_reset();
      }

      uint16_t idx = (start + i) % MAX_ENTRIES;
      JsonObject entry = logs.createNestedObject();

      if (entries[idx].timestamp > 0) {
        struct tm timeinfo;
        localtime_r(&entries[idx].timestamp, &timeinfo);
        char timeStr[32];
        strftime(timeStr, sizeof(timeStr), "%Y-%m-%d %H:%M:%S", &timeinfo);
        entry["time"] = timeStr;
      } else {
        entry["time"] = entries[idx].timestamp;  // Fallback to millis if no NTP
      }

      entry["action"] = entries[idx].action;
      if (entries[idx].target > 0) entry["target"] = entries[idx].target;
      if (strlen(entries[idx].detail) > 0) entry["detail"] = entries[idx].detail;
    }

    doc["count"] = count;
    doc["psram"] = usePSRAM;
  }
};

// ============================================
// WIFI MANAGER CLASS
// ============================================
class WiFiManager {
private:
  ConfigManager* config;
  bool connected;
  uint32_t lastReconnect;
  bool ntpSynced;

public:
  WiFiManager(ConfigManager* cfg) : config(cfg), connected(false), lastReconnect(0), ntpSynced(false) {}

  void begin() {
    if (!config->isWiFiEnabled()) {
      Serial.println(F("WiFi disabled in config"));
      return;
    }

    const char* ssid = config->getSSID();
    const char* pass = config->getPass();

    if (strlen(ssid) == 0) {
      Serial.println(F("No WiFi credentials configured"));
      return;
    }

    Serial.println(F("========================================"));
    Serial.println(F("WiFi Connection"));
    Serial.print(F("SSID: "));
    Serial.println(ssid);
    Serial.print(F("Password: "));
    Serial.println(strlen(pass) > 0 ? "****" : "(none)");

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, pass);

    Serial.print(F("Connecting"));
    uint8_t attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts++ < 20) {
      esp_task_wdt_reset();  // Feed watchdog during WiFi connection
      delay(500);
      Serial.print(".");

      // Print detailed status every 5 attempts
      if (attempts % 5 == 0) {
        Serial.print(F(" [Status: "));
        Serial.print(WiFi.status());
        Serial.print(F("]"));
      }
    }

    if (WiFi.status() == WL_CONNECTED) {
      connected = true;
      Serial.println(F("\n✓ WiFi Connected!"));
      Serial.print(F("  IP Address: "));
      Serial.println(WiFi.localIP());
      Serial.print(F("  Subnet Mask: "));
      Serial.println(WiFi.subnetMask());
      Serial.print(F("  Gateway: "));
      Serial.println(WiFi.gatewayIP());
      Serial.print(F("  DNS: "));
      Serial.println(WiFi.dnsIP());
      Serial.print(F("  RSSI: "));
      Serial.print(WiFi.RSSI());
      Serial.println(F(" dBm"));

      // Start mDNS
      if (MDNS.begin(config->getMDNS())) {
        Serial.print(F("mDNS started: "));
        Serial.print(config->getMDNS());
        Serial.println(F(".local"));
        MDNS.addService("http", "tcp", 80);
      }

      // Sync NTP
      configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
      Serial.println(F("NTP time sync started"));
      ntpSynced = true;
    } else {
      Serial.println(F("\nWiFi connection failed"));
    }
  }

  void loop() {
    if (!config->isWiFiEnabled()) return;

    // Auto-reconnect
    if (!connected && millis() - lastReconnect > RECONNECT_DELAY_MS) {
      lastReconnect = millis();
      esp_task_wdt_reset();  // Feed watchdog before reconnect attempt
      begin();
      esp_task_wdt_reset();  // Feed watchdog after reconnect attempt
    }
  }

  bool isConnected() { return connected; }
  String getIP() { return WiFi.localIP().toString(); }
};

// ============================================
// LED CONTROLLER CLASS
// ============================================
class LEDController {
private:
  uint8_t statusPin;
  uint8_t activityPin;
  uint32_t lastBlink;
  bool statusState;

#ifdef USE_RGB_LED
  Adafruit_NeoPixel* rgbLed;
  uint32_t lastActivityTime;
  bool activityState;
#endif

public:
  LEDController(uint8_t status, uint8_t activity)
    : statusPin(status), activityPin(activity), lastBlink(0), statusState(false) {
#ifdef USE_RGB_LED
    rgbLed = nullptr;
    lastActivityTime = 0;
    activityState = false;
#endif
  }

  void begin() {
#ifdef USE_RGB_LED
    // Initialize RGB LED for S3-Zero
    rgbLed = new Adafruit_NeoPixel(RGB_LED_COUNT, RGB_LED_PIN, NEO_GRB + NEO_KHZ800);
    rgbLed->begin();
    rgbLed->setBrightness(RGB_LED_BRIGHTNESS);  // Not too bright
    setRGBStatus(true);  // Green for status on
#else
    // Standard GPIO LEDs
    pinMode(statusPin, OUTPUT);
    pinMode(activityPin, OUTPUT);
    setStatus(true);  // Status on at startup
    setActivity(false);
#endif
  }

#ifdef USE_RGB_LED
  void setRGBColor(uint8_t r, uint8_t g, uint8_t b) {
    if (rgbLed) {
      rgbLed->setPixelColor(0, rgbLed->Color(r, g, b));
      rgbLed->show();
    }
  }

  void setRGBStatus(bool on) {
    if (on) {
      setRGBColor(0, 25, 0);  // Green for status OK
    } else {
      setRGBColor(0, 0, 0);    // Off
    }
    statusState = on;
  }

  void flashRGBActivity() {
    setRGBColor(0, 0, 25);  // Blue for activity
    lastActivityTime = millis();
    activityState = true;
  }

  void updateRGB() {
    // Auto-clear activity flash after 50ms
    if (activityState && millis() - lastActivityTime > 50) {
      setRGBStatus(statusState);  // Return to status color
      activityState = false;
    }
  }
#endif

  void setStatus(bool on) {
#ifdef USE_RGB_LED
    setRGBStatus(on);
#else
    digitalWrite(statusPin, on ? HIGH : LOW);
    statusState = on;
#endif
  }

  void setActivity(bool on) {
#ifdef USE_RGB_LED
    if (on) {
      flashRGBActivity();
    }
#else
    digitalWrite(activityPin, on ? HIGH : LOW);
#endif
  }

  void flashActivity(uint32_t ms = ACTIVITY_FLASH_MS) {
#ifdef USE_RGB_LED
    flashRGBActivity();
#else
    setActivity(true);
    delay(ms);
    setActivity(false);
#endif
  }

  void blinkStatus(uint32_t interval = 1000) {
    if (millis() - lastBlink > interval) {
      statusState = !statusState;
      setStatus(statusState);
      lastBlink = millis();
    }
  }

  void errorPattern() {
#ifdef USE_RGB_LED
    for (int i = 0; i < 3; i++) {
      setRGBColor(25, 0, 0);  // Red for error
      delay(ERROR_FLASH_MS);
      setRGBColor(0, 0, 0);   // Off
      delay(ERROR_FLASH_MS);
    }
    setRGBStatus(statusState);  // Return to normal
#else
    for (int i = 0; i < 3; i++) {
      setStatus(true);
      setActivity(true);
      delay(ERROR_FLASH_MS);
      setStatus(false);
      setActivity(false);
      delay(ERROR_FLASH_MS);
    }
#endif
  }

  void loop() {
#ifdef USE_RGB_LED
    updateRGB();
#endif
  }
};

// ============================================
// PIN CONTROLLER CLASS
// ============================================
class PinController {
private:
  uint8_t bootPin;
  uint8_t resetPin;
  bool bootState;
  bool resetState;

public:
  PinController(uint8_t boot, uint8_t reset)
    : bootPin(boot), resetPin(reset), bootState(false), resetState(false) {}

  void begin() {
    pinMode(bootPin, OUTPUT);
    pinMode(resetPin, OUTPUT);

    // Safe defaults
    setBoot(false);   // Boot pin LOW
    setReset(false);  // Reset not asserted (HIGH)

    Serial.println(F("Pin controller initialized"));
  }

  // Direct pin control - just set HIGH or LOW
  void setBoot(bool high) {
    digitalWrite(bootPin, high ? HIGH : LOW);
    bootState = high;
  }

  // Reset is active LOW - but we expose it as logical state
  void setReset(bool asserted) {
    digitalWrite(resetPin, asserted ? LOW : HIGH);
    resetState = asserted;
  }

  void pulseReset(uint32_t ms = 100) {
    setReset(true);   // Assert reset (LOW)
    // For longer pulses, feed watchdog during delay
    if (ms > 1000) {
      uint32_t chunks = ms / 500;
      uint32_t remainder = ms % 500;
      for (uint32_t i = 0; i < chunks; i++) {
        delay(500);
        esp_task_wdt_reset();
      }
      if (remainder > 0) delay(remainder);
    } else {
      delay(ms);
    }
    setReset(false);  // Release reset (HIGH)
  }

  bool getBootState() { return bootState; }
  bool getResetState() { return resetState; }
};

// ============================================
// COMMAND PROCESSOR
// ============================================
class CommandProcessor {
private:
  HubController* hub;
  PinController* pins;
  LEDController* leds;
  ConfigManager* config;
  ActivityLogger* logger;
  WiFiManager* network;
  StaticJsonDocument<1024> response;  // Increased for log output
  uint32_t commandCount;

public:
  CommandProcessor(HubController* h, PinController* p, LEDController* l,
                   ConfigManager* c, ActivityLogger* log, WiFiManager* n)
    : hub(h), pins(p), leds(l), config(c), logger(log), network(n), commandCount(0) {}

  void processCommand(const String& cmdStr) {
    StaticJsonDocument<256> cmd;
    DeserializationError error = deserializeJson(cmd, cmdStr);

    if (error) {
      sendError("JSON parse error", error.c_str());
      return;
    }

    commandCount++;
    leds->flashActivity();

    const char* action = cmd["cmd"];
    if (!action) {
      sendError("No command specified");
      return;
    }

    // Log the command
    logger->log(action);

    // Port control commands
    if (strcmp(action, "port") == 0) {
      handlePortCommand(cmd);
    }
    else if (strcmp(action, "hub") == 0) {
      handleHubCommand(cmd);
    }
    else if (strcmp(action, "alloff") == 0) {
      hub->allOff();
      pins->setReset(true);
      delay(100);
      pins->setReset(false);
      logger->log("emergency_stop");
      sendOK("Emergency stop - all ports off");
    }
    // Pin control commands
    else if (strcmp(action, "boot") == 0) {
      bool state = cmd["state"];
      pins->setBoot(state);
      logger->log("boot_pin", 0, state ? "HIGH" : "LOW");
      sendOK(state ? "Boot pin HIGH" : "Boot pin LOW");
    }
    else if (strcmp(action, "reset") == 0) {
      if (cmd.containsKey("pulse")) {
        uint32_t ms = cmd["pulse"] | 100;
        pins->pulseReset(ms);
        logger->log("reset_pulse", ms);
        sendOK("Reset pulsed");
      } else {
        bool state = cmd["state"];
        pins->setReset(state);
        logger->log("reset_pin", 0, state ? "asserted" : "released");
        sendOK(state ? "Reset asserted (LOW)" : "Reset released (HIGH)");
      }
    }
    // LED control commands
    else if (strcmp(action, "led") == 0) {
      handleLEDCommand(cmd);
    }
    // Configuration commands
    else if (strcmp(action, "config") == 0) {
      handleConfigCommand(cmd);
    }
    // Activity log
    else if (strcmp(action, "log") == 0) {
      sendLog();
    }
    // Status commands
    else if (strcmp(action, "status") == 0) {
      sendStatus();
    }
    else if (strcmp(action, "ping") == 0) {
      sendOK("pong");
    }
    else if (strcmp(action, "help") == 0) {
      printHelp();
    }
    else {
      sendError("Unknown command", action);
    }
  }

private:
  void handlePortCommand(JsonDocument& cmd) {
    uint8_t portNum = cmd["port"] | 0;

    if (portNum == 0) {
      sendError("Missing port number");
      return;
    }

    // Check for power level
    const char* powerStr = cmd["power"] | "default";
    uint8_t powerLevel = POWER_DEFAULT;

    if (strcmp(powerStr, "off") == 0) {
      powerLevel = POWER_OFF;
    } else if (strcmp(powerStr, "100mA") == 0 || strcmp(powerStr, "low") == 0) {
      powerLevel = POWER_100MA;
    } else if (strcmp(powerStr, "500mA") == 0 || strcmp(powerStr, "high") == 0) {
      powerLevel = POWER_500MA;
    }

    if (hub->setPortByNumber(portNum, powerLevel)) {
      logger->log("port_set", portNum, powerStr);
      response.clear();
      response["status"] = "ok";
      response["port"] = portNum;
      response["power"] = powerStr;
      serializeJson(response, Serial);
      Serial.println();
    } else {
      sendError("Failed to set port");
    }
  }

  void handleHubCommand(JsonDocument& cmd) {
    uint8_t hubNum = cmd["hub"] | 0;

    if (hubNum == 0 || hubNum > MAX_HUBS) {
      sendError("Invalid hub number");
      return;
    }

    uint8_t hubIndex = hubNum - 1;

    // Handle LED control
    if (cmd.containsKey("led")) {
      bool ledOn = cmd["led"].as<bool>();
      hub->updateHubLED(hubIndex, ledOn);
      logger->log(ledOn ? "hub_led_on" : "hub_led_off", hubNum);
      sendOK(ledOn ? "Hub LEDs turned on" : "Hub LEDs turned off");
      return;
    }

    // Handle power control
    if (cmd.containsKey("power")) {
      const char* power = cmd["power"];
      bool high = (strcmp(power, "500mA") == 0);
      hub->updateHubPower(hubIndex, high);
      logger->log(high ? "hub_power_500mA" : "hub_power_100mA", hubNum);
      sendOK(high ? "Hub power set to 500mA" : "Hub power set to 100mA");
      return;
    }

    // Handle raw state control (legacy)
    if (cmd.containsKey("state")) {
      uint8_t state = cmd["state"];
      if (hub->setHub(hubNum, state)) {
        logger->log("hub_set", hubNum);
        sendOK("Hub state updated");
      } else {
        sendError("Failed to set hub state");
      }
    } else {
      // Query hub state
      uint8_t state = hub->getHubState(hubNum);
      response.clear();
      response["status"] = "ok";
      response["hub"] = hubNum;
      response["state"] = state;
      response["led"] = hub->getHubLEDState(hubIndex);
      response["power"] = hub->getHubPowerHigh(hubIndex) ? "500mA" : "100mA";
      serializeJson(response, Serial);
      Serial.println();
    }
  }

  void handleLEDCommand(JsonDocument& cmd) {
    const char* led = cmd["led"] | "status";
    const char* action = cmd["action"] | "on";

    if (strcmp(led, "status") == 0) {
      if (strcmp(action, "on") == 0) {
        leds->setStatus(true);
        sendOK("Status LED on");
      } else if (strcmp(action, "off") == 0) {
        leds->setStatus(false);
        sendOK("Status LED off");
      } else if (strcmp(action, "blink") == 0) {
        leds->blinkStatus();
        sendOK("Status LED blinking");
      }
    } else if (strcmp(led, "activity") == 0) {
      if (strcmp(action, "flash") == 0) {
        leds->flashActivity();
        sendOK("Activity LED flashed");
      } else if (strcmp(action, "on") == 0) {
        leds->setActivity(true);
        sendOK("Activity LED on");
      } else if (strcmp(action, "off") == 0) {
        leds->setActivity(false);
        sendOK("Activity LED off");
      }
    } else if (strcmp(led, "error") == 0) {
      leds->errorPattern();
      sendOK("Error pattern displayed");
    }
  }

  void handleConfigCommand(JsonDocument& cmd) {
    if (cmd.containsKey("wifi")) {
      JsonObject wifi = cmd["wifi"];
      if (wifi.containsKey("ssid") && wifi.containsKey("pass")) {
        const char* ssid = wifi["ssid"];
        const char* pass = wifi["pass"];
        bool enable = wifi["enable"] | true;
        config->setWiFi(ssid, pass, enable);
        logger->log("wifi_config", 0, ssid);
        sendOK("WiFi configuration saved. Restart to apply.");
      } else if (wifi.containsKey("enable")) {
        bool enable = wifi["enable"];
        config->setWiFi(nullptr, nullptr, enable);
        logger->log("wifi_toggle", enable);
        sendOK(enable ? "WiFi enabled" : "WiFi disabled");
      } else {
        sendError("WiFi config requires ssid+pass or enable flag");
      }
    } else if (cmd.containsKey("mdns")) {
      const char* name = cmd["mdns"];
      config->setMDNS(name);
      logger->log("mdns_config", 0, name);
      sendOK("mDNS name saved. Restart to apply.");
    } else {
      // Return current config
      response.clear();
      response["status"] = "ok";
      config->getConfig(response);
      if (network->isConnected()) {
        response["ip"] = network->getIP();
      }
      serializeJson(response, Serial);
      Serial.println();
    }
  }

  void sendLog() {
    response.clear();
    response["status"] = "ok";
    logger->getLog(response);
    serializeJson(response, Serial);
    Serial.println();
  }

public:
  void sendStatus() {
    response.clear();
    response["status"] = "ok";
    response["device"] = "USBFlashHub";
    response["version"] = "2.0";
    response["uptime"] = millis();
    response["commands"] = commandCount;

    JsonObject pinStates = response.createNestedObject("pins");
    pinStates["boot"] = pins->getBootState() ? "HIGH" : "LOW";
    pinStates["reset"] = pins->getResetState() ? "asserted" : "released";

    hub->getStatus(response);

    // Add network status
    if (config->isWiFiEnabled()) {
      JsonObject net = response.createNestedObject("network");
      net["enabled"] = true;
      net["connected"] = network->isConnected();
      if (network->isConnected()) {
        net["ip"] = network->getIP();
        net["mdns"] = String(config->getMDNS()) + ".local";
      }
    }

    serializeJson(response, Serial);
    Serial.println();
  }

  void sendOK(const char* msg) {
    response.clear();
    response["status"] = "ok";
    response["msg"] = msg;
    serializeJson(response, Serial);
    Serial.println();
  }

  void sendError(const char* msg, const char* detail = nullptr) {
    response.clear();
    response["status"] = "error";
    response["msg"] = msg;
    if (detail) response["detail"] = detail;
    serializeJson(response, Serial);
    Serial.println();
    leds->errorPattern();
  }

  void printHelp() {
    Serial.println(F("\n=== USBFlashHub Commands ==="));
    Serial.println(F("\nPort Control:"));
    Serial.println(F("  {\"cmd\":\"port\",\"port\":1,\"power\":\"500mA\"}"));
    Serial.println(F("  {\"cmd\":\"port\",\"port\":5,\"power\":\"off\"}"));
    Serial.println(F("  Power levels: off, 100mA, 500mA"));
    Serial.println(F("\nHub Control:"));
    Serial.println(F("  {\"cmd\":\"hub\",\"hub\":1,\"state\":255}"));
    Serial.println(F("  {\"cmd\":\"alloff\"}"));
    Serial.println(F("\nPin Control:"));
    Serial.println(F("  {\"cmd\":\"boot\",\"state\":true}   (HIGH)"));
    Serial.println(F("  {\"cmd\":\"boot\",\"state\":false}  (LOW)"));
    Serial.println(F("  {\"cmd\":\"reset\",\"state\":true}  (asserted/LOW)"));
    Serial.println(F("  {\"cmd\":\"reset\",\"state\":false} (released/HIGH)"));
    Serial.println(F("  {\"cmd\":\"reset\",\"pulse\":100}  (LOW 100ms then HIGH)"));
    Serial.println(F("\nLED Control:"));
    Serial.println(F("  {\"cmd\":\"led\",\"led\":\"status\",\"action\":\"on\"}"));
    Serial.println(F("  {\"cmd\":\"led\",\"led\":\"activity\",\"action\":\"flash\"}"));
    Serial.println(F("  {\"cmd\":\"led\",\"led\":\"error\"}"));
    Serial.println(F("\nConfiguration:"));
    Serial.println(F("  {\"cmd\":\"config\",\"wifi\":{\"ssid\":\"MyNet\",\"pass\":\"pass\"}}"));
    Serial.println(F("  {\"cmd\":\"config\",\"wifi\":{\"enable\":false}}"));
    Serial.println(F("  {\"cmd\":\"config\",\"mdns\":\"usbhub\"}"));
    Serial.println(F("  {\"cmd\":\"config\"}  (get current config)"));
    Serial.println(F("\nStatus:"));
    Serial.println(F("  {\"cmd\":\"status\"}"));
    Serial.println(F("  {\"cmd\":\"log\"}  (activity log)"));
    Serial.println(F("  {\"cmd\":\"ping\"}"));
    Serial.println(F("  {\"cmd\":\"help\"}"));
    Serial.println(F("\nPort Numbering:"));
    for (uint8_t i = 0; i < MAX_HUBS; i++) {
      Serial.print(F("  Hub "));
      Serial.print(i + 1);
      Serial.print(F(": ports "));
      Serial.print(i * PORTS_PER_HUB + 1);
      Serial.print(F("-"));
      Serial.println(i * PORTS_PER_HUB + PORTS_PER_HUB);
    }
    Serial.println(F("==============================\n"));
  }
};

// ============================================
// MAIN PROGRAM
// ============================================
// Wire1 is predefined in ESP32 library
HubController hubController(&Wire);
PinController pinController(BOOT_PIN, RESET_PIN);
LEDController ledController(STATUS_LED, ACTIVITY_LED);
ConfigManager configManager;
ActivityLogger activityLogger;
WiFiManager wifiManager(&configManager);
CommandProcessor processor(&hubController, &pinController, &ledController,
                          &configManager, &activityLogger, &wifiManager);

// Web server and WebSocket
WebServer webServer(80);
WebSocketsServer wsServer(81);
bool wsConnected = false;

// Emergency stop handler
volatile bool emergencyStopFlag = false;

void IRAM_ATTR emergencyStopISR() {
  emergencyStopFlag = true;
}

// ============================================
// WEB SERVER HANDLERS
// ============================================
void handleWebRoot() {
  Serial.println(F("HTTP: Root page requested"));
  if (LittleFS.exists("/index.html")) {
    Serial.println(F("  Serving index.html"));
    File file = LittleFS.open("/index.html", "r");
    webServer.streamFile(file, "text/html");
    file.close();
  } else {
    Serial.println(F("  index.html not found, serving default"));
    webServer.send(200, "text/html", "<h1>USBFlashHub</h1><p>Upload index.html to LittleFS</p>");
  }
}

void handleWebNotFound() {
  Serial.print(F("HTTP: 404 - "));
  Serial.println(webServer.uri());
  webServer.send(404, "text/plain", "404: Not Found");
}

void handleWebStatus() {
  Serial.println(F("HTTP: Status API requested"));
  StaticJsonDocument<1024> doc;
  doc["status"] = "ok";
  doc["uptime"] = millis();

  // Add port states
  JsonObject ports = doc.createNestedObject("ports");
  for (uint8_t i = 1; i <= TOTAL_PORTS; i++) {
    uint8_t hubIndex, portIndex;
    if (hubController.getHubAndPort(i, hubIndex, portIndex)) {
      uint8_t state = hubController.getPortPower(i);
      if (state == POWER_OFF) ports[String(i)] = "off";
      else if (state == POWER_100MA) ports[String(i)] = "100mA";
      else if (state == POWER_500MA) ports[String(i)] = "500mA";
    }
  }

  // Add system info
  JsonObject system = doc.createNestedObject("system");
  system["ip"] = WiFi.localIP().toString();
  system["rssi"] = WiFi.RSSI();
  system["heap"] = ESP.getFreeHeap();

  // Add pin states
  JsonObject pins = doc.createNestedObject("pins");
  pins["boot"] = digitalRead(BOOT_PIN);
  pins["reset"] = digitalRead(RESET_PIN);

  String response;
  serializeJson(doc, response);
  webServer.send(200, "application/json", response);
}

// WebSocket event handler
void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      wsConnected = false;
      Serial.printf("WebSocket client %u disconnected\n", num);
      break;

    case WStype_CONNECTED: {
      wsConnected = true;
      IPAddress ip = wsServer.remoteIP(num);
      Serial.printf("WebSocket client %u connected from %s\n", num, ip.toString().c_str());

      // Send initial status
      StaticJsonDocument<256> doc;
      doc["status"] = "connected";
      doc["msg"] = "USBFlashHub WebSocket connected";
      String msg;
      serializeJson(doc, msg);
      wsServer.sendTXT(num, msg);
      break;
    }

    case WStype_TEXT: {
      // Process command from WebSocket
      String cmdStr = String((char*)payload);
      Serial.print(F("WebSocket command: "));
      Serial.println(cmdStr);

      StaticJsonDocument<256> cmd;
      DeserializationError error = deserializeJson(cmd, cmdStr);

      if (!error) {
        // Process the command
        processor.processCommand(cmdStr);

        // Special handling for status command - send full response
        const char* action = cmd["cmd"];
        if (strcmp(action, "status") == 0) {
          StaticJsonDocument<1024> status;
          status["status"] = "ok";
          status["uptime"] = millis();

          // Add hubs info
          JsonArray hubs = status.createNestedArray("hubs");
          hubController.getStatus(status);

          // Add network info
          JsonObject network = status.createNestedObject("network");
          network["ip"] = WiFi.localIP().toString();
          network["connected"] = true;

          // Add ports info
          JsonObject ports = status.createNestedObject("ports");
          for (uint8_t i = 1; i <= TOTAL_PORTS; i++) {
            uint8_t hubIndex, portIndex;
            if (hubController.getHubAndPort(i, hubIndex, portIndex)) {
              uint8_t state = hubController.getPortPower(i);
              if (state == POWER_OFF) ports[String(i)] = "off";
              else if (state == POWER_100MA) ports[String(i)] = "100mA";
              else if (state == POWER_500MA) ports[String(i)] = "500mA";
            }
          }

          String msg;
          serializeJson(status, msg);
          wsServer.sendTXT(num, msg);
        } else if (strcmp(action, "port") == 0) {
          // Port command - send full status update to all clients
          delay(50); // Give hardware time to update

          StaticJsonDocument<1024> status;
          status["status"] = "ok";
          status["uptime"] = millis();

          // Add hubs info with updated states
          JsonArray hubs = status.createNestedArray("hubs");
          hubController.getStatus(status);

          // Add network info
          JsonObject network = status.createNestedObject("network");
          network["ip"] = WiFi.localIP().toString();
          network["connected"] = true;

          // Add confirmation message
          uint8_t portNum = cmd["port"] | 0;
          const char* power = cmd["power"] | "unknown";
          status["msg"] = String("Port ") + portNum + " set to " + power;

          // Send full status to all connected clients
          String msg;
          serializeJson(status, msg);
          wsServer.broadcastTXT(msg);  // Broadcast to all clients
        } else if (strcmp(action, "boot") == 0 || strcmp(action, "reset") == 0) {
          // Pin command - send success with details
          StaticJsonDocument<256> response;
          response["status"] = "ok";
          response["cmd"] = action;

          if (cmd.containsKey("pulse")) {
            // For pulse command, send clear message
            if (strcmp(action, "reset") == 0) {
              response["msg"] = "Reset pulsed";
            } else {
              response["msg"] = "Boot pulsed";
            }
          } else {
            bool state = cmd["state"] | false;
            if (strcmp(action, "reset") == 0) {
              response["msg"] = state ? "Reset released (HIGH)" : "Reset asserted (LOW)";
            } else {
              response["msg"] = state ? "Boot pin HIGH" : "Boot pin LOW";
            }
          }

          // Also send pin states update
          JsonObject pins = response.createNestedObject("pins");
          pins["boot"] = digitalRead(BOOT_PIN);
          pins["reset"] = digitalRead(RESET_PIN);

          String msg;
          serializeJson(response, msg);
          wsServer.sendTXT(num, msg);
        } else if (strcmp(action, "hub") == 0) {
          // Hub command - send full status update to all clients
          StaticJsonDocument<1024> status;
          status["status"] = "ok";
          status["uptime"] = millis();

          // Add hubs info
          JsonArray hubs = status.createNestedArray("hubs");
          hubController.getStatus(status);

          // Add network info
          JsonObject network = status.createNestedObject("network");
          network["ip"] = WiFi.localIP().toString();
          network["connected"] = true;

          // Send full status to all connected clients
          String msg;
          serializeJson(status, msg);
          wsServer.broadcastTXT(msg);  // Broadcast to all clients
        } else if (strcmp(action, "alloff") == 0) {
          // All off command - send full status update to all clients
          delay(50); // Give hardware time to update

          StaticJsonDocument<1024> status;
          status["status"] = "ok";
          status["uptime"] = millis();

          // Add hubs info with updated states
          JsonArray hubs = status.createNestedArray("hubs");
          hubController.getStatus(status);

          // Add network info
          JsonObject network = status.createNestedObject("network");
          network["ip"] = WiFi.localIP().toString();
          network["connected"] = true;

          // Add confirmation message
          status["msg"] = "All ports turned off";

          // Send full status to all connected clients
          String msg;
          serializeJson(status, msg);
          wsServer.broadcastTXT(msg);  // Broadcast to all clients
        } else {
          // Other commands - generic success
          StaticJsonDocument<256> response;
          response["status"] = "ok";
          response["cmd"] = action;
          String msg;
          serializeJson(response, msg);
          wsServer.sendTXT(num, msg);
        }
      } else {
        StaticJsonDocument<256> response;
        response["status"] = "error";
        response["msg"] = "Invalid JSON";
        String msg;
        serializeJson(response, msg);
        wsServer.sendTXT(num, msg);
      }
      break;
    }

    default:
      break;
  }
}

// Broadcast status update to all WebSocket clients
void broadcastStatus() {
  if (!wsConnected) return;

  StaticJsonDocument<1024> doc;

  // Add full hub information
  JsonArray hubs = doc.createNestedArray("hubs");
  hubController.getStatus(doc);

  // Add port states (for backward compatibility)
  JsonObject ports = doc.createNestedObject("ports");
  for (uint8_t i = 1; i <= TOTAL_PORTS; i++) {
    uint8_t hubIndex, portIndex;
    if (hubController.getHubAndPort(i, hubIndex, portIndex)) {
      uint8_t state = hubController.getPortPower(i);
      if (state == POWER_OFF) ports[String(i)] = "off";
      else if (state == POWER_100MA) ports[String(i)] = "100mA";
      else if (state == POWER_500MA) ports[String(i)] = "500mA";
    }
  }

  // Add system info
  JsonObject system = doc.createNestedObject("system");
  system["uptime"] = millis();
  system["ip"] = WiFi.localIP().toString();

  // Add pin states
  JsonObject pins = doc.createNestedObject("pins");
  pins["boot"] = digitalRead(BOOT_PIN);
  pins["reset"] = digitalRead(RESET_PIN);

  String msg;
  serializeJson(doc, msg);
  wsServer.broadcastTXT(msg);
}

void setup() {
  Serial.begin(115200);

  // Wait for serial or timeout
  uint32_t start = millis();
  while (!Serial && millis() - start < 3000);

  Serial.println(F("\n====================================="));
  Serial.println(F("        USBFlashHub v2.0"));
  Serial.println(F("   USB Hub & Programming Control"));
  Serial.print(F("         Board: "));
  Serial.println(F(BOARD_TYPE));
  Serial.println(F("=====================================\n"));

  // Initialize watchdog timer
  Serial.print(F("Initializing watchdog ("));
  Serial.print(WDT_TIMEOUT);
  Serial.print(F("s)... "));

#if defined(CONFIG_IDF_TARGET_ESP32C3)
  // ESP32-C3 uses simplified watchdog config (single core)
  esp_task_wdt_config_t wdt_config = {
    .timeout_ms = WDT_TIMEOUT * 1000,
    .idle_core_mask = 1,  // Single core for C3
    .trigger_panic = true
  };
#else
  // Multi-core ESP32 variants
  esp_task_wdt_config_t wdt_config = {
    .timeout_ms = WDT_TIMEOUT * 1000,
    .idle_core_mask = 0,
    .trigger_panic = true
  };
#endif

  esp_task_wdt_init(&wdt_config);
  esp_task_wdt_add(NULL);  // Add current task to WDT
  esp_task_wdt_reset();    // Feed the watchdog
  Serial.println(F("OK"));

  // Initialize configuration first
  configManager.begin();
  activityLogger.begin();
  esp_task_wdt_reset();  // Feed watchdog

  // Initialize components
  ledController.begin();
  ledController.flashActivity();

  Serial.println(F("Initializing I2C..."));
  Serial.print(F("  Using Wire (primary I2C) on pins SDA="));
  Serial.print(I2C_SDA);
  Serial.print(F(", SCL="));
  Serial.println(I2C_SCL);
  Wire.begin(I2C_SDA, I2C_SCL);
  Serial.println(F("  I2C initialized"));

  pinController.begin();

  // Initialize network if configured
  esp_task_wdt_reset();  // Feed watchdog before network init
  wifiManager.begin();
  esp_task_wdt_reset();  // Feed watchdog after network init

  if (hubController.begin()) {
    Serial.println(F("Hub controller ready"));
    ledController.setStatus(true);
  } else {
    Serial.println(F("WARNING: No USB hubs found"));
    ledController.errorPattern();
  }

  // Setup emergency stop button
  pinMode(EMERGENCY_BTN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(EMERGENCY_BTN), emergencyStopISR, FALLING);
  Serial.println(F("Emergency stop on GPIO0 (BOOT button)"));

  Serial.println(F("\nReady for commands"));
  Serial.println(F("Type {\"cmd\":\"help\"} for command list"));

  if (configManager.isWiFiEnabled() && wifiManager.isConnected()) {
    Serial.print(F("Web interface: http://"));
    Serial.print(wifiManager.getIP());
    Serial.print(F(" or http://"));
    Serial.print(configManager.getMDNS());
    Serial.println(F(".local"));
  }
  Serial.println();

  // Initialize LittleFS for web files
  Serial.println(F("\n========================================"));
  Serial.println(F("Web Server Setup"));
  Serial.print(F("WiFi Connected: "));
  Serial.println(wifiManager.isConnected() ? "YES" : "NO");

  if (wifiManager.isConnected()) {
    Serial.print(F("IP Address: "));
    Serial.println(WiFi.localIP());
    Serial.print(F("Initializing LittleFS... "));
    if (!LittleFS.begin(true)) {
      Serial.println(F("Failed"));
      Serial.println(F("WARNING: Web interface files not available"));
    } else {
      Serial.println(F("OK"));

      // Check if index.html exists
      if (LittleFS.exists("/index.html")) {
        Serial.println(F("  index.html found"));
      } else {
        Serial.println(F("  WARNING: index.html not found"));
      }

      // Setup web server routes
      Serial.println(F("Configuring web server routes..."));
      webServer.on("/", handleWebRoot);
      webServer.on("/status", handleWebStatus);
      webServer.onNotFound(handleWebNotFound);
      webServer.begin();
      Serial.print(F("Web server started on port 80 at http://"));
      Serial.print(WiFi.localIP());
      Serial.println(F("/"));

      // Initialize WebSocket server
      wsServer.begin();
      wsServer.onEvent(webSocketEvent);
      Serial.println(F("WebSocket server started on port 81"));
    }
  } else {
    Serial.println(F("WARNING: WiFi not connected - web server disabled"));
  }
  Serial.println(F("========================================\n"));

  activityLogger.log("system_start");
  processor.sendStatus();
}

void loop() {
  // Feed the watchdog
  esp_task_wdt_reset();

  // Network reconnect handler
  wifiManager.loop();

  // Check emergency stop
  if (emergencyStopFlag) {
    emergencyStopFlag = false;
    Serial.println(F("\n!!! EMERGENCY STOP !!!"));
    hubController.allOff();
    pinController.setReset(true);
    ledController.errorPattern();
    delay(500);
    pinController.setReset(false);
  }

  // Process serial commands
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      processor.processCommand(line);
    }
  }

  // Handle web server and WebSocket if WiFi is connected
  if (wifiManager.isConnected()) {
    webServer.handleClient();
    wsServer.loop();

    // Broadcast status updates periodically
    static uint32_t lastBroadcast = 0;
    if (millis() - lastBroadcast > BROADCAST_INTERVAL) {
      broadcastStatus();
      lastBroadcast = millis();
    }
  }

  // Update LED controller (needed for RGB LED timing)
  ledController.loop();

  // Heartbeat - blink status LED every 5 seconds when idle
  static uint32_t lastHeartbeat = 0;
  if (millis() - lastHeartbeat > HEARTBEAT_INTERVAL) {
    ledController.blinkStatus();
    lastHeartbeat = millis();
    // Watchdog is fed at top of loop, so no need here
  }
}
