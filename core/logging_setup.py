"""Centralised logging configuration.

Call :func:`configure_logging` once at startup.  Modules obtain loggers via
``logging.getLogger("hub.<area>")``.  A rotating file handler keeps a bounded
on-disk history so field issues can be diagnosed from a customer's log file.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


def configure_logging(log_dir: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger("hub")
    if getattr(root, "_configured", False):
        return root

    root.setLevel(level)
    root.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_dir:
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                Path(log_dir) / "hub.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
            file_handler.setFormatter(fmt)
            root.addHandler(file_handler)
        except Exception as e:  # noqa: BLE001
            root.warning("file logging disabled: %s", e)

    root._configured = True  # type: ignore[attr-defined]
    return root
