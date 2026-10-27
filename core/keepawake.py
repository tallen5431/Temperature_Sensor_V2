"""Stop the hub PC idling into sleep while Setpoint is running.

A default Windows install puts the machine to sleep after a period with no
keyboard or mouse input — and a sleeping hub raises no alarms, including the
"probe went silent" one, because the thing that would notice is asleep. The
customer who installs Setpoint on a back-office PC and walks away is exactly the
customer this bites, and nothing in the product told them to change it.

What this does, per platform:

- **Windows:** re-asserts ``SetThreadExecutionState(ES_SYSTEM_REQUIRED)`` once a
  minute from a dedicated thread. That resets the system idle timer — the same
  mechanism a media player uses — so the PC does not idle to sleep. The display
  may still turn off (that is fine and saves power). It does NOT override a
  person choosing Sleep, closing a laptop lid, or a power-button press.
- **macOS:** holds a ``caffeinate -i`` assertion tied to this process.
- **Linux:** nothing. Servers there rarely suspend; ``INSTALL.md`` covers the
  ``systemctl mask sleep.target`` step for a desktop that does.

Controlled live by ``keep_awake`` in config (default on), so a Settings change
takes effect within a minute with no restart.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

log = logging.getLogger("hub.keepawake")

ES_SYSTEM_REQUIRED = 0x00000001
REASSERT_SEC = 60


def supported(platform: str = sys.platform) -> bool:
    return platform == "win32" or platform == "darwin"


class KeepAwake(threading.Thread):
    def __init__(self, cfg, platform: str = sys.platform, interval: float = REASSERT_SEC):
        super().__init__(name="keep-awake", daemon=True)
        self.cfg = cfg
        self.platform = platform
        self.interval = interval
        self._stop_event = threading.Event()
        self._caffeinate = None
        self.active = False

    def wanted(self) -> bool:
        return bool(self.cfg.get("keep_awake", True)) and supported(self.platform)

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.apply()
            except Exception as e:  # noqa: BLE001 - a nicety must never crash the hub
                log.warning("keep-awake: %s", e)
            self._stop_event.wait(self.interval)
        self._release()

    def apply(self) -> None:
        """Bring the OS assertion in line with the config, once."""
        if not self.wanted():
            self._release()
            return
        if self.platform == "win32":
            import ctypes
            # Without ES_CONTINUOUS this is a one-shot reset of the idle timer,
            # which is why it is repeated: nothing is left asserted if the hub
            # dies, so a crashed hub cannot keep a PC awake forever.
            ctypes.windll.kernel32.SetThreadExecutionState(ES_SYSTEM_REQUIRED)
        elif self.platform == "darwin":
            if self._caffeinate is None or self._caffeinate.poll() is not None:
                # -w ties the assertion to this process, so it ends with the hub.
                self._caffeinate = subprocess.Popen(
                    ["caffeinate", "-i", "-w", str(os.getpid())],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not self.active:
            log.info("keep-awake on: this PC will not idle to sleep while the hub runs")
        self.active = True

    def _release(self) -> None:
        if self._caffeinate is not None:
            try:
                self._caffeinate.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._caffeinate = None
        if self.active:
            log.info("keep-awake off: normal power settings apply")
        self.active = False
