# CLAUDE.md — Somfy RTS Home Assistant Add-on

## Projektübersicht

**Name:** hassio-somfy-rts  
**GitHub:** https://github.com/isi07/hassio-somfy-rts  
**Lizenz:** MIT  
**Version:** 0.1.0  
**Maintainer:** isi07

Dieses Repository ist ein **Home Assistant Add-on Repository**, das das Add-on
"Somfy RTS" enthält. Das Add-on steuert Somfy RTS Geräte (Markisen, Rollläden,
Jalousien usw.) über einen **NanoCUL USB-Stick** mit **culfw-Firmware** via **MQTT**.

---

## Technischer Stack

| Komponente | Details |
|---|---|
| Add-on Runtime | Docker (baseimage: `ghcr.io/home-assistant/amd64-base-python:3.11`) |
| Sprache | Python 3.11 |
| Protokoll | Somfy RTS (433,42 MHz) über NanoCUL USB (culfw) |
| Kommunikation | MQTT (Paho) → Home Assistant |
| HA-Integration | MQTT Discovery (Cover/Button-Entitäten) |
| Config | Add-on Options (`/data/options.json`) |
| Versionierung | Conventional Commits + git-cliff + semver Tags |

---

## Hardware

- **NanoCUL USB-Stick** mit culfw-Firmware (**433,42 MHz** — nicht 433.92!)
- Kommunikation über serielle Schnittstelle (z.B. `/dev/ttyUSB0`), 38400 Baud
- Sendet RTS-Telegramme; **Checksumme und Verschlüsselung übernimmt culfw intern**

---

## culfw Befehlsformat (Somfy RTS)

```
Sequenz pro Befehl (immer beide Zeilen senden):
  1.  Yr1                            → Wiederholungen auf 1 setzen (PFLICHT)
  2.  YsA0<CMD><RC><ADDR>            → RTS Telegramm

Felder:
  A0    = festes culfw-Präfix (Timing/Flags-Byte)
  CMD   = 1 Byte, 2 Hex-Zeichen, z.B. "02"
  RC    = Rolling Code, 4 Hex-Zeichen (16-Bit Big-Endian), z.B. "001A"
  ADDR  = Geräteadresse, 6 Hex-Zeichen (3 Byte), z.B. "A1B2C3"

Beispiel (OPEN, RC=1, Addr=A1B2C3):
  Yr1
  YsA002001AA1B2C3
```

### CMD-Bytes

| Aktion | CMD (hex) | Beschreibung |
|--------|-----------|--------------|
| OPEN   | 0x2 (02)  | Auf / Hoch |
| CLOSE  | 0x4 (04)  | Ab / Runter |
| STOP   | 0x1 (01)  | My / Stop |
| PROG   | 0x8 (08)  | Programmiermodus (Anlern) |
| MY_UP  | 0x3 (03)  | My + Auf |
| MY_DOWN| 0x5 (05)  | My + Ab |

**WICHTIG:** `repeat=1` (`Yr1`) ist **PFLICHT** für Centralis uno RTS — der Motor
ignoriert Telegramme mit repeat>1.

---

## Rolling Code Persistenz

- Datei: `/data/somfy_codes.json`
- Format:
  ```json
  {
    "devices": [
      {"address": "A1B2C3", "name": "Wohnzimmer", "rolling_code": 42}
    ],
    "groups": [],
    "settings": {
      "address_prefix": "A000",
      "prefix_locked": false
    }
  }
  ```
- **KRITISCH:** Rolling Code wird **atomar** (tempfile + `os.replace()`) gespeichert
  **BEVOR** der RTS-Befehl gesendet wird. Strom-Ausfallsicherheit.
- 16-Bit Rollover (0 → 65535 → 0)
- Adress-Prefix ist konfigurierbar; nach erstem Gerät gesperrt (`prefix_locked: true`)

---

## Projektstruktur

```
hassio-somfy-rts/
├── CLAUDE.md
├── README.md
├── repository.yaml                    # HA Add-on Repository Metadaten
├── cliff.toml                         # git-cliff Changelog-Konfiguration
├── .gitignore
├── .github/
│   └── workflows/
│       └── build.yaml                 # CI: lint bei PR, Build+Release nur bei Tags
├── somfy-rts/                         # Das eigentliche Add-on
│   ├── config.yaml                    # HA Add-on Schema
│   ├── Dockerfile
│   ├── requirements.txt               # paho-mqtt, pyserial
│   ├── run.sh
│   ├── DOCS.md
│   ├── CHANGELOG.md
│   └── somfy_rts/                     # Python-Paket
│       ├── __init__.py                # __version__
│       ├── main.py                    # Einstiegspunkt
│       ├── config.py                  # Liest /data/options.json
│       ├── gateway.py                 # BaseGateway (ABC) + CULGateway
│       ├── cul.py                     # Shim → gateway.py (Rückwärtskompatibilität)
│       ├── rolling_code.py            # Atomare RC-Persistenz (/data/somfy_codes.json)
│       ├── rts.py                     # build_rts_sequence() — culfw-Befehlsbau
│       ├── mqtt_client.py             # MQTT + HA Discovery (Modus A/B, LWT, Origin)
│       ├── cover.py                   # Cover-Entitäts-Logik (Modus A/B)
│       └── device_profiles.json      # Gerätetyp-Definitionen
└── blueprints/
    └── template/
        ├── somfy_markise.yaml         # Template Cover mit Fensterkontakt + Fahrzeit
        └── somfy_rollladen.yaml       # Automation: Sonne + Anwesenheit
```

---

## Architektur

### Gateway-Abstraktion

```python
BaseGateway (ABC)          # gateway.py
    └── CULGateway         # pyserial → NanoCUL
    └── SIGNALduinoGateway # (zukünftig)
```

### MQTT Discovery Struktur

**Gateway-Device** (`identifiers: ["somfy_rts_gateway"]`):
- 4 Diagnose-Sensoren: Verbindung, USB-Port, Geräteanzahl, SW-Version
- Alle `entity_category: diagnostic`

**Sub-Device pro Gerät** (`via_device: "somfy_rts_gateway"`):
- **Modus A:** 1x Cover-Entity (optimistisch, device_class je Typ)
- **Modus B:** 3x Button (`entity_category: config`) + 2x Sensor (`entity_category: diagnostic`)

**Availability:** LWT auf `cul2mqtt/status` (online/offline, retain=True)

**Origin-Block** in allen Discovery-Payloads:
```json
{"name": "Somfy RTS", "support_url": "https://github.com/isi07/hassio-somfy-rts"}
```

---

## Geräte-Modi

| Modus | Discovery | Verwendung |
|-------|-----------|------------|
| A | Cover-Entity (optimistisch) | Standalone, direkte Steuerung |
| B | 3 Buttons + 2 Diagnose-Sensoren | Template Cover in HA (Blueprint) |

---

## Add-on Konfigurationsoptionen

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `serial_port` | string | `/dev/ttyUSB0` | NanoCUL Pfad |
| `baud_rate` | int | 38400 | Baudrate |
| `mqtt_host` | string | `core-mosquitto` | MQTT Broker |
| `mqtt_port` | int | 1883 | MQTT Port |
| `mqtt_user` | string | `""` | MQTT Benutzer |
| `mqtt_password` | password | `""` | MQTT Passwort |
| `mqtt_topic_prefix` | string | `somfy` | MQTT Topic Präfix |
| `log_level` | enum | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `devices` | list | `[]` | Geräteliste |

### Device-Schema

```yaml
devices:
  - name: "Wohnzimmer Markise"
    type: awning        # awning | shutter | blind | screen | gate | light | heater
    address: "A1B2C3"  # 6 Hex-Zeichen (eindeutig!)
    mode: "A"           # A = Cover | B = Buttons
    rolling_code: 0     # Startwert (Persistenz in somfy_codes.json)
```

---

## Gerätetypen (`device_profiles.json`)

| Typ | HA device_class | Icon |
|-----|----------------|------|
| awning | awning | mdi:awning |
| shutter | shutter | mdi:window-shutter |
| blind | blind | mdi:blinds |
| screen | shade | mdi:roller-shade |
| gate | gate | mdi:gate |
| light | — | mdi:lightbulb |
| heater | — | mdi:radiator |

---

## MQTT Topics

### Modus A (Cover)

| Topic | Richtung | Inhalt |
|---|---|---|
| `homeassistant/cover/<id>/config` | Publish | Discovery-Payload (retain) |
| `somfy/<slug>/state` | Publish | open / closed / stopped (retain) |
| `somfy/<slug>/set` | Subscribe | OPEN / CLOSE / STOP |

### Modus B (Buttons)

| Topic | Richtung | Inhalt |
|---|---|---|
| `somfy/<slug>/button/auf` | Subscribe | PRESS |
| `somfy/<slug>/button/zu` | Subscribe | PRESS |
| `somfy/<slug>/button/stop` | Subscribe | PRESS |
| `somfy/<slug>/rolling_code` | Publish | aktueller RC (retain) |
| `somfy/<slug>/last_command` | Publish | OPEN/CLOSE/STOP (retain) |

### Gateway

| Topic | Inhalt |
|---|---|
| `cul2mqtt/status` | online / offline (LWT, retain) |
| `cul2mqtt/gateway/status` | Verbindungstext |
| `cul2mqtt/gateway/port` | USB-Port Pfad |
| `cul2mqtt/gateway/device_count` | Anzahl Geräte |
| `cul2mqtt/gateway/sw_version` | Add-on Version |

---

## Blueprints (HA 2024.11+)

### `blueprints/template/somfy_rts_awning.yaml` — `domain: template`

Erstellt ein Template Cover für Markisen:
- Fensterkontakt-Priorität (Schließen blockiert wenn Fenster offen)
- Fahrzeit-Schätzung via Timer (time_pattern `/1s` nur wenn Timer aktiv)
- Inputs: somfy_cover_entity, device_class, contact_sensor, contact_closed_state,
  use_travel_time, travel_timer, travel_time_open (default 35s), travel_time_close (default 38s)

### `blueprints/template/somfy_rts_shutter.yaml` — `domain: template`

Erstellt ein Template Cover für Rollläden:
- Identische Struktur wie somfy_rts_awning.yaml
- device_class: shutter (default)
- travel_time_open default: 40s, travel_time_close default: 43s
- Labels: "Hochfahren"/"Runterfahren"

---

## CI/CD (GitHub Actions)

- **Lint (`ruff`):** Bei jedem PR und Tag
- **Docker Build (amd64/aarch64/armv7):** Nur bei Tag-Push (`v*`)
- **Release:** Automatisch bei Tag, Changelog via git-cliff
- **Conventional Commits:** `feat:`, `fix:`, `perf:`, `refactor:`, `docs:`, `chore:`, `ci:`
- **Tag-Format:** `v0.1.0` (stable), `v0.1.0-beta.1` (pre-release)
- **Images:** `ghcr.io/isi07/hassio-somfy-rts/somfy-rts:<version>-<arch>`

---

## Anlern-Wizard (5 Schritte)

1. Gerät in `config.yaml` eintragen (`rolling_code: 0`)
2. Add-on neu starten → MQTT Discovery veröffentlicht neue Entität
3. Motor in Programmiermodus versetzen (Orig.-FB PROG 3s halten → kurzes Auf-Ab)
4. In HA: Button/Cover STOP senden (= PROG-Signal, cmd=0x8 oder 0x1)
5. Motor bestätigt mit kurzem Auf-Ab → Pairing abgeschlossen

---

## Entwicklungs-Hinweise

- Lokaler Test: `OPTIONS_PATH=./test_options.json SOMFY_CODES_PATH=./test_codes.json python -m somfy_rts.main`
- culfw antwortet auf `V\n` mit Versions-String
- `cul.py` ist ein Shim → immer `gateway.py` direkt importieren
- Rolling Code Datei NIE manuell löschen → Neu-Pairing nötig
