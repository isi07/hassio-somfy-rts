# Changelog

Alle nennenswerten Änderungen werden hier dokumentiert.
Format: [Conventional Commits](https://www.conventionalcommits.org/de/)


## [0.4.0] - 2026-10-04

### CI/CD

- Build the image on every PR and push, publish only on tags

### Dokumentation

- Document address byte order as a critical invariant
- Bring README and DOCS.md up to date for 0.4.0
- Clarify that PROG Lang only works from an already paired sender

### Fehlerbehebungen

- Remove PROG Lang from the pairing wizard
- Keep retrying the MQTT connection instead of crashing
- Replace 1x1 placeholder icon and logo with real images

### Neu hinzugefügt

- Add German and English translations for the add-on options

### Refactoring

- Migrate MQTT client to paho-mqtt callback API v2
- Adopt ruff 0.16 default rules and lint tests and tools

### Sonstiges

- **deps:** Bump docker/setup-qemu-action from 3 to 4
- **deps:** Bump docker/build-push-action from 6 to 7
- **deps:** Bump docker/setup-buildx-action from 3 to 4
- **deps:** Bump actions/checkout from 4 to 7
- **deps:** Bump actions/setup-python from 6 to 7
- **docker:** Move base image to Python 3.14 / Alpine 3.24
- **deps:** Pin all dependencies exactly and group Dependabot updates
- **deps:** Bump hadolint/hadolint-action from 3.3.0 to 3.5.0
- Mark tools/cul_sniff.py as executable
- **docker:** Use HA multi-arch base image pinned to a dated release

## [0.3.22] - 2026-10-04

### CI/CD

- Pin ruff to 0.15.10

### Dokumentation

- Correct culfw frame field descriptions (KK byte, X21, address order)

### Fehlerbehebungen

- Make rolling code persistence fail-safe and thread-safe
- Always attach the frame logger's own stdout handler

### Sonstiges

- Add read-only CUL serial sniffer for receive-side diagnostics
- Fix changelog generation and bring CLAUDE.md up to date

### Tests

- Cover store errors on prog, import and wizard endpoints

## [0.3.20] - 2026-04-21

### Fehlerbehebungen

- MY_UP/MY_DOWN MQTT-Publishing und kein Cover-State-Update bei Tilt-Befehlen

## [0.3.19] - 2026-04-20

### Fehlerbehebungen

- MY-Button in HA und Ingress, MY_UP/MY_DOWN in Modus A, device_address in Modus B

## [0.3.18] - 2026-04-20

### Fehlerbehebungen

- Wizard-State-Reset beim zweiten Durchlauf, MQTT Discovery nach Wizard, Diagnose-Topics nach REST-Befehl
- Remove unused json import (ruff F401)

## [0.3.17] - 2026-04-20

### Dokumentation

- Hinweis zur Big-Endian Adress-Darstellung in culfw-Befehlen

### Neu hinzugefügt

- Ha_platform pro Gerätetyp, light als HA light-Entity, heater als switch, light_dimmer nur Modus B, Tilt-Buttons nur für Jalousien

## [0.3.16] - 2026-04-19

### Fehlerbehebungen

- PROG_LONG Yr14, PROG_PAIR Yr4, Auto-Reconnect bei I/O Error
- Debug-Panel nur via Settings steuerbar, Repeat-Default auf 1

## [0.3.15] - 2026-04-19

### Neu hinzugefügt

- Temporäres Debug-Feature für PROG Repeat-Anzahl testen
- Debug-Modus als Settings-Option, raw-cmd Endpunkt, README aktualisiert

## [0.3.14] - 2026-04-16

### CI/CD

- Blueprint-Lint-Schritte aus build.yaml entfernen

### Dokumentation

- Blueprints entfernt, Template Cover Beispiele in DOCS.md

### Sonstiges

- .claude/worktrees/ zu .gitignore hinzufügen

## [0.3.13] - 2026-04-16

### Dokumentation

- CLAUDE.md - immer auf main arbeiten, kein Worktree

### Fehlerbehebungen

- State-Topics beim Löschen eines Geräts ebenfalls clearen

## [0.3.12] - 2026-04-16

### Fehlerbehebungen

- Yr im Log sichtbar, RC als reine Dezimalzahl ohne 0x-Prefix

### Neu hinzugefügt

- MQTT Discovery Cleanup beim Löschen eines Geräts

## [0.3.11] - 2026-04-16

### Neu hinzugefügt

- PROG Lang (Yr8) und PROG Anlern (Yr4), repeat-Parameter im Frame-Log
- PROG Lang und PROG Anlern als MQTT Discovery Entitäten in HA (entity_category: config)
- Blueprints vereinfacht — Kontaktsensor statt Fahrzeitverfolgung

## [0.3.10] - 2026-04-15

### Fehlerbehebungen

- Gateway-Verbindung zeigt Online/Offline, _FALLBACK_PROFILE auf shutter-Profil

## [0.3.9] - 2026-04-15

### Fehlerbehebungen

- Command_map auch für WebUI REST-API Befehle anwenden

### Refactoring

- HA-Semantik vs RTS-Protokoll getrennt, gerätetypspez. Beschriftungen, Log UP/DOWN/MY

## [0.3.8] - 2026-04-15

### Fehlerbehebungen

- Ctrl nibble korrekt ins high byte (Somfy RTS Protokoll)
- Awning OPEN/CLOSE Zuordnung korrigiert (Ausfahren=CLOSE, Einfahren=OPEN)

## [0.3.7] - 2026-04-15

### Fehlerbehebungen

- Build.yaml python 3.12, checkout@v4, armv7 aus CLAUDE.md entfernen
- Import-Gerätetyp, Markise Pfeilrichtung, device_count nach Import

## [0.3.6] - 2026-04-15

### Dokumentation

- CLAUDE.md mit CRITICAL-Block, Interaction Protocol, Do's/Don'ts, Checkliste

### Fehlerbehebungen

- Log_frame nach send_raw verschieben, STATUS=OK erst nach echtem Senden
- Unused field import entfernen (ruff F401)

### Neu hinzugefügt

- Gerät manuell importieren via UI und REST-API (POST /api/devices/import)
- Modus A/B per UI wählbar, CLAUDE.md aktualisiert
- Diagnose-Sensoren in Modus A, raw_frame Attribut, availability_topic geprüft

## [0.3.5] - 2026-04-15

### Fehlerbehebungen

- Publish MQTT discovery for existing and newly paired devices

## [0.3.4] - 2026-04-14

### Fehlerbehebungen

- Disable caching for static files in web server

## [0.3.3] - 2026-04-14

### Fehlerbehebungen

- Log timestamp with date+tz, download button always visible, RC auto-refresh

## [0.3.2] - 2026-04-14

### Fehlerbehebungen

- Delete button visible, MY buttons correct, log shows date and timezone

### Neu hinzugefügt

- Add RTS frame log file download endpoint

## [0.3.1] - 2026-04-14

### Fehlerbehebungen

- Save device_type in somfy_codes.json

### Neu hinzugefügt

- Add timezone configuration for log timestamps
- Add delete button to device card in Web UI

## [0.3.0] - 2026-04-14

### Fehlerbehebungen

- Read version from config.yaml instead of hardcoded
- Use deferred import for rts_logger in rts.py and gateway.py
- Show correct MY buttons per device profile

## [0.2.3] - 2026-04-13

### Fehlerbehebungen

- Build amd64 and aarch64 separately in matrix strategy
- Use absolute workspace path for builder target
- Revert to --all builder strategy
- Use absolute path for builder target
- Upgrade builder to 2025.03.0 and use explicit arch matrix
- Use correct /data/ mount path for builder target
- Migrate to Docker Buildx, drop deprecated HA builder
- Correct base image name for HA python
- Replace bashio with plain bash in run.sh

### Debug

- Add workspace debug step

## [0.2.2] - 2026-04-13

### Fehlerbehebungen

- Override base image entrypoint in Dockerfile
- Bump version to 0.2.2, mask mqtt_password, add release process docs

## [0.2.1] - 2026-04-13

### Dokumentation

- Update version to 0.2.0 in README

### Fehlerbehebungen

- Correct ghcr.io image path in config.yaml
- Bump version to 0.2.1

## [0.2.0] - 2026-04-13

### CI/CD

- Add yamllint, shellcheck, hadolint, jsonlint to build pipeline
- Add yamllint config and blueprint validator
- Add addon-linter, actionlint and dependabot
- Run lint on PRs, build+release only on tags
- Add eslint for JavaScript files

### Dokumentation

- Update all documentation to current state
- Add documentation maintenance rules to CLAUDE.md
- Add shields badges and update addon→app terminology

### Fehlerbehebungen

- Bump config.yaml version to 0.1.2, add code quality standards
- Add missing -> None type hints and annotate paho callbacks
- Resolve shellcheck warnings in run.sh
- Resolve hadolint warnings in Dockerfile
- Clean up config.yaml per addon-linter requirements
- Remove unused set_address_prefix import in wizard.py

### Neu hinzugefügt

- Add structured RTS frame logging system
- Add web UI with device dashboard, pairing wizard and settings

### Tests

- Add pytest unit tests for rts, rolling_code and wizard

### Build

- **deps:** Bump hadolint/hadolint-action from 3.1.0 to 3.3.0
- **deps:** Bump softprops/action-gh-release from 2 to 3
- **deps:** Bump actions/setup-python from 5 to 6
- **deps:** Bump actions/checkout from 4 to 6
- **deps:** Bump docker/login-action from 3 to 4

## [0.1.2] - 2026-04-12

### Fehlerbehebungen

- Upgrade git-cliff-action to v4 to fix Debian Buster EOL failure

## [0.1.1] - 2026-04-12

### Fehlerbehebungen

- Resolve ruff lint errors

## [0.1.0] - 2026-04-12

### Dokumentation

- Fix blueprint filenames in CLAUDE.md

### Fehlerbehebungen

- Correct baudrate to 9600 and send X21 init to CUL
- Correct config.yaml and run.sh for HA addon
- Export ADDRESS_PREFIX env var in run.sh
- Correct Dockerfile for HA addon builder
- Correct GitHub Actions build workflow

### Neu hinzugefügt

- Initial project structure


