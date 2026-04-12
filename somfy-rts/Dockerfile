ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.11
FROM ${BUILD_FROM}

# Install system dependencies for serial communication
RUN apk add --no-cache \
    py3-pip \
    eudev

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY somfy_rts/ ./somfy_rts/
COPY run.sh /run.sh

RUN chmod +x /run.sh

CMD ["/run.sh"]
