ARG BUILD_FROM
FROM ${BUILD_FROM}

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

# Install Python pip (base image already includes Python 3.11)
RUN apk add --no-cache py3-pip

# Create persistent data directory
RUN mkdir -p /data

# Set working directory
WORKDIR /app

# Copy and install Python dependencies (separate layer for caching)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code and entrypoint
COPY somfy_rts/ ./somfy_rts/
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
