"""Settings page: notification channels, integrations and data management.

The page is a short INDEX, not a wall of forms.  Each area is a collapsed card
whose header carries a live status badge ("Off", "Email", "Keep forever"), so a
glance answers "what is switched on here?" and only the section someone came for
is ever expanded.  Inside a section the same rule applies again: the two or
three fields that matter are visible and everything an expert might tune sits
behind an "Advanced" toggle.

Fields the hub can work out for itself are not asked for at all — the SMTP
host/port/encryption are inferred from the email address, the From/To addresses
default to that same address, and a new site's name defaults to this machine's
hostname.  Every inferred value stays editable underneath "Advanced".

The form skeleton is static; a one-shot interval populates it from the live
config when the page opens.  Saving writes back through ``cfg.update`` so the
running alert monitor and notifier pick up changes without a restart.
"""
from __future__ import annotations

import socket

import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, dcc, no_update

from core.notifications import Notifier
from core.alerts import format_event
from core.forwarder import FORWARDER
from core.mqtt_publish import MQTT
from core.storage import sanitize_site
from components.setup_helper import SetupHelperBody, set_scanning


def _section_title(text):
    return html.H6(text, className="fw-bold mt-3 mb-2")


# --- Collapsible section shell ----------------------------------------------
# Every settings area is one of these. The header is a real <button> (dbc.Button
# renders one) so the section is reachable and toggleable from the keyboard, not
# just by mouse — a clickable <div> would look identical and be unusable without
# a pointer.

def _section(key, title, subtitle, body, is_open=False):
    """A settings card that collapses down to a single summary row.

    ``key`` names the section's ids (``sec-<key>-toggle`` / ``-collapse`` /
    ``-chevron`` / ``-badge``); ``subtitle`` is the one-line "what is this for"
    that lets someone skip the section without opening it, and the badge is
    filled at runtime with what the section is currently set to.
    """
    return dbc.Card([
        dbc.Button(
            [
                html.Span("▸", id=f"sec-{key}-chevron", className="settings-chevron"),
                html.Span([
                    html.Span(title, className="settings-title"),
                    html.Small(subtitle, className="text-muted d-block"),
                ], className="flex-grow-1"),
                dbc.Badge("—", id=f"sec-{key}-badge", color="secondary",
                          className="settings-badge"),
            ],
            id=f"sec-{key}-toggle", n_clicks=0, color="link",
            className="settings-head",
        ),
        dbc.Collapse(dbc.CardBody(body, className="settings-body"),
                     id=f"sec-{key}-collapse", is_open=is_open),
    ], className="mb-2 settings-card")


def _advanced(key, body, label="Advanced settings"):
    """A second level of the same idea: fields an expert may want, folded away.

    The children stay mounted (``dbc.Collapse`` hides rather than unmounts), so
    every ``State`` the Save callbacks read still resolves whether or not the
    operator ever opened this.
    """
    return html.Div([
        # The button is wrapped so it always starts its own line — a bare .btn is
        # inline-block and would otherwise tuck itself onto the end of whatever
        # help text precedes it.
        html.Div(dbc.Button(f"▸ {label}", id=f"{key}-advanced-toggle", color="link",
                            size="sm", className="p-0 advanced-toggle"),
                 className="mt-3"),
        dbc.Collapse(html.Div(body, className="advanced-body"),
                     id=f"{key}-advanced-collapse", is_open=False),
    ])


# --- SMTP auto-configuration -------------------------------------------------
# Typing an email address is something every operator can do unaided. The
# host/port/encryption behind it is the part that generates support tickets, and
# it is fully determined by the address's domain for the providers people
# actually use — so infer it and stop asking. (host, port, starttls, label, hint)
SMTP_PRESETS = {
    "gmail.com": ("smtp.gmail.com", 587, True, "Gmail",
                  "Gmail needs an App Password — Google Account → Security → "
                  "2-Step Verification → App passwords — not your normal password."),
    "googlemail.com": ("smtp.gmail.com", 587, True, "Gmail",
                       "Gmail needs an App Password, not your normal password."),
    "outlook.com": ("smtp-mail.outlook.com", 587, True, "Outlook", ""),
    "hotmail.com": ("smtp-mail.outlook.com", 587, True, "Outlook", ""),
    "live.com": ("smtp-mail.outlook.com", 587, True, "Outlook", ""),
    "msn.com": ("smtp-mail.outlook.com", 587, True, "Outlook", ""),
    "yahoo.com": ("smtp.mail.yahoo.com", 587, True, "Yahoo",
                  "Yahoo needs an app password generated in your account security settings."),
    "ymail.com": ("smtp.mail.yahoo.com", 587, True, "Yahoo",
                  "Yahoo needs an app password generated in your account security settings."),
    "aol.com": ("smtp.aol.com", 587, True, "AOL",
                "AOL needs an app password generated in your account security settings."),
    "icloud.com": ("smtp.mail.me.com", 587, True, "iCloud",
                   "iCloud needs an app-specific password from appleid.apple.com."),
    "me.com": ("smtp.mail.me.com", 587, True, "iCloud",
               "iCloud needs an app-specific password from appleid.apple.com."),
    "mac.com": ("smtp.mail.me.com", 587, True, "iCloud",
                "iCloud needs an app-specific password from appleid.apple.com."),
    "zoho.com": ("smtp.zoho.com", 587, True, "Zoho", ""),
    "fastmail.com": ("smtp.fastmail.com", 465, False, "Fastmail",
                     "Fastmail needs an app password created under Settings → Privacy & Security."),
    "fastmail.fm": ("smtp.fastmail.com", 465, False, "Fastmail",
                    "Fastmail needs an app password created under Settings → Privacy & Security."),
    "gmx.com": ("mail.gmx.com", 587, True, "GMX", ""),
    "gmx.net": ("mail.gmx.net", 587, True, "GMX", ""),
    "mail.com": ("smtp.mail.com", 587, True, "Mail.com", ""),
    "yandex.com": ("smtp.yandex.com", 587, True, "Yandex", ""),
    "yandex.ru": ("smtp.yandex.ru", 587, True, "Yandex", ""),
    "comcast.net": ("smtp.comcast.net", 587, True, "Comcast", ""),
    "cox.net": ("smtp.cox.net", 587, True, "Cox", ""),
    "verizon.net": ("smtp.verizon.net", 587, True, "Verizon", ""),
    "att.net": ("smtp.mail.att.net", 465, False, "AT&T", ""),
    "sbcglobal.net": ("smtp.mail.att.net", 465, False, "AT&T", ""),
    "bellsouth.net": ("smtp.mail.att.net", 465, False, "AT&T", ""),
    # Proton has no direct SMTP: mail goes through Proton Mail Bridge running on
    # this machine. Saying so is worth far more than leaving the fields blank —
    # "it just doesn't work" is otherwise the whole diagnosis.
    "protonmail.com": ("127.0.0.1", 1025, True, "Proton Mail",
                       "Proton needs Proton Mail Bridge running on this machine; "
                       "use the username and password Bridge shows you."),
    "proton.me": ("127.0.0.1", 1025, True, "Proton Mail",
                  "Proton needs Proton Mail Bridge running on this machine; "
                  "use the username and password Bridge shows you."),
    "pm.me": ("127.0.0.1", 1025, True, "Proton Mail",
              "Proton needs Proton Mail Bridge running on this machine; "
              "use the username and password Bridge shows you."),
}


def smtp_preset_for(address):
    """Best-known SMTP settings for the provider behind an email address.

    Returns ``{"host", "port", "tls", "label", "hint", "certain"}``, or ``None``
    when there is no domain to work from.  An unknown domain still returns a
    result — ``smtp.<domain>`` on 587 with STARTTLS is right for the large
    majority of business mail — but with ``certain=False`` so the UI can offer it
    as a starting point rather than state it as fact.  Pure and module-level so
    it can be unit-tested without a browser.
    """
    domain = str(address or "").strip().lower()
    if "@" in domain:
        local, _, domain = domain.rpartition("@")
        if not local.strip():
            return None  # "@gmail.com" — still mid-typing; don't commit a server yet
    domain = domain.strip().strip(".")
    if not domain or "." not in domain or " " in domain:
        return None
    preset = SMTP_PRESETS.get(domain)
    if preset:
        host, port, tls, label, hint = preset
        return {"host": host, "port": port, "tls": tls, "label": label,
                "hint": hint, "certain": True}
    return {"host": f"smtp.{domain}", "port": 587, "tls": True, "label": domain,
            "hint": "", "certain": False}


# Recognising the destination lets the card say what will show up at the other
# end instead of leaving the operator to find out by sending a test.
_WEBHOOK_SERVICES = [
    ("hooks.slack.com", "Slack"),
    ("discord.com/api/webhooks", "Discord"),
    ("discordapp.com/api/webhooks", "Discord"),
    ("webhook.office.com", "Microsoft Teams"),
    ("chat.googleapis.com", "Google Chat"),
    ("hooks.zapier.com", "Zapier"),
    ("maker.ifttt.com", "IFTTT"),
    ("events.pagerduty.com", "PagerDuty"),
    ("api.pushover.net", "Pushover"),
    ("ntfy.sh", "ntfy"),
]


def webhook_service(url):
    """Name the service a webhook URL points at, or ``None`` if unrecognised."""
    u = str(url or "").strip().lower()
    if not u:
        return None
    for needle, name in _WEBHOOK_SERVICES:
        if needle in u:
            return name
    return None


def default_site_name():
    """This machine's hostname, slugged — the obvious default for a site label.

    Someone setting up the Atlanta store is standing at a machine already called
    something like ``atlanta-hub``; asking them to invent a name is a question
    with an answer the hub already has.
    """
    try:
        host = socket.gethostname() or ""
    except Exception:  # noqa: BLE001 - a name is a nicety; never break Settings
        host = ""
    host = host.split(".")[0].strip().replace(" ", "-").replace("_", "-").lower()
    # Strip a trailing "-hub"/"-pi" so "atlanta-hub" reads as the site, not the box.
    for suffix in ("-hub", "-pi", "-server"):
        if host.endswith(suffix) and len(host) > len(suffix):
            host = host[: -len(suffix)]
    return sanitize_site(host)


def settings_badges(cfg):
    """One-line status per settings section, for the collapsed card headers.

    Keyed by section id (``alerts``, ``probes``, …) to ``(label, colour)``.  A
    collapsed page is only readable if these are honest: "On (no channel)" and
    "Enter an address" exist so a half-configured section can never sit there
    looking finished.  Pure so it can be unit-tested directly.
    """
    n = cfg.get("notifications", {}) or {}
    email = n.get("email", {}) or {}
    webhook = n.get("webhook", {}) or {}
    if not n.get("enabled"):
        alerts = ("Off", "secondary")
    else:
        channels = [name for name, on in (("Email", email.get("enabled")),
                                          ("Webhook", webhook.get("enabled"))) if on]
        if not channels:
            alerts = ("On · no channel", "warning")
        elif email.get("enabled") and not (email.get("smtp_host") or "").strip():
            alerts = ("Email not finished", "warning")
        elif webhook.get("enabled") and not (webhook.get("url") or "").strip():
            alerts = ("Webhook not finished", "warning")
        else:
            alerts = (" + ".join(channels), "success")

    probes = (("Automatic", "success") if cfg.get("auto_provision", True)
              else ("Manual", "secondary"))

    try:
        days = int(cfg.get("retention_days", 0) or 0)
    except (TypeError, ValueError):
        days = 0
    data = ("Keep forever", "secondary") if days <= 0 else \
        (f"Keep {days} day{'' if days == 1 else 's'}", "info")

    m = cfg.get("mqtt", {}) or {}
    if not m.get("enabled"):
        integrations = ("Off", "secondary")
    elif not (m.get("host") or "").strip():
        integrations = ("Broker not set", "warning")
    else:
        integrations = (f"MQTT → {m.get('host')}", "success")

    u = cfg.get("upstream", {}) or {}
    if not u.get("enabled"):
        multisite = ("Single site", "secondary")
    elif not (u.get("url") or "").strip():
        multisite = ("Address not set", "warning")
    else:
        multisite = (f"Sending as “{u.get('site') or '?'}”", "success")

    return {"alerts": alerts, "probes": probes, "data": data,
            "integrations": integrations, "multisite": multisite}


# --- Alerts ------------------------------------------------------------------
# Visible: the master switch, the two destinations, and "tell me if a probe goes
# quiet". Everything else — timing, damping, rate-of-rise — is tuning for a
# deployment that has been running a while, and lives under Advanced.
_ALERTS_BODY = [
    html.P("Get told when a probe goes out of range or stops reporting. "
           "The temperature limits themselves are set per probe on the Devices page.",
           className="text-muted small"),
    dcc.Link("Set each probe’s min/max limits on the Devices page →", href="/devices",
             className="small d-block mb-2"),

    dbc.Switch(id="notif-enabled", label="Enable alerts", value=False),
    html.Div(id="alert-config-note", className="mt-1"),

    # Everything below only takes effect while "Enable alerts" is on. When it's
    # off the whole block is dimmed and made non-interactive (see
    # _toggle_alert_config) so a user can't fill the form, see it fully lit, and
    # walk away believing alerts are configured when nothing will ever fire.
    html.Div(id="alert-config-body", children=[

        _section_title("Where to send them"),

        dbc.Switch(id="notif-email-enabled", label="Email", value=False),
        dbc.Collapse(dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Small("Your email address", className="text-muted"),
                    # debounce: the address drives SMTP auto-fill, which should
                    # run when the field is finished — not on every keystroke.
                    dbc.Input(id="email-user", placeholder="you@example.com",
                              debounce=True),
                ], md=6),
                dbc.Col([
                    html.Small("Password", className="text-muted"),
                    dbc.Input(id="email-pass", type="password", placeholder="(unchanged)"),
                    html.Small("Leave blank to keep the saved password.",
                               className="text-muted"),
                ], md=6),
            ], className="g-2"),
            html.Small(id="email-smtp-note", className="d-block mt-2"),
            dbc.Row([
                dbc.Col([
                    html.Small("Send alerts to", className="text-muted"),
                    dbc.Input(id="email-to",
                              placeholder="blank = your address above"),
                    html.Small("Several addresses? Separate them with commas.",
                               className="text-muted"),
                ], md=12),
            ], className="g-2 mt-1"),
            dbc.Row([
                dbc.Col([
                    dbc.Switch(id="daily-summary-enabled",
                               label="Also send a daily summary email", value=False,
                               className="mt-2"),
                    html.Small("One email a day with each probe's min/max/average.",
                               className="text-muted"),
                ], md=6),
                dbc.Col([
                    html.Small("Send at (hour, 0–23)", className="text-muted d-block"),
                    dbc.Input(id="daily-summary-hour", type="number", min=0, max=23,
                              step=1, value=8),
                ], md=6),
            ], className="g-2 mt-1"),

            # The three fields the address already answered. Kept, kept editable,
            # kept out of the way.
            _advanced("email-smtp", [
                html.Small("Filled in from your email address — change these only if "
                           "your provider uses a different server.",
                           className="text-muted d-block mb-2"),
                dbc.Row([
                    dbc.Col([html.Small("SMTP host", className="text-muted"),
                             dbc.Input(id="email-host", placeholder="smtp.example.com")], md=8),
                    dbc.Col([html.Small("Port", className="text-muted"),
                             dbc.Input(id="email-port", type="number", value=587)], md=4),
                ], className="g-2"),
                dbc.Switch(id="email-tls",
                           label="Use STARTTLS (encryption — leave on for most providers)",
                           value=True, className="mt-2"),
                dbc.Row([
                    dbc.Col([html.Small("From address", className="text-muted"),
                             dbc.Input(id="email-from",
                                       placeholder="blank = your address above")], md=12),
                ], className="g-2 mt-1"),
            ], label="Server settings"),
        ]), className="mt-2 mb-1"), id="email-collapse", is_open=False),

        dbc.Switch(id="notif-webhook-enabled", label="Webhook", value=False,
                   className="mt-2"),
        dbc.Collapse(dbc.Card(dbc.CardBody([
            html.Small("Posts JSON (with a Slack-compatible \"text\" field) to this URL.",
                       className="text-muted d-block"),
            dbc.Input(id="webhook-url", placeholder="https://hooks.slack.com/services/...",
                      className="mt-1", debounce=True),
            html.Small(id="webhook-service-note", className="d-block mt-1"),
        ]), className="mt-2 mb-1"), id="webhook-collapse", is_open=False),

        _section_title("When to send them"),
        dbc.Switch(id="notif-offline-enabled",
                   label="Alert when a probe stops reporting", value=True),
        html.Small("Out-of-range alerts are always on while alerts are enabled.",
                   className="text-muted d-block mt-1"),

        _advanced("alerts", [
            html.Small("Sensible defaults are already applied — these are for tuning a "
                       "deployment that is alerting too often, or not soon enough.",
                       className="text-muted d-block mb-2"),
            dbc.Row([
                dbc.Col([
                    html.Small("Re-alert every (minutes)", className="text-muted d-block"),
                    dbc.Input(id="notif-cooldown-min", type="number", min=1, step=1, value=30),
                    html.Small("How often to remind you while a probe stays out of range.",
                               className="text-muted"),
                ], md=6),
                dbc.Col([
                    dbc.Switch(id="notif-recovery",
                               label="Notify when a probe returns to normal",
                               value=True, className="mt-4"),
                ], md=6),
            ], className="g-2"),
            dbc.Row([
                dbc.Col([
                    html.Small("Deadband (°C)", className="text-muted d-block"),
                    dbc.Input(id="notif-hysteresis", type="number", min=0, step=0.1, value=0.5),
                    html.Small("How far a probe must move back inside its limit before the "
                               "alert clears — stops a probe sitting on the line from "
                               "flapping.", className="text-muted"),
                ], md=6),
                dbc.Col([
                    html.Small("Offline after (minutes)", className="text-muted d-block"),
                    dbc.Input(id="offline-after-min", type="number", min=1, step=1, value=5),
                    html.Small("Flag a probe that stops reporting for this long. Probes on a "
                               "slower cadence get proportionally longer automatically.",
                               className="text-muted"),
                ], md=6),
            ], className="g-2 mt-1"),
            dbc.Row([
                dbc.Col([
                    html.Small("Confirm back-online after (minutes)",
                               className="text-muted d-block"),
                    dbc.Input(id="notif-flap-grace-min", type="number", min=0, step=1,
                              placeholder="auto"),
                    html.Small("Hold the “back online” alert until a probe has reported "
                               "steadily for this long — stops a spotty link (e.g. weak "
                               "freezer Wi-Fi) from flapping offline/online. Blank = auto "
                               "(match the offline window); 0 = off.",
                               className="text-muted"),
                ], md=6),
            ], className="g-2 mt-1"),
            dbc.Row([
                dbc.Col([
                    html.Small("Rate alert (°C rise)", className="text-muted d-block"),
                    dbc.Input(id="notif-rate-alert", type="number", min=0, step=0.5, value=0),
                    html.Small("0 = off — catches a failing freezer early.",
                               className="text-muted"),
                ], md=6),
                dbc.Col([
                    html.Small("within (minutes)", className="text-muted d-block"),
                    dbc.Input(id="notif-rate-window", type="number", min=1, step=1, value=10),
                    html.Small("Alert when a probe rises this many degrees inside the window.",
                               className="text-muted"),
                ], md=6),
            ], className="g-2 mt-1"),
        ]),
    ]),

    html.Div([
        dbc.Button("Save", id="notif-save", color="primary", className="mt-3 me-2"),
        dbc.Button("Send test", id="notif-test", color="secondary", outline=True,
                   className="mt-3"),
        html.Small("Save first, then send a test to the channels above.",
                   className="text-muted d-block mt-1"),
    ]),
    html.Div(id="notif-status", className="mt-2"),
]


_DATA_BODY = [
    dbc.Row([
        dbc.Col([
            html.Small("Keep readings for", className="text-muted d-block"),
            dbc.InputGroup([
                dbc.Input(id="retention-days", type="number", min=0, step=1, value=0),
                dbc.InputGroupText("days"),
            ]),
            html.Small(id="retention-note", className="text-muted"),
        ], md=6),
        dbc.Col([
            html.Small("Backup", className="text-muted d-block"),
            dbc.Button("⬇ Download database backup", id="backup-btn", color="secondary",
                       outline=True, href="/download/backup.db", external_link=True),
            html.Small("Downloads the full readings database as a file.",
                       className="text-muted d-block mt-1"),
        ], md=6, className="d-flex flex-column justify-content-center"),
    ], className="g-3"),
    dbc.Button("Save", id="data-save", color="primary", className="mt-3"),
    html.Div(id="data-status", className="mt-2"),
]


_INTEGRATIONS_BODY = [
    html.P("Publish every reading to an MQTT broker with Home Assistant "
           "auto-discovery — each probe appears there as a sensor automatically.",
           className="text-muted small"),

    dbc.Switch(id="mqtt-enabled", label="Publish to MQTT (Home Assistant)", value=False),
    dbc.Collapse(dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col([html.Small("Broker host", className="text-muted"),
                     dbc.Input(id="mqtt-host", placeholder="homeassistant.local")], md=8),
            dbc.Col([html.Small("Port", className="text-muted"),
                     dbc.Input(id="mqtt-port", type="number", value=1883)], md=4),
        ], className="g-2"),
        dbc.Row([
            dbc.Col([html.Small("Username", className="text-muted"),
                     dbc.Input(id="mqtt-user", placeholder="(optional)")], md=6),
            dbc.Col([html.Small("Password", className="text-muted"),
                     dbc.Input(id="mqtt-pass", type="password", placeholder="(unchanged)"),
                     html.Small("Leave blank to keep the saved password.",
                                className="text-muted")], md=6),
        ], className="g-2 mt-1"),
        _advanced("mqtt", [
            dbc.Row([
                dbc.Col([html.Small("Base topic", className="text-muted"),
                         dbc.Input(id="mqtt-base-topic", placeholder="setpoint")], md=6),
                dbc.Col([dbc.Switch(id="mqtt-discovery",
                                    label="Home Assistant auto-discovery",
                                    value=True, className="mt-4")], md=6),
            ], className="g-2"),
        ], label="Topic settings"),
    ]), className="mt-2 mb-1"), id="mqtt-collapse", is_open=False),

    dbc.Button("Save", id="mqtt-save", color="primary", className="mt-3"),
    html.Div(id="mqtt-status", className="mt-2"),
]


_PROBES_BODY = [
    dbc.Switch(id="auto-provision-enabled",
               label="Automatically configure probes found on this network",
               value=True),
    html.Small(
        "On by default: the hub finds probes over the network and points them at "
        "itself, so a new probe just works. Turn it off if you configure probes by "
        "hand, or on a head-office hub that only receives forwarded readings — two "
        "hubs on one network with this on will take turns claiming the same probes.",
        className="text-muted d-block mt-1"),
    dbc.Button("Save", id="auto-provision-save", color="primary", className="mt-3"),
    html.Div(id="auto-provision-status", className="mt-2"),
]


_MULTISITE_BODY = [
    html.P("Running more than one location? Each site keeps its own hub, its own "
           "database and its own alerts — nothing changes there. A site can also "
           "send a copy of its readings to a hub at head office, so one dashboard "
           "covers them all.",
           className="text-muted small"),

    # Everything below the switch is hidden until it is on, so a single-site
    # customer — nearly everyone — sees one line they can ignore.
    dbc.Switch(id="upstream-enabled",
               label="Send a copy of my readings to head office", value=False),
    dbc.Collapse(dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col([
                html.Small("Head office hub address", className="text-muted"),
                dbc.Input(id="upstream-url", placeholder="http://192.168.1.50:8088"),
                html.Small("Shown on the head-office hub's Diagnostics page.",
                           className="text-muted"),
            ], md=7),
            dbc.Col([
                html.Small("This site's name", className="text-muted"),
                dbc.Input(id="upstream-site", placeholder="atlanta"),
                html.Small("Pre-filled from this machine's name — change it if head "
                           "office knows this location as something else.",
                           className="text-muted"),
            ], md=5),
        ], className="g-2"),
        dbc.Row([
            dbc.Col([
                html.Small("Head office token", className="text-muted"),
                dbc.Input(id="upstream-token", type="password", placeholder="(unchanged)"),
                html.Small("Head office's device token — not this hub's. "
                           "Leave blank to keep the saved one.",
                           className="text-muted"),
            ], md=7),
            dbc.Col([
                html.Small("Send every (seconds)", className="text-muted d-block"),
                dbc.Input(id="upstream-interval", type="number", min=5, step=5, value=30),
            ], md=5),
        ], className="g-2 mt-1"),
    ]), className="mt-2 mb-1"), id="upstream-collapse", is_open=False),

    dbc.Button("Save", id="upstream-save", color="primary", className="mt-3"),
    html.Div(id="upstream-status", className="mt-2"),

    # --- The other half: what a store needs in order to point HERE ----------
    html.Hr(className="mt-4"),
    dbc.Button("Head office: show what my sites need ▾", id="upstream-hq-toggle",
               color="link", size="sm", className="p-0"),
    dbc.Collapse(html.Div(id="upstream-hq-body", className="mt-2"),
                 id="upstream-hq-collapse", is_open=False),
]


# Ordered most- to least-commonly needed. Everything starts collapsed: the page
# opens as a six-line index of what this hub is doing, not six forms at once.
SETTINGS_SECTIONS = [
    ("alerts", "Alerts & notifications",
     "Email or a webhook when a probe goes out of range or stops reporting.",
     _ALERTS_BODY),
    ("probes", "Probes",
     "How the hub finds and configures probes on your network.", _PROBES_BODY),
    ("setup", "Set up a new probe",
     "Find a brand-new probe's temporary Wi-Fi network and point it at yours.",
     SetupHelperBody),
    ("data", "Data & storage",
     "How long readings are kept, and a one-click database backup.", _DATA_BODY),
    ("integrations", "Integrations",
     "Publish readings to Home Assistant or any MQTT broker.", _INTEGRATIONS_BODY),
    ("multisite", "Multi-site",
     "Roll several locations up into one head-office dashboard.", _MULTISITE_BODY),
]

# Sections whose badge is derived from config by settings_badges(); "setup" is
# excluded because its badge reports a live Wi-Fi scan, not a saved setting.
_CONFIG_BADGE_KEYS = [k for k, *_ in SETTINGS_SECTIONS if k != "setup"]

# Sub-sections using the _advanced() shell, for the toggle callbacks below.
_ADVANCED_KEYS = ["alerts", "email-smtp", "mqtt"]


SettingsPanel = html.Div(
    [_section(key, title, subtitle, body)
     for key, title, subtitle, body in SETTINGS_SECTIONS]
    # Fires once when the page opens to load current values from config.
    + [dcc.Interval(id="settings-loaded", interval=300, n_intervals=0, max_intervals=1)],
)


def _ok(msg):
    return dbc.Alert(msg, color="success", dismissable=True, className="mb-0")


def _err(msg):
    return dbc.Alert(msg, color="danger", dismissable=True, className="mb-0")


def build_notifications_config(enabled, cooldown_min, recovery, email_enabled, host, port,
                               tls, user, sender, to, webhook_enabled, url, password,
                               offline_alerts=True, existing_password="",
                               daily_summary_enabled=False, daily_summary_hour=8,
                               flap_grace_min=None):
    """Turn raw Settings form values into a notifications config dict.

    Pure and module-level so it can be unit-tested.  A blank password means
    "keep the stored one"; cooldown is taken in minutes and stored as seconds.
    ``flap_grace_min`` blank/None omits the key (auto flap damping); a number is
    stored as ``flap_grace_sec`` (0 disables damping).

    A blank ``sender``/``to`` falls back to the account address.  Both fields ask
    for something the operator has already typed one line above, and a blank
    ``to`` is not a neutral default — ``send_email`` refuses to send without a
    recipient, so it would silently turn a configured-looking email channel into
    one that never delivers.
    """
    try:
        cooldown_sec = max(60, int(float(cooldown_min)) * 60)
    except (TypeError, ValueError):
        cooldown_sec = 1800
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 587
    try:
        summary_hour = min(23, max(0, int(float(daily_summary_hour))))
    except (TypeError, ValueError):
        summary_hour = 8
    account = (user or "").strip()
    conf = {
        "enabled": bool(enabled),
        "cooldown_sec": cooldown_sec,
        "notify_recovery": bool(recovery),
        "offline_alerts": bool(offline_alerts),
        "email": {
            "enabled": bool(email_enabled),
            "smtp_host": (host or "").strip(),
            "smtp_port": port,
            "use_tls": bool(tls),
            "username": account,
            "password": password if password else existing_password,
            "from": (sender or "").strip() or account,
            "to": (to or "").strip() or account,
        },
        "webhook": {"enabled": bool(webhook_enabled), "url": (url or "").strip()},
        "daily_summary": {"enabled": bool(daily_summary_enabled), "hour": summary_hour},
    }
    # Blank -> omit the key entirely so the monitor's "auto" default applies; a
    # number (including 0, which disables damping) is stored as seconds.
    if flap_grace_min is not None and str(flap_grace_min).strip() != "":
        try:
            conf["flap_grace_sec"] = max(0, int(float(flap_grace_min)) * 60)
        except (TypeError, ValueError):
            pass
    return conf


def build_upstream_config(enabled, url, site, token, interval, existing=None):
    """Turn the Multi-site form values into the ``upstream`` config block.

    Pure and module-level so it can be unit-tested. A blank token keeps the saved
    one (same rule as the MQTT/SMTP passwords), and keys the form does not expose
    — ``batch`` — are carried over untouched.

    ``site`` is sanitised to the same charset the wire protocol accepts rather
    than rejected, so "Atlanta Store #2" becomes a usable label instead of an
    error the operator has to decode.
    """
    out = dict(existing or {})
    try:
        interval = max(5, int(interval))
    except (TypeError, ValueError):
        interval = 30
    out.update({
        "enabled": bool(enabled),
        "url": (url or "").strip().rstrip("/"),
        "site": sanitize_site((site or "").strip().replace(" ", "-").lower()),
        "token": token if token else out.get("token", ""),
        "interval_sec": interval,
    })
    return out


def build_mqtt_config(enabled, host, port, username, password, base_topic, discovery,
                      existing=None):
    """Turn raw Integrations form values into the ``mqtt`` config block.

    Pure and module-level so it can be unit-tested.  A blank password keeps the
    saved one, and keys the form does not expose (e.g. ``discovery_prefix``)
    are carried over from the existing block untouched.
    """
    out = dict(existing or {})
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 1883
    out.update({
        "enabled": bool(enabled),
        "host": (host or "").strip(),
        "port": port,
        "username": (username or "").strip(),
        "password": password if password else out.get("password", ""),
        "base_topic": (base_topic or "").strip() or "setpoint",
        "discovery_enabled": bool(discovery),
    })
    return out


def register_settings_callbacks(app, cfg, public_base_func=None):
    # --- Collapsible sections -------------------------------------------------
    # One pair of identical toggles per section/advanced block. The callback body
    # closes over nothing, so defining them in a loop is safe.
    for _key in [k for k, *_ in SETTINGS_SECTIONS]:
        @app.callback(
            Output(f"sec-{_key}-collapse", "is_open"),
            Output(f"sec-{_key}-chevron", "children"),
            Input(f"sec-{_key}-toggle", "n_clicks"),
            State(f"sec-{_key}-collapse", "is_open"),
            prevent_initial_call=True,
        )
        def _toggle_section(_n, is_open):
            return (not is_open), ("▾" if not is_open else "▸")

    for _key in _ADVANCED_KEYS:
        @app.callback(
            Output(f"{_key}-advanced-collapse", "is_open"),
            Output(f"{_key}-advanced-toggle", "children"),
            Input(f"{_key}-advanced-toggle", "n_clicks"),
            State(f"{_key}-advanced-collapse", "is_open"),
            State(f"{_key}-advanced-toggle", "children"),
            prevent_initial_call=True,
        )
        def _toggle_advanced(_n, is_open, label):
            text = str(label or "").lstrip("▸▾ ").strip()
            return (not is_open), f"{'▾' if not is_open else '▸'} {text}"

    # Header badges: what each collapsed section is currently set to. Driven by
    # the load interval plus every Save result, so a badge is never stale — and
    # never polled, because config only changes when someone saves.
    @app.callback(
        [Output(f"sec-{k}-badge", "children") for k in _CONFIG_BADGE_KEYS]
        + [Output(f"sec-{k}-badge", "color") for k in _CONFIG_BADGE_KEYS],
        Input("settings-loaded", "n_intervals"),
        Input("notif-status", "children"),
        Input("data-status", "children"),
        Input("mqtt-status", "children"),
        Input("auto-provision-status", "children"),
        Input("upstream-status", "children"),
    )
    def _section_badges(*_):
        badges = settings_badges(cfg)
        labels = [badges[k][0] for k in _CONFIG_BADGE_KEYS]
        colors = [badges[k][1] for k in _CONFIG_BADGE_KEYS]
        return labels + colors

    # The Wi-Fi scan behind "Set up a new probe" only runs while that section is
    # open. It shells out to netsh/nmcli every few seconds, and opening Settings
    # to change a retention day is not consent to scan the airwaves.
    @app.callback(
        Output("ap-poll", "disabled"),
        Input("sec-setup-collapse", "is_open"),
    )
    def _gate_ap_scan(is_open):
        # Both halves matter. Disabling the interval stops the UI polling;
        # set_scanning stops the watcher THREAD, which otherwise keeps shelling
        # out to netsh/nmcli every few seconds for the rest of the process's life
        # once the section has been opened once.
        set_scanning(bool(is_open))
        return not bool(is_open)

    @app.callback(
        Output("sec-setup-badge", "children"),
        Output("sec-setup-badge", "color"),
        Input("sec-setup-collapse", "is_open"),
        Input("ap-seen-label", "children"),
    )
    def _setup_badge(is_open, seen):
        if not is_open:
            return "Not searching", "secondary"
        if str(seen or "").startswith("Found"):
            return "Probe found", "success"
        return "Searching…", "info"

    @app.callback(
        Output("notif-enabled", "value"),
        Output("notif-cooldown-min", "value"),
        Output("notif-recovery", "value"),
        Output("notif-email-enabled", "value"),
        Output("email-host", "value"),
        Output("email-port", "value"),
        Output("email-tls", "value"),
        Output("email-user", "value"),
        Output("email-from", "value"),
        Output("email-to", "value"),
        Output("notif-webhook-enabled", "value"),
        Output("webhook-url", "value"),
        Output("retention-days", "value"),
        Output("notif-offline-enabled", "value"),
        Output("offline-after-min", "value"),
        Output("notif-rate-alert", "value"),
        Output("notif-rate-window", "value"),
        Output("daily-summary-enabled", "value"),
        Output("daily-summary-hour", "value"),
        Output("notif-flap-grace-min", "value"),
        Input("settings-loaded", "n_intervals"),
    )
    def _load(_n):
        n = cfg.get("notifications", {}) or {}
        email = n.get("email", {}) or {}
        webhook = n.get("webhook", {}) or {}
        summary = n.get("daily_summary", {}) or {}
        try:
            rate_alert = max(0.0, float(cfg.get("rate_alert_c", 0.0) or 0.0))
        except (TypeError, ValueError):
            rate_alert = 0.0
        try:
            rate_window = max(1, int(cfg.get("rate_window_min", 10) or 10))
        except (TypeError, ValueError):
            rate_window = 10
        try:
            summary_hour = min(23, max(0, int(summary.get("hour", 8))))
        except (TypeError, ValueError):
            summary_hour = 8
        fg = n.get("flap_grace_sec")
        try:
            flap_grace_min = None if fg is None else max(0, int(fg) // 60)
        except (TypeError, ValueError):
            flap_grace_min = None
        # From/To echo back blank when they merely mirror the account address, so
        # the fields keep showing their "blank = your address above" placeholder
        # instead of three copies of the same string.
        account = (email.get("username", "") or "").strip()
        sender = email.get("from", "") or ""
        recipients = email.get("to", "") or ""
        return (
            bool(n.get("enabled", False)),
            int(n.get("cooldown_sec", 1800) or 1800) // 60,
            bool(n.get("notify_recovery", True)),
            bool(email.get("enabled", False)),
            email.get("smtp_host", ""),
            int(email.get("smtp_port", 587) or 587),
            bool(email.get("use_tls", True)),
            account,
            "" if sender.strip() == account else sender,
            "" if recipients.strip() == account else recipients,
            bool(webhook.get("enabled", False)),
            webhook.get("url", ""),
            int(cfg.get("retention_days", 0) or 0),
            bool(n.get("offline_alerts", True)),
            max(1, int(cfg.get("offline_after_sec", 300) or 300) // 60),
            rate_alert,
            rate_window,
            bool(summary.get("enabled", False)),
            summary_hour,
            flap_grace_min,
        )

    @app.callback(
        Output("notif-hysteresis", "value"),
        Input("settings-loaded", "n_intervals"),
    )
    def _load_hysteresis(_n):
        try:
            return float(cfg.get("alert_hysteresis_c", 0.5))
        except (TypeError, ValueError):
            return 0.5

    # Progressive disclosure: only show a channel's fields once it's enabled.
    @app.callback(
        Output("email-collapse", "is_open"),
        Input("notif-email-enabled", "value"),
    )
    def _toggle_email(enabled):
        return bool(enabled)

    @app.callback(
        Output("webhook-collapse", "is_open"),
        Input("notif-webhook-enabled", "value"),
    )
    def _toggle_webhook(enabled):
        return bool(enabled)

    # Fill the SMTP server fields in from the address. Only ever writes into a
    # host field the operator has not filled themselves — re-typing the address
    # must never silently overwrite a hand-entered corporate relay.
    @app.callback(
        Output("email-host", "value", allow_duplicate=True),
        Output("email-port", "value", allow_duplicate=True),
        Output("email-tls", "value", allow_duplicate=True),
        Output("email-smtp-note", "children"),
        Output("email-smtp-note", "className"),
        Input("email-user", "value"),
        State("email-host", "value"),
        prevent_initial_call=True,
    )
    def _autofill_smtp(address, current_host):
        preset = smtp_preset_for(address)
        if preset is None:
            return no_update, no_update, no_update, "", "d-block mt-2"
        # An app-password rule is the single most common reason a correct-looking
        # email setup never delivers, so it is the one thing here worth amber.
        cls = "d-block mt-2 " + ("text-warning" if preset["hint"] else "text-muted")
        if (current_host or "").strip():
            # Already set. Say nothing about the server; still surface the
            # provider's app-password rule.
            note = preset["hint"] if preset["certain"] else ""
            return no_update, no_update, no_update, note, cls
        if preset["certain"]:
            lead = f"Recognised {preset['label']} — using {preset['host']}:{preset['port']}. "
        else:
            lead = (f"No preset for {preset['label']} — trying {preset['host']}:"
                    f"{preset['port']}. Change it under “Server settings” if your "
                    "provider uses a different one. ")
        return (preset["host"], preset["port"], preset["tls"],
                lead + (preset["hint"] or ""), cls)

    @app.callback(
        Output("webhook-service-note", "children"),
        Output("webhook-service-note", "className"),
        Input("webhook-url", "value"),
    )
    def _webhook_note(url):
        name = webhook_service(url)
        if not name:
            return "", "d-block mt-1"
        return f"Recognised {name} — alerts will post there as messages.", \
            "d-block mt-1 text-info"

    # --- Integrations (MQTT) --------------------------------------------------
    @app.callback(
        Output("mqtt-enabled", "value"),
        Output("mqtt-host", "value"),
        Output("mqtt-port", "value"),
        Output("mqtt-user", "value"),
        Output("mqtt-base-topic", "value"),
        Output("mqtt-discovery", "value"),
        Input("settings-loaded", "n_intervals"),
    )
    def _load_mqtt(_n):
        m = cfg.get("mqtt", {}) or {}
        return (
            bool(m.get("enabled", False)),
            m.get("host", ""),
            int(m.get("port", 1883) or 1883),
            m.get("username", ""),
            m.get("base_topic", "setpoint"),
            bool(m.get("discovery_enabled", True)),
        )

    @app.callback(
        Output("mqtt-collapse", "is_open"),
        Input("mqtt-enabled", "value"),
    )
    def _toggle_mqtt(enabled):
        return bool(enabled)

    # --- Probes (auto-provisioning) -------------------------------------------
    @app.callback(
        Output("auto-provision-enabled", "value"),
        Input("settings-loaded", "n_intervals"),
    )
    def _load_auto_provision(_n):
        return bool(cfg.get("auto_provision", True))

    @app.callback(
        Output("auto-provision-status", "children"),
        Input("auto-provision-save", "n_clicks"),
        State("auto-provision-enabled", "value"),
        prevent_initial_call=True,
    )
    def _save_auto_provision(_n, enabled):
        try:
            cfg.update({"auto_provision": bool(enabled)})
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}")
        # Takes effect on the provisioner's next cycle (~10 s) — no restart.
        if enabled:
            return _ok("Saved — the hub will configure probes it finds on this network.")
        return _ok("Saved — the hub will stop claiming probes within about 10 seconds. "
                   "Probes already pointed here keep reporting to it.")

    # --- Multi-site (upstream roll-up) ---------------------------------------
    @app.callback(
        Output("upstream-enabled", "value"),
        Output("upstream-url", "value"),
        Output("upstream-site", "value"),
        Output("upstream-interval", "value"),
        Input("settings-loaded", "n_intervals"),
    )
    def _load_upstream(_n):
        u = cfg.get("upstream", {}) or {}
        try:
            interval = max(5, int(u.get("interval_sec", 30) or 30))
        except (TypeError, ValueError):
            interval = 30
        # An unnamed site pre-fills from this machine's hostname. Head office
        # needs the label to tell locations apart, so an empty box here is a
        # question the hub can already answer for itself.
        site = (u.get("site") or "").strip() or default_site_name()
        return (bool(u.get("enabled", False)), u.get("url", ""), site, interval)

    @app.callback(
        Output("upstream-collapse", "is_open"),
        Input("upstream-enabled", "value"),
    )
    def _toggle_upstream(enabled):
        return bool(enabled)

    @app.callback(
        Output("upstream-hq-collapse", "is_open"),
        Output("upstream-hq-body", "children"),
        Input("upstream-hq-toggle", "n_clicks"),
        State("upstream-hq-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def _toggle_hq_help(_n, is_open):
        """The other half of setup: what to type into each site's hub.

        Kept behind a click because it reveals this hub's device token, and
        because it is irrelevant to the store-side operator reading the card
        above it. Built on open so the address and token are always current.
        """
        if is_open:
            return False, None
        base = public_base_func() if public_base_func else ""
        token = str(cfg.get("provision_token", "") or "")
        return True, html.Div([
            html.P("At each of your sites, open that hub's Settings → Multi-site, "
                   "turn on “Send a copy of my readings to head office”, and enter:",
                   className="small mb-2"),
            dbc.Table([html.Tbody([
                html.Tr([html.Td("Head office hub address", className="text-muted small"),
                         html.Td([
                             html.Code(base or "(unknown)"),
                             # This address is auto-detected from the default
                             # route, so on a hub reached over a VPN it is the
                             # physical NIC's address — correct for the same LAN,
                             # useless to a store on another network, and wrong in
                             # a way that looks right. Name the fix here, because
                             # this table is exactly where someone copies it from.
                             html.Small(
                                 "Detected from this machine's network. If your "
                                 "sites are on other networks, they need an address "
                                 "that reaches this hub — a VPN address such as "
                                 "Tailscale's. Set PUBLIC_BASE to it and restart, "
                                 "and this line will show the right one.",
                                 className="text-muted d-block mt-1"),
                         ])]),
                html.Tr([html.Td("Head office token", className="text-muted small"),
                         html.Td(html.Code(token or "(none set)"))]),
                html.Tr([html.Td("This site's name", className="text-muted small"),
                         html.Td(html.Span("a different label per site — atlanta, marietta, …",
                                           className="small"))]),
            ])], bordered=False, size="sm", className="mb-2"),
            dbc.Alert(
                [html.Strong("Treat the token like a password. "),
                 "Anyone who has it can post readings to this hub. The address above "
                 "must be reachable from each site — same network, or a VPN such as "
                 "Tailscale. Do not port-forward it to the open internet."],
                color="warning", className="small mb-0"),
        ])

    @app.callback(
        Output("upstream-status", "children"),
        # Echo the stored label back into the field. The wire protocol accepts
        # [A-Za-z0-9_-] only, so "Atlanta Store #2" is saved as "atlanta-store-2"
        # — and a form still showing the typed text while the dashboard shows the
        # slug is how someone concludes their site name "didn't save".
        Output("upstream-site", "value", allow_duplicate=True),
        Input("upstream-save", "n_clicks"),
        State("upstream-enabled", "value"),
        State("upstream-url", "value"),
        State("upstream-site", "value"),
        State("upstream-token", "value"),
        State("upstream-interval", "value"),
        prevent_initial_call=True,
    )
    def _save_upstream(_n, enabled, url, site, token, interval):
        try:
            block = build_upstream_config(enabled, url, site, token, interval,
                                          existing=cfg.get("upstream", {}) or {})
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}"), no_update

        # Validate before writing: a half-configured block is the one state the
        # forwarder refuses to run in, and silently saving it is how someone ends
        # up believing their freezer data is reaching head office when it is not.
        if block["enabled"]:
            if not block["url"]:
                return _err("Enter the head office hub address, or switch forwarding off."), no_update
            if not block["url"].startswith(("http://", "https://")):
                return _err("The address needs to start with http:// or https://."), no_update
            if not block["site"]:
                return _err("Give this site a name — head office uses it to tell your "
                            "locations apart, and readings sent without one could never "
                            "be separated later."), no_update
            if not block["token"]:
                return _err("Enter head office's device token."), no_update

        try:
            cfg.update({"upstream": block})
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}"), no_update

        if not block["enabled"]:
            return _ok("Saved — this hub is not sending readings anywhere."), block["site"]

        # Report what actually happened, not that a file was written. A saved
        # setting that cannot reach head office must never look like a working one.
        sent, err = FORWARDER.sync_now()
        if err:
            return (dbc.Alert(f"Saved, but nothing has reached head office yet. {err}",
                              color="warning", dismissable=True, className="mb-0"),
                    block["site"])
        pending = FORWARDER.status()["pending"]
        if sent:
            tail = f" {pending:,} still to send." if pending else " Everything is up to date."
            return _ok(f"Saved — sent {sent:,} reading{'s' if sent != 1 else ''} "
                       f"to head office as “{block['site']}”.{tail}"), block["site"]
        return _ok(f"Saved — connected to head office as “{block['site']}”. "
                   "New readings will be sent as they arrive."), block["site"]

    @app.callback(
        Output("mqtt-status", "children"),
        Input("mqtt-save", "n_clicks"),
        State("mqtt-enabled", "value"),
        State("mqtt-host", "value"),
        State("mqtt-port", "value"),
        State("mqtt-user", "value"),
        State("mqtt-pass", "value"),
        State("mqtt-base-topic", "value"),
        State("mqtt-discovery", "value"),
        prevent_initial_call=True,
    )
    def _save_mqtt(_n, enabled, host, port, user, password, base_topic, discovery):
        try:
            existing = cfg.get("mqtt", {}) or {}
            cfg.update({"mqtt": build_mqtt_config(
                enabled, host, port, user, password, base_topic, discovery,
                existing=existing)})
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}")
        # Restart the publisher so the new settings take effect without a hub
        # restart, then report the LIVE connection state — a saved-but-
        # unreachable broker must not look like a working integration.
        try:
            MQTT.stop()
            MQTT.start(cfg)
        except Exception as e:  # noqa: BLE001
            return _err(f"Saved, but restarting the MQTT publisher failed: {e}")
        if not enabled:
            return _ok("MQTT settings saved — publishing is off.")
        if MQTT.is_ready():
            return _ok("MQTT settings saved — connected to the broker and publishing.")
        return dbc.Alert(
            "Saved, but MQTT is not publishing yet — check the broker host, port "
            "and credentials, and that paho-mqtt is installed (details in the hub log).",
            color="warning", dismissable=True, className="mb-0")

    # Dim + disable the whole alert-config block while the master switch is off,
    # with an inline note, so the form never looks live when it isn't.
    @app.callback(
        Output("alert-config-body", "style"),
        Output("alert-config-note", "children"),
        Input("notif-enabled", "value"),
    )
    def _toggle_alert_config(enabled):
        if enabled:
            return {}, None
        return (
            {"opacity": 0.5, "pointerEvents": "none"},
            html.Small(
                "Alerts are off — turn on “Enable alerts” above and Save to activate "
                "the settings below.", className="text-warning"),
        )

    # Retention is destructive above 0 — say so plainly as the user types.
    @app.callback(
        Output("retention-note", "children"),
        Output("retention-note", "className"),
        Input("retention-days", "value"),
    )
    def _retention_note(days):
        try:
            d = int(days or 0)
        except (TypeError, ValueError):
            d = 0
        if d <= 0:
            return "0 = keep everything, forever (the default for a data logger).", "text-muted"
        return (f"⚠ Readings older than {d} day{'s' if d != 1 else ''} are permanently deleted.",
                "text-warning")

    @app.callback(
        Output("notif-status", "children"),
        Input("notif-save", "n_clicks"),
        State("notif-enabled", "value"),
        State("notif-cooldown-min", "value"),
        State("notif-recovery", "value"),
        State("notif-offline-enabled", "value"),
        State("offline-after-min", "value"),
        State("notif-email-enabled", "value"),
        State("email-host", "value"),
        State("email-port", "value"),
        State("email-tls", "value"),
        State("email-user", "value"),
        State("email-from", "value"),
        State("email-to", "value"),
        State("notif-webhook-enabled", "value"),
        State("webhook-url", "value"),
        State("email-pass", "value"),
        State("notif-hysteresis", "value"),
        State("notif-rate-alert", "value"),
        State("notif-rate-window", "value"),
        State("daily-summary-enabled", "value"),
        State("daily-summary-hour", "value"),
        State("notif-flap-grace-min", "value"),
        prevent_initial_call=True,
    )
    def _save(_n, enabled, cooldown_min, recovery, offline_enabled, offline_after_min,
              email_enabled, host, port, tls, user, sender, to, webhook_enabled, url, password,
              hysteresis, rate_alert, rate_window, summary_enabled, summary_hour,
              flap_grace_min):
        try:
            existing = ((cfg.get("notifications", {}) or {}).get("email", {}) or {}).get("password", "")
            notif = build_notifications_config(
                enabled, cooldown_min, recovery, email_enabled, host, port, tls, user,
                sender, to, webhook_enabled, url, password,
                offline_alerts=offline_enabled, existing_password=existing,
                daily_summary_enabled=summary_enabled, daily_summary_hour=summary_hour,
                flap_grace_min=flap_grace_min)
            updates = {"notifications": notif}
            try:
                updates["offline_after_sec"] = max(60, int(float(offline_after_min)) * 60)
            except (TypeError, ValueError):
                pass
            try:
                updates["alert_hysteresis_c"] = max(0.0, float(hysteresis))
            except (TypeError, ValueError):
                pass
            try:
                updates["rate_alert_c"] = max(0.0, float(rate_alert))
            except (TypeError, ValueError):
                pass
            try:
                updates["rate_window_min"] = max(1, int(float(rate_window)))
            except (TypeError, ValueError):
                pass
            cfg.update(updates)
            return _ok("✅ Notification settings saved.")
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}")

    @app.callback(
        Output("notif-status", "children", allow_duplicate=True),
        Input("notif-test", "n_clicks"),
        prevent_initial_call=True,
    )
    def _test(_n):
        conf = cfg.get("notifications", {}) or {}
        if not (conf.get("email", {}).get("enabled") or conf.get("webhook", {}).get("enabled")):
            return _err("Enable and save at least one channel (email or webhook) first.")
        subject, message = format_event(
            {"probe_id": "test", "kind": "test", "temperature_c": 21.0, "limit": None},
            {"test": "Test probe"},
        )
        results = Notifier(cfg).dispatch({"subject": "[Test] " + subject, "message": message,
                                          "probe_id": "test", "kind": "test"})
        if not results:
            return _err("No channels were attempted.")
        lines = [html.Div(f"{ch}: {'✅ sent' if ok else '❌ ' + info}") for ch, ok, info in results]
        all_ok = all(ok for _, ok, _ in results)
        # The test dispatches to the channels regardless of the master switch, so
        # a channel can report "sent" while live alerts are still OFF. Say so
        # plainly — this is the usual reason a real breach doesn't notify.
        if not conf.get("enabled"):
            lines.append(html.Div(
                "⚠ Live alerts are OFF — turn on “Enable alerts” at the top and click "
                "Save, or real breaches won’t notify you.", className="fw-bold mt-1"))
            return dbc.Alert([html.Strong("Test result: "), html.Br(), *lines],
                             color="warning", dismissable=True, className="mb-0")
        return (_ok if all_ok else _err)(
            html.Span([html.Strong("Test result: "), html.Br(), *lines]))

    @app.callback(
        Output("data-status", "children"),
        Input("data-save", "n_clicks"),
        State("retention-days", "value"),
        prevent_initial_call=True,
    )
    def _save_data(_n, days):
        try:
            cfg.update({"retention_days": max(0, int(days or 0))})
            return _ok("✅ Data settings saved.")
        except Exception as e:  # noqa: BLE001
            return _err(f"Could not save: {e}")
