# TempSensor — containerized hub for homelab / self-hosted deployment.
FROM python:3.11-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist data + runtime config outside the image via a mounted volume.
ENV CSV_FILE=/data/temperature_log.csv \
    LOG_DIR=/data/logs \
    CONFIG_FILE=/data/config.json \
    HOST=0.0.0.0 \
    PORT=8080
VOLUME ["/data"]
EXPOSE 8080

# NOTE: mDNS probe auto-discovery needs the host network (see docker-compose.yml
# `network_mode: host`). With bridge networking, probes can still POST readings
# to the mapped port, but automatic discovery/provisioning won't work.
CMD ["python", "app.py"]
