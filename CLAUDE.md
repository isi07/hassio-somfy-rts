# CLAUDE.md — Somfy RTS Home Assistant App

## Inhaltsverzeichnis

- [⚠️ Kritische Invarianten](#kritische-invarianten--vor-jeder-änderung-lesen)
- [Projektübersicht](#projektübersicht)
- [Technischer Stack](#technischer-stack)
- [Hardware](#hardware)
- [culfw Befehlsformat](#culfw-befehlsformat-somfy-rts)
- [Rolling Code Persistenz](#rolling-code-persistenz)
- [Projektstruktur](#projektstruktur)
- [Architektur](#architektur)
- [Geräte-Modi](#geräte-modi)
- [App-Konfigurationsoptionen](#app-konfigurationsoptionen)
- [Gerätetypen](#gerätetypen-device_profilesjson)
- [MQTT Topics](#mqtt-topics)
- [Blueprints](#blueprints-ha-202411)
- [CI/CD](#cicd-github-actions)
- [Anlern-Wizard](#anlern-wizard-wizardpy)
- [Dokumentationspflicht](#dokumentationspflicht)
- [Code-Qualitätsstandards](#code-qualitätsstandards)
- [Release-Prozess](#release-prozess-immer-in-dieser-reihenfolge)
- [Interaction Protocol](#interaction-protocol)
- [Do's / Don'ts](#dos--donts)
- [Refactoring Checkliste](#refactoring-checkliste)
- [Entwicklungs-Hinweise](#entwicklungs-hinweise)

---

## ⚠️ Kritische Invarianten — vor jeder Änderung lesen

### 1 · Rolling Code Atomizität

- RC wird **atomar** (`tempfile` + `os.replace()`) gespeichert **BEVOR** der RTS-Befehl gesendet wird
- Reihenfolge: `RC speichern` → `Yr{n} senden` → `YsA0… senden`
- **NIEMALS** RC nach dem Senden speichern — bei Stromausfall dazwischen lässt sich der Motor nicht mehr steuern
- **NIEMALS** direkt in `somfy_codes.json` schreiben ohne `os.replace()`

```python
# ❌ FALSCH — RC wird nach dem Senden gespeichert
gateway.send_raw("Yr1")
gateway.send_raw(telegram)
save_rolling_code(rc)            # Stromausfall hier → RC desynchronisiert!

# ✅ RICHTIG — RC atomar BEVOR dem Senden (rolling_code.py: get_and_increment)
rc = get_and_increment(address)  # speichert atomar via tempfile + os.replace()
telegram = f"YsA0{cmd:02X}{rc:04X}{address}"
gateway.send_raw("Yr1")
gateway.send_raw(telegram)
```

### 2 · Yr{n} Pflicht-Kommando

- `Yr{n}` **MUSS** immer **VOR** dem `YsA0…`-Telegramm gesendet werden
- Centralis uno RTS ignoriert Telegramme ohne vorherigen `Yr`-Befehl — **kommentarlos, kein Fehler**
- `build_rts_sequence()` gibt **immer** `[f"Yr{repeat}", telegram]` zurück — nie nur `[telegram]`
- `log_rts_frame()` wird **nach** dem `send_raw()`-Loop aufgerufen — `STATUS=OK` bedeutet echt gesendet
- **repeat-Werte:** `1` = Normalbefehle (Centralis uno: PFLICHT!), `4` = PROG Anlern, `8` = PROG Lang

```python
# ❌ FALSCH — Yr{n} fehlt
gateway.send_raw(telegram)        # Motor ignoriert das Telegramm stillschweigend!

# ✅ RICHTIG — beide Kommandos aus RTSSequence.commands, log NACH dem Senden
seq = build_rts_sequence(address, action, name)          # repeat=1 (Standard)
seq = build_rts_sequence(address, "PROG", name, repeat=8)  # PROG Lang
for cmd in seq.commands:          # [f"Yr{repeat}", "YsA0..."]
    gateway.send_raw(cmd)
log_rts_frame(seq, address, action, success=True)   # erst hier: STATUS=OK ist echt
```

---

## Projektübersicht

**Name:** hassio-somfy-rts  
**GitHub:** https://github.com/isi07/hassio-somfy-rts  
**Lizenz:** MIT  
**Version:** 0.1.0  
**Maintainer:** isi07

Dieses Repository ist ein **Home Assistant App-Repository** (ehemals Add-on-Repository),
das die App "Somfy RTS" enthält. Die App steuert Somfy RTS Geräte (Markisen, Rollläden,
Jalousien usw.) über einen **NanoCUL USB-Stick** mit **culfw-Firmware** via **MQTT**.

---

## Technischer Stack

| Komponente | Details |
|---|---|
| App Runtime | Docker (baseimage: `ghcr.io/home-assistant/amd64-base-python:3.12`) |
| Sprache | Python 3.12 |
| Protokoll | Somfy RTS (433,42 MHz) über NanoCUL USB (culfw) |
| Kommunikation | MQTT (Paho) → Home Assistant |
| HA-Integration | MQTT Discovery (Cover/Button-Entitäten) |
| Config | App-Options (`/data/options.json`) |
| Versionierung | Conventional Commits + git-cliff + semver Tags |

---

## Hardware

- **NanoCUL USB-Stick** mit culfw-Firmware (**433,42 MHz** — nicht 433.92!)
- Kommunikation über serielle Schnittstelle (z.B. `/dev/ttyACM0`), 9600 Baud
- Sendet RTS-Telegramme; **Checksumme und Verschlüsselung übernimmt culfw intern**

---

## culfw Befehlsformat (Somfy RTS)

```
Sequenz pro Befehl (immer beide Zeilen senden):
  1.  Yr{n}                          → Wiederholungsanzahl setzen (Standard: n=1)
  2.  YsA0<CMD><RC><ADDR>            → RTS Telegramm

  Wiederholungswerte (n):
    1 = Normalbefehle (PFLICHT für Centralis uno RTS!)
    4 = PROG Anlern (virtuellen Sender am Motor registrieren)
    8 = PROG Lang (Motor in Anlernmodus versetzen, ersetzt PROG-Taste der Original-FB)

Felder:
  A0    = festes culfw-Präfix (Timing/Flags-Byte)
  CMD   = 1 Byte, 2 Hex-Zeichen = Byte 1 des Somfy-Frames
          Byte 1 = (ctrl << 4) | cks
          ctrl  = Befehlsnibble im High-Nibble, z.B. 0x2 für OPEN → "20"
          cks   = Prüfsummen-Nibble (Low-Nibble), von culfw intern berechnet
          → culfw erwartet ctrl im High-Nibble mit cks=0
  RC    = Rolling Code, 4 Hex-Zeichen (16-Bit Big-Endian), z.B. "001A"
  ADDR  = Geräteadresse, 6 Hex-Zeichen (3 Byte), z.B. "A1B2C3"

Beispiel (UP, RC=1, Addr=A1B2C3, repeat=1):
  Yr1
  YsA020001AA1B2C3

Beispiel PROG Lang (repeat=8):
  Yr8
  YsA080001AA1B2C3
```

### CMD-Bytes

| Aktion | ctrl-Nibble | Byte 1 (ctrl<<4) | Beschreibung |
|--------|-------------|------------------|--------------|
| OPEN   | 0x2         | 0x20             | Auf / Hoch |
| CLOSE  | 0x4         | 0x40             | Ab / Runter |
| STOP   | 0x1         | 0x10             | My / Stop |
| PROG   | 0x8         | 0x80             | Programmiermodus (Anlern) |
| MY_UP  | 0x3         | 0x30             | My + Auf |
| MY_DOWN| 0x5         | 0x50             | My + Ab |

**WICHTIG:** `repeat=1` (`Yr1`) ist **PFLICHT** für Centralis uno RTS bei Normalbefehlen — der Motor
ignoriert Telegramme mit repeat>1. Ausnahme: PROG-Telegramme mit repeat=4 oder repeat=8
werden unterstützt und von culfw korrekt verarbeitet.

---

## Rolling Code Persistenz

- Datei: `/data/somfy_codes.json`
- Format:
  ```json
  {
    "devices": [
      {
        "address": "A1B2C3",
        "name": "Wohnzimmer",
        "rolling_code": 42,
        "device_type": "shutter",
        "mode": "A"
      }
    ],
    "groups": [],
    "settings": {
      "address_prefix": "A000",
      "prefix_locked": false
    }
  }
  ```
- `mode`: `"A"` = Cover-Entity (optimistisch), `"B"` = 3 Buttons + 2 Diagnose-Sensoren
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
├── repository.yaml                    # HA App-Repository Metadaten
├── cliff.toml                         # git-cliff Changelog-Konfiguration
├── .gitignore
├── .github/
│   └── workflows/
│       └── build.yaml                 # CI: lint bei PR, Build+Release nur bei Tags
├── somfy-rts/                         # Die eigentliche App
│   ├── config.yaml                    # HA App-Schema
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
│       ├── rolling_code.py            # Atomare RC-Persistenz (/data/somfy_codes.json)
│       ├── rts.py                     # build_rts_sequence() → RTSSequence, log_rts_frame()
│       ├── mqtt_client.py             # MQTT + HA Discovery (Modus A/B, LWT, Origin)
│       ├── device.py                  # Device-Klasse (alle 7 Typen, Modus A/B)
│       ├── wizard.py                  # PairingWizard (5-Schritt Anlern-Flow)
│       └── device_profiles.json      # Gerätetyp-Definitionen
└── blueprints/
    └── template/
        ├── somfy_rts_awning.yaml      # Template Cover Markise: Fensterkontakt + Fahrzeit
        └── somfy_rts_shutter.yaml     # Template Cover Rollladen: Fensterkontakt + Fahrzeit
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
| A | Cover-Entity (optimistisch) + 3 Diagnose-Sensoren + 2 PROG-Buttons | Standalone, direkte Steuerung |
| B | 3 Buttons + 2 PROG-Buttons + 2 Diagnose-Sensoren | Template Cover in HA (Blueprint) |

### PROG-Buttons (beide Modi, entity_category: config)

| Button | unique_id Suffix | Topic | Payload |
|--------|-----------------|-------|---------|
| PROG Lang | `_prog_long` | `somfy/<slug>/cmd` | `PROG_LONG` → PROG Yr8 |
| PROG Anlern | `_prog_pair` | `somfy/<slug>/cmd` | `PROG_PAIR` → PROG Yr4 |

Beide Buttons erscheinen in HA unter **Konfiguration** des jeweiligen Geräts.
Kein Cover-State-Update bei PROG_LONG/PROG_PAIR — nur `rolling_code` + `last_command` (="PROG").

### Diagnose-Sensoren (beide Modi)

| Sensor | Topic | Inhalt |
|--------|-------|--------|
| `rolling_code` | `somfy/<slug>/rolling_code` | aktueller RC nach jedem Befehl (integer) |
| `last_command` | `somfy/<slug>/last_command` | letzter Befehl (OPEN/CLOSE/STOP/MY/PROG) |
| `last_command` Attribut | `somfy/<slug>/last_command_attr` | `{"raw_frame": "YsA0…"}` — vollständiger Telegram-String |

### Nur Modus A zusätzlich

| Sensor | Topic | Inhalt |
|--------|-------|--------|
| `device_address` | `somfy/<slug>/device_address` | statische Hex-Adresse des virtuellen Senders |

### Availability

Alle Discovery-Payloads (Cover, Buttons, Sensoren, Gateway) enthalten einen Availability-Block:
```json
{"topic": "cul2mqtt/status", "payload_available": "online", "payload_not_available": "offline"}
```
Das LWT-Topic `cul2mqtt/status` wird bei Verbindungsabbruch automatisch auf `"offline"` gesetzt.

---

## App-Konfigurationsoptionen

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `usb_port` | string | `/dev/ttyACM0` | NanoCUL Pfad |
| `baudrate` | int | 9600 | Baudrate |
| `mqtt_host` | string | `core-mosquitto` | MQTT Broker |
| `mqtt_port` | int | 1883 | MQTT Port |
| `mqtt_user` | string | `""` | MQTT Benutzer |
| `mqtt_password` | password | `""` | MQTT Passwort |
| `address_prefix` | string | `A000` | Präfix für neue Adressen (4 Hex-Zeichen) |
| `log_level` | enum | `info` | debug/info/warning/error |

Geräte werden **nicht** in `config.yaml` verwaltet, sondern in `/data/somfy_codes.json`
(automatisch durch den Anlern-Wizard oder ioBroker-Import erstellt).

### Device-Schema (somfy_codes.json)

```json
{
  "devices": [
    {
      "address": "A1B2C3",
      "name": "Wohnzimmer Markise",
      "rolling_code": 42,
      "device_type": "shutter",
      "mode": "A"
    }
  ]
}
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

### Modus A (Cover + Diagnose-Sensoren + PROG-Buttons)

| Topic | Richtung | Inhalt |
|---|---|---|
| `homeassistant/cover/<id>/config` | Publish | Discovery-Payload Cover (retain) |
| `homeassistant/sensor/<id>_rolling_code/config` | Publish | Discovery Rolling Code (retain) |
| `homeassistant/sensor/<id>_last_command/config` | Publish | Discovery Letzter Befehl (retain) |
| `homeassistant/sensor/<id>_device_address/config` | Publish | Discovery Adresse (retain) |
| `homeassistant/button/<id>_prog_long/config` | Publish | Discovery PROG Lang (retain) |
| `homeassistant/button/<id>_prog_pair/config` | Publish | Discovery PROG Anlern (retain) |
| `somfy/<slug>/state` | Publish | open / closed / stopped (retain) |
| `somfy/<slug>/set` | Subscribe | OPEN / CLOSE / STOP |
| `somfy/<slug>/cmd` | Subscribe | PROG_LONG / PROG_PAIR |
| `somfy/<slug>/rolling_code` | Publish | aktueller RC nach Befehl (retain) |
| `somfy/<slug>/last_command` | Publish | OPEN/CLOSE/STOP/MY/PROG (retain) |
| `somfy/<slug>/last_command_attr` | Publish | `{"raw_frame": "YsA0…"}` (retain) |
| `somfy/<slug>/device_address` | Publish | Hex-Adresse, einmalig beim Setup (retain) |

### Modus B (Buttons + PROG-Buttons + Diagnose-Sensoren)

| Topic | Richtung | Inhalt |
|---|---|---|
| `homeassistant/button/<id>_prog_long/config` | Publish | Discovery PROG Lang (retain) |
| `homeassistant/button/<id>_prog_pair/config` | Publish | Discovery PROG Anlern (retain) |
| `somfy/<slug>/button/auf` | Subscribe | PRESS |
| `somfy/<slug>/button/zu` | Subscribe | PRESS |
| `somfy/<slug>/button/stop` | Subscribe | PRESS |
| `somfy/<slug>/cmd` | Subscribe | PROG_LONG / PROG_PAIR |
| `somfy/<slug>/rolling_code` | Publish | aktueller RC (retain) |
| `somfy/<slug>/last_command` | Publish | OPEN/CLOSE/STOP/MY/PROG (retain) |
| `somfy/<slug>/last_command_attr` | Publish | `{"raw_frame": "YsA0…"}` (retain) |

### Gateway

| Topic | Inhalt |
|---|---|
| `cul2mqtt/status` | online / offline (LWT, retain) |
| `cul2mqtt/gateway/status` | Verbindungstext |
| `cul2mqtt/gateway/port` | USB-Port Pfad |
| `cul2mqtt/gateway/device_count` | Anzahl Geräte |
| `cul2mqtt/gateway/sw_version` | App-Version |

---

## Blueprints (HA 2024.11+)

Blueprints verwenden **Modus A** (Cover-Entität). Fahrzeitverfolgung wurde entfernt —
sie ist unzuverlässig bei MY-Taste und manueller Fernbedienung.
Zustand kommt ausschließlich vom Kontaktsensor.

### `blueprints/template/somfy_rts_awning.yaml` — `domain: template`

Erstellt ein Template Cover für Markisen (device_class: awning):
- Inputs: `somfy_cover_entity`, `contact_sensor`, `contact_closed_state` (default: `"off"`)
- `value_template`: Sensor == contact_closed_state → `closed`, sonst `open`
- `availability_template`: beide Entitäten nicht unknown/unavailable

### `blueprints/template/somfy_rts_shutter.yaml` — `domain: template`

Erstellt ein Template Cover für Rollläden (device_class: shutter):
- Identische Struktur wie somfy_rts_awning.yaml
- `contact_closed_state` default: `"on"` (Rollladensensor an = geschlossen)

---

## CI/CD (GitHub Actions)

- **Lint (`ruff`):** Bei jedem PR und Tag
- **Docker Build (amd64/aarch64):** Nur bei Tag-Push (`v*`)
- **Release:** Automatisch bei Tag, Changelog via git-cliff
- **Conventional Commits:** `feat:`, `fix:`, `perf:`, `refactor:`, `docs:`, `chore:`, `ci:`
- **Tag-Format:** `v0.1.0` (stable), `v0.1.0-beta.1` (pre-release)
- **Images:** `ghcr.io/isi07/hassio-somfy-rts/somfy-rts:<version>-<arch>`

---

## Anlern-Wizard (`wizard.py`)

Der `PairingWizard` steuert den 5-stufigen Anlern-Flow:

1. `wizard.start(name, device_type, mode="A")` — Adresse generieren, RC auf 0 setzen, in `somfy_codes.json` voranlegen (inkl. `mode`-Feld)
2. Motor in Programmiermodus versetzen — entweder:
   - **Klassisch:** Orig.-FB PROG 3s halten → kurzes Auf-Ab
   - **Alternativ:** `wizard.send_prog_long()` (Yr8) senden — ersetzt die Original-FB
3. `wizard.send_prog_pair()` (oder Alias `wizard.send_prog()`) — PROG Yr4 senden → virtuellen Sender anlernen
4. Operator sieht Motor-Bestätigungsbewegung → `wizard.confirm()` aufrufen
5. `wizard.get_device_config()` — Config-Dict zurückgeben (enthält `mode`)

### PROG-Methoden im Wizard

| Methode | repeat | Aktion | Zustand danach |
|---------|--------|--------|----------------|
| `send_prog_long()` | Yr8 | Motor in Anlernmodus versetzen (ersetzt Orig.-FB PROG) | ADDR_READY |
| `send_prog_pair()` | Yr4 | Virtuellen Sender am Motor registrieren/deregistrieren | PROG_SENT |
| `send_prog()` | Yr4 | Alias für `send_prog_pair()` | PROG_SENT |

**Modus A/B** ist in der Web-UI wählbar: Anlern-Wizard (Schritt 1) und Import-Dialog
bieten je ein Dropdown — `A` = Cover-Entity, `B` = Buttons + Sensoren für Blueprint.

**ioBroker-Import:** `PairingWizard.import_from_iobroker(name, type, address, rolling_code, mode="A")`  
Rolling Code muss ≥ letzter ioBroker-Wert sein (Sicherheitsmarge +10 empfohlen).
Auch hier ist `mode` ein optionaler Parameter (`"A"` oder `"B"`).

### REST-Endpunkt: `POST /api/devices/import`

Für Geräte, die bereits via ioBroker oder einer anderen App gepaart wurden:

```json
{
  "name": "Carport Markise",
  "device_type": "awning",
  "address": "A1B2C3",
  "rolling_code": 42,
  "mode": "A"
}
```

- Antwort: HTTP 201 + Device-Dict (inkl. `mode`)
- Validierung: Name, Adresse (6 Hex-Zeichen), RC ≥ 0, `device_type` aus Whitelist, `mode` ∈ {A, B}
- Publiziert MQTT Discovery sofort (kein Neustart nötig)

### `rts.py` — `RTSSequence` und Frame-Logging

`build_rts_sequence(address, action, device_name="", repeat=1)` gibt einen `RTSSequence`-Dataclass zurück:

```python
@dataclass
class RTSSequence:
    commands: list[str]   # [f"Yr{repeat}", "YsA0..."]
    frame: str            # telegram string = commands[1]
    rc_before: int        # rolling code vor Inkrement
    rc_after: int         # rolling code nach Inkrement (im Frame kodiert)
    repeat: int = 1       # culfw repeat count (Yr{repeat})
```

`log_rts_frame(seq, device_id, action, success, error="")` wird vom **Aufrufer** nach
dem `send_raw()`-Loop aufgerufen — **nicht** innerhalb von `build_rts_sequence()`.
`STATUS=OK` im Frame-Log bedeutet damit, dass das Telegramm wirklich gesendet wurde.
Das Frame-Log enthält `REPEAT={n}` (text) bzw. `"repeat": n` (JSON).

### REST-Endpunkte für PROG

| Endpunkt | repeat | Aktion |
|----------|--------|--------|
| `POST /api/devices/{id}/prog-long` | Yr8 | Motor in Anlernmodus versetzen |
| `POST /api/devices/{id}/prog-pair` | Yr4 | Virtuellen Sender registrieren/deregistrieren |
| `POST /api/wizard/send_prog_long` | Yr8 | Wizard: Motor in Anlernmodus (Zustand bleibt ADDR_READY) |
| `POST /api/wizard/send_prog` | Yr4 | Wizard: Virtuellen Sender anlernen (→ PROG_SENT) |

### MQTT Discovery Cleanup beim Löschen

`DELETE /api/devices/{id}` ruft **vor** dem Löschen aus `somfy_codes.json` die Methode
`mqtt_client.unregister_device(device_cfg)` auf — sofern ein MQTT-Client verfügbar ist.
Danach wird `update_device_count()` mit der neuen Geräteanzahl publiziert.

`mqtt_client.unregister_device(device: DeviceConfig)` publiziert eine leere Payload (`""`)
mit `retain=True` auf alle Discovery-Topics des Geräts. HA entfernt die Entitäten dadurch
automatisch ohne Neustart.

`discovery_topics(device: DeviceConfig) → list[str]` (Modul-Level-Hilfsfunktion in
`mqtt_client.py`) gibt alle Discovery-Topic-Namen zurück — gemeinsam genutzt von
`unregister_device()` und implizit von den `_register_mode_*()` Methoden, damit
Registrierung und Deregistrierung immer dieselben Topics verwenden.

| Modus | Topics die gecleart werden |
|-------|---------------------------|
| A | cover, sensor_rolling_code, sensor_last_command, sensor_device_address, button_prog_long, button_prog_pair |
| B | button_auf, button_zu, button_stop, sensor_rolling_code, sensor_last_command, button_prog_long, button_prog_pair |

### Gateway TX-Logging

`CULGateway.send_raw()` und `SimGateway.send_raw()` loggen jeden gesendeten Befehl
auf **`INFO`**-Level (`CUL TX: ...` bzw. `[SIM] TX: ...`), nicht mehr auf DEBUG.

---

## Dokumentationspflicht

Bei **jeder** Änderung am Code müssen folgende Dateien geprüft und falls nötig
aktualisiert werden:

- **CLAUDE.md** — bei Änderungen an Dateistruktur, Modulnamen,
  Konfigurationsfeldern, Workflows
- **somfy-rts/DOCS.md** — bei Änderungen an `config.yaml`-Optionen,
  neuen Features, Anlern-Prozess, Blueprints
- **README.md** — bei neuen Features oder geänderten Installationsschritten
- **somfy-rts/CHANGELOG.md** — wird automatisch via git-cliff generiert,
  **NICHT manuell bearbeiten**

**Commit-Regel:** Dokumentationsänderungen immer im **gleichen Commit** wie der
zugehörige Code.

- Falsch: `feat: add travel time tracking` gefolgt von `docs: update readme`
- Richtig: `feat: add travel time tracking` enthält bereits die aktualisierten Docs

---

## Code-Qualitätsstandards

### Type Hints

Alle Funktionen und Methoden müssen vollständige Type Hints haben:

```python
# Falsch:
def send(address, code, cmd):
    ...

# Richtig:
def send(address: str, rolling_code: int, cmd: str) -> bool:
    ...
```

- Parameter mit Typen annotieren
- Rückgabewert mit `->` annotieren
- `-> None` explizit angeben wenn nichts zurückgegeben wird
- Komplexe Typen aus `typing` importieren: `Optional`, `List`, `Dict`, `Tuple`, `Union`

### Docstrings

Jede Klasse und jede öffentliche Methode braucht einen Docstring (Google Style):

```python
def send_prog(self, address: str) -> bool:
    """Send PROG command to enter pairing mode.

    Args:
        address: 6-char hex address e.g. 'A00000'

    Returns:
        True if command was sent successfully
    """
```

### Ruff Regeln (bereits in build.yaml)

| Selector | Bedeutung |
|----------|-----------|
| `E` | pycodestyle Fehler (Pflicht) |
| `F` | pyflakes — unused imports, undefined names (Pflicht) |
| `I` | isort — Import-Reihenfolge |
| `UP` | pyupgrade — moderne Python-Syntax |

### Allgemein

- **Keine Magic Numbers:** Konstanten definieren — `BAUDRATE = 9600` statt direkt `9600`
- **Maximale Zeilenlänge:** 88 Zeichen (ruff default)
- **Kein `print()`:** immer `logging` verwenden
- **Spezifische Exceptions:** `except serial.SerialException` statt `except Exception`

### Bestehender Code

Bei Änderungen an bestehenden Dateien: Type Hints und Docstrings nur für
**geänderte Funktionen** ergänzen — nicht die ganze Datei auf einmal umschreiben.

---

## Release-Prozess (IMMER in dieser Reihenfolge)

1. version in `somfy-rts/config.yaml` auf neue Version setzen
2. `git cliff --unreleased --tag vX.Y.Z -o somfy-rts/CHANGELOG.md`
3. `git add -A`
4. `git commit -m "chore: release X.Y.Z"`
5. `git tag vX.Y.Z`
6. `git push origin main`
7. `git push origin vX.Y.Z`

**NIEMALS** einen Tag setzen ohne vorher die Version in `config.yaml` aktualisiert zu haben.
Tag und `config.yaml` version müssen **IMMER** übereinstimmen.

---

## Interaction Protocol

1. **Approach zuerst** — Vor dem Coden den geplanten Ansatz kurz beschreiben (außer bei trivialen Änderungen < 5 Zeilen). Das verhindert unnötige Arbeit bei falschen Annahmen.
2. **Anforderungen klären** — Unklares sofort fragen, nicht raten und nachträglich korrigieren.
3. **Edge Cases nennen** — Nach jeder Implementierung: Was könnte schiefgehen? Welche Tests fehlen noch?
4. **Bug Fix = Test zuerst** — Erst einen reproduzierenden Test schreiben, dann fixen, dann prüfen ob der Test grün ist.
5. **Aus Korrekturen lernen** — Was war das Problem, warum ist es passiert, wie in Zukunft vermeiden?

---

## Do's / Don'ts

### ✅ Do's

- `Yr{n}` immer **vor** `YsA0…` senden — `build_rts_sequence(repeat=n)` macht das automatisch
- RC **atomar** speichern (`tempfile` + `os.replace()`) **vor** dem Senden
- `log_rts_frame()` **nach** `send_raw()` aufrufen
- `pytest` nach jeder Änderung ausführen — alle Tests müssen grün bleiben
- `CLAUDE.md` und `DOCS.md` im **gleichen Commit** wie Code-Änderungen aktualisieren
- Approach kurz beschreiben bevor Code geschrieben wird
- Type Hints für **geänderte** Funktionen ergänzen (nicht die ganze Datei umschreiben)

### ❌ Don'ts

- RC **nicht** nach dem Senden speichern
- `Yr{n}` **nicht** weglassen
- `log_rts_frame()` **nicht** vor `send_raw()` aufrufen (`STATUS=OK` wäre gelogen)
- **Nicht** direkt in `somfy_codes.json` schreiben ohne atomares Speichern
- **Kein** `print()` — immer `logging` verwenden
- **Nicht** mit dem Coden anfangen bevor unklare Anforderungen geklärt sind
- **Nie** einen Tag setzen ohne vorher `config.yaml` Version aktualisiert zu haben

---

## Refactoring Checkliste

```
□ pytest — alle Tests grün
□ ruff check somfy_rts/ — keine Lint-Fehler
□ CLAUDE.md aktualisiert (bei Struktur-/API-/Modul-Änderungen)
□ DOCS.md aktualisiert (bei Feature-/Config-Änderungen)
□ Code + Docs im gleichen Commit
```

---

## Entwicklungs-Hinweise

- Lokaler Test: `OPTIONS_PATH=./test_options.json SOMFY_CODES_PATH=./test_codes.json python -m somfy_rts.main`
- culfw antwortet auf `V\n` mit Versions-String
- Rolling Code Datei NIE manuell löschen → Neu-Pairing nötig
