# Somfy RTS Add-on — Dokumentation

## Voraussetzungen

- **NanoCUL USB-Stick** mit culfw-Firmware  
  **WICHTIG: 433,42 MHz — nicht 433,92 MHz!** Falsche Frequenz = Motor reagiert nicht.
- **MQTT Broker** (z.B. das Mosquitto Add-on für Home Assistant)
- Home Assistant 2024.11.0 oder neuer
- Somfy RTS kompatible Geräte (Markisen, Rollläden, Jalousien, Tore, ...)

---

## Installation

1. Repository zu Home Assistant hinzufügen:
   - **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
   - URL eingeben: `https://github.com/isi07/hassio-somfy-rts`

2. Add-on "Somfy RTS" installieren

3. NanoCUL USB-Stick anschließen

4. Konfiguration anpassen (siehe unten)

5. Add-on starten

---

## Konfiguration

Alle Optionen werden unter **Konfiguration** im Add-on eingestellt:

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

Den NanoCUL-Pfad im Add-on unter **Info → Hardware** nachschlagen,
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

Das Add-on unterstützt zwei Betriebsmodi pro Gerät:

| Modus | HA Discovery | Verwendung |
|-------|-------------|-----------|
| **A** | 1× Cover-Entität (optimistisch) | Direkte Steuerung, einfachste Einrichtung |
| **B** | 3× Button + 2× Diagnose-Sensor | Für Template Covers mit Blueprints |

**Modus A** eignet sich für die meisten Anwendungsfälle.  
**Modus B** empfiehlt sich, wenn Fahrzeitschätzung oder Fensterkontakt-Logik
über einen Blueprint gewünscht wird.

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
   Der Wizard ist über die Add-on Ingress-Seite erreichbar.
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

2. Import via Python (einmalig im Add-on Terminal ausführen):
   ```python
   from somfy_rts.wizard import PairingWizard
   PairingWizard.import_from_iobroker(
       name="Wohnzimmer Markise",
       device_type="awning",
       address="A1B2C3",   # aus ioBroker
       rolling_code=142,   # letzter ioBroker-Wert + 10
   )
   ```

3. Add-on neu starten — Gerät erscheint sofort in Home Assistant

**Wichtig:** Der Rolling Code muss ≥ dem letzten von ioBroker verwendeten Wert sein.
Ein zu niedriger Rolling Code bewirkt, dass der Motor alle Befehle ignoriert.

---

## Blueprint Nutzung

Die mitgelieferten Blueprints erstellen Template Covers mit erweiterter Logik.

### Voraussetzungen

- Gerät im **Modus B** konfiguriert (3 Buttons + Diagnose-Sensoren)
- Home Assistant 2024.11.0+

### Blueprint importieren

1. **Einstellungen → Automatisierungen & Szenen → Blueprints**
2. **Blueprint importieren** → GitHub URL einfügen:
   - Markise: `https://github.com/isi07/hassio-somfy-rts/blob/main/blueprints/template/somfy_rts_awning.yaml`
   - Rollladen: `https://github.com/isi07/hassio-somfy-rts/blob/main/blueprints/template/somfy_rts_shutter.yaml`

### somfy_rts_awning.yaml — Template Cover für Markisen

Erstellt ein Template Cover mit:
- Fensterkontakt-Priorität (Schließen blockiert, wenn Fenster offen)
- Fahrzeit-Schätzung via Timer (Standard: 35 s auf / 38 s zu)

| Parameter | Beschreibung |
|-----------|-------------|
| `somfy_cover_entity` | Die Somfy-Button-Entität (Modus B) |
| `contact_sensor` | Fensterkontakt-Sensor (optional) |
| `contact_closed_state` | Zustand = "geschlossen" (z.B. `off`) |
| `use_travel_time` | Fahrzeit-Schätzung aktivieren |
| `travel_timer` | Timer-Helfer für Fahrzeitberechnung |
| `travel_time_open` | Fahrzeit Hochfahren in Sekunden (Standard: 35) |
| `travel_time_close` | Fahrzeit Runterfahren in Sekunden (Standard: 38) |

### somfy_rts_shutter.yaml — Template Cover für Rollläden

Identisch zu Markise, mit anderen Standardwerten:
- Fahrzeit Standard: 40 s auf / 43 s zu
- Labels: "Hochfahren" / "Runterfahren"

---

## MQTT Topics

### Modus A (Cover)

| Topic | Richtung | Inhalt |
|-------|----------|--------|
| `homeassistant/cover/<id>/config` | Publish | Discovery-Payload (retain) |
| `somfy/<slug>/state` | Publish | `open` / `closed` / `stopped` (retain) |
| `somfy/<slug>/set` | Subscribe | `OPEN` / `CLOSE` / `STOP` |

### Modus B (Buttons + Diagnose)

| Topic | Richtung | Inhalt |
|-------|----------|--------|
| `somfy/<slug>/button/auf` | Subscribe | `PRESS` |
| `somfy/<slug>/button/zu` | Subscribe | `PRESS` |
| `somfy/<slug>/button/stop` | Subscribe | `PRESS` |
| `somfy/<slug>/rolling_code` | Publish | Aktueller Rolling Code (retain) |
| `somfy/<slug>/last_command` | Publish | `OPEN` / `CLOSE` / `STOP` (retain) |

### Gateway

| Topic | Inhalt |
|-------|--------|
| `cul2mqtt/status` | `online` / `offline` (LWT, retain) |
| `cul2mqtt/gateway/status` | Verbindungstext |
| `cul2mqtt/gateway/port` | USB-Port Pfad |
| `cul2mqtt/gateway/device_count` | Anzahl angelernte Geräte |
| `cul2mqtt/gateway/sw_version` | Add-on Version |

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

- USB-Gerät prüfen: **Add-on → Info → Hardware** oder im HA Terminal `ls /dev/ttyACM* /dev/ttyUSB*`
- Anderen USB-Port versuchen
- culfw-Firmware Version prüfen: `V` über serielle Konsole senden (Antwort: `V 1.67 CUL868...`)

### Motor reagiert nicht

- **433,42 MHz** Firmware auf dem NanoCUL? (nicht 433,92 MHz!)
- Entfernung zum Motor prüfen (~30 m Freifeld; Betonwände reduzieren Reichweite stark)
- Add-on Log auf `PROG_SENT` und `CONFIRMED` prüfen (`log_level: debug` aktivieren)

### MQTT Verbindung schlägt fehl

- Mosquitto Add-on läuft? **Einstellungen → Add-ons → Mosquitto**
- `mqtt_host: core-mosquitto` für das interne HA-Netzwerk korrekt?
- Zugangsdaten korrekt gesetzt?

### Motor ignoriert Befehle nach ioBroker-Migration

- Rolling Code zu niedrig → Import mit höherem Wert wiederholen
- Empfehlung: letzten ioBroker-Wert + 10 als Startwert verwenden
