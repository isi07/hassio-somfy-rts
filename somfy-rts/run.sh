#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Somfy RTS Add-on..."

# ---------- Read config via bashio ----------
USB_PORT=$(bashio::config 'usb_port')
BAUDRATE=$(bashio::config 'baudrate')
MQTT_HOST=$(bashio::config 'mqtt_host')
MQTT_PORT=$(bashio::config 'mqtt_port')
MQTT_USER=$(bashio::config 'mqtt_user')
MQTT_PASSWORD=$(bashio::config 'mqtt_password')
ADDRESS_PREFIX=$(bashio::config 'address_prefix')
LOG_LEVEL=$(bashio::config 'log_level')

# ---------- Validate USB port ----------
if [ ! -e "${USB_PORT}" ]; then
    bashio::log.warning "USB port ${USB_PORT} not found."
    bashio::log.warning "Please connect the NanoCUL USB stick and restart the add-on."
fi

# ---------- Initialize /data/somfy_codes.json if missing ----------
if [ ! -f /data/somfy_codes.json ]; then
    bashio::log.info "Initializing /data/somfy_codes.json..."
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
export SOMFY_CODES_PATH="/data/somfy_codes.json"

bashio::log.info "USB: ${USB_PORT} | MQTT: ${MQTT_HOST}:${MQTT_PORT} | Log: ${LOG_LEVEL}"

# ---------- Start Python application ----------
cd /app
exec python3 -m somfy_rts.main
