#!/bin/bash
# Script to manually provision a specific device
# Usage: ./provision_device.sh <device_ip> [port] [interval_ms] [hub_port]

DEVICE_IP=${1:-"192.168.1.229"}
DEVICE_PORT=${2:-80}
INTERVAL_MS=${3:-2000}
HUB_PORT=${4:-8088}

# /api/provision requires the hub's device token, and a default hub always has
# one (app.py generates it on first run), so without this every invocation of
# this script came back {"ok": false, "error": "unauthorized"} -- and, because
# curl was called with -s and no --fail, the script printed that and carried on
# to the status check as though it had worked. Env first, then config.json; an
# empty token means an open hub (tests, air-gapped dev) and the header is then
# omitted entirely rather than sent blank.
TOKEN="${SERVER_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f config.json ]; then
  TOKEN=$(python3 -c 'import json;print(json.load(open("config.json")).get("provision_token",""))' 2>/dev/null) || TOKEN=""
fi

echo "Provisioning device at $DEVICE_IP:$DEVICE_PORT with interval $INTERVAL_MS ms..."

curl -X POST "http://localhost:$HUB_PORT/api/provision" \
  -H "Content-Type: application/json" \
  ${TOKEN:+-H "X-Token: $TOKEN"} \
  -d "{\"host\": \"$DEVICE_IP\", \"port\": $DEVICE_PORT, \"interval_ms\": $INTERVAL_MS}" \
  -w "\n" \
  -s

echo ""
echo "Checking device status..."
curl -s "http://$DEVICE_IP:$DEVICE_PORT/status" | python3 -m json.tool || echo "Failed to get status"
