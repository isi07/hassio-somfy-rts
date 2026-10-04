# Somfy RTS — Home Assistant App-Repository

![Release](https://img.shields.io/github/v/release/isi07/hassio-somfy-rts?style=for-the-badge&color=blue)
![License](https://img.shields.io/github/license/isi07/hassio-somfy-rts?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.14-yellow?style=for-the-badge&logo=python&logoColor=white)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11+-41BDF5?style=for-the-badge&logo=home-assistant&logoColor=white)
![Build](https://img.shields.io/github/actions/workflow/status/isi07/hassio-somfy-rts/build.yaml?style=for-the-badge)
![Arch](https://img.shields.io/badge/Arch-amd64%20%7C%20aarch64-informational?style=for-the-badge)

Steuert **Somfy RTS** Geräte (Markisen, Rollläden, Jalousien) direkt aus
Home Assistant heraus — über einen **NanoCUL USB-Stick** mit culfw-Firmware
und **MQTT**.

---

## Apps in diesem Repository

| App (ehemals Add-on) | Beschreibung |
|----------------------|--------------|
| [Somfy RTS](somfy-rts/DOCS.md) | Steuerung von Somfy RTS Geräten via NanoCUL/culfw |

Aktuelle Version: siehe Release-Badge oben bzw. [Releases](https://github.com/isi07/hassio-somfy-rts/releases)
und [CHANGELOG](somfy-rts/CHANGELOG.md).

### Funktionen

- **Anlern-Wizard** in der Web-UI (Ingress) — Motor ohne Konfigurationsdateien anlernen
- **Import** bereits angelernter Geräte (z. B. aus ioBroker) mit Adresse und Rolling Code
- **MQTT Discovery** — Geräte erscheinen automatisch in Home Assistant, wahlweise als
  Cover/Light/Switch (Modus A) oder als Buttons für Template Covers (Modus B)
- **MY-Position**, Lamellensteuerung (Jalousien), PROG-Funktionen direkt aus HA
- **Rolling Codes ausfallsicher** gespeichert — Senden nur, wenn der Code persistiert ist

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

Weitere Optionen (Simulation ohne Hardware, Frame-Log, Zeitzone, Debug-Modus) stehen in
[DOCS.md](somfy-rts/DOCS.md#konfiguration).

Vollständige Dokumentation: [DOCS.md](somfy-rts/DOCS.md)

---

## Hardware-Voraussetzungen

- **NanoCUL USB-Stick** (433 MHz) mit culfw-Firmware (**433,42 MHz** — nicht 433,92 MHz!)
  - culfw muss bereits geflasht sein, **mit Somfy-RTS-Unterstützung** (`HAS_SOMFY_RTS` —
    im Standard-Build von a-culfw für den nanoCUL deaktiviert)
  - Die App **sendet** nur; culfw kann Somfy-Funk nicht empfangen (kein Rückkanal)
- **MQTT Broker**, z. B. die Mosquitto App
- Somfy RTS kompatible Geräte (Motoren mit dem RTS-Protokoll)

---

## Unterstützte Gerätetypen

| Typ | HA Entität (Modus A) | Beispiel |
|-----|---------------------|---------|
| `awning` | Cover (awning) | Markise |
| `shutter` | Cover (shutter) | Rollladen |
| `blind` | Cover (blind) + MY Auf/Runter | Jalousie / Raffstore |
| `screen` | Cover (shade) | Insektenschutzrollo |
| `gate` | Cover (gate) | Garagentor / Tor |
| `light` | Light (Ein/Aus) | Somfy Lighting Slim Receiver |
| `heater` | Switch (Ein/Aus) | Somfy Heat Receiver |
| `light_dimmer` | — (nur Modus B) | Somfy Lighting Dimmer |

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
 Funk-Signal  (Cover / Light / Switch /
     │         Buttons / Sensoren)
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
