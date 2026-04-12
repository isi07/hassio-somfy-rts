#!/usr/bin/with-contenv bashio

bashio::log.info "Starte Somfy RTS Add-on..."

# Validate serial port exists
SERIAL_PORT=$(bashio::config 'serial_port')
if [ ! -e "${SERIAL_PORT}" ]; then
    bashio::log.warning "Serielle Schnittstelle ${SERIAL_PORT} nicht gefunden."
    bashio::log.warning "Bitte NanoCUL USB-Stick anschließen und Add-on neu starten."
fi

cd /app
exec python3 -m somfy_rts.main
