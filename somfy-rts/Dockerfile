# Home Assistant multi-arch base image (amd64 + arm64), pinned to a dated release.
# Dependabot (docker ecosystem) proposes updates. Keep the Python minor version in
# sync with setup-python in .github/workflows/build.yaml and ruff.toml.
FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.08.0

# Override S6-Overlay entrypoint from base image — run.sh directly
ENTRYPOINT ["/run.sh"]

# Version injected at build time — readable at runtime via SOMFY_VERSION env var
ARG BUILD_VERSION=unknown
ENV SOMFY_VERSION=${BUILD_VERSION}

# HA Builder labels
ARG BUILD_VERSION
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_REF

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="${BUILD_ARCH}" \
    maintainer="isi07" \
    org.opencontainers.image.title="Somfy RTS" \
    org.opencontainers.image.description="Controls Somfy RTS devices via NanoCUL USB stick" \
    org.opencontainers.image.source="https://github.com/isi07/hassio-somfy-rts" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}"

# Create persistent data directory (pip ships with the base-python image)
RUN mkdir -p /data

# Health check inside the container (independent of the host port mapping).
# The Supervisor restarts the app on "unhealthy" when the Watchdog switch is on
# (replaces the obsolete config.yaml "watchdog" key). The web UI starts first,
# so the app stays healthy while it waits for the NanoCUL or the MQTT broker.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/api/status', timeout=5)" || exit 1

# Set working directory
WORKDIR /app

# Copy and install Python dependencies (separate layer for caching)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code and entrypoint
COPY somfy_rts/ ./somfy_rts/
COPY run.sh /run.sh
RUN chmod +x /run.sh

