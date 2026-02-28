#!/bin/bash
# Script to manually provision a specific device
# Usage: ./provision_device.sh <device_ip> [port] [interval_ms] [hub_port]

DEVICE_IP=${1:-"192.168.1.229"}
DEVICE_PORT=${2:-80}
INTERVAL_MS=${3:-2000}
HUB_PORT=${4:-8080}

echo "Provisioning device at $DEVICE_IP:$DEVICE_PORT with interval $INTERVAL_MS ms..."

curl -X POST "http://localhost:$HUB_PORT/api/provision" \
  -H "Content-Type: application/json" \
  -d "{\"host\": \"$DEVICE_IP\", \"port\": $DEVICE_PORT, \"interval_ms\": $INTERVAL_MS}" \
  -w "\n" \
  -s

echo ""
echo "Checking device status..."
curl -s "http://$DEVICE_IP:$DEVICE_PORT/status" | python3 -m json.tool || echo "Failed to get status"
