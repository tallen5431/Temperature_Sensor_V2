"""Single source of truth for hub version and product metadata."""

HUB_VERSION = "2.6.1"
PRODUCT_NAME = "Setpoint"
DOCS_URL = "https://github.com/tallen5431/temperature_sensor_v2#readme"

# Firmware<->hub wire protocol version. Probes advertise `proto` in their mDNS
# TXT record; the hub warns (not crashes) on a mismatch.
PROTOCOL_VERSION = 1

# Backwards-compatible alias so modules/tests that import ``__version__`` keep
# working alongside the ``HUB_VERSION`` name used across the UI/API.
__version__ = HUB_VERSION
