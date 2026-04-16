# Somfy RTS App (ehemals Add-on) — Dokumentation

## Voraussetzungen

- **NanoCUL USB-Stick** mit culfw-Firmware  
  **WICHTIG: 433,42 MHz — nicht 433,92 MHz!** Falsche Frequenz = Motor reagiert nicht.
- **MQTT Broker** (z.B. die Mosquitto App für Home Assistant)
- Home Assistant 2024.11.0 oder neuer
- Somfy RTS kompatible Geräte (Markisen, Rollläden, Jalousien, Tore, ...)

---

## Installation

1. Repository zu Home Assistant hinzufügen:
   - **Einstellungen → Apps → App Store → ⋮ → Repositories**
   - URL eingeben: `https://github.com/isi07/hassio-somfy-rts`

2. App "Somfy RTS" installieren

3. NanoCUL USB-Stick anschließen

4. Konfiguration anpassen (siehe unten)

5. App starten

---

## Konfiguration

Alle Optionen werden unter **Konfiguration** in der App eingestellt:

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `usb_port` | `/dev/ttyACM0` | Pfad zum NanoCUL USB-Stick |
| `baudrate` | `9600` | Serielle Baudrate (culfw Standard) |
| `mqtt_host` | `core-mosquitto` | MQTT Broker Hostname |
| `mqtt_port` | `1883` | MQTT Broker Port |
| `mqtt_user` | `""` | MQTT Benutzername (leer = keine Auth) |
| `mqtt_password` | `""` | MQTT Passwort |
| `address_prefix` | `A000` | 4-stelliger Hex-Präfix für neue Geräteadressen |
| `log_level` | `info` | Log-Level: `debug` / `info` / `warning` / `error` |

### USB-Port ermitteln

Den NanoCUL-Pfad in der App unter **Info → Hardware** nachschlagen,
oder im HA Terminal: `ls /dev/ttyACM* /dev/ttyUSB*`

### Geräte

Geräte werden **nicht** in der Konfiguration eingetragen, sondern automatisch
durch den Anlern-Wizard in `/data/somfy_codes.json` verwaltet.

---

## Gerätetypen

| Typ | HA Geräteklasse | Verwendung |
|-----|----------------|-----------|
| `awning` | awning | Markise |
| `shutter` | shutter | Rollladen |
| `blind` | blind | Jalousie / Raffstore |
| `screen` | shade | Insektenschutzrollo |
| `gate` | gate | Garagentor / Einfahrtstor |
| `light` | — | Somfy-kompatibles Licht |
| `heater` | — | Heizung |

---

## Gerätemodi

Die App unterstützt zwei Betriebsmodi pro Gerät:

| Modus | HA Discovery | Verwendung |
|-------|-------------|-----------|
| **A** | 1× Cover-Entität (optimistisch) | Direkte Steuerung, einfachste Einrichtung |
| **B** | 3× Button + 2× Diagnose-Sensor | Für Template Covers mit Blueprints |

**Modus A** eignet sich für die meisten Anwendungsfälle — auch für Blueprints.  
**Modus B** eignet sich für fortgeschrittene Automatisierungen, die direkt auf
die einzelnen Buttons (Auf/Zu/Stop) reagieren möchten.

---

## Gerät anlernen (Pairing-Wizard)

Der integrierte Pairing-Wizard führt durch den 5-stufigen Anlernprozess:

### Voraussetzung

Der Motor muss sich in Reichweite des NanoCUL befinden (~30 m Freifeld).

### Schritt-für-Schritt

1. **Motor in Programmiermodus versetzen**  
   `PROG`-Taste der Original-Fernbedienung **ca. 3 Sekunden** halten, bis der
   Motor kurz auf und ab fährt (Bestätigungsbewegung).

2. **Wizard in Home Assistant starten**  
   Der Wizard ist über die App-Ingress-Seite erreichbar.
   Er generiert automatisch eine eindeutige 6-stellige Hex-Adresse
   (Format: `<address_prefix><lfd. Nummer>`, z.B. `A00001`).

3. **PROG-Signal senden**  
   Der Wizard sendet das PROG-Telegramm (CMD `0x8`) innerhalb von 2 Minuten
   nach dem Motor-Programmiermodus-Start.

4. **Bestätigung abwarten**  
   Motor bestätigt das Pairing mit einer kurzen Auf-Ab-Bewegung.

5. **Fertig**  
   Das Gerät erscheint in Home Assistant unter  
   **Einstellungen → Geräte & Dienste → MQTT**.

### Adress-Präfix

Der `address_prefix` aus der Konfiguration wird als erste 4 Hex-Zeichen der
Geräteadresse verwendet. Nach dem ersten angelernten Gerät wird der Präfix in
`/data/somfy_codes.json` gesperrt (`prefix_locked: true`), um Adresskonflikte
zu vermeiden.

---

## ioBroker Migration

Geräte, die bereits über ioBroker angelernt wurden, können ohne erneutes
Pairing übernommen werden:

1. Adresse und Rolling Code aus ioBroker notieren  
   (Rolling Code mit einem Sicherheitspuffer von **+10** erhöhen)

2. Import via Python (einmalig im App-Terminal ausführen):
   ```python
   from somfy_rts.wizard import PairingWizard
   PairingWizard.import_from_iobroker(
       name="Wohnzimmer Markise",
       device_type="awning",
       address="A1B2C3",   # aus ioBroker
       rolling_code=142,   # letzter ioBroker-Wert + 10
   )
   ```

3. App neu starten — Gerät erscheint sofort in Home Assistant

**Wichtig:** Der Rolling Code muss ≥ dem letzten von ioBroker verwendeten Wert sein.
Ein zu niedriger Rolling Code bewirkt, dass der Motor alle Befehle ignoriert.

---

## Blueprint Nutzung

Die mitgelieferten Blueprints erstellen Template Covers, deren Zustand über einen
Kontaktsensor ermittelt wird. Fahrzeitverfolgung entfällt — sie ist unzuverlässig
bei MY-Taste und manueller Fernbedienung.

### Voraussetzungen

- Gerät im **Modus A** konfiguriert (Cover-Entität)
- Kontaktsensor (z.B. Fensterkontakt, Rollladenkontakt) vorhanden
- Home Assistant 2024.11.0+

### Blueprint importieren

1. **Einstellungen → Automatisierungen & Szenen → Blueprints**
2. **Blueprint importieren** → GitHub URL einfügen:
   - Markise: `https://github.com/isi07/hassio-somfy-rts/blob/main/blueprints/template/somfy_rts_awning.yaml`
   - Rollladen: `https://github.com/isi07/hassio-somfy-rts/blob/main/blueprints/template/somfy_rts_shutter.yaml`

### somfy_rts_awning.yaml — Template Cover für Markisen

Erstellt ein Template Cover. Zustand = eingefahren/ausgefahren kommt vom Kontaktsensor.

| Parameter | Beschreibung |
|-----------|-------------|
| `somfy_cover_entity` | Die Somfy Cover-Entität (Modus A) |
| `contact_sensor` | Sensor der den Einfahrzustand anzeigt |
| `contact_closed_state` | Sensor-Zustand = Markise eingefahren (Standard: `off`) |

### somfy_rts_shutter.yaml — Template Cover für Rollläden

Identische Struktur, angepasst für Rollläden:

| Parameter | Beschreibung |
|-----------|-------------|
| `somfy_cover_entity` | Die Somfy Cover-Entität (Modus A) |
| `contact_sensor` | Sensor der den Geschlossen-Zustand anzeigt |
| `contact_closed_state` | Sensor-Zustand = Rollladen geschlossen (Standard: `on`) |

### Zustandsermittlung

Der `value_template` wertet ausschließlich den Kontaktsensor aus:
- Sensor meldet "eingefahren/geschlossen" → Cover-Zustand: `closed`
- Sensor meldet alles andere → Cover-Zustand: `open`

Das Cover bleibt damit auch nach manueller Bedienung oder MY-Taste korrekt,
da der physische Zustand über den Sensor abgebildet wird.

---

## MQTT Topics

### Modus A (Cover + PROG-Buttons)

| Topic | Richtung | Inhalt |
|-------|----------|--------|
| `homeassistant/cover/<id>/config` | Publish | Discovery Cover (retain) |
| `homeassistant/button/<id>_prog_long/config` | Publish | Discovery PROG Lang (retain) |
| `homeassistant/button/<id>_prog_pair/config` | Publish | Discovery PROG Anlern (retain) |
| `somfy/<slug>/state` | Publish | `open` / `closed` / `stopped` (retain) |
| `somfy/<slug>/set` | Subscribe | `OPEN` / `CLOSE` / `STOP` |
| `somfy/<slug>/cmd` | Subscribe | `PROG_LONG` / `PROG_PAIR` |
| `somfy/<slug>/rolling_code` | Publish | Aktueller Rolling Code (retain) |
| `somfy/<slug>/last_command` | Publish | `OPEN` / `CLOSE` / `STOP` / `PROG` (retain) |

### Modus B (Buttons + PROG-Buttons + Diagnose)

| Topic | Richtung | Inhalt |
|-------|----------|--------|
| `homeassistant/button/<id>_prog_long/config` | Publish | Discovery PROG Lang (retain) |
| `homeassistant/button/<id>_prog_pair/config` | Publish | Discovery PROG Anlern (retain) |
| `somfy/<slug>/button/auf` | Subscribe | `PRESS` |
| `somfy/<slug>/button/zu` | Subscribe | `PRESS` |
| `somfy/<slug>/button/stop` | Subscribe | `PRESS` |
| `somfy/<slug>/cmd` | Subscribe | `PROG_LONG` / `PROG_PAIR` |
| `somfy/<slug>/rolling_code` | Publish | Aktueller Rolling Code (retain) |
| `somfy/<slug>/last_command` | Publish | `OPEN` / `CLOSE` / `STOP` / `PROG` (retain) |

### Gateway

| Topic | Inhalt |
|-------|--------|
| `cul2mqtt/status` | `online` / `offline` (LWT, retain) |
| `cul2mqtt/gateway/status` | Verbindungstext |
| `cul2mqtt/gateway/port` | USB-Port Pfad |
| `cul2mqtt/gateway/device_count` | Anzahl angelernte Geräte |
| `cul2mqtt/gateway/sw_version` | App-Version |

---

## Rolling Code Persistenz

Die Rolling Codes werden in `/data/somfy_codes.json` gespeichert:

```json
{
  "devices": [
    {"address": "A00001", "name": "Wohnzimmer Markise", "rolling_code": 42}
  ],
  "groups": [],
  "settings": {
    "address_prefix": "A000",
    "prefix_locked": true
  }
}
```

**Nie manuell löschen!** Rolling Codes werden vor dem Senden atomar gespeichert
(Strom-Ausfallsicherheit). Gelöschte Datei = alle Geräte müssen neu angelernt werden.

---

## Fehlerbehebung

### NanoCUL wird nicht erkannt

- USB-Gerät prüfen: **App → Info → Hardware** oder im HA Terminal `ls /dev/ttyACM* /dev/ttyUSB*`
- Anderen USB-Port versuchen
- culfw-Firmware Version prüfen: `V` über serielle Konsole senden (Antwort: `V 1.67 CUL868...`)

### Motor reagiert nicht

- **433,42 MHz** Firmware auf dem NanoCUL? (nicht 433,92 MHz!)
- Entfernung zum Motor prüfen (~30 m Freifeld; Betonwände reduzieren Reichweite stark)
- App-Log auf `PROG_SENT` und `CONFIRMED` prüfen (`log_level: debug` aktivieren)

### MQTT Verbindung schlägt fehl

- Mosquitto App läuft? **Einstellungen → Apps → Mosquitto**
- `mqtt_host: core-mosquitto` für das interne HA-Netzwerk korrekt?
- Zugangsdaten korrekt gesetzt?

### Motor ignoriert Befehle nach ioBroker-Migration

- Rolling Code zu niedrig → Import mit höherem Wert wiederholen
- Empfehlung: letzten ioBroker-Wert + 10 als Startwert verwenden
