# core/config.py
from __future__ import annotations
import copy, json, logging, os, shutil, threading
from pathlib import Path

from core.config_schema import normalize_config

log = logging.getLogger("hub.config")

class Config:
    @staticmethod
    def _preserve_corrupt(path: Path) -> None:
        """Move *path* to a new, owner-only recovery file without collisions."""
        suffix = 0
        while True:
            name = path.name + ".corrupt"
            if suffix:
                name += f".{suffix}"
            backup = path.with_name(name)
            try:
                # Reserving the destination with O_EXCL makes the selection safe
                # even when two processes discover a corrupt config together.
                fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                break
            except FileExistsError:
                suffix += 1

        try:
            with path.open("rb") as source, os.fdopen(fd, "wb") as destination:
                shutil.copyfileobj(source, destination)
                destination.flush()
                os.fsync(destination.fileno())
        except OSError:
            # This path was created by this attempt, not an older recovery. Do
            # not leave an incomplete file which could be mistaken for one.
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                backup.unlink()
            except OSError:
                pass
            raise

        # Only remove the broken live config after its complete contents are
        # durable in the owner-only recovery file.
        try:
            path.unlink()
        except OSError as e:
            log.warning("could not remove corrupt config after copying it to %s: %s", backup, e)
        log.error("moved unparseable config to %s", backup)

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.data = {"interval_sec": 5, "pull_enabled": True, "auto_provision": True, "provision_token": ""}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
                else:
                    log.warning("config.json is not a JSON object; ignoring its contents")
            except Exception as e:
                # A corrupt/half-written file must not silently discard the user's
                # settings. Preserve it for recovery instead of overwriting it on
                # the next save, and start from defaults.
                log.error("config.json could not be parsed (%s); preserving it and using defaults", e)
                try:
                    self._preserve_corrupt(self.path)
                except OSError as backup_error:
                    # Recovery is best-effort: a read-only/full filesystem must
                    # not prevent the hub from starting with safe defaults.
                    log.error("could not preserve unparseable config %s: %s", self.path, backup_error)
        # Coerce hand-edited values to safe types/ranges so a bad file can't
        # crash the hub; surface every correction in the log.
        self.data, _warnings = normalize_config(self.data)
        for w in _warnings:
            log.warning("config: %s", w)
        # Re-secure an already-loose config.json (e.g. one left 0o644 by a crash
        # in a prior save's replace->chmod window) so its secrets don't stay
        # world-readable across restarts.
        if self.path.exists():
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def _write_atomic(self, data: dict) -> None:
        """Persist config crash-safely: write a temp file in the same directory,
        fsync it, then atomically rename over the target. A crash/power-loss can
        never leave a truncated config.json (which would reset every setting)."""
        payload = json.dumps(data, indent=2)
        tmp = self.path.with_name(self.path.name + ".tmp")
        # Create the temp already owner-only (0o600): it holds SMTP/webhook/token
        # secrets, and a plain open() would leave it group/other-readable (0o644
        # under the default umask) in the window before the rename+chmod.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        # Config can hold SMTP/webhook/token secrets — keep it owner-only.
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def save(self):
        with self.lock:
            self._write_atomic(self.data)

    # convenience
    def get(self, k, default=None):
        with self.lock:
            v = self.data.get(k, default)
            # Hand out a copy of mutable values. Callers (device/settings panels)
            # read a nested dict, mutate it, then call update(); returning the
            # LIVE object let those in-place edits race a concurrent save()'s
            # json.dumps (RuntimeError: dict changed size) and silently drop
            # updates. Copying makes get()->mutate->update() safe by construction.
            if isinstance(v, (dict, list)):
                return copy.deepcopy(v)
            return v

    def set(self, k, v):
        with self.lock:
            self.data[k] = v
            self.data, warns = normalize_config(self.data)
            self.save()
        for w in warns:
            log.warning("config: %s", w)

    def update(self, mapping: dict):
        """Merge keys from mapping into config and persist.

        The merged result is re-normalised so programmatic/API writes are coerced
        to safe types exactly like a hand-edited file is on load — otherwise a
        POST /api/config could persist a value that crashes the next startup.

        The change is recorded in the tamper-evident audit trail by KEY NAME
        only — never the values, which may be secrets (tokens, SMTP passwords).
        """
        if not isinstance(mapping, dict):
            return
        with self.lock:
            self.data.update(mapping)
            self.data, warns = normalize_config(self.data)
            self.save()
        for w in warns:
            log.warning("config: %s", w)
        try:
            from core.audit import AUDIT
            keys = ", ".join(sorted(str(k) for k in mapping))
            AUDIT.record("config.update", detail=keys)
        except Exception:
            pass

    def to_dict(self) -> dict:
        with self.lock:
            return copy.deepcopy(self.data)
