# Changelog

Alle nennenswerten Änderungen werden hier dokumentiert.
Format: [Conventional Commits](https://www.conventionalcommits.org/de/)


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


