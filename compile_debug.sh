#!/bin/bash
# Compile with debug output enabled
arduino-cli compile \
  --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc,PSRAM=enabled,DebugLevel=verbose \
  --build-property compiler.cpp.extra_flags="-DCORE_DEBUG_LEVEL=5 -DCONFIG_ARDUHAL_LOG_COLORS=1" \
  USBFlashHub.ino
