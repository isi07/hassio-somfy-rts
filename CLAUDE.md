# CLAUDE.md — Somfy RTS Home Assistant App

## Inhaltsverzeichnis

- [⚠️ Kritische Invarianten](#kritische-invarianten--vor-jeder-änderung-lesen) (RC-Atomizität, Yr{n}, Adressdarstellung)
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
- [Template Cover](#template-cover-ha-202411)
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
- `_save_atomic()` macht `flush` + `fsync` → `os.replace()` → Verzeichnis-`fsync` und wirft bei
  Fehlern `RollingCodeStoreError` (Subklasse von `OSError`) — **nie** still weitermachen.
  `get_and_increment()` kehrt dann nicht zurück → es wird **nicht** gesendet.
- Existiert die Datei, ist aber kaputt/strukturell ungültig, wirft `_load()`
  `RollingCodeStoreError` (einmalige Kopie `somfy_codes.json.corrupt-<ts>`), statt mit einem
  leeren Store weiterzumachen. Nur `FileNotFoundError` (Erststart) liefert einen leeren Store.
- Jeder Load-Modify-Save-Zyklus läuft unter `with store_lock():` (RLock) — paho-Thread und
  aiohttp-Event-Loop greifen parallel zu.

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
- RC-Vergabe + `send_raw()`-Loop laufen unter `with rts.TX_LOCK:` — sonst können sich `Yr`/`Ys`
  zweier Befehle aus verschiedenen Threads auf der seriellen Leitung verschränken
- **repeat-Werte:**
  - `1`  = Normalbefehle (Centralis uno: PFLICHT!)
  - `4`  = PROG Anlern (Motor bereits im Anlernmodus, kurzer Druck reicht)
  - `14` = PROG Lang (~420 ms, Motor in Anlernmodus versetzen) — **empirisch verifiziert**: Yr13=nein, Yr14=ja
  - ⚠️ **Yr16+ kann NanoCUL USB-Verbindung crashen — niemals überschreiten!**

```python
# ❌ FALSCH — Yr{n} fehlt
gateway.send_raw(telegram)        # Motor ignoriert das Telegramm stillschweigend!

# ✅ RICHTIG — beide Kommandos aus RTSSequence.commands, log NACH dem Senden
with TX_LOCK:
    seq = build_rts_sequence(address, action, name)           # repeat=1 (Standard)
    # seq = build_rts_sequence(address, "PROG", name, repeat=14)  # PROG Lang
    for cmd in seq.commands:      # [f"Yr{repeat}", "YsA0..."]
        gateway.send_raw(cmd)
log_rts_frame(seq, address, action, success=True)   # erst hier: STATUS=OK ist echt
```

### 3 · Adressdarstellung nie ändern

Die Adresse hat im ganzen Add-on **eine** Darstellung — die FHEM/culfw-Konvention. Die
Byte-Umkehr auf Funk (Somfy sendet die Adresse LSB-first) macht **culfw** selbst
(`somfy_rts.c`: Eingabe-Byte 1 → Frame-Byte 6). Beispiel `A00001`:

| Stelle | Darstellung |
|---|---|
| `somfy_codes.json`, Web-UI, Wizard, Import, Sensor `device_address` | `A00001` |
| culfw-Befehl / `raw_frame` / Frame-Log | `YsA0 20 0001 A00001` |
| Auf Funk, Frame-Bytes 4–6 | `01 00 A0` |
| culfw-Echo nach dem Senden (wird nicht gelesen) | `…0001 0100A0` |

- **NIEMALS** die Reihenfolge beim Speichern oder Senden ändern — alle angelernten Motoren
  würden den virtuellen Sender nicht mehr erkennen (Neu-Anlernen aller Geräte nötig)
- Eingehende Adressen (culfw-Echo, künftiger Empfang via SIGNALduino/rtl_433) im **Parser**
  auf diese Darstellung zurückdrehen: `raw[14:16] + raw[12:14] + raw[10:12]` (wie FHEM)
- Import: Adressen aus Funk-Mitschnitten sind umgedreht und müssen vorher gedreht werden

---

## Projektübersicht

**Name:** hassio-somfy-rts  
**GitHub:** https://github.com/isi07/hassio-somfy-rts  
**Lizenz:** MIT  
**Version:** siehe `somfy-rts/config.yaml` (einzige Quelle der Wahrheit)  
**Maintainer:** isi07

Dieses Repository ist ein **Home Assistant App-Repository** (ehemals Add-on-Repository),
das die App "Somfy RTS" enthält. Die App steuert Somfy RTS Geräte (Markisen, Rollläden,
Jalousien usw.) über einen **NanoCUL USB-Stick** mit **culfw-Firmware** via **MQTT**.

---

## Technischer Stack

| Komponente | Details |
|---|---|
| App Runtime | Docker, Basis `ghcr.io/home-assistant/{arch}-base-python:3.14-alpine3.24` (Build-Arg `BUILD_FROM` in `build.yaml`) |
| Architekturen | amd64, aarch64 |
| Sprache | Python 3.14 (CI-Tests `setup-python` und `BUILD_FROM` immer gleich halten) |
| Protokoll | Somfy RTS (433,42 MHz) über NanoCUL USB (culfw) |
| Kommunikation | MQTT (paho-mqtt 2.x, **Callback API v2**, Thread-Modus `loop_start`, Auto-Reconnect) → Home Assistant |
| Web-UI | aiohttp (asyncio), HA Ingress Port 8099 |
| HA-Integration | MQTT Discovery (Cover/Light/Switch/Button/Sensor-Entitäten) |
| Config | App-Options → `run.sh` → `SOMFY_*` Env-Variablen → `config.py` |
| Abhängigkeiten | Exakt gepinnt (`==`): `requirements.txt` (Image: pyserial, paho-mqtt, aiohttp), `requirements-test.txt` (`-r requirements.txt` + pytest, ruff, yamllint) |
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
   14 = PROG Lang (Motor in Anlernmodus versetzen, ersetzt PROG-Taste der Original-FB)

Felder:
  A0    = KK, Somfy "encryption key"-Byte (Frame-Byte 0). culfw übernimmt es unverändert,
          prüft/überschreibt es nicht. FHEM zählt es pro Frame A0..AF hoch, wir senden fest A0.
  CMD   = 1 Byte, 2 Hex-Zeichen = Byte 1 des Somfy-Frames
          Byte 1 = (ctrl << 4) | cks
          ctrl  = Befehlsnibble im High-Nibble, z.B. 0x2 für OPEN → "20"
          cks   = Prüfsummen-Nibble (Low-Nibble), von culfw intern berechnet
          → culfw erwartet ctrl im High-Nibble mit cks=0
  RC    = Rolling Code, 4 Hex-Zeichen (16-Bit Big-Endian), z.B. "001A"
  ADDR  = Geräteadresse, 6 Hex-Zeichen (3 Byte), z.B. "A1B2C3"
          culfw dreht die Bytereihenfolge auf Funk um und gibt nach jedem Senden ein
          Echo "Ys<frame>" in Funk-Reihenfolge aus (z.B. "...C3B2A1").

  X21 (beim Connect gesendet) = SlowRF-Report-Flags (Bit 0 bekannte Nachrichten, Bit 5 RSSI),
  KEIN Somfy-Modus. culfw/a-culfw können Somfy RTS nur SENDEN, nicht empfangen.

Beispiel (UP, RC=0x001A, Addr=A1B2C3, repeat=1):
  Yr1
  YsA020001AA1B2C3

Beispiel PROG Lang (repeat=14):
  Yr14
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
ignoriert Telegramme mit repeat>1. Ausnahme: PROG-Telegramme mit repeat=4 oder repeat=14
werden unterstützt und von culfw korrekt verarbeitet. **Yr16+ crasht den NanoCUL — nicht überschreiten!**

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
├── .gitignore / .gitattributes        # LF im Repo erzwungen
├── .yamllint
├── .github/
│   ├── dependabot.yaml                # wöchentliche Updates: GitHub Actions + pip
│   └── workflows/
│       └── build.yaml                 # CI: Lint+Tests+Build-Check immer, Push+Release nur bei Tags
├── tools/
│   └── cul_sniff.py                   # Diagnose: liest CUL-Rohzeilen (nicht im Image)
├── somfy-rts/                         # Die eigentliche App
│   ├── config.yaml                    # HA App-Schema + version
│   ├── Dockerfile
│   ├── requirements.txt               # pyserial, paho-mqtt, aiohttp
│   ├── requirements-test.txt          # pytest, pytest-asyncio, pytest-aiohttp, pytest-mock
│   ├── pytest.ini
│   ├── run.sh                         # options.json → SOMFY_* Env, legt somfy_codes.json an
│   ├── DOCS.md
│   ├── CHANGELOG.md                   # generiert via git-cliff — nie manuell bearbeiten
│   ├── tests/                         # pytest (conftest.py + test_<modul>.py)
│   └── somfy_rts/                     # Python-Paket
│       ├── __init__.py                # __version__ (aus Env SOMFY_VERSION)
│       ├── main.py                    # Einstiegspunkt (asyncio)
│       ├── config.py                  # Config/DeviceConfig aus SOMFY_* Env
│       ├── gateway.py                 # BaseGateway (ABC), CULGateway, SimGateway
│       ├── rolling_code.py            # Atomare RC-Persistenz, store_lock(), RollingCodeStoreError
│       ├── rts.py                     # build_rts_sequence(), log_rts_frame(), TX_LOCK
│       ├── rts_logger.py              # strukturiertes Frame-Log (text/json, optional Datei)
│       ├── mqtt_client.py             # MQTT + HA Discovery (Modus A/B, LWT, Origin)
│       ├── device.py                  # Device-Klasse (alle 8 Typen, Modus A/B)
│       ├── wizard.py                  # PairingWizard (5-Schritt Anlern-Flow)
│       ├── device_profiles.json       # Gerätetyp-Definitionen
│       └── web/
│           ├── api.py                 # REST-Endpunkte (aiohttp RouteTableDef)
│           ├── server.py              # App-Setup, statische Seiten, store_error_middleware
│           └── static/                # index/wizard/settings/logs.html, style.css
```

---

## Architektur

### Gateway-Abstraktion

```python
BaseGateway (ABC)          # gateway.py
    └── CULGateway         # pyserial → NanoCUL
    └── SimGateway         # ohne Hardware (simulation_mode, Tests)
    └── SIGNALduinoGateway # (zukünftig)
```

### Threads

- **paho-Thread** (`loop_start`): MQTT-Befehle → `Device._handle_command()`
- **asyncio-Event-Loop**: Web-UI/REST, Wizard, Import, Löschen
- Beide greifen auf `somfy_codes.json` und die serielle Schnittstelle zu →
  `store_lock()` und `rts.TX_LOCK` (siehe Kritische Invarianten)

### MQTT Discovery Struktur

**Gateway-Device** (`identifiers: ["somfy_rts_gateway"]`):
- 1 binary_sensor Verbindung (liest LWT `cul2mqtt/status` direkt)
- 3 Diagnose-Sensoren: USB-Port, Geräteanzahl, SW-Version
- Alle `entity_category: diagnostic`
- `cul2mqtt/gateway/status` (Text) wird publiziert, hat aber **keine** HA-Entität

**Sub-Device pro Gerät** (`via_device: "somfy_rts_gateway"`) — maßgeblich ist
`discovery_topics()` in `mqtt_client.py`:
- **Beide Modi:** Buttons PROG Lang, PROG Anlern, MY; Sensoren rolling_code, last_command,
  device_address; bei `has_tilt` zusätzlich Buttons MY_UP/MY_DOWN
- **Modus A:** + Haupt-Entity je `ha_platform` (cover/light/switch, optimistisch;
  keins bei `light_dimmer`)
- **Modus B:** + Buttons Auf, Zu, Stop

**Availability:** LWT auf `cul2mqtt/status` (online/offline, retain=True)

**Origin-Block** in allen Discovery-Payloads:
```json
{"name": "Somfy RTS", "support_url": "https://github.com/isi07/hassio-somfy-rts"}
```

---

## Geräte-Modi

| Modus | Discovery | Verwendung |
|-------|-----------|------------|
| A | Haupt-Entity je `ha_platform` (optimistisch) + MY-Button + 2 PROG-Buttons + 3 Diagnose-Sensoren | Standalone, direkte Steuerung |
| B | Buttons Auf/Zu/Stop + MY-Button + 2 PROG-Buttons + 3 Diagnose-Sensoren | Template Cover in HA (manuell, siehe DOCS.md) |

Bei `has_tilt` (blind) in beiden Modi zusätzlich Buttons MY_UP/MY_DOWN.

### PROG-Buttons (beide Modi, entity_category: config)

| Button | unique_id Suffix | Topic | Payload |
|--------|-----------------|-------|---------|
| PROG Lang | `_prog_long` | `somfy/<slug>/cmd` | `PROG_LONG` → PROG Yr14 |
| PROG Anlern | `_prog_pair` | `somfy/<slug>/cmd` | `PROG_PAIR` → PROG Yr4 |

Beide Buttons erscheinen in HA unter **Konfiguration** des jeweiligen Geräts.
Kein Cover-State-Update bei PROG_LONG/PROG_PAIR — nur `rolling_code` + `last_command` (="PROG").

### Diagnose-Sensoren (beide Modi)

| Sensor | Topic | Inhalt |
|--------|-------|--------|
| `rolling_code` | `somfy/<slug>/rolling_code` | aktueller RC nach jedem Befehl (integer) |
| `last_command` | `somfy/<slug>/last_command` | letzter Befehl (OPEN/CLOSE/STOP/MY/PROG) |
| `last_command` Attribut | `somfy/<slug>/last_command_attr` | `{"raw_frame": "YsA0…"}` — vollständiger Telegram-String |

| `device_address` | `somfy/<slug>/device_address` | statische Hex-Adresse des virtuellen Senders (einmalig beim Setup) |

### MY-Button (beide Modi, entity_category: config)

| Modus | unique_id Suffix | Topic | Payload |
|-------|-----------------|-------|---------|
| A | `_my` | `somfy/<slug>/set` | `MY` |
| B | `_my` | `somfy/<slug>/button/my` | `PRESS` |

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
| `log_format` | enum | `text` | text/json (Frame-Log) |
| `simulation_mode` | bool | `false` | `SimGateway` statt NanoCUL (ohne Hardware) |
| `file_logging` | bool | `false` | Frame-Log nach `/share/somfy_rts/rts_frames.log` |
| `timezone` | string | `Europe/Berlin` | IANA-Zeitzone für Log-Zeitstempel |
| `debug_mode` | bool? | `false` | Erweiterte Web-UI-Steuerung (`raw-cmd`, freier Repeat) |

Neue Option = `config.yaml` (options + schema) + `run.sh` (export `SOMFY_*`) + `config.py`
+ DOCS.md — alle vier anpassen.

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

| Typ | HA device_class | ha_platform | has_tilt | Icon |
|-----|----------------|-------------|---------|------|
| awning | awning | cover | false | mdi:awning |
| shutter | shutter | cover | false | mdi:window-shutter |
| blind | blind | cover | **true** | mdi:blinds |
| screen | shade | cover | false | mdi:roller-shade |
| gate | gate | cover | false | mdi:gate |
| light | — | **light** | false | mdi:lightbulb |
| heater | — | **switch** | false | mdi:radiator |
| light_dimmer | — | **null** (nur Modus B) | false | mdi:lightbulb-on |

### ha_platform

`ha_platform` bestimmt den HA Discovery Entity-Typ in **Modus A**:
- `"cover"` → MQTT Cover-Entity (OPEN/CLOSE/STOP, device_class je Typ)
- `"light"` → MQTT Light-Entity (ON/OFF, optimistic) — Somfy Lighting Slim Receiver
- `"switch"` → MQTT Switch-Entity (ON/OFF, optimistic) — Somfy Heat Receiver
- `null` → kein Haupt-Entity (light_dimmer: nur Modus B empfohlen)

HA MQTT light/switch senden `"ON"`/`"OFF"` auf das Command-Topic.
`device._handle_command()` normalisiert ON→OPEN, OFF→CLOSE vor der command_map-Übersetzung.
In Modus A publiziert das Gerät den Zustand als `"ON"`/`"OFF"` für light/switch (nicht "open"/"closed").

### has_tilt

`has_tilt: true` aktiviert zusätzliche **MY_UP** / **MY_DOWN** Lamellen-Buttons in **Modus B**:
- Modus B: 5 Buttons (auf/zu/stop/**my_auf**/**my_zu**) statt 3
- Discovery: 9 Topics statt 7 (inkl. `button/{uid}_my_auf` und `button/{uid}_my_zu`)
- Aktuell nur `blind` (Jalousie/Raffstore) hat `has_tilt: true`

### light_dimmer (nur Modus B)

- Somfy Lighting Dimmer: Impulse UP/DOWN/MY — kein echtes Brightness-API möglich
- Wizard und Import-Modal: Modus A deaktiviert, Modus B vorausgewählt
- Modus B Buttons: **Hochdimmen** (UP) / **Abdimmen** (DOWN) / **Helligkeit merken** (MY)
- `ha_platform: null` → kein Modus-A-Haupt-Entity; PROG-Buttons + Diagnose-Sensoren bleiben

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
| `somfy/<slug>/set` | Subscribe | OPEN / CLOSE / STOP / MY (light/switch: ON / OFF) |
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
| `somfy/<slug>/button/my` | Subscribe | PRESS |
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

## Template Cover (HA 2024.11+)

Template Covers verbinden Somfy-Entitäten mit einem physischen Kontaktsensor für
einen zuverlässigen Zustand — auch nach manueller Bedienung oder MY-Taste.
Vollständige YAML-Beispiele für Modus A und Modus B in **DOCS.md**.

- **Modus B** (empfohlen): Aktionen via `button.press` auf die drei Button-Entitäten
- **Modus A**: Aktionen via `cover.open_cover` / `cover.close_cover` / `cover.stop_cover`
- Zustand immer über externen Kontaktsensor — nie über Fahrzeitverfolgung
- Availability über `binary_sensor.somfy_rts_gateway_verbindung`

---

## CI/CD (GitHub Actions)

Workflow `.github/workflows/build.yaml`, Job-Kette `lint → build → manifest → release`:

- **lint** (jeder Push auf `main`, jeder PR, jeder Tag): installiert `requirements-test.txt`,
  dann ruff, **pytest**, yamllint, shellcheck, hadolint, JSON-Check, HA-Add-on-Linter,
  actionlint (Version im Workflow gepinnt). Tool-Versionen nur über `requirements-test.txt` ändern
- **build** (immer, Matrix amd64/aarch64): baut das Image — bei PR/`main` nur als Check plus
  Smoke-Test (Container starten, Python-Version + Imports prüfen), Login + Push nach ghcr.io
  **nur bei Tag `v*`**. So testen auch Dependabot-PRs die Docker-Actions und das Image
- **manifest**: Multi-Arch-Image `ghcr.io/isi07/somfy-rts:<version>` + `:latest`
- **release**: GitHub Release, Notes = `git cliff --latest` (Pre-Release bei `-` im Tag)
- **Images:** `ghcr.io/isi07/somfy-rts:<version>-<arch>`; `config.yaml` → `image: ghcr.io/isi07/somfy-rts`
- **Conventional Commits:** `feat:`, `fix:`, `perf:`, `refactor:`, `docs:`, `chore:`, `ci:`, `test:`
  (`chore: release …` wird im Changelog ausgeblendet)
- **Tag-Format:** `v0.1.0` (stable), `v0.1.0-beta.1` (pre-release)
- **Dependabot** (`.github/dependabot.yaml`): wöchentlich je **ein** gruppierter PR für GitHub
  Actions und für pip (`somfy-rts/requirements*.txt`). Mergen erst, wenn lint **und** build
  (inkl. Smoke-Test) grün sind; nicht zusammen mit einem Release. Ein rotes Paket blockiert die
  Gruppe → Ursache fixen oder Paket per `ignore` zurückstellen. Basis-Image (BUILD_FROM in
  `build.yaml`) sieht Dependabot nicht — manuell prüfen

---

## Anlern-Wizard (`wizard.py`)

Der `PairingWizard` steuert den 5-stufigen Anlern-Flow:

1. `wizard.start(name, device_type, mode="A")` — Adresse generieren, RC auf 0 setzen, in `somfy_codes.json` voranlegen (inkl. `mode`-Feld)
2. Motor in Programmiermodus versetzen — entweder:
   - **Klassisch:** Orig.-FB PROG 3s halten → kurzes Auf-Ab
   - **Alternativ:** `wizard.send_prog_long()` (Yr14) senden — ersetzt die Original-FB
3. `wizard.send_prog_pair()` (oder Alias `wizard.send_prog()`) — PROG Yr4 senden → virtuellen Sender anlernen
4. Operator sieht Motor-Bestätigungsbewegung → `wizard.confirm()` aufrufen
5. `wizard.get_device_config()` — Config-Dict zurückgeben (enthält `mode`)

### PROG-Methoden im Wizard

| Methode | repeat | Aktion | Zustand danach |
|---------|--------|--------|----------------|
| `send_prog_long()` | Yr14 | Motor in Anlernmodus versetzen (ersetzt Orig.-FB PROG) | ADDR_READY |
| `send_prog_pair()` | Yr4 | Virtuellen Sender am Motor registrieren/deregistrieren | PROG_SENT |
| `send_prog()` | Yr4 | Alias für `send_prog_pair()` | PROG_SENT |

**Modus A/B** ist in der Web-UI wählbar: Anlern-Wizard (Schritt 1) und Import-Dialog
bieten je ein Dropdown — `A` = Cover-Entity, `B` = Buttons + Sensoren für Template Cover.

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
| `POST /api/devices/{id}/prog-long` | Yr14 | Motor in Anlernmodus versetzen |
| `POST /api/devices/{id}/prog-pair` | Yr4 | Virtuellen Sender registrieren/deregistrieren |
| `POST /api/wizard/send_prog_long` | Yr14 | Wizard: Motor in Anlernmodus (Zustand bleibt ADDR_READY) |
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
| A | Haupt-Entity (cover/light/switch, nicht bei light_dimmer), button_my, sensor_rolling_code, sensor_last_command, sensor_device_address, button_prog_long, button_prog_pair (+ button_my_auf/my_zu bei has_tilt) |
| B | button_auf, button_zu, button_stop, button_my, sensor_rolling_code, sensor_last_command, sensor_device_address, button_prog_long, button_prog_pair (+ button_my_auf/my_zu bei has_tilt) |

Zusätzlich leert `state_topics()` die retained `somfy/<slug>/…`-Werte.

### Fehlerbehandlung `RollingCodeStoreError`

| Aufrufer | Verhalten |
|----------|-----------|
| `device._send_rts()` (paho-Thread) | Log `ERROR`, nichts senden, `None` zurück |
| `wizard._send_prog_telegram()` | Session → `FAILED`, Exception weiterwerfen |
| REST-API | Middleware `store_error_middleware` (`web/server.py`) → HTTP 503 `{"error", "message"}` |
| `main.py` beim Start | Log `ERROR`, keine Geräte registrieren, `cul2mqtt/gateway/status` = „Fehler: …" (Topic hat keine HA-Entität) |
| `mqtt_client._on_message()` | Sicherheitsnetz: jede Handler-Exception wird geloggt, paho-Thread überlebt |

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
  neuen Features, Anlern-Prozess, Template Cover
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
2. `git cliff --tag vX.Y.Z -o somfy-rts/CHANGELOG.md`
   (**ohne** `--unreleased` — `-o` überschreibt die Datei, sie wird aus der kompletten
   Historie neu erzeugt; git-cliff: `pip install git-cliff`)
3. `git add -A`
4. `git commit -m "chore: release X.Y.Z"`
5. `git tag vX.Y.Z`
6. `git push origin vX.Y.Z` → warten bis der Workflow grün ist (`gh run watch`)
7. `git push origin main` — erst jetzt sieht HA die neue Version; das Image existiert dann schon

**NIEMALS** einen Tag setzen ohne vorher die Version in `config.yaml` aktualisiert zu haben.
Tag und `config.yaml` version müssen **IMMER** übereinstimmen.
Tag und Push nur nach ausdrücklicher Bestätigung durch den Maintainer.

**Rollback:** Kein Downgrade per HA-Backup-Restore (setzt `somfy_codes.json` auf alte
Rolling Codes zurück → Motoren ignorieren Befehle). Stattdessen Vorwärts-Fix: `git revert`
der fehlerhaften Commits und neue Patch-Version releasen.

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
- `build_rts_sequence()` + `send_raw()`-Loop unter `with TX_LOCK:`
- Jedes `_load()` → ändern → `_save_atomic()` unter `with store_lock():`
- `RollingCodeStoreError` beim Aufrufer behandeln (nie in einen Thread entkommen lassen)
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

- Setup: `pip install -r somfy-rts/requirements-test.txt` (gleiche Versionen wie CI)
- Tests: `cd somfy-rts && pytest` (Fixture `tmp_codes_path` isoliert `somfy_codes.json`)
- Lokaler Lauf ohne Hardware (aus `somfy-rts/`):
  `SOMFY_SIMULATION_MODE=true SOMFY_CODES_PATH=./test_codes.json python -m somfy_rts.main`
  (Config kommt aus `SOMFY_*`-Env-Variablen, siehe `config.py`)
- culfw/a-culfw können Somfy RTS nur senden, nicht empfangen (`tools/cul_sniff.py` zum Prüfen)
- culfw antwortet auf `V\n` mit Versions-String
- Rolling Code Datei NIE manuell löschen → Neu-Pairing nötig
- **Branch-Regel:** Immer direkt auf `main` arbeiten. Kein Worktree, kein `claude/*`-Branch. Alle Commits gehen direkt auf `main`.
