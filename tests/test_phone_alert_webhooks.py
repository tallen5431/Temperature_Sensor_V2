"""Webhook payloads for the services the Settings page says it recognises.

The hub sent every webhook the same body — Slack's ``text`` plus the event
fields — while Settings told the operator "Recognised ntfy / Pushover / Discord
— alerts will post there as messages". Three of those reject or mangle it: ntfy
showed the raw JSON as the notification text, Pushover answered 400 for the
missing ``token``/``user``/``message``, and Discord refused ``text`` as an empty
message. The test button would report the failure, but only if someone pressed
it; the first real freezer alarm would otherwise be the discovery.
"""
import pytest

from core import notifications
from core.notifications import _webhook_request, send_webhook
from components.settings_panel import webhook_service_note

ALARM = {"probe_id": "p1", "kind": "high", "temperature_c": 9.5,
         "subject": "⚠️ Walk-in: ABOVE 5.0°C", "message": "Walk-in is 9.5°C / 49.1°F."}
RECOVERY = {**ALARM, "kind": "recovery", "subject": "✅ Walk-in: back in range"}


class _Resp:
    ok = True
    status_code = 200


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def fake_post(url, timeout=None, **kwargs):
        calls.append((url, kwargs))
        return _Resp()
    monkeypatch.setattr(notifications.requests, "post", fake_post)
    return calls


# --- ntfy ---------------------------------------------------------------------

def test_ntfy_gets_its_json_publish_form_at_the_server_root():
    url, kw = _webhook_request("https://ntfy.sh/my-freezers", ALARM)
    assert url == "https://ntfy.sh/"
    body = kw["json"]
    # The topic moves into the body; a POST of JSON to /<topic> is shown verbatim.
    assert body["topic"] == "my-freezers"
    assert body["title"] == ALARM["subject"]          # UTF-8 safe: no header encoding
    assert body["message"] == ALARM["message"]
    assert body["priority"] == 4                       # an alarm should actually ring


def test_ntfy_good_news_does_not_ring_at_high_priority():
    _url, kw = _webhook_request("https://ntfy.sh/my-freezers", RECOVERY)
    assert kw["json"]["priority"] == 3


def test_self_hosted_ntfy_keeps_its_subpath_and_access_token():
    url, kw = _webhook_request(
        "https://ntfy.example.com/alerts/kitchen?auth=tk_secret", ALARM)
    assert url == "https://ntfy.example.com/alerts?auth=tk_secret"
    assert kw["json"]["topic"] == "kitchen"


# --- Pushover -----------------------------------------------------------------

def test_pushover_gets_a_form_built_from_the_keys_in_the_url():
    url, kw = _webhook_request(
        "https://api.pushover.net/1/messages.json?token=APP&user=USR", ALARM)
    assert url == "https://api.pushover.net/1/messages.json"   # keys not left in the URL
    form = kw["data"]
    assert (form["token"], form["user"]) == ("APP", "USR")
    assert form["message"] == ALARM["message"]
    assert form["priority"] == 1


def test_pushover_without_its_keys_fails_with_a_reason_instead_of_a_400(posted):
    ok, info = send_webhook({"url": "https://api.pushover.net/1/messages.json"}, ALARM)
    assert not ok and "token" in info
    assert posted == []                     # nothing sent that could only be rejected


# --- Discord ------------------------------------------------------------------

def test_discord_gets_content_not_text():
    url, kw = _webhook_request("https://discord.com/api/webhooks/1/abc", ALARM)
    assert url == "https://discord.com/api/webhooks/1/abc"
    assert set(kw["json"]) == {"content"}
    assert ALARM["subject"] in kw["json"]["content"]


def test_discord_content_respects_its_2000_character_limit():
    big = {**ALARM, "message": "x" * 5000}
    _url, kw = _webhook_request("https://discord.com/api/webhooks/1/abc", big)
    assert len(kw["json"]["content"]) == 2000


# --- everything else is unchanged ---------------------------------------------

@pytest.mark.parametrize("url", [
    "https://hooks.slack.com/services/T/B/x",
    "https://hooks.zapier.com/hooks/catch/1/x",
    "https://example.com/hook",
])
def test_generic_endpoints_keep_the_slack_compatible_body(url):
    post_url, kw = _webhook_request(url, ALARM)
    assert post_url == url
    assert kw["json"]["text"] == ALARM["message"]
    assert kw["json"]["probe_id"] == "p1"


def test_send_webhook_posts_the_shaped_request(posted):
    ok, _ = send_webhook({"url": "https://ntfy.sh/my-freezers"}, ALARM)
    assert ok
    assert posted == [("https://ntfy.sh/", {"json": _webhook_request(
        "https://ntfy.sh/my-freezers", ALARM)[1]["json"]})]


# --- what Settings promises ---------------------------------------------------

def test_settings_does_not_promise_pagerduty_will_work():
    text, cls = webhook_service_note("https://events.pagerduty.com/integration/x/enqueue")
    assert "Recognised" not in text and "text-warning" in cls


def test_settings_asks_for_the_pushover_keys_until_they_are_there():
    text, cls = webhook_service_note("https://api.pushover.net/1/messages.json")
    assert "token" in text and "text-warning" in cls
    text, cls = webhook_service_note(
        "https://api.pushover.net/1/messages.json?token=a&user=b")
    assert "text-info" in cls


def test_settings_says_ntfy_lands_on_the_phone():
    text, cls = webhook_service_note("https://ntfy.sh/my-freezers")
    assert "phone" in text and "text-info" in cls
