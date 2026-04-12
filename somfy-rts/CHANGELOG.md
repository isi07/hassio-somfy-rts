# Changelog

Alle nennenswerten Änderungen werden in dieser Datei dokumentiert.
Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [0.1.2] - 2026-04-12

### Behoben
- GitHub Actions Release-Job: `orhun/git-cliff-action` auf v4 aktualisiert
  (v3 nutzte Debian Buster EOL — apt-Repository 404-Fehler)

## [0.1.1] - 2026-04-12

### Behoben
- Ruff Lint-Fehler in `wizard.py`: ungenutzte Importe `dataclasses.field`
  und `rolling_code.get_settings` entfernt

## [0.1.0] - 2026-04-12

### Hinzugefügt
- Initiale Version des Somfy RTS Add-ons
- Unterstützung für NanoCUL USB-Stick mit culfw-Firmware (433,42 MHz)
- MQTT Integration mit Home Assistant Discovery (Modus A und B)
- Gerätetypen: `awning`, `shutter`, `blind`, `screen`, `gate`, `light`, `heater`
- Persistente Rolling Code Speicherung in `/data/somfy_codes.json`
  (atomar via tempfile + os.replace, strom-ausfallsicher)
- Unterstützung für Architekturen: amd64, aarch64, armv7
- Befehle: OPEN, CLOSE, STOP, PROG, MY_UP, MY_DOWN
- Pairing-Wizard (`PairingWizard`) für 5-stufigen Anlernprozess
- ioBroker-Migration ohne erneutes Pairing
- Gateway-Abstraktion (`BaseGateway` / `CULGateway`)
- Template Blueprints für Markisen und Rollläden (HA 2024.11+)
