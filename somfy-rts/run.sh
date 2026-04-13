#!/usr/bin/env bash
# shellcheck shell=bash
set -e

echo "Starting Somfy RTS App..."

OPTIONS_FILE="/data/options.json"

# ---------- Read config from /data/options.json ----------
# HA Supervisor writes the add-on options to this file before container start.
_opt() {
    python3 -c "import json,sys; d=json.load(open('${OPTIONS_FILE}')); print(d.get('$1','$2'),end='')" 2>/dev/null || echo -n "$2"
}

USB_PORT=$(_opt usb_port "/dev/ttyACM0")
BAUDRATE=$(_opt baudrate "9600")
MQTT_HOST=$(_opt mqtt_host "core-mosquitto")
MQTT_PORT=$(_opt mqtt_port "1883")
MQTT_USER=$(_opt mqtt_user "")
MQTT_PASSWORD=$(_opt mqtt_password "")
ADDRESS_PREFIX=$(_opt address_prefix "A000")
LOG_LEVEL=$(_opt log_level "info")
LOG_FORMAT=$(_opt log_format "text")
SIMULATION_MODE=$(_opt simulation_mode "false")
FILE_LOGGING=$(_opt file_logging "false")

# ---------- Validate USB port ----------
if [ ! -e "${USB_PORT}" ]; then
    echo "WARNING: USB port ${USB_PORT} not found."
    echo "WARNING: Please connect the NanoCUL USB stick and restart the add-on."
fi

# ---------- Initialize /data/somfy_codes.json if missing ----------
if [ ! -f /data/somfy_codes.json ]; then
    echo "Initializing /data/somfy_codes.json..."
    printf '{\n  "devices": [],\n  "groups": [],\n  "settings": {\n    "address_prefix": "%s",\n    "prefix_locked": false\n  }\n}\n' \
        "${ADDRESS_PREFIX}" > /data/somfy_codes.json
fi

# ---------- Export config as environment variables for Python ----------
export SOMFY_USB_PORT="${USB_PORT}"
export SOMFY_ADDRESS_PREFIX="${ADDRESS_PREFIX}"
export SOMFY_BAUDRATE="${BAUDRATE}"
export SOMFY_MQTT_HOST="${MQTT_HOST}"
export SOMFY_MQTT_PORT="${MQTT_PORT}"
export SOMFY_MQTT_USER="${MQTT_USER}"
export SOMFY_MQTT_PASSWORD="${MQTT_PASSWORD}"
export SOMFY_LOG_LEVEL="${LOG_LEVEL}"
export SOMFY_LOG_FORMAT="${LOG_FORMAT}"
export SOMFY_SIMULATION_MODE="${SIMULATION_MODE}"
export SOMFY_FILE_LOGGING="${FILE_LOGGING}"
export SOMFY_CODES_PATH="/data/somfy_codes.json"

echo "USB: ${USB_PORT} | MQTT: ${MQTT_HOST}:${MQTT_PORT} | Log: ${LOG_LEVEL} | Format: ${LOG_FORMAT}"

# ---------- Prepare log directory ----------
mkdir -p /share/somfy_rts/

# ---------- Start Python application ----------
cd /app || exit 1
exec python3 -m somfy_rts.main
