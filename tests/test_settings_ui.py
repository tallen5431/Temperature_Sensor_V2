"""The Settings page's automation and its collapsed-header summaries.

These are the parts that decide what an operator is *not* asked for — the SMTP
server behind their email address, the site name behind their hostname — and
what the page says a section is set to while it is folded shut. All pure, so
they are testable without a browser.
"""
import pytest

from components.settings_panel import (
    SETTINGS_SECTIONS,
    build_notifications_config,
    default_site_name,
    settings_badges,
    smtp_preset_for,
    webhook_service,
)


# --- SMTP auto-configuration -------------------------------------------------

@pytest.mark.parametrize("address,host,port,tls", [
    ("me@gmail.com", "smtp.gmail.com", 587, True),
    ("me@GMAIL.COM", "smtp.gmail.com", 587, True),      # case-insensitive
    ("  me@outlook.com  ", "smtp-mail.outlook.com", 587, True),
    ("me@icloud.com", "smtp.mail.me.com", 587, True),
    # Fastmail is SMTPS on 465, where send_email() uses SMTP_SSL and STARTTLS
    # must be off — getting this pair wrong is a connection that hangs, not an
    # error message, so the preset carries both.
    ("me@fastmail.com", "smtp.fastmail.com", 465, False),
])
def test_known_providers_are_filled_in_completely(address, host, port, tls):
    p = smtp_preset_for(address)
    assert (p["host"], p["port"], p["tls"]) == (host, port, tls)
    assert p["certain"] is True


def test_unknown_domain_is_a_labelled_guess_not_a_claim():
    """`smtp.<domain>` is right for most business mail and a fine starting
    point — but the UI has to be able to say so rather than assert it."""
    p = smtp_preset_for("ops@acme-foods.co.uk")
    assert p["host"] == "smtp.acme-foods.co.uk"
    assert (p["port"], p["tls"]) == (587, True)
    assert p["certain"] is False


def test_a_bare_domain_works_too():
    assert smtp_preset_for("gmail.com")["host"] == "smtp.gmail.com"


@pytest.mark.parametrize("junk", ["", None, "   ", "notanemail", "me@", "@gmail.com",
                                  "me@no dots", 12345])
def test_nothing_usable_returns_none(junk):
    assert smtp_preset_for(junk) is None


def test_providers_needing_an_app_password_say_so():
    """"Wrong password" from Gmail actually means "you used the wrong kind of
    password". Every provider that behaves this way carries the hint."""
    for address in ("me@gmail.com", "me@yahoo.com", "me@icloud.com", "me@fastmail.com"):
        assert "app" in smtp_preset_for(address)["hint"].lower(), address


# --- Webhook destination -----------------------------------------------------

@pytest.mark.parametrize("url,name", [
    ("https://hooks.slack.com/services/T/B/x", "Slack"),
    ("https://discord.com/api/webhooks/1/abc", "Discord"),
    ("https://acme.webhook.office.com/webhookb2/x", "Microsoft Teams"),
    ("https://hooks.zapier.com/hooks/catch/1/x", "Zapier"),
    ("https://ntfy.sh/my-freezers", "ntfy"),
])
def test_webhook_service_is_recognised(url, name):
    assert webhook_service(url) == name


@pytest.mark.parametrize("url", ["", None, "https://example.com/hook"])
def test_unrecognised_webhook_is_left_unlabelled(url):
    assert webhook_service(url) is None


# --- Site name default -------------------------------------------------------

def test_site_name_defaults_to_the_hostname(monkeypatch):
    monkeypatch.setattr("components.settings_panel.socket.gethostname",
                        lambda: "Atlanta_Hub.local")
    # Slugged to the wire protocol's charset, with the "-hub" that names the box
    # rather than the location trimmed off.
    assert default_site_name() == "atlanta"


def test_site_name_survives_a_hostname_it_cannot_use(monkeypatch):
    monkeypatch.setattr("components.settings_panel.socket.gethostname",
                        lambda: (_ for _ in ()).throw(OSError("no hostname")))
    assert default_site_name() == ""


# --- Blank From/To fall back to the account address --------------------------

def _form(**over):
    base = dict(enabled=True, cooldown_min=30, recovery=True, email_enabled=True,
                host="smtp.x", port=587, tls=True, user="me@example.com",
                sender="", to="", webhook_enabled=False, url="", password="")
    base.update(over)
    return [base[k] for k in ("enabled", "cooldown_min", "recovery", "email_enabled",
                              "host", "port", "tls", "user", "sender", "to",
                              "webhook_enabled", "url", "password")]


def test_blank_recipient_falls_back_to_the_account_address():
    """A blank `to` is not a neutral default: send_email() refuses to send
    without a recipient, so leaving it empty would produce an email channel that
    looks configured and never delivers."""
    email = build_notifications_config(*_form())["email"]
    assert email["to"] == "me@example.com"
    assert email["from"] == "me@example.com"


def test_explicit_from_and_to_still_win():
    email = build_notifications_config(
        *_form(sender="alerts@example.com", to="ops@example.com, boss@example.com")
    )["email"]
    assert email["from"] == "alerts@example.com"
    assert email["to"] == "ops@example.com, boss@example.com"


# --- Collapsed-header badges -------------------------------------------------

def test_badges_on_a_fresh_hub_are_all_quiet():
    b = settings_badges({})
    assert b["alerts"] == ("Off", "secondary")
    assert b["probes"] == ("Automatic", "secondary") or b["probes"][0] == "Automatic"
    assert b["data"][0] == "Keep forever"
    assert b["integrations"] == ("Off", "secondary")
    assert b["multisite"] == ("Single site", "secondary")


def test_alerts_badge_names_the_live_channels():
    cfg = {"notifications": {"enabled": True,
                             "email": {"enabled": True, "smtp_host": "smtp.x"},
                             "webhook": {"enabled": True, "url": "https://x"}}}
    assert settings_badges(cfg)["alerts"] == ("Email + Webhook", "success")


@pytest.mark.parametrize("notif,expected", [
    # On with nothing selected: the state where a breach notifies no one.
    ({"enabled": True}, "On · no channel"),
    # Enabled but never finished — the form was half filled and saved.
    ({"enabled": True, "email": {"enabled": True, "smtp_host": ""}}, "Email not finished"),
    ({"enabled": True, "webhook": {"enabled": True, "url": ""}}, "Webhook not finished"),
])
def test_a_half_configured_section_never_reads_as_finished(notif, expected):
    label, colour = settings_badges({"notifications": notif})["alerts"]
    assert (label, colour) == (expected, "warning")


def test_retention_and_multisite_badges_state_the_actual_value():
    b = settings_badges({"retention_days": 90,
                         "upstream": {"enabled": True, "url": "http://hq:8088",
                                      "site": "atlanta"}})
    assert b["data"] == ("Keep 90 days", "info")
    assert b["multisite"][0] == "Sending as “atlanta”"


def test_every_section_gets_a_badge_except_the_live_wifi_scan():
    """The badge callback fans one dict out across fixed Outputs, so a section
    added without a badge would raise a KeyError on the Settings page."""
    badges = settings_badges({})
    for key, *_ in SETTINGS_SECTIONS:
        if key == "setup":
            continue  # reports a live Wi-Fi scan, not a saved setting
        assert key in badges, key
