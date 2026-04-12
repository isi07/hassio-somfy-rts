# Changelog

Alle nennenswerten Änderungen werden in dieser Datei dokumentiert.
Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [0.1.0] - 2026-04-12

### Hinzugefügt
- Initiale Version des Somfy RTS Add-ons
- Unterstützung für NanoCUL USB-Stick mit culfw-Firmware
- MQTT Integration mit Home Assistant Discovery
- Gerätetypen: Markise (`awning`), Jalousie (`blind`), Rollladen (`roller_shutter`)
- Persistente Rolling Code Speicherung in `/data/rolling_codes.json`
- Unterstützung für Architekturen: amd64, aarch64, armv7
- Befehle: OPEN, CLOSE, STOP (My-Taste)
