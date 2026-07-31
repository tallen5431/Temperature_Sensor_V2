"""Constant-time secret comparison that survives non-ASCII input.

``hmac.compare_digest`` accepts ``str`` only when BOTH operands are ASCII-only;
give it anything else and it raises::

    TypeError: comparing strings with non-ASCII characters is not supported

Every secret this hub compares can be non-ASCII. The dashboard password comes
from ``UI_PASSWORD`` or ``ui_auth.password`` in config.json, and the config
schema coerces those to ``str`` without constraining the character set — so an
operator whose password contains an accented character turned every dashboard
request into a 500 and locked themselves out permanently. The other operand is
worse: it is request data, so any unauthenticated client could turn its own 401
into a 500 just by sending a non-ASCII password.

Comparing the UTF-8 encodings sidesteps the restriction entirely — bytes are
always accepted — and keeps the constant-time property, which is the whole
reason for using ``compare_digest`` rather than ``==``.

Note the timing guarantee has always been partial here: ``compare_digest`` hides
the position of the first differing byte but not the length of the operands, and
encoding does not change that.
"""
from __future__ import annotations

import hmac


def constant_time_eq(a, b) -> bool:
    """True when ``a`` and ``b`` are equal, compared in constant time.

    Accepts ``str``/``bytes``/``None`` in any combination; ``None`` is treated as
    the empty string so a missing credential compares false rather than raising.
    """
    def _as_bytes(v) -> bytes:
        if v is None:
            return b""
        if isinstance(v, (bytes, bytearray)):
            return bytes(v)
        return str(v).encode("utf-8", errors="surrogatepass")

    return hmac.compare_digest(_as_bytes(a), _as_bytes(b))
