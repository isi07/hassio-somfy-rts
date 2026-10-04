# Somfy RTS App (ehemals Add-on) — Dokumentation

## Voraussetzungen

- **NanoCUL USB-Stick** mit culfw-Firmware **mit Somfy-RTS-Unterstützung**
  (Build-Option `HAS_SOMFY_RTS`; im Standard-Build von a-culfw für den nanoCUL ist sie
  deaktiviert)
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
| `log_format` | `text` | Format des RTS-Frame-Logs: `text` / `json` |
| `simulation_mode` | `false` | Ohne Hardware testen — Befehle werden nur geloggt, nicht gesendet |
| `file_logging` | `false` | Frame-Log zusätzlich nach `/share/somfy_rts/rts_frames.log` schreiben |
| `timezone` | `Europe/Berlin` | Zeitzone für Log-Zeitstempel |
| `debug_mode` | `false` | Erweiterte Steuerung in der Web-UI (beliebiger Befehl mit freiem Repeat-Wert) |

### USB-Port ermitteln

Den NanoCUL-Pfad in der App unter **Info → Hardware** nachschlagen,
oder im HA Terminal: `ls /dev/ttyACM* /dev/ttyUSB*`

### Geräte

Geräte werden **nicht** in der Konfiguration eingetragen, sondern automatisch
durch den Anlern-Wizard in `/data/somfy_codes.json` verwaltet.

### Web-UI

Die App hat eine eigene Oberfläche (Seitenleiste **Somfy RTS** bzw. **App → Web-UI öffnen**):

- **Geräte:** alle Geräte mit Auf / Stop / Ab, MY, PROG Lang / PROG Anlern, Löschen
- **Importieren:** bereits angelerntes Gerät mit bekannter Adresse und Rolling Code übernehmen
- **Anlern-Wizard:** neues Gerät Schritt für Schritt anlernen
- **Logs:** die letzten gesendeten RTS-Frames
- **Einstellungen:** aktuelle Konfiguration (Änderungen in der App-Konfiguration)

---

## Gerätetypen

| Typ | HA Entität (Modus A) | Verwendung |
|-----|---------------------|-----------|
| `awning` | Cover (awning) | Markise |
| `shutter` | Cover (shutter) | Rollladen |
| `blind` | Cover (blind) | Jalousie / Raffstore — inkl. MY_UP/MY_DOWN Lamellensteuerung |
| `screen` | Cover (shade) | Insektenschutzrollo |
| `gate` | Cover (gate) | Garagentor / Einfahrtstor |
| `light` | **Light** (EIN/AUS) | Somfy Lighting Slim Receiver |
| `heater` | **Switch** (EIN/AUS) | Somfy Heat Receiver |
| `light_dimmer` | — (nur Modus B) | Somfy Lighting Dimmer (Impulse UP/DOWN/MY) |

**Hinweis light / heater:** HA sendet `ON`/`OFF` an das Command-Topic; die App übersetzt
das intern in RTS UP bzw. DOWN. Der Zustand wird als `ON`/`OFF` zurückgemeldet.

**Hinweis light_dimmer:** Kein echtes Brightness-API möglich — Modus B mit HA-Automationen
verwenden (z.B. bei Tastendruck dimmen). Modus A ist für diesen Typ deaktiviert.

**Hinweis blind:** In Modus B werden zusätzlich **MY Auf** (`MY_UP`) und **MY Runter**
(`MY_DOWN`) als separate Button-Entitäten registriert (Lamellensteuerung via Jalousie-Lamellen).

---

## Gerätemodi

Die App unterstützt zwei Betriebsmodi pro Gerät:

| Modus | HA Discovery | Verwendung |
|-------|-------------|-----------|
| **A** | 1× Cover / Light / Switch-Entität (optimistisch) | Direkte Steuerung, einfachste Einrichtung |
| **B** | Buttons Auf / Zu / Stop | Für Template Covers und Automationen |

In **beiden** Modi kommen hinzu: Button **MY**, Buttons **PROG Lang** / **PROG Anlern**
(unter *Konfiguration*), Sensoren **Rolling Code**, **Letzter Befehl** und **Adresse**
(unter *Diagnose*); bei `blind` zusätzlich **MY Auf** / **MY Runter**.

**Modus A** eignet sich für die meisten Anwendungsfälle — auch für Blueprints.  
**Modus B** eignet sich für fortgeschrittene Automatisierungen, die direkt auf
die einzelnen Buttons (Auf/Zu/Stop) reagieren möchten.

Für `light_dimmer` ist ausschließlich **Modus B** sinnvoll (Impulse via HA-Automationen).

---

## Gerät anlernen (Pairing-Wizard)

Der integrierte Pairing-Wizard führt durch den 5-stufigen Anlernprozess:

### Voraussetzung

Der Motor muss sich in Reichweite des NanoCUL befinden (~30 m Freifeld).

### Schritt-für-Schritt

1. **Wizard in der Web-UI starten**
   Gerätename, Gerätetyp und Modus (A/B) wählen. Der Wizard erzeugt eine eindeutige
   6-stellige Hex-Adresse (Format: `<address_prefix><lfd. Nummer>`, z.B. `A00001`).

2. **Motor in den Anlernmodus versetzen** — eine der beiden Varianten:
   - **Original-Fernbedienung:** `PROG`-Taste **ca. 3 Sekunden** halten, bis der Motor
     kurz auf und ab fährt
   - **Über ein bereits angelerntes Gerät der App:** Steuert die App diesen Motor schon
     (z. B. über ein anderes Gerät mit eigener Adresse), in der Geräteliste bei diesem
     Gerät **⏱ PROG Lang** drücken. Das wirkt wie das Halten der PROG-Taste — aber nur
     von einem Sender, den der Motor bereits kennt; von der neuen Adresse aus wirkt es nicht

3. **PROG senden**
   **📡 PROG senden** lernt den virtuellen Sender der App am Motor an
   (innerhalb von 2 Minuten nach Schritt 2).

4. **Bestätigen**
   Der Motor bestätigt mit einer kurzen Auf-Ab-Bewegung → im Wizard **✓ Bestätigen**.

5. **Fertig**
   Das Gerät erscheint sofort in Home Assistant unter
   **Einstellungen → Geräte & Dienste → MQTT**.

### Adress-Präfix

Der `address_prefix` aus der Konfiguration wird als erste 4 Hex-Zeichen der
Geräteadresse verwendet. Nach dem ersten angelernten Gerät wird der Präfix in
`/data/somfy_codes.json` gesperrt (`prefix_locked: true`), um Adresskonflikte
zu vermeiden.

---

## ioBroker Migration

Geräte, die bereits über ioBroker (oder ein anderes System) angelernt wurden, können
ohne erneutes Pairing übernommen werden:

1. Adresse und letzten Rolling Code aus ioBroker notieren
2. In der Web-UI **↑ Importieren** wählen: Name, Gerätetyp, Adresse, Rolling Code
   (**letzter Wert + 10** als Sicherheitspuffer) und Modus eintragen
3. **Importieren** — das Gerät erscheint sofort in Home Assistant, kein Neustart nötig

Alternativ per REST: `POST /api/devices/import` mit
`{"name", "device_type", "address", "rolling_code", "mode"}`.

**Wichtig:** Der Rolling Code muss ≥ dem letzten von ioBroker verwendeten Wert sein.
Ein zu niedriger Rolling Code bewirkt, dass der Motor alle Befehle ignoriert.

**Adress-Format:** Die Adresse (6 Hex-Zeichen, z.&nbsp;B. `A1B2C3`) wird unverändert in
den culfw-Befehl eingebaut — dieselbe Schreibweise wie FHEM und alle Systeme, die über
culfw senden. Adressen aus solchen Systemen sind daher ohne Konvertierung übertragbar.
culfw sendet die drei Bytes auf Funk in umgekehrter Reihenfolge (`C3 B2 A1`); das ist
protokollbedingt korrekt.

- **Funk-Mitschnitte** (Rohdaten eines Empfängers, culfw-Echo `Ys…`) zeigen die
  umgedrehte Reihenfolge → vor dem Import zurückdrehen (`C3B2A1` → `A1B2C3`)
- **Andere Systeme** (z.&nbsp;B. ESPSomfy, RFLink) nicht geprüft — im Zweifel mit einem
  einzelnen Befehl testen; reagiert der Motor nicht, die Byte-Reihenfolge drehen

---

## Template Cover in Home Assistant

Ein Template Cover kombiniert die Somfy-Entitäten mit einem physischen Sensor
(z.B. Fensterkontakt, Rollladenkontakt) für einen zuverlässigen Zustand —
auch nach manueller Bedienung oder MY-Taste.

### Modus A vs. Modus B

| | Modus A | Modus B |
|---|---|---|
| HA-Entität | Cover (optimistisch) | 3 einzelne Buttons |
| Template Cover | Aktionen via `cover.*` | Aktionen via `button.press` |
| Empfehlung | Einfachste Einrichtung | Flexibler, für Automatisierungen |

**Modus A** eignet sich wenn kein Template Cover benötigt wird — die Cover-Entität
funktioniert sofort ohne weitere Konfiguration.

**Modus B** empfiehlt sich für Template Covers: Die drei separaten Buttons
(Ausfahren / Einfahren / Stop) lassen sich präzise als Aktionen einsetzen und
reagieren unabhängig voneinander auf Automatisierungen.

### Entity-IDs herausfinden

**Einstellungen → Entwicklerwerkzeuge → Zustände** — dort alle Entitäten des
Geräts suchen (nach Gerätename oder `somfy` filtern). Die Entity-IDs in den
folgenden Beispielen durch die tatsächlichen IDs ersetzen.

---

### Beispiel: Modus B (Buttons — empfohlen)

Gerät im **Modus B** anlegen. HA erstellt drei Button-Entitäten:
- `button.meine_markise_ausfahren`
- `button.meine_markise_einfahren`
- `button.meine_markise_stop`

Template Cover in `configuration.yaml`:

```yaml
template:
  - cover:
      name: "Markise Terrasse"
      device_class: awning
      state_template: >
        {% if is_state('input_boolean.markise_eingefahren', 'on') %}
          closed
        {% else %}
          open
        {% endif %}
      open_cover:
        action: button.press
        target:
          entity_id: button.meine_markise_ausfahren
      close_cover:
        action: button.press
        target:
          entity_id: button.meine_markise_einfahren
      stop_cover:
        action: button.press
        target:
          entity_id: button.meine_markise_stop
      availability_template: >
        {{ is_state('binary_sensor.somfy_rts_gateway_verbindung', 'on')
           and states('input_boolean.markise_eingefahren')
           not in ['unknown', 'unavailable'] }}
```

Den Sensor (`input_boolean.markise_eingefahren`) durch den eigenen Kontaktsensor
ersetzen und den `state_template`-Ausdruck entsprechend anpassen:
- `is_state('binary_sensor.mein_sensor', 'on')` → `closed` wenn Sensor aktiv
- `is_state('binary_sensor.mein_sensor', 'off')` → `closed` wenn Sensor inaktiv

---

### Beispiel: Modus A (Cover-Entität — einfacher)

Gerät im **Modus A** anlegen. HA erstellt eine Cover-Entität:
- `cover.meine_markise`

Template Cover in `configuration.yaml`:

```yaml
template:
  - cover:
      name: "Markise Terrasse"
      device_class: awning
      state_template: >
        {% if is_state('input_boolean.markise_eingefahren', 'on') %}
          closed
        {% else %}
          open
        {% endif %}
      open_cover:
        action: cover.open_cover
        target:
          entity_id: cover.meine_markise
      close_cover:
        action: cover.close_cover
        target:
          entity_id: cover.meine_markise
      stop_cover:
        action: cover.stop_cover
        target:
          entity_id: cover.meine_markise
      availability_template: >
        {{ is_state('binary_sensor.somfy_rts_gateway_verbindung', 'on')
           and states('input_boolean.markise_eingefahren')
           not in ['unknown', 'unavailable'] }}
```

---

## MQTT Topics

### Modus A (Cover + PROG-Buttons)

| Topic | Richtung | Inhalt |
|-------|----------|--------|
| `homeassistant/cover/<id>/config` | Publish | Discovery Cover — bzw. `light/…` / `switch/…` je Gerätetyp (retain) |
| `homeassistant/button/<id>_my/config` | Publish | Discovery MY-Button (retain) |
| `homeassistant/sensor/<id>_{rolling_code,last_command,device_address}/config` | Publish | Discovery Diagnose-Sensoren (retain) |
| `homeassistant/button/<id>_prog_long/config` | Publish | Discovery PROG Lang (retain) |
| `homeassistant/button/<id>_prog_pair/config` | Publish | Discovery PROG Anlern (retain) |
| `somfy/<slug>/state` | Publish | `open` / `closed` / `stopped` (retain) |
| `somfy/<slug>/set` | Subscribe | `OPEN` / `CLOSE` / `STOP` / `MY` (light/switch: `ON` / `OFF`) |
| `somfy/<slug>/cmd` | Subscribe | `PROG_LONG` / `PROG_PAIR` |
| `somfy/<slug>/rolling_code` | Publish | Aktueller Rolling Code (retain) |
| `somfy/<slug>/last_command` | Publish | `OPEN` / `CLOSE` / `STOP` / `MY` / `PROG` (retain) |
| `somfy/<slug>/last_command_attr` | Publish | `{"raw_frame": "YsA0…"}` (retain) |
| `somfy/<slug>/device_address` | Publish | Adresse des virtuellen Senders (retain) |

### Modus B (Buttons + PROG-Buttons + Diagnose)

| Topic | Richtung | Inhalt |
|-------|----------|--------|
| `homeassistant/button/<id>_{auf,zu,stop,my}/config` | Publish | Discovery Buttons (retain) |
| `homeassistant/sensor/<id>_{rolling_code,last_command,device_address}/config` | Publish | Discovery Diagnose-Sensoren (retain) |
| `homeassistant/button/<id>_prog_long/config` | Publish | Discovery PROG Lang (retain) |
| `homeassistant/button/<id>_prog_pair/config` | Publish | Discovery PROG Anlern (retain) |
| `somfy/<slug>/button/auf` | Subscribe | `PRESS` |
| `somfy/<slug>/button/zu` | Subscribe | `PRESS` |
| `somfy/<slug>/button/stop` | Subscribe | `PRESS` |
| `somfy/<slug>/button/my` | Subscribe | `PRESS` |
| `somfy/<slug>/cmd` | Subscribe | `PROG_LONG` / `PROG_PAIR` |
| `somfy/<slug>/rolling_code` | Publish | Aktueller Rolling Code (retain) |
| `somfy/<slug>/last_command` | Publish | `OPEN` / `CLOSE` / `STOP` / `MY` / `PROG` (retain) |
| `somfy/<slug>/last_command_attr` | Publish | `{"raw_frame": "YsA0…"}` (retain) |
| `somfy/<slug>/device_address` | Publish | Adresse des virtuellen Senders (retain) |

Bei `blind` zusätzlich `somfy/<slug>/button/my_auf` und `…/my_zu` (`PRESS`).

### Gateway

| Topic | Inhalt |
|-------|--------|
| `cul2mqtt/status` | `online` / `offline` (LWT, retain) — HA-Entität `binary_sensor.somfy_rts_gateway_verbindung` |
| `cul2mqtt/gateway/status` | Statustext (keine HA-Entität) |
| `cul2mqtt/gateway/port` | USB-Port Pfad |
| `cul2mqtt/gateway/device_count` | Anzahl angelernte Geräte |
| `cul2mqtt/gateway/sw_version` | App-Version |

---

## Rolling Code Persistenz

Die Rolling Codes werden in `/data/somfy_codes.json` gespeichert:

```json
{
  "devices": [
    {"address": "A00001", "name": "Wohnzimmer Markise", "rolling_code": 42,
     "device_type": "awning", "mode": "A"}
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

Kann der neue Rolling Code nicht gespeichert werden (z. B. Speicher voll), wird
**nicht gesendet** — der Befehl schlägt mit einer Fehlermeldung im Log fehl.

---

## Fehlerbehebung

### NanoCUL wird nicht erkannt

- USB-Gerät prüfen: **App → Info → Hardware** oder im HA Terminal `ls /dev/ttyACM* /dev/ttyUSB*`
- Anderen USB-Port versuchen
- culfw-Firmware Version prüfen: Das App-Log zeigt beim Start die Antwort auf `V`
  (z. B. `NanoCUL verbunden auf /dev/ttyACM0 — V 1.67 nanoCUL433 …`)

### Motor reagiert nicht

- **433,42 MHz** Firmware auf dem NanoCUL? (nicht 433,92 MHz!)
- Firmware mit Somfy-RTS-Unterstützung (`HAS_SOMFY_RTS`)? Ohne sie ignoriert der Stick
  die `Ys…`-Befehle kommentarlos
- App-Log: Steht bei jedem Befehl `CUL TX: Yr1` und `CUL TX: YsA0…`? Dann wurde gesendet
- Entfernung zum Motor prüfen (~30 m Freifeld; Betonwände reduzieren Reichweite stark)
- App-Log auf `PROG_SENT` und `CONFIRMED` prüfen (`log_level: debug` aktivieren)

### MQTT Verbindung schlägt fehl

- Mosquitto App läuft? **Einstellungen → Apps → Mosquitto**
- `mqtt_host: core-mosquitto` für das interne HA-Netzwerk korrekt?
- Zugangsdaten korrekt gesetzt?

Die App bricht bei MQTT-Problemen **nicht** ab, sondern verbindet sich selbstständig neu —
beim Start (z. B. wenn Mosquitto nach einem HA-Neustart später hochkommt) und im laufenden
Betrieb. Wartezeit zwischen den Versuchen: anfangs 1 s, wachsend bis höchstens 60 s.
Meldungen im App-Log:

| Meldung | Bedeutung |
|---|---|
| `Warte auf Verbindung zum MQTT-Broker …` | Start: Geräte werden erst nach dem Verbinden in HA angemeldet |
| `MQTT-Broker <host:port> nicht erreichbar (Versuch N) …` (WARNING) | Broker antwortet nicht — neuer Versuch folgt |
| `MQTT-Broker <host:port> lehnt die Verbindung ab: … — Zugangsdaten prüfen` (ERROR) | Benutzer/Passwort falsch oder nicht berechtigt |
| `MQTT-Verbindung verloren: … — automatischer Reconnect` (WARNING) | Verbindung im Betrieb abgerissen |
| `MQTT wieder verbunden nach X s (N fehlgeschlagene Versuche)` | Verbindung wiederhergestellt, Befehle kommen wieder an |

### „somfy_codes.json ist beschädigt — Senden gesperrt"

Die Datei existiert, ist aber kein gültiges JSON (oder es fehlt das `devices`-Array).
Die App überschreibt sie in diesem Fall **nicht** mit leeren Werten, denn dann wären
alle Motoren desynchronisiert. Stattdessen:

- Beim ersten Erkennen wird eine Kopie als `somfy_codes.json.corrupt-<Zeitstempel>` abgelegt
- Alle Befehle werden verweigert (Log `ERROR`, Web-UI HTTP 503, MQTT-Topic
  `cul2mqtt/gateway/status` = „Fehler: somfy_codes.json beschädigt"; dafür gibt es
  keine eigene HA-Entität — maßgeblich ist das App-Log)
- Datei manuell reparieren oder aus einem HA-Backup wiederherstellen, danach App neu starten.
  Im Zweifel die Rolling Codes um **+10** erhöhen.

### Motor ignoriert Befehle nach ioBroker-Migration

- Rolling Code zu niedrig → Import mit höherem Wert wiederholen
- Empfehlung: letzten ioBroker-Wert + 10 als Startwert verwenden
