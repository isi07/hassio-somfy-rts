"""Somfy RTS App — steuert Somfy RTS Geräte via NanoCUL/culfw und MQTT."""

import os

# Injected at build time via Docker build-arg BUILD_VERSION → ENV SOMFY_VERSION.
# Falls back to the last known version for local development runs.
__version__ = os.environ.get("SOMFY_VERSION", "0.2.3")
