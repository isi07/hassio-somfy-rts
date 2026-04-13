# Changelog

Alle nennenswerten Änderungen werden hier dokumentiert.
Format: [Conventional Commits](https://www.conventionalcommits.org/de/)


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


