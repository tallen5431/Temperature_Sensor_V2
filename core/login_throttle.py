"""Lock a client out of the dashboard login after repeated wrong passwords."""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("hub.app")


class LoginThrottle:
    """Lock a client out after repeated WRONG passwords.

    Basic auth has no built-in limit, so on a shared LAN anyone could guess as
    fast as the hub answers. After ``limit`` failures inside ``window`` seconds a
    client gets 429 for ``lockout`` seconds — even with the right password, or
    the lockout would only slow a guesser down by one request. A success clears
    the count. Keyed by client address; behind a tunnel or reverse proxy every
    visitor shares one address, which is a reason to put an authenticating proxy
    in front (MULTI_SITE.md), not to turn this off.

    A request with NO credentials is not a failure — that is just a browser
    asking for the login prompt.
    """

    def __init__(self, limit=10, window=900, lockout=900, clock=time.time,
                 max_clients=1024):
        self.limit, self.window, self.lockout = limit, window, lockout
        self._clock = clock
        self._max = max_clients
        self._lock = threading.Lock()
        self._fails = {}        # client -> [failure epochs inside the window]
        self._locked = {}       # client -> locked-until epoch

    def retry_after(self, client):
        """Seconds left on ``client``'s lockout, or 0 when it may try."""
        now = self._clock()
        with self._lock:
            until = self._locked.get(client, 0)
            if until > now:
                return int(until - now) + 1
            self._locked.pop(client, None)
            return 0

    def failure(self, client):
        now = self._clock()
        with self._lock:
            recent = [t for t in self._fails.get(client, []) if now - t < self.window]
            recent.append(now)
            if len(recent) >= self.limit:
                self._locked[client] = now + self.lockout
                self._fails.pop(client, None)
                log.warning("dashboard login: %s locked out for %d s after %d "
                            "wrong passwords", client, self.lockout, len(recent))
            else:
                self._fails[client] = recent
            if len(self._fails) > self._max:          # bound memory on a noisy LAN
                for k in sorted(self._fails, key=lambda c: self._fails[c][-1])[
                        :len(self._fails) - self._max]:
                    del self._fails[k]

    def success(self, client):
        with self._lock:
            self._fails.pop(client, None)
