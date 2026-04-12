# Somfy RTS Add-on — Dokumentation

## Voraussetzungen

- **NanoCUL USB-Stick** mit culfw-Firmware (433,42 MHz Version)
- **MQTT Broker** (z.B. das Mosquitto Add-on für Home Assistant)
- Somfy RTS kompatible Geräte (Markisen, Rollläden, Jalousien)

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

```yaml
serial_port: /dev/ttyUSB0    # Pfad zum NanoCUL USB-Stick
baud_rate: 38400              # Baudrate (Standard für culfw)
mqtt_host: core-mosquitto     # MQTT Broker (Standard: HA Mosquitto Add-on)
mqtt_port: 1883
mqtt_user: ""                 # Leer lassen wenn keine Authentifizierung
mqtt_password: ""
mqtt_topic_prefix: somfy      # Präfix für alle MQTT Topics

devices:
  - name: Wohnzimmer Markise
    type: awning               # awning | blind | roller_shutter
    address: A1B2C3            # Eindeutige 3-Byte Hex-Adresse
    rolling_code: 0            # Startwert (wird automatisch hochgezählt)

  - name: Schlafzimmer Rollladen
    type: roller_shutter
    address: D4E5F6
    rolling_code: 0
```

### Gerätetypen

| Typ | Beschreibung | HA Geräteklasse |
|---|---|---|
| `awning` | Markise | awning |
| `blind` | Jalousie / Raffstore | blind |
| `roller_shutter` | Rollladen | shutter |

### Adresse vergeben

Jedes virtuelle Somfy-Gerät braucht eine **eindeutige 6-stellige Hex-Adresse**
(z.B. `A1B2C3`). Diese darf nicht mit echten Somfy-Fernbedienungen kollidieren.
Empfehlung: Mit `100000` beginnen und hochzählen.

---

## Gerät anlernen (Pairing)

Nach dem ersten Start sendet das Add-on automatisch MQTT Discovery-Nachrichten.
Die Cover-Entitäten erscheinen in Home Assistant unter **Einstellungen → Geräte & Dienste → MQTT**.

### Somfy Motor anlernen

1. Motor mit einer **echten Somfy-Fernbedienung** in den Programmiermodus versetzen:
   - `PROG`-Taste der Originalf­ernbedienung **3 Sekunden** halten bis kurzes Auf-Ab
   
2. Innerhalb von **2 Minuten** in Home Assistant: Cover-Entität → **STOP** senden
   (entspricht dem "My"-Befehl / PROG-Signal)
   
3. Motor bestätigt mit kurzem Auf-Ab → Pairing erfolgreich

---

## MQTT Topics

| Topic | Beschreibung |
|---|---|
| `somfy/<name>/set` | Befehl senden: `OPEN`, `CLOSE`, `STOP` |
| `somfy/<name>/state` | Status: `open`, `closed`, `stopped` |
| `somfy/<name>/position` | Position 0–100 (sofern bekannt) |

---

## Fehlerbehebung

### NanoCUL wird nicht erkannt
- `ls /dev/ttyUSB*` im Terminal prüfen
- Im Add-on: **Hardware** → USB-Geräte prüfen
- culfw-Firmware Version prüfen: `V\n` über serielle Konsole senden

### Motor reagiert nicht
- Rolling Code zurücksetzen: `rolling_code: 0` in der Konfiguration
- Neu-Pairing durchführen (siehe oben)
- Entfernung zum Motor prüfen (NanoCUL hat ~30m Reichweite)

### MQTT Verbindung schlägt fehl
- Mosquitto Add-on läuft? **Einstellungen → Add-ons → Mosquitto**
- Zugangsdaten korrekt?
- `mqtt_host: core-mosquitto` für das interne HA-Netzwerk

---

## Rolling Code Persistenz

Die Rolling Codes werden in `/data/rolling_codes.json` gespeichert und
überleben Add-on Neustarts. **Nie manuell löschen**, sonst muss neu gepairt werden.
