# core/logger.py
from __future__ import annotations
import threading, time, datetime, requests
from pathlib import Path
from core.config import Config
from core.storage import append_row

class PullLogger:
    def __init__(self, cfg: Config, csv_file: Path, esp32_url: str):
        self.cfg = cfg
        self.csv_file = csv_file
        self.esp32_url = esp32_url
        self.stop_evt = threading.Event()
        self.th = None

    def _fetch_temp(self):
        try:
            r = requests.get(self.esp32_url, timeout=3)
            r.raise_for_status()
            lines = r.text.strip().splitlines()
            if len(lines) < 2: return None
            parts = [p.strip() for p in lines[1].split(',')]
            if len(parts) < 3: return None
            t_c = float(parts[1]); t_f = float(parts[2])
            ts = datetime.datetime.now().isoformat(timespec="seconds")
            return ts, t_c, t_f
        except Exception:
            return None

    def _loop(self):
        while not self.stop_evt.is_set():
            interval = max(1, int(self.cfg.get("interval_sec", 5)))
            if self.cfg.get("pull_enabled", True):
                row = self._fetch_temp()
                if row:
                    ts, t_c, t_f = row
                    append_row(self.csv_file, ts, t_c, t_f)
            time.sleep(interval)

    def start(self):
        if self.th and self.th.is_alive(): return
        self.th = threading.Thread(target=self._loop, daemon=True)
        self.th.start()

    def stop(self):
        self.stop_evt.set()
