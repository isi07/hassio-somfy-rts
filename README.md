# Somfy RTS — Home Assistant App-Repository

![Release](https://img.shields.io/github/v/release/isi07/hassio-somfy-rts?style=for-the-badge&color=blue)
![License](https://img.shields.io/github/license/isi07/hassio-somfy-rts?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.12+-yellow?style=for-the-badge&logo=python&logoColor=white)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11+-41BDF5?style=for-the-badge&logo=home-assistant&logoColor=white)
![Build](https://img.shields.io/github/actions/workflow/status/isi07/hassio-somfy-rts/build.yaml?style=for-the-badge)
![Arch](https://img.shields.io/badge/Arch-amd64%20%7C%20aarch64-informational?style=for-the-badge)

Steuert **Somfy RTS** Geräte (Markisen, Rollläden, Jalousien) direkt aus
Home Assistant heraus — über einen **NanoCUL USB-Stick** mit culfw-Firmware
und **MQTT**.

---

## Apps in diesem Repository

| App (ehemals Add-on) | Version | Beschreibung |
|----------------------|---------|--------------|
| [Somfy RTS](somfy-rts/DOCS.md) | 0.3.14 | Steuerung von Somfy RTS Geräten via NanoCUL/culfw |

---

## Installation

### Schritt 1 — Repository hinzufügen

[![Add Repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fisi07%2Fhassio-somfy-rts)

Oder manuell:

1. **Einstellungen → Apps → App Store**
2. Oben rechts: **⋮ → Repositories**
3. URL eintragen: `https://github.com/isi07/hassio-somfy-rts`

### Schritt 2 — App installieren

Die App "Somfy RTS" erscheint im App Store unter dem neuen Repository.

### Schritt 3 — Konfigurieren

Minimale Konfiguration (Geräte werden per Anlern-Wizard hinzugefügt):

```yaml
usb_port: /dev/ttyACM0      # Pfad zum NanoCUL USB-Stick
baudrate: 9600
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_user: ""
mqtt_password: ""
address_prefix: "A000"      # Präfix für automatisch generierte Adressen
log_level: info
```

Vollständige Dokumentation: [DOCS.md](somfy-rts/DOCS.md)

---

## Hardware-Voraussetzungen

- **NanoCUL USB-Stick** mit culfw-Firmware (**433,42 MHz** — nicht 433,92 MHz!)
  - Verfügbar z.B. bei busware.de oder als DIY-Bausatz
  - culfw muss bereits geflasht sein
- Somfy RTS kompatible Geräte (Motoren mit dem RTS-Protokoll)

---

## Unterstützte Gerätetypen

| Typ | HA Geräteklasse | Beispiel |
|-----|----------------|---------|
| `awning` | awning | Markise |
| `shutter` | shutter | Rollladen |
| `blind` | blind | Jalousie / Raffstore |
| `screen` | shade | Insektenschutzrollo |
| `gate` | gate | Garagentor / Tor |
| `light` | — | Somfy-kompatibles Licht |
| `heater` | — | Heizung |

---

## Architektur

```
Home Assistant
     │
     ▼
 Somfy RTS App (Docker)
     │           │
     ▼           ▼
 NanoCUL      MQTT Broker
 (USB/Serial)  (Mosquitto)
     │           │
     ▼           ▼
 433,42 MHz   HA Entitäten
 Funk-Signal  (Cover / Buttons)
     │
     ▼
 Somfy RTS Motor
```

---

## Template Cover

Vollständige YAML-Beispiele für Template Covers (Modus A und B) befinden sich in
[DOCS.md](somfy-rts/DOCS.md). Template Covers verbinden Somfy-Entitäten mit einem
physischen Kontaktsensor für einen zuverlässigen Zustand — auch nach manueller
Bedienung oder MY-Taste.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE)
