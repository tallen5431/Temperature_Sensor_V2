# core/version.py
"""Single source of truth for the product version.

Surfaced in the UI footer, GET /api/health, and stamped on QC labels so a
customer can always tell which build they are running.
"""
from __future__ import annotations

__version__ = "2.0.0"

# Firmware<->hub protocol version the hub speaks. Probes advertise `proto` in
# their mDNS TXT record; the hub warns (not crashes) on a mismatch.
PROTOCOL_VERSION = 1
