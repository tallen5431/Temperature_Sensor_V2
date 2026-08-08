"""Wire-protocol limits, shared by both sides of the ingest contract.

Dependency-neutral on purpose. ``api/routes.py`` enforces these on the receiving
side and ``core/forwarder.py`` has to respect them on the sending side, but the
forwarder must not import the API module — that would pull Flask into a core
module imported at startup. Two copies of a limit that must agree is exactly the
kind of drift that shows up as "head office rejects every batch".

See PROTOCOL.md §6-7.
"""

# Maximum encoded request body accepted by the ingest endpoints.
MAX_INGEST_BYTES = 64 * 1024

# Maximum readings accepted by one bulk-ingest request.
MAX_BATCH_ROWS = 1000

# The probe only deep-sleeps when its reporting interval is at least this long
# (``DEEP_SLEEP_MIN_MS`` in esp32_temp_probe.ino); below it the probe stays
# always-on, which is what makes a Fixed unit continuously reachable.
#
# It belongs here because the THRESHOLD WATCH depends on it. The watch's saving
# comes from skipping the radio on a sample wake, and the firmware only decides a
# wake is sample-only when it woke from deep sleep — so on an always-on probe the
# watch cannot do anything, and every sample is transmitted regardless.
#
# The hub therefore must not arm it below this line. It used to: a probe on a 6 s
# reporting interval with a 5 s check was sent a sample cadence, and both the
# Devices dialog and Settings reported it as checking between reports, while the
# firmware transmitted every single reading. A setting that reads as applied and
# is not is worse than one that is plainly unavailable.
DEEP_SLEEP_MIN_MS = 10000
