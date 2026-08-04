"""Dependency-neutral constants shared by protocol clients and servers."""

# Maximum encoded request body accepted by the ingest endpoints.
MAX_INGEST_BYTES = 64 * 1024

# Maximum readings accepted by one bulk-ingest request.
MAX_BATCH_ROWS = 1000
