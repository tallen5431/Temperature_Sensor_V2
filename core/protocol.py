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
