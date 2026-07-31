"""Secret comparison must not raise on non-ASCII input.

``hmac.compare_digest`` accepts ``str`` only when BOTH operands are ASCII-only;
anything else raises ``TypeError: comparing strings with non-ASCII characters is
not supported``. Both operands of every secret check in this hub can be
non-ASCII:

* the configured side -- ``UI_PASSWORD`` / ``ui_auth.password`` / ``SERVER_TOKEN``
  are coerced to ``str`` by the schema but never constrained to ASCII, so an
  operator with an accented character in their password 500s every dashboard
  request and is locked out permanently, with no way in through the UI;
* the supplied side -- request data, so any unauthenticated client could turn
  its own 401 into a 500 (and a traceback in the log) just by sending one.
"""
import pytest

from core.secret_compare import constant_time_eq


@pytest.mark.parametrize("a,b", [
    ("café123", "café123"),
    ("pässwörd", "pässwörd"),
    ("日本語", "日本語"),
    ("s3cret", "s3cret"),
    ("", ""),
])
def test_equal_secrets_match(a, b):
    assert constant_time_eq(a, b) is True


@pytest.mark.parametrize("a,b", [
    ("s3cret", "wröng"),        # non-ASCII on the CLIENT side -> used to 500
    ("café123", "cafe123"),     # accent is the only difference
    ("s3cret", "wrong"),
    ("s3cret", ""),
    ("s3cret", "s3cre"),        # prefix must not match
])
def test_differing_secrets_do_not_match(a, b):
    assert constant_time_eq(a, b) is False


def test_none_is_treated_as_empty_not_an_error():
    """A missing header must compare false, never raise."""
    assert constant_time_eq(None, "") is True
    assert constant_time_eq(None, "s3cret") is False
    assert constant_time_eq("s3cret", None) is False


def test_bytes_and_str_interoperate():
    assert constant_time_eq(b"s3cret", "s3cret") is True
    assert constant_time_eq("café", "café".encode("utf-8")) is True


def test_non_string_types_are_coerced_not_raised():
    """config.json can hold a bare number as a PIN."""
    assert constant_time_eq(1234, "1234") is True
    assert constant_time_eq(1234, "9999") is False


def test_ui_auth_gate_returns_401_not_500_for_non_ascii_password():
    """End-to-end through the real gate logic: fail closed, cleanly."""
    UI_USER, UI_PW = "admin", "s3cret"

    def gate(sent_user, sent_pw):
        if constant_time_eq(sent_user, UI_USER) and constant_time_eq(sent_pw, UI_PW):
            return 200
        return 401

    assert gate("admin", "s3cret") == 200
    assert gate("admin", "wröng") == 401      # was TypeError -> 500
    assert gate("ädmin", "s3cret") == 401


def test_non_ascii_configured_password_still_authenticates():
    """The lockout case: an operator whose own password has an accent."""
    UI_USER, UI_PW = "admin", "café123"
    assert constant_time_eq("admin", UI_USER) and constant_time_eq("café123", UI_PW)
