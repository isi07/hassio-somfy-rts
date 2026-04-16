# Changelog

Alle nennenswerten Änderungen werden hier dokumentiert.
Format: [Conventional Commits](https://www.conventionalcommits.org/de/)


## [0.3.14] - 2026-04-16

### Dokumentation

- Blueprints entfernt — Template Cover Beispiele (Modus A + B) direkt in DOCS.md
- .claude/worktrees/ und .claude/projects/ zu .gitignore hinzugefügt

### CI

- Blueprint-Lint und Blueprint-Validierungs-Schritte aus build.yaml entfernt


## [0.3.13] - 2026-04-16

### Behoben

- State-Topics (somfy/{slug}/state, rolling_code, last_command, last_command_attr) beim Löschen eines Geräts ebenfalls mit leerer retained Payload clearen


## [0.3.12] - 2026-04-16

### Neu hinzugefügt

- MQTT Discovery Cleanup beim Löschen eines Geräts — HA entfernt Entitäten automatisch

### Behoben

- Yr-Repeat-Wert im Log-Tab sichtbar (Frame-Spalte: "Yr1 | YsA0…")
- RC (Post) im Log-Tab als reine Dezimalzahl statt "0x…"-Hex-String


## [0.3.11] - 2026-04-16

### Neu hinzugefügt

- PROG Lang (Yr8) und PROG Anlern (Yr4), repeat-Parameter im Frame-Log
- PROG Lang und PROG Anlern als MQTT Discovery Entitäten in HA (entity_category: config)
- Blueprints vereinfacht — Kontaktsensor statt Fahrzeitverfolgung


