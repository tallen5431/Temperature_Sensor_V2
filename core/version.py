"""Single source of truth for hub version and product metadata."""

HUB_VERSION = "2.6.2"
PRODUCT_NAME = "Setpoint"
DOCS_URL = "https://github.com/tallen5431/temperature_sensor_v2#readme"

# Firmware<->hub wire protocol version. This is the contract number the two
# sides are built against; the current firmware does not yet advertise it in its
# mDNS TXT record (only `id` and `name`), and the hub does not yet check it, so
# it is informational today (a future handshake could warn on a mismatch).
PROTOCOL_VERSION = 1

# Backwards-compatible alias so modules/tests that import ``__version__`` keep
# working alongside the ``HUB_VERSION`` name used across the UI/API.
__version__ = HUB_VERSION
