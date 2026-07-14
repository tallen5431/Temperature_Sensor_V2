# Setpoint — containerized hub for homelab / self-hosted deployment.
FROM python:3.11-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist all writable state outside the image via a mounted volume. app.py
# derives the DB, config.json, logs and the audit trail from DATA_DIR, so this
# single var is what actually redirects them onto /data. (The previous
# CSV_FILE/LOG_DIR/CONFIG_FILE vars were never read by app.py, so data was
# silently written to the ephemeral container layer and lost on every recreate.)
ENV DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8080 \
    OPEN_BROWSER=0
VOLUME ["/data"]
EXPOSE 8080

# Liveness via the unauthenticated health endpoint (urlopen raises on non-2xx).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/health' % os.getenv('PORT','8080'), timeout=3)" || exit 1

# NOTE: mDNS probe auto-discovery needs the host network (see docker-compose.yml
# `network_mode: host`). With bridge networking, probes can still POST readings
# to the mapped port, but automatic discovery/provisioning won't work.
CMD ["python", "app.py"]
