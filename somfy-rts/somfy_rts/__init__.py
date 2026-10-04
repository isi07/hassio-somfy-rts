"""Somfy RTS App — steuert Somfy RTS Geräte via NanoCUL/culfw und MQTT."""

import os

# Injected at build time via Docker build-arg BUILD_VERSION → ENV SOMFY_VERSION.
# Local development runs (no Docker) report "dev".
__version__ = os.environ.get("SOMFY_VERSION", "dev")
