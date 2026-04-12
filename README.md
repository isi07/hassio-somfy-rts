# Somfy RTS — Home Assistant Add-on Repository

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/isi07/hassio-somfy-rts)](https://github.com/isi07/hassio-somfy-rts/releases)
[![Build Status](https://github.com/isi07/hassio-somfy-rts/actions/workflows/build.yaml/badge.svg)](https://github.com/isi07/hassio-somfy-rts/actions)

Steuert **Somfy RTS** Geräte (Markisen, Rollläden, Jalousien) direkt aus
Home Assistant heraus — über einen **NanoCUL USB-Stick** mit culfw-Firmware
und **MQTT**.

---

## Add-ons in diesem Repository

| Add-on | Version | Beschreibung |
|--------|---------|--------------|
| [Somfy RTS](somfy-rts/DOCS.md) | 0.1.0 | Steuerung von Somfy RTS Geräten via NanoCUL/culfw |

---

## Installation

### Schritt 1 — Repository hinzufügen

[![Add Repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fisi07%2Fhassio-somfy-rts)

Oder manuell:

1. **Einstellungen → Add-ons → Add-on Store**
2. Oben rechts: **⋮ → Repositories**
3. URL eintragen: `https://github.com/isi07/hassio-somfy-rts`

### Schritt 2 — Add-on installieren

Das Add-on "Somfy RTS" erscheint im Add-on Store unter dem neuen Repository.

### Schritt 3 — Konfigurieren

Beispielkonfiguration:

```yaml
serial_port: /dev/ttyUSB0
baud_rate: 38400
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_user: ""
mqtt_password: ""
mqtt_topic_prefix: somfy

devices:
  - name: Terrasse Markise
    type: awning
    address: A1B2C3
    rolling_code: 0
  - name: Wohnzimmer Rollladen
    type: roller_shutter
    address: D4E5F6
    rolling_code: 0
```

Vollständige Dokumentation: [DOCS.md](somfy-rts/DOCS.md)

---

## Hardware-Voraussetzungen

- **NanoCUL USB-Stick** mit culfw-Firmware (433,42 MHz)
  - Verfügbar z.B. bei busware.de oder als DIY-Bausatz
  - culfw muss bereits geflasht sein
- Somfy RTS kompatible Geräte (Motoren mit dem RTS-Protokoll)

---

## Architektur

```
Home Assistant
     │
     ▼
 Somfy RTS Add-on (Docker)
     │           │
     ▼           ▼
 NanoCUL      MQTT Broker
 (USB/Serial)  (Mosquitto)
     │           │
     ▼           ▼
 433,42 MHz   HA Entitäten
 Funk-Signal  (Cover)
     │
     ▼
 Somfy RTS Motor
```

---

## Blueprints

Im Ordner `blueprints/template/` befinden sich vorgefertigte Automatisierungs-
Blueprints:

- **somfy_markise.yaml** — Zeitsteuerung, Windschutz, Regenschutz
- **somfy_rollladen.yaml** — Sonnenaufgang/Sonnenuntergang, Anwesenheit

---

## Lizenz

MIT — siehe [LICENSE](LICENSE)
