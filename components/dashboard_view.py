import datetime
import logging
import time

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objs as go
from dash import Input, Output, State, dcc, html, no_update

from core.storage import threshold_breach
from core.status import (probe_fresh_window as _probe_fresh_window,
                         probe_state, reporting_probe_ids, ONLINE_TIMEOUT_SEC)
from core.demo import has_demo_data, load_demo_data, clear_demo_data
from core import units

# Held-breach registry: the AlertMonitor's hysteresis can hold a probe "in
# breach" after its raw reading is back inside the limit. The probe cards read
# it so a held probe shows amber "recovering" instead of green OK.
try:
    from core.alerts import HELD
except ImportError:  # registry ships with core.alerts — degrade to plain OK
    HELD = None

log = logging.getLogger("hub.dashboard")

# Maps the UI time-range selector to a rolling window in seconds (None = all).
RANGE_SECONDS = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000, "all": None}
RANGE_LABELS = {"1h": "last hour", "6h": "last 6 hours", "24h": "last 24 hours",
                "7d": "last week", "30d": "last month", "all": "all time"}

# How far back the per-probe views (status cards, focus dropdown, humidity/VPD
# cards, Devices merge) look for a probe's latest reading, so a probe that
# reports less often than daily still appears everywhere consistently.
PROBE_PRESENCE_WINDOW = 7 * 86400  # 7 days

PROBE_COLORS =["#17b3cc", "#ef8354", "#9b8cf0", "#38c172", "#e5c04b", "#ec6a7a",
                "#4d9de0", "#b57edc", "#45cbb0", "#f0a94e", "#7f8ea3", "#e05a8a"]

# Shared font stack for Plotly figures — matches assets/theme.css (system fonts,
# no webfont dependency) so charts read as part of the same UI.
FONT_STACK = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
              "'Helvetica Neue', Arial, sans-serif")

# --- Gauge Card ---
# The gauge is a fixed 230 px inside a card stretched to the graph's height, so
# it used to sit pinned to the top over ~250 px of dead space. gauge-fill takes
# the leftover height and centres it (see theme.css).
GaugeCard = dbc.Card(
    dbc.CardBody([
        html.H5(
            ["Current Temperature",
             html.Span("LIVE", id="live-badge", className="ms-2 text-success small fw-bold")],
            className="card-title",
        ),
        html.Div(
            dcc.Graph(id="temp-gauge", style={"height": "260px"},
                      config={"displayModeBar": False}),
            className="gauge-fill",
        ),
    ], className="d-flex flex-column"),
    className="h-100 gauge-card",
)

# --- Metrics Row ---
# Three KPIs, not four: the °C/°F/K picker used to sit here dressed as a metric,
# which put a control the eye reads as a readout in the middle of the readouts.
# It now lives with the other view controls in the toolbar above, leaving this
# row showing only things that are actually measured.
#
# Responsive widths (xs=6, md=4) keep the two that matter most side by side on a
# phone, and give a clean 3-across row from tablets up.
MetricsRow = dbc.Row([
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Connected Probes", className="text-muted mb-1"),
        html.H2(id="metric-probes", className="fw-bold mb-0 kpi-value"),
    ]), className="h-100"), xs=6, md=4),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Last Update", className="text-muted mb-1"),
        html.H2(id="metric-lastupdate", className="fw-bold mb-0 kpi-value"),
    ]), className="h-100"), xs=6, md=4),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Logging Status", className="text-muted mb-1"),
        html.H2(id="metric-logging", className="fw-bold text-success mb-0 kpi-value"),
    ]), className="h-100"), xs=12, md=4),
], className="g-3 mb-3 metric-row")

# --- Statistics Row ---
# xs=12 stacks the three stat cards on a phone; md=4 restores the 3-across row on
# tablets and up.
StatsRow = dbc.Row([
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Min Temperature", className="text-muted mb-1"),
        html.H4(id="stat-min", className="fw-bold text-info mb-0"),
        html.Small(id="stat-min-time", className="text-muted"),
    ]), className="h-100 text-center"), xs=12, md=4),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Max Temperature", className="text-muted mb-1"),
        # Neutral in the markup too, not just in the callback: this class is what
        # shows for the instant before the first render, and painting the peak
        # alarm-red before anything has been compared to a limit is the same
        # false signal one frame earlier.
        html.H4(id="stat-max", className="fw-bold text-body mb-0"),
        html.Small(id="stat-max-time", className="text-muted"),
    ]), className="h-100 text-center"), xs=12, md=4),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Average Temperature", className="text-muted mb-1"),
        html.H4(id="stat-avg", className="fw-bold text-success mb-0"),
        html.Small(id="stat-avg-info", className="text-muted"),
    ]), className="h-100 text-center"), xs=12, md=4),
], className="g-3 mb-3 stat-row")

# Per-probe Min/Max/Average — only rendered when 2+ probes have data, so a
# multi-probe deployment doesn't collapse into one misleading aggregate (an
# average across a freezer and a room means nothing). A single-probe deployment
# leaves this empty; the global StatsRow above already tells the whole story.
ProbeStatsRow = html.Div(id="probe-stats-row", className="mb-3")

# --- Alerts Row ---
AlertsRow = html.Div(id="alerts-container", className="mb-3")

# Recent alert-lifecycle events (breaches, recoveries, offline/online, rate) —
# rendered from the events log on its own 30 s interval so the log never rides
# the 5 s temperature refresh. Stays empty (invisible) until an event exists.
# The interval lives in DashboardLayout, NOT inside this div: the callback
# replaces the div's children, which would destroy a nested interval.
EventsRow = html.Div(id="events-row", className="mb-3")

# Per-probe status cards — one per probe that has reported, with its current
# temperature and an at-a-glance OK / HIGH / LOW / stale state. Populated by an
# independent callback (keyed off ingest, so deep-sleep probes still show).
ProbesRow = html.Div(id="probes-row", className="mb-3")

# Humidity / VPD cards — only rendered for probes that report humidity (grow
# variant). A temperature-only deployment leaves this empty. Populated by an
# independent callback so it never disturbs the main temperature refresh.
EnvironmentRow = html.Div(id="env-row", className="mb-3")

# --- Graph Card ---
GraphCard = dbc.Card(
    dbc.CardBody([
        dbc.Row([
            dbc.Col(html.H5("Temperature History", className="card-title"), width="auto"),
            dbc.Col(
                dbc.Select(
                    id="time-range-selector",
                    options=[
                        {"label": "Last Hour", "value": "1h"},
                        {"label": "Last 6 Hours", "value": "6h"},
                        {"label": "Last 24 Hours", "value": "24h"},
                        {"label": "Last Week", "value": "7d"},
                        {"label": "Last Month", "value": "30d"},
                        {"label": "All Time", "value": "all"},
                    ],
                    value="24h", size="sm", className="w-auto",
                ),
                width="auto", className="ms-auto",
            ),
        ], className="mb-2 align-items-center"),
        html.Small(id="time-range-info", className="text-muted d-block mb-2"),
        dcc.Graph(
            id="graph-temp", style={"height": "360px"},
            config={"displaylogo": False, "displayModeBar": "hover", "responsive": True,
                    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d",
                                               "zoomIn2d", "zoomOut2d", "toggleSpikelines"]},
        ),
        html.Div([
            dbc.Button("Export…", id="export-open", color="secondary", outline=True,
                       size="sm", className="mt-2 me-2"),
            dbc.Button("Download CSV", id="download-btn", color="secondary", size="sm",
                       className="mt-2", external_link=True, href="/download/temperature_log.csv"),
        ], className="text-end"),
        html.Small(id="heartbeat", className="text-muted mt-2 d-block"),
        dcc.Interval(id="dash-refresh", interval=5000, n_intervals=0),
    ]),
    className="h-100 graph-card",
)

# --- First-run onboarding banner ---
def _onboarding_card(base_url="", needs_token=False):
    """First-run guidance. ``base_url`` is this hub's real address and
    ``needs_token`` whether ingest is authenticated, because the sample command
    used to hard-code ``http://localhost:8088`` and omit the token — so on a
    default install (which always generates one) the very first thing a new user
    copied returned ``{"error":"unauthorized"}``, and on any non-8088 port it did
    not connect at all.

    The token itself is deliberately NOT printed here. Settings keeps it behind a
    click for a reason, and this card is on the page people screenshot when they
    ask for help."""
    base = (base_url or "http://localhost:8088").rstrip("/")
    cmd = "curl -X POST -H 'Content-Type: application/json' "
    if needs_token:
        cmd += "-H 'X-Token: YOUR-DEVICE-TOKEN' "
    cmd += "-d '{\"temperature_c\":22.3}' " + base + "/api/ingest"
    return dbc.Alert(
        [
            html.H5("Waiting for your first reading…", className="alert-heading"),
            html.P("No data has arrived yet. To get a probe online:", className="mb-2"),
            html.Ol([
                html.Li("Power your probe on the same Wi-Fi network as this hub."),
                html.Li(["First-time setup? Join the probe’s ", html.B("Setpoint-XXXXXX"),
                         " Wi-Fi from your phone and choose your network."]),
                html.Li("It appears on the Devices page within ~20 seconds and readings begin."),
            ], className="mb-2"),
            html.Hr(),
            html.P(["Just exploring? Load a day of sample readings to try everything out — "
                    "the dashboard, charts, export and per-probe views — no hardware needed."],
                   className="mb-2 small"),
            dbc.Button("Load demo data", id="demo-load-btn", color="info", size="sm"),
            html.P(["Or send a real test reading from a terminal: ",
                    html.Code(cmd)]
                   + ([html.Br(),
                       html.Small(["Replace ", html.Code("YOUR-DEVICE-TOKEN"),
                                   " with this hub's token — Settings \u2192 Probes \u2192 "
                                   "\u201cShow token\u201d."],
                                  className="text-muted")] if needs_token else []),
                   className="mb-0 mt-2 small"),
        ],
        color="info", className="mb-3",
    )


def _demo_alert():
    """Persistent reminder + one-click cleanup shown while demo data is loaded."""
    return dbc.Alert([
        html.Span("Demo data is loaded — these are sample readings, not a real probe.",
                  className="small"),
        dbc.Button("Clear demo data", id="demo-clear-btn", color="warning", outline=True,
                   size="sm", className="ms-3 flex-shrink-0"),
    ], color="warning",
        className="mb-3 py-2 demo-banner d-flex align-items-center justify-content-between")


# Focus selector — "All probes" (overview) or drill into a single probe. When a
# probe is chosen, the gauge, graph and statistics show only that probe, and the
# per-probe overview grids collapse to just that one — so a many-probe hub can be
# read either at a glance or one probe at a time.
FocusBar = dbc.Row([
    dbc.Col(
        dbc.InputGroup([
            dbc.InputGroupText("Viewing"),
            dbc.Select(id="focus-probe-selector", value="all",
                       options=[{"label": "All probes (overview)", "value": "all"}]),
        ], size="sm"),
        xl=4, lg=5, md=6, sm=12, className="mb-2 mb-lg-0",
    ),
    # Site picker — only rendered on a hub that actually holds forwarded data
    # (see core/forwarder.py). A single-site hub never sees it, so the common
    # case gains no chrome; an HQ hub gets "all stores / one store" without a
    # separate roll-up screen. Hidden by an inline style rather than omitted, so
    # the callback's Output always has a target to write to.
    dbc.Col(
        dbc.InputGroup([
            dbc.InputGroupText("Site"),
            dbc.Select(id="site-selector", value="all",
                       options=[{"label": "All sites", "value": "all"}]),
        ], size="sm"),
        id="site-selector-col", style={"display": "none"},
        xl=3, lg=4, md=6, sm=12, className="mb-2 mb-lg-0",
    ),
    # Display unit and clock format. Both start from the browser's own locale
    # (see the clientside callback in register_dashboard_callbacks), so a US
    # customer opens the page already in °F on a 12-hour clock and never has to
    # find these; they sit here, next to the other view controls, for the times
    # someone wants to override that.
    dbc.Col(
        dbc.ButtonGroup([
            dbc.Button("°C", id="unit-celsius", size="sm", color="primary", outline=False),
            dbc.Button("°F", id="unit-fahrenheit", size="sm", color="primary", outline=True),
            dbc.Button("K", id="unit-kelvin", size="sm", color="primary", outline=True),
        ], size="sm"),
        width="auto",
    ),
    dbc.Col(
        dbc.ButtonGroup([
            dbc.Button("24h", id="clock-24h", size="sm", color="secondary", outline=False),
            dbc.Button("12h", id="clock-12h", size="sm", color="secondary", outline=True),
        ], size="sm"),
        width="auto",
    ),
], className="mb-3 justify-content-end g-2 align-items-center dash-toolbar")

# Hub's local timezone label, shown so a user knows what the on-screen and
# exported local timestamps mean (the CSV also carries an unambiguous UTC column).
try:
    _TZ_NAME = datetime.datetime.now().astimezone().tzname() or "local time"
except Exception:
    _TZ_NAME = "local time"

# Export dialog: pick a format, a probe and an optional absolute date range.
ExportModal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Export data")),
    dbc.ModalBody([
        html.Small("Format", className="text-muted d-block"),
        dbc.Select(id="export-format", value="excel", className="mb-3", options=[
            {"label": "Excel-friendly CSV (recommended)", "value": "excel"},
            {"label": "Excel workbook (.xlsx)", "value": "xlsx"},
            {"label": "Raw CSV (ISO timestamps)", "value": "raw"},
        ]),
        html.Small("Probe", className="text-muted d-block"),
        dbc.Select(id="export-probe", value="all",
                   options=[{"label": "All probes", "value": "all"}], className="mb-3"),
        dbc.Row([
            dbc.Col([html.Small("From", className="text-muted d-block"),
                     dbc.Input(id="export-from", type="date")], md=6),
            dbc.Col([html.Small("To", className="text-muted d-block"),
                     dbc.Input(id="export-to", type="date")], md=6),
        ], className="g-2"),
        html.Small(id="export-format-hint", className="text-muted d-block mt-2"),
        html.Small(f"Leave dates blank to export everything. Dates are in the hub's "
                   f"local time ({_TZ_NAME}).",
                   className="text-muted d-block mt-1"),
    ]),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="export-cancel", color="secondary", className="me-2"),
        dbc.Button("Download", id="export-download", color="primary",
                   external_link=True, href="/download/temperature_log.csv?format=excel"),
    ]),
], id="export-modal", is_open=False)


# --- "More detail" -----------------------------------------------------------
# The secondary reads — recent events, the per-probe breakdown, humidity/VPD —
# folded behind one toggle. They are genuinely useful and none of them is the
# question someone opens the dashboard to answer, so they used to sit between
# the operator and the chart. Collapsed, the page ends at the numbers that
# matter; the choice is remembered per browser.
#
# Their callbacks are gated on this being open (see register_dashboard_callbacks)
# so a closed section costs nothing at all — no per-probe GROUP BY every 5 s.
DetailsSection = html.Div([
    dbc.Button("▸ More detail", id="dash-details-toggle", color="link", size="sm",
               className="px-0 details-toggle"),
    dbc.Collapse([
        html.Div(id="details-empty", className="mb-2"),
        ProbeStatsRow,
        EnvironmentRow,
        EventsRow,
    ], id="dash-details-collapse", is_open=False),
], className="mt-2 mb-3")


# --- Dashboard Layout ---
# Reading order is now urgency order: anything wrong → how the hub is doing →
# each probe → the chart → the numbers behind it → everything else on request.
# The gauge and graph used to sit below five stacked sections, so the single most
# looked-at element on the page was also the one furthest down it.
# temp-unit-store and clock-format-store moved to the app-wide layout
# (components/layout_main.LAYOUT): the unit a customer reads temperatures in is a
# property of the PERSON, not of one page, and while they lived here the Devices
# grid could not honour the choice at all — it had no such id to read. Anything
# outside the dashboard that wants them can now take them as an Input.
DashboardLayout = html.Div([
    dcc.Store(id="dash-details-store", storage_type="local", data=False),
    # Per-client render signature for the main refresh callback: when a 5 s tick
    # arrives and nothing it would draw has changed, the callback answers
    # no_update instead of re-rendering both figures (see update_dashboard).
    dcc.Store(id="dash-render-sig"),
    dcc.Interval(id="events-refresh", interval=30000, n_intervals=0),
    html.Div(id="dashboard-onboarding"),
    html.Div(id="demo-banner"),
    ExportModal,
    FocusBar,
    AlertsRow,
    MetricsRow,
    ProbesRow,
    dbc.Row([
        dbc.Col(GaugeCard, xs=12, lg=4),
        dbc.Col(GraphCard, xs=12, lg=8),
    ], className="g-3 align-items-stretch mb-3"),
    StatsRow,
    DetailsSection,
])


# --- Helpers -----------------------------------------------------------------
# Display conversion. The arithmetic lives in core.units (shared with the
# Devices edit form, which rounds; the dashboard keeps full precision until
# format time). Aliased rather than imported under their own names so the ~15
# call sites below read the same as they always have.
_convert = units.to_unit
_unit_symbol = units.unit_symbol


def _fmt(temp_c, unit):
    return f"{_convert(temp_c, unit):.1f} {_unit_symbol(unit)}"


def _fmt_clock(ts_str, clock_format="24h"):
    fmt = "%I:%M %p" if clock_format == "12h" else "%H:%M"
    try:
        # format="ISO8601" parses whole-second AND millisecond stamps alike; the
        # default parser infers one format and NaTs the odd precision out.
        return pd.to_datetime(str(ts_str).rstrip("Z"), format="ISO8601",
                              errors="coerce").strftime(fmt)
    except Exception:
        return "N/A"


def _online_probe_count(finder, timeout_sec=ONLINE_TIMEOUT_SEC):
    try:
        probes = (finder.list_probes() or {}).values()
    except Exception:
        return 0
    now = time.time()
    n = 0
    for p in probes:
        last = p.get("last_seen") if isinstance(p, dict) else getattr(p, "last_seen", None)
        if isinstance(last, (int, float)) and (now - last) <= timeout_sec:
            n += 1
    return n


def _age_text(age_sec):
    if age_sec is None:
        return "—"
    if age_sec < 15:
        return "just now"
    if age_sec < 60:
        return f"{int(age_sec)} s ago"
    if age_sec < 3600:
        return f"{int(age_sec // 60)} min ago"
    return f"{int(age_sec // 3600)} h ago"


def _row_age_seconds(row, now_dt=None):
    """Age in seconds of a latest-per-probe row's timestamp, or None if unparseable.

    Used to decide whether a probe's most recent reading is fresh enough to still
    count as an active alert / breach (via ``_probe_fresh_window``).
    """
    now_dt = now_dt or datetime.datetime.now()
    try:
        dt = datetime.datetime.fromisoformat(str(row["timestamp"]).rstrip("Z"))
        return max(0.0, (now_dt - dt).total_seconds())
    except Exception:
        return None


def _reporting_probe_count(db, cfg, finder, site=None):
    """Count probes that reported recently — each judged against its OWN freshness
    window (interval-aware), keyed off ingest not mDNS.

    A deep-sleep battery probe keeps its radio off between readings so it is never
    mDNS-discovered, and a fixed 60 s timeout would flag it stale between wakes;
    both are handled here. Falls back to mDNS discovery if the DB query fails.

    ``site`` narrows the count to the store the dashboard is showing. Leaving the
    KPI global while every other number on the page filtered would read as data
    loss — "Connected Probes 12" over three cards. The mDNS fallback cannot be
    scoped (a forwarded probe is on another LAN and was never discoverable here),
    so a selected site reports 0 rather than a number that means something else.
    """
    try:
        # Shared with Diagnostics, the API and /metrics so every surface counts
        # the same probes as "connected".
        return len(reporting_probe_ids(cfg, db, site=site))
    except Exception:
        if site is not None:
            return 0
        return _online_probe_count(
            finder, cfg.get("probe_online_timeout_sec", ONLINE_TIMEOUT_SEC))


def _empty_fig(message="Waiting for data…"):
    """A placeholder figure that reads as EMPTY rather than as broken.

    paper_bgcolor was transparent but plot_bgcolor was not, so plotly_dark's own
    dark fill painted the plotting area — a brand-new hub showed two large black
    rectangles where the gauge and chart belong, which looks like a half-loaded
    page rather than one waiting for its first probe. Both layers are now
    transparent, and the space carries a line of text instead of nothing.
    """
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"visible": False}, yaxis={"visible": False},
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        annotations=[{
            "text": message, "showarrow": False,
            "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5,
            "font": {"size": 13, "color": "#8A99A8"},
        }],
    )
    return fig


def _site_filter(site):
    """Translate the site picker's value into a database filter.

    The picker says ``"all"`` (or nothing at all, on a hub that has never seen a
    forwarded reading and keeps the control hidden); the database layer says
    ``None`` for "every site". Distinct vocabularies, and ``''`` means something
    different again — this hub's OWN probes — so the conversion is not a cast and
    lives in one place rather than at each of the six query sites.
    """
    return None if (not site or site == "all") else str(site)


def _friendly_name(cfg, probe_id):
    if not probe_id:
        return "Unknown"
    return cfg.get("probe_names", {}).get(probe_id, probe_id)


def _make_gauge(name, t_c, lo, hi, temp_unit, suffix, stale=False):
    """A temperature gauge that shows ONE probe in context: coloured threshold
    zones (blue below min, green in the safe band, red above max), a bar coloured
    by state, and an axis ranged around the band (or the value) — so a −18 °C
    freezer and a 32 °C office each read sensibly instead of on a fixed 0–100.

    ``stale`` mutes the whole thing. This is the largest element on the page, and
    a probe that stopped reporting still had its last reading drawn as a
    confident green bar — right beside a "NO DATA" badge saying the opposite. The
    per-probe cards below already grey out and say "stale"; the biggest number on
    the screen was the one still claiming everything was fine.
    """
    val = _convert(t_c, temp_unit)
    breach = threshold_breach(t_c, lo, hi)
    bar = {"high": "#f05a54", "low": "#38b6d9"}.get(breach, "#2fbf71")
    if stale:
        bar = "#6e8393"
        name = f"{name} · last known"

    # Axis range in Celsius, then converted — padded to always include the value.
    if lo is not None and hi is not None:
        span = max(hi - lo, 1.0)
        a_lo, a_hi = lo - span, hi + span
    elif hi is not None:
        a_lo, a_hi = hi - 20, hi + 10
    elif lo is not None:
        a_lo, a_hi = lo - 10, lo + 20
    else:
        a_lo, a_hi = t_c - 15, t_c + 15
    a_lo, a_hi = min(a_lo, t_c - 2), max(a_hi, t_c + 2)
    ax = sorted((_convert(a_lo, temp_unit), _convert(a_hi, temp_unit)))

    steps = []
    if lo is not None or hi is not None:
        lo_u = _convert(lo, temp_unit) if lo is not None else ax[0]
        hi_u = _convert(hi, temp_unit) if hi is not None else ax[1]
        steps = [
            {"range": [ax[0], lo_u], "color": "rgba(56,182,217,0.20)"},
            {"range": [lo_u, hi_u], "color": "rgba(47,191,113,0.20)"},
            {"range": [hi_u, ax[1]], "color": "rgba(240,90,84,0.20)"},
        ]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val,
        # valueformat pins one decimal to match _fmt(), which every other
        # readout on the page uses. Without it Plotly picks ~3 significant
        # digits from the magnitude, so the same reading rendered "19.8 °C"
        # and "67.7 °F" but "293 K" — the gauge is the largest number on the
        # dashboard and was the only one that silently dropped a decimal.
        number={"suffix": suffix, "valueformat": ".1f",
                "font": {"size": 40, "color": "#6e8393" if stale else "#e9f1f7"}},
        title={"text": name, "font": {"size": 15, "color": "#9db0be"}},
        gauge={"axis": {"range": ax, "tickcolor": "#6e8393",
                        "tickfont": {"color": "#9db0be", "size": 10}},
               "bar": {"color": bar, "thickness": 0.28},
               "bgcolor": "rgba(255,255,255,0.03)",
               "steps": steps, "borderwidth": 0},
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(margin=dict(t=40, b=10, l=20, r=20), height=230,
                      paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#e9f1f7", family=FONT_STACK))
    return fig


def _render_sig(latest, time_range, temp_unit, focus_probe, clock_format, now=None,
                site="all"):
    """Cheap change signature for the main dashboard refresh.

    Combines everything the big callback's output depends on: the newest
    reading's timestamp (new data), the view selectors (range/unit/focus/clock)
    and a 15 s wall-clock bucket. The bucket keeps time-relative output ("12 s
    ago", staleness cut-offs) moving even when no new reading arrives, bounding
    how long a gated dashboard can display an outdated relative age.
    """
    ts = (latest or {}).get("timestamp")
    bucket = int((now if now is not None else time.time()) // 15)
    return f"{ts}|{time_range}|{temp_unit}|{focus_probe}|{clock_format}|{site}|{bucket}"


def clicked_id(triggered):
    """Which button was actually pressed, given ``callback_context.triggered``.

    ``prevent_initial_call=True`` is NOT enough for a button that lives on a page
    rather than in the app shell. These pages are served by the ``page-content``
    callback, so their buttons are *inserted into the layout later* — and Dash
    fires the callbacks of a newly-inserted subtree, with every ``n_clicks``
    still ``None``. Reading ``triggered[0]["prop_id"]`` there names a button
    nobody touched.

    That shipped, twice, on the two settings a reader is most likely to change:
    every page load fired the unit toggle and the clock toggle, which wrote
    "celsius" and "24h" over whatever the reader had chosen. Picking °F worked
    until the next navigation, and the locale defaults below never ran at all —
    by the time they looked, the stores were no longer empty.

    A real click always carries a click count, so the value is the tell: skip
    every triggered entry whose value is falsy and return "" if none is left.
    """
    for t in triggered or []:
        if t.get("value"):
            return str(t.get("prop_id", "")).split(".")[0]
    return ""


# Badge colour per event kind: breaches read as alerts (high hot-red, low
# cool-blue), offline/rate as cautions, recovery/online as good news.
_EVENT_COLORS = {"high": "danger", "low": "info", "offline": "warning",
                 "rate": "warning", "recovery": "success", "online": "success"}


# Connectivity churn (online/offline) is coalesced per probe so a probe on a
# weak link doesn't bury the alerts that matter; everything else shows per event.
_CONNECTIVITY_KINDS = {"online", "offline"}


def _relative_time(epoch, now=None):
    """Friendly age of an event: 'just now', '22m ago', '3h ago', '2d ago'.

    Returns '' when the epoch can't be read, so one bad row degrades quietly.
    ``now`` is injectable for deterministic tests.
    """
    try:
        now = time.time() if now is None else now
        d = int(now - float(epoch))
    except (TypeError, ValueError):
        return ""
    d = max(0, d)
    if d < 60:
        return "just now"
    if d < 3600:
        return f"{d // 60}m ago"
    if d < 86400:
        return f"{d // 3600}h ago"
    return f"{d // 86400}d ago"


def _event_row(badge_kind, bits):
    return html.Div([
        dbc.Badge(badge_kind.upper(), color=_EVENT_COLORS.get(badge_kind, "secondary"),
                  className="me-2 flex-shrink-0"),
        html.Small(" · ".join(b for b in bits if b), className="text-muted"),
    ], className="d-flex align-items-center mb-1")


def build_events(db, cfg, temp_unit, limit=8, window_seconds=86400, site="all"):
    """Compact "Recent events" feed from the alert-lifecycle event log.

    Threshold/rate events (high/low/recovery/rate) render individually, newest
    first — "HIGH · Freezer · -14.8 °C (limit -15.0) · 4h ago". Connectivity
    churn (online/offline) is **coalesced per probe** into a single row that
    reports the probe's current state plus a "flapping (N×)" count, so a probe
    dropping on a weak link (e.g. Wi-Fi from inside a metal fridge) shows one row
    instead of burying the real alerts under a wall of online/offline entries.
    Returns ``[]`` when there's nothing to show. Dash-callback-free for tests.

    ``site`` narrows the feed to the hub that RECORDED the events — a store's own
    alert engine's decisions against its own thresholds, forwarded here. That is
    the record an auditor asks for, and it is why this filters on the event's own
    site rather than inferring membership from which probes report where.

    Note this filters the *scrollback*, not the live alert banner: a breach in
    another store still raises, it just does not clutter the page while someone
    is reading a different store.
    """
    temp_unit = temp_unit or "celsius"
    site_filter = _site_filter(site)
    try:
        # Fetch alerts and connectivity in SEPARATE, kind-filtered queries. A
        # flapping probe can emit hundreds of online/offline rows; if we pulled
        # one combined slice, that churn could evict a genuine breach from the
        # fetch window *before* we ever coalesced it (the newest N rows would all
        # be connectivity). Querying alerts on their own guarantees the newest
        # `limit` of them are always fetched; connectivity gets a wider slice
        # that we then collapse to one row per probe below.
        alerts = db.list_events(limit=limit, window_seconds=window_seconds,
                                exclude_kinds=_CONNECTIVITY_KINDS, site=site_filter)
        conn_events = db.list_events(limit=max(limit * 8, 64), window_seconds=window_seconds,
                                     kinds=_CONNECTIVITY_KINDS, site=site_filter)
    except Exception:
        return []  # events log unavailable — hide the section rather than break
    if not alerts and not conn_events:
        return []

    entries = []  # (epoch, html.Div) — alerts and coalesced connectivity, then sorted
    for ev in alerts:
        kind = str(ev.get("kind", "")).strip().lower()
        bits = [_friendly_name(cfg, ev.get("probe_id"))]
        t_c, lim = ev.get("temperature_c"), ev.get("limit_c")
        if t_c is not None:
            txt = _fmt(t_c, temp_unit)
            if lim is not None:
                txt += f" (limit {_convert(lim, temp_unit):.1f})"
            bits.append(txt)
        bits.append(_relative_time(ev.get("epoch")))
        entries.append((ev.get("epoch") or 0, _event_row(kind, bits)))

    # `conn_events` is newest-first, so the first row seen for a probe is its
    # current state; count offline transitions in the window to gauge flapping.
    conn: dict = {}
    for ev in conn_events:
        kind = str(ev.get("kind", "")).strip().lower()
        if kind not in _CONNECTIVITY_KINDS:
            continue
        pid = ev.get("probe_id") or ""
        g = conn.setdefault(pid, {"latest": ev, "state": kind, "drops": 0})
        if kind == "offline":
            g["drops"] += 1

    for pid, g in conn.items():
        ev = g["latest"]
        bits = [_friendly_name(cfg, pid)]
        if g["drops"] > 1:
            bits.append(f"flapping ({g['drops']}×)")
        bits.append(_relative_time(ev.get("epoch")))
        entries.append((ev.get("epoch") or 0, _event_row(g["state"], bits)))

    entries.sort(key=lambda e: e[0], reverse=True)
    rows = [div for _, div in entries[:limit]]
    if not rows:
        return []
    return html.Div([
        html.H6("Recent events", className="text-muted mb-2"),
        html.Div(rows),
    ])


def build_probe_cards(db, cfg, temp_unit, focus_probe="all", site="all"):
    """One status card per probe: current temperature + OK/HIGH/LOW/stale.

    In focus mode only the selected probe's card is shown, and on an HQ hub
    ``site`` narrows the grid to one store. A probe whose raw reading is back
    inside the limits but which the alert monitor's hysteresis still holds in
    breach shows amber "recovering" instead of green OK, so the card agrees with
    the (held) alert banner. Kept Dash-callback-free so tests can call it
    directly.
    """
    temp_unit = temp_unit or "celsius"
    focus = focus_probe if (focus_probe and focus_probe != "all") else None
    site_filter = _site_filter(site)
    try:
        latest = db.latest_per_probe(window_seconds=PROBE_PRESENCE_WINDOW,
                                     site=site_filter)
    except Exception:
        return []
    if latest is None or latest.empty:
        return []
    thresholds = cfg.get("alert_thresholds", {}) or {}
    now = datetime.datetime.now()
    cards = []
    for _, row in latest.iterrows():
        pid = row["probe_id"]
        if not str(pid).strip():
            continue
        if focus is not None and pid != focus:
            continue
        t_c = row["temperature_c"]
        age = None
        try:
            dt = datetime.datetime.fromisoformat(str(row["timestamp"]).rstrip("Z"))
            age = (now - dt).total_seconds()
        except Exception:
            pass
        thr = thresholds.get(pid, thresholds.get("default", {})) or {}
        stale = age is not None and age > _probe_fresh_window(cfg, pid)
        held = HELD.get(pid) if HELD is not None else None
        # Shared with the Devices grid (core.status.probe_state) so one probe
        # cannot read grey "stale" here and red "ALARM" there at the same moment,
        # which is exactly what happened whenever a probe breached and then went
        # silent — each page reported one of the two facts and dropped the other.
        state = probe_state(t_c, thr, stale=stale, held=held)
        raw_breach = threshold_breach(t_c, thr.get("min"), thr.get("max"))
        val_color = None                 # set only where it differs from `color`
        if state["alarm"] and stale:
            # The worst case the product has: out of range, and no longer
            # reporting. Neither half may be dropped, and the number above it is
            # old — say so rather than colouring it like a live reading.
            color, badge = "danger", "▲ ALARM · NO SIGNAL"
        elif raw_breach == "high":
            color, badge = "danger", "▲ HIGH"
        elif raw_breach == "low":
            color, badge = "info", "▼ LOW"
        elif state["alarm"]:
            # Back inside the limit but still held by the monitor's hysteresis
            # deadband — not yet a clean OK.
            color, badge = "warning", "● recovering"
        elif stale:
            color, badge = "secondary", "● stale"
        elif not state["watched"]:
            # No limit is set, so nothing is checking this probe. The Devices
            # grid already refused to call that "OK"; this card said OK in green
            # for a probe with no alarm behind it at all. The badge is muted, not
            # the reading — the number IS live and current, it is only the alarm
            # that is missing, so greying the temperature would say the wrong
            # thing about a working probe.
            color, badge, val_color = "secondary", "● no alarm set", "body"
        else:
            color, badge = "success", "● OK"
        val_color = val_color or color
        body = [
            html.Div([
                html.Span(_friendly_name(cfg, pid), className="fw-bold text-truncate"),
                dbc.Badge(badge, color=color, className="ms-2 flex-shrink-0"),
            ], className="d-flex justify-content-between align-items-center"),
            html.H3(_fmt(t_c, temp_unit), className=f"fw-bold text-{val_color} my-1"),
            html.Small(_age_text(age), className="text-muted"),
        ]
        # Which building this probe is in. Present only on a hub that another hub
        # forwards to, so a single-site card is unchanged — but on an HQ hub with
        # six stores reporting, "Walk-in" alone is ambiguous and this is the line
        # that makes the card mean anything.
        site_name = row.get("site")
        if site_name is not None and not pd.isna(site_name) and str(site_name).strip():
            body.append(html.Small(f"⌂ {site_name}", className="d-block text-info"))
        batt = row.get("battery_pct")
        if batt is not None and not pd.isna(batt):
            batt_cls = "text-warning" if float(batt) < 20 else "text-muted"
            body.append(html.Small(f"Batt {float(batt):.0f}%",
                                   className=f"d-block {batt_cls}"))
        cards.append(dbc.Col(dbc.Card(dbc.CardBody(body), className="h-100"),
                             xl=3, md=4, sm=6, className="mb-2"))
    return dbc.Row(cards, className="g-3")


def build_probe_stats(db, cfg, time_range, temp_unit, site="all"):
    """Per-probe Min / Avg / Max cards, shown only when 2+ probes have data in
    the window — so a mixed deployment (a −18 °C freezer + a 22 °C room) isn't
    reduced to one meaningless aggregate. A single probe returns ``[]``; the
    global StatsRow already tells that story. On an HQ hub ``site`` narrows the
    breakdown to one store. Kept Dash-free for direct testing.
    """
    temp_unit = temp_unit or "celsius"
    window = RANGE_SECONDS.get(time_range or "24h", 86400)
    site_filter = _site_filter(site)
    try:
        stats = db.stats_per_probe(window_seconds=window, site=site_filter)
    except Exception:
        return []
    named = {pid: s for pid, s in stats.items() if str(pid).strip()}
    use = named if named else stats
    if len(use) < 2:
        return []
    items = sorted(use.items(), key=lambda kv: _friendly_name(cfg, kv[0]).lower())
    cards = []
    for pid, s in items:
        name = _friendly_name(cfg, pid)
        cards.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.H6(name, className="text-truncate mb-2", title=name),
            html.Div([
                html.Div([html.Small("Min", className="text-muted d-block"),
                          html.Span(_fmt(s["min"], temp_unit), className="fw-bold text-info")],
                         className="text-center"),
                html.Div([html.Small("Avg", className="text-muted d-block"),
                          html.Span(_fmt(s["avg"], temp_unit), className="fw-bold text-success")],
                         className="text-center"),
                html.Div([html.Small("Max", className="text-muted d-block"),
                          html.Span(_fmt(s["max"], temp_unit), className="fw-bold text-danger")],
                         className="text-center"),
            ], className="d-flex justify-content-between"),
            html.Small(f"{s['count']:,} readings", className="text-muted d-block mt-2 text-center"),
        ]), className="h-100"), xl=3, md=4, sm=6, className="mb-2"))
    return html.Div([
        html.H6("Per-probe statistics", className="text-muted mb-2"),
        dbc.Row(cards, className="g-3"),
    ])


def build_dashboard(db, cfg, finder, time_range, temp_unit, focus_probe="all", clock_format="24h",
                    latest=None, site="all"):
    """Pure(ish) computation behind the dashboard refresh callback.

    Returns the 14-tuple the Dash callback emits.  Kept free of Dash specifics
    (only reads ``db``/``cfg``/``finder``) so it can be unit-tested directly.

    ``latest`` lets the callback wrapper pass in the newest-reading row it
    already fetched for its render signature, avoiding a second ``db.latest()``
    per tick; when ``None`` (direct/test callers) it is fetched here.

    ``focus_probe`` selects a single probe for the gauge, graph and statistics
    (drill-in). ``"all"`` (or a probe with no data) keeps the multi-probe
    overview: the gauge auto-picks the worst breach and the graph overlays every
    probe.

    ``clock_format`` is ``"24h"`` (default) or ``"12h"`` and controls every
    absolute clock time shown: the graph's ticks/hover, the Min/Max "at ..."
    times, and the "Last Update" KPI once it falls back to a calendar date.
    """
    temp_unit = temp_unit or "celsius"
    clock_format = clock_format if clock_format == "12h" else "24h"
    time_range = time_range or "24h"
    window = RANGE_SECONDS.get(time_range, 86400)
    suffix = " " + _unit_symbol(temp_unit)
    logging_status = "ON" if cfg.get("pull_enabled", True) else "OFF"
    site_filter = _site_filter(site)
    probes_online = _reporting_probe_count(db, cfg, finder, site=site_filter)
    focus = focus_probe if (focus_probe and focus_probe != "all") else None
    focus_ts = None  # the focused probe's OWN latest timestamp (for "Last Update")

    # Value colours. MAX used to be painted alarm red unconditionally, in the
    # markup AND here, so a Prep Room peaking at 22.9 °C inside an 18–25 °C band
    # sat in the KPI row looking like an incident. Red on this page means "a limit
    # was crossed" everywhere else, so it has to mean that here too — otherwise it
    # is decoration, and the operator learns to ignore the one colour that should
    # never be ignored. `_stat_classes` below decides per render.
    STAT_NEUTRAL = "fw-bold text-body mb-0"
    STAT_COLD = "fw-bold text-info mb-0"
    STAT_BREACH = "fw-bold text-danger mb-0"
    STAT_OK = "fw-bold text-success mb-0"
    STAT_EMPTY = ("fw-bold text-muted mb-0",) * 3

    def _breached(value, probe_id, bound):
        """Did this extreme actually cross the limit the probe it came from is
        held to? ``bound`` is "min" or "max"."""
        try:
            thr = (cfg.get("alert_thresholds", {}) or {}).get(probe_id) or {}
            limit = thr.get(bound)
            if limit is None or value is None:
                return False
            return float(value) > float(limit) if bound == "max" \
                else float(value) < float(limit)
        except (TypeError, ValueError):
            return False

    def _no_data():
        """The 17-tuple for 'nothing to plot yet'. Shared by the first-run path
        and the failure handler so the two can never drift in arity."""
        return (_empty_fig(), _empty_fig(), str(probes_online), "(no data)",
                logging_status, "Waiting for the first reading", "No data yet",
                "—", "", "—", "", "—", "", []) + STAT_EMPTY

    try:
        if latest is None:
            latest = db.latest()
        if not latest:
            # An empty store is the NORMAL first-run state -- the onboarding card
            # says "Waiting for your first reading". This used to raise into the
            # handler below, which logs at ERROR with a traceback, so a hub that
            # had simply not been used yet wrote a stack trace on every refresh
            # (~4/min per open tab) into the same rotating log that real field
            # incidents have to be diagnosable from. Return the state directly.
            return _no_data()

        thresholds = cfg.get("alert_thresholds", {}) or {}
        if focus is not None:
            # --- Focus mode: the gauge shows the SELECTED probe's most recent
            # reading. Look it up over the SAME 7-day window the selector and the
            # per-probe cards use (not the chosen time range) so focus is retained
            # even when the probe has no reading inside a short range — otherwise
            # the gauge/graph/stats would silently revert to the all-probes
            # overview while the dropdown and its card still show the probe. ---
            frow = None
            try:
                lp = db.latest_per_probe(PROBE_PRESENCE_WINDOW)
                match = lp[lp["probe_id"] == focus]
                if not match.empty:
                    frow = match.iloc[0]
                    focus_ts = frow["timestamp"]
            except Exception:
                frow = None
            if frow is None:
                # Probe genuinely unknown (not seen in a week) — fall back to overview.
                focus = None
            else:
                focus_pid = focus
                focus_c = float(frow["temperature_c"])
                thr = thresholds.get(focus_pid, thresholds.get("default", {})) or {}
                focus_lo, focus_hi = thr.get("min"), thr.get("max")

        # One latest-per-probe scan shared by the worst-breach gauge picker and
        # the alerts loop below (each previously ran its own identical query on
        # every tick). None on failure or when neither consumer needs it
        # (focused view with no thresholds configured).
        #
        # Scanned over PROBE_PRESENCE_WINDOW, deliberately NOT the selected chart
        # range. Both consumers already gate each row on _probe_fresh_window,
        # which is the interval-aware "is this probe live?" test and the only one
        # that should decide. Scoping the QUERY to the chart range as well made a
        # view control silence a real alert: a probe on a 2 h cadence whose last
        # reading is 90 min old is still fresh (18000 s window) and its card
        # reads "▲ HIGH", but selecting "Last Hour" dropped its row here, so the
        # banner showed nothing and the gauge picked a different probe. The cards
        # already query at this window every tick, so this costs nothing new.
        latest_each = None
        if focus is None or thresholds:
            try:
                latest_each = db.latest_per_probe(window_seconds=PROBE_PRESENCE_WINDOW)
            except Exception:
                latest_each = None

        # The GAUGE follows the store the operator selected; the ALERTS loop below
        # deliberately does not. A breach in Savannah is still a breach while head
        # office is looking at Atlanta, so it keeps the unfiltered scan — but a
        # gauge captioned with a Savannah probe over an Atlanta chart would just
        # be wrong. Filtered in pandas off the column that is already loaded, so
        # the split costs no extra query.
        gauge_rows = latest_each
        site_newest = None      # this store's most recent row, for the gauge + KPI
        if site_filter is not None and latest_each is not None and not latest_each.empty:
            gauge_rows = latest_each[latest_each["site"].fillna("") == site_filter]
            if not gauge_rows.empty:
                site_newest = gauge_rows.sort_values("timestamp").iloc[-1]

        if focus is None:
            # --- Overview: the probe that needs attention (worst active breach),
            # else the latest reading overall — shown with its own threshold zones.
            focus_pid = latest.get("probe_id")
            focus_c = float(latest["temperature_c"])
            if site_newest is not None:
                # ...and "latest overall" means latest IN THIS STORE.
                focus_pid = site_newest["probe_id"]
                focus_c = float(site_newest["temperature_c"])
            thr = thresholds.get(focus_pid, thresholds.get("default", {})) or {}
            focus_lo, focus_hi = thr.get("min"), thr.get("max")
            try:
                best = None  # (severity, pid, t_c, lo, hi)
                now_dt = datetime.datetime.now()
                for _, r in (gauge_rows.iterrows() if gauge_rows is not None else ()):
                    pid = r["probe_id"]
                    age = _row_age_seconds(r, now_dt)
                    if age is not None and age > _probe_fresh_window(cfg, pid):
                        continue  # a stale breach must not hijack the "needs attention" gauge
                    tc = float(r["temperature_c"])
                    t = thresholds.get(pid, thresholds.get("default", {})) or {}
                    lo, hi = t.get("min"), t.get("max")
                    b = threshold_breach(tc, lo, hi)
                    sev = (tc - hi) if b == "high" else (lo - tc) if b == "low" else None
                    if sev is not None and (best is None or sev > best[0]):
                        best = (sev, pid, tc, lo, hi)
                if best:
                    _, focus_pid, focus_c, focus_lo, focus_hi = best
            except Exception:
                pass
        # Is the reading the gauge is about to draw still current? Judged by the
        # same per-probe rule as everything else on the page, off the row the
        # gauge actually took its value from, so the biggest number on the screen
        # cannot disagree with the small card underneath it.
        gauge_stale = False
        try:
            gauge_row = None
            if gauge_rows is not None and not gauge_rows.empty:
                match = gauge_rows[gauge_rows["probe_id"] == focus_pid]
                gauge_row = match.iloc[-1] if not match.empty else None
            if gauge_row is None and latest is not None \
                    and latest.get("probe_id") == focus_pid:
                gauge_row = latest
            if gauge_row is not None:
                age = _row_age_seconds(gauge_row, datetime.datetime.now())
                gauge_stale = (age is not None
                               and age > _probe_fresh_window(cfg, focus_pid))
        except Exception:  # noqa: BLE001 - a freshness read must never lose the gauge
            gauge_stale = False
        gauge = _make_gauge(_friendly_name(cfg, focus_pid), focus_c,
                            focus_lo, focus_hi, temp_unit, suffix,
                            stale=gauge_stale)

        # --- Windowed series for the graph (focus mode filters to one probe) ---
        # Stats first: a provably-empty window skips window_df entirely —
        # including the duplicate COUNT it runs internally to size its
        # downsampling stride. window_df now takes the same probe_id, so in focus
        # mode its scan AND its stride track the focused probe's own volume (not
        # the global all-probe count, which used to decimate a quiet probe to a
        # point or two). The SQL filter also removes the old post-filter step.
        # site_filter is computed at the top of this function, not here, because
        # the Connected-Probes KPI needs it before any of this runs.
        stats = db.window_stats(window_seconds=window, probe_id=focus, site=site_filter)
        filtered_points = stats["count"]
        if time_range != "all" and not filtered_points:
            df = pd.DataFrame(columns=["timestamp", "temperature_c",
                                       "temperature_f", "probe_id"])
        else:
            df = db.window_df(window_seconds=window, probe_id=focus, site=site_filter)
        # "all" renders the same figure for filtered and total; otherwise the
        # "of Y" denominator is scoped to match the numerator — the focused
        # probe's own all-time total in focus mode, the whole store in overview —
        # so a quiet focused probe never reads "Showing 20 of 60,020".
        if time_range == "all":
            total_points = filtered_points
        elif site_filter is not None:
            # A site is selected, so the denominator has to be scoped to it too —
            # otherwise "Showing 40 of 60,020" compares one store's window against
            # every store's history and reads as catastrophic data loss.
            total_points = db.window_stats(probe_id=focus, site=site_filter)["count"]
        elif focus is not None:
            total_points = db.count_readings(probe_id=focus)
        else:
            total_points = db.count()

        # --- Graph ---
        fig = go.Figure()
        if not df.empty:
            df = df.copy()
            # format="ISO8601" is REQUIRED: after a probe is flashed to firmware
            # that stamps milliseconds, its window mixes pre-flash whole-second
            # ("...T03:00:00") and post-flash millisecond ("...T03:00:00.500")
            # timestamps. pandas' default parser infers ONE format from the first
            # row and silently coerces the other precision to NaT — so the newly
            # flashed probe records fine (stats count it) but its points vanish
            # from the graph. ISO8601 parses both precisions.
            df["_dt"] = pd.to_datetime(df["timestamp"].astype(str).str.rstrip("Z"),
                                       format="ISO8601", errors="coerce")
            probe_ids = list(df["probe_id"].unique())
            multi = len([p for p in probe_ids if str(p).strip()]) > 1
            for i, pid in enumerate(probe_ids):
                chunk = df[df["probe_id"] == pid]
                y = chunk["temperature_c"].apply(lambda x: _convert(x, temp_unit))
                fig.add_trace(go.Scatter(
                    x=chunk["_dt"], y=y, mode="lines",
                    name=_friendly_name(cfg, pid) if str(pid).strip() else _unit_symbol(temp_unit),
                    line=dict(color=PROBE_COLORS[i % len(PROBE_COLORS)], width=2),
                ))
            y_all = df["temperature_c"].apply(lambda x: _convert(x, temp_unit))
            pad = (y_all.max() - y_all.min()) * 0.1 if y_all.max() > y_all.min() else 5
            y_range = [y_all.min() - pad, y_all.max() + pad]

            # --- Threshold bands: drawn only when exactly ONE probe's series
            # is plotted (focus mode, or an overview that has a single probe),
            # because then its min/max limits apply to the whole chart. Each
            # limit gets a dashed line plus a faint wash over the out-of-band
            # region. A multi-probe overlay skips this — several probes'
            # differing limits would just be chart noise.
            if len(probe_ids) == 1:
                band_pid = focus if focus is not None else probe_ids[0]
                bthr = thresholds.get(band_pid, thresholds.get("default", {})) or {}
                lo_u = _convert(bthr["min"], temp_unit) if bthr.get("min") is not None else None
                hi_u = _convert(bthr["max"], temp_unit) if bthr.get("max") is not None else None
                # Widen the y-range so both limits stay visible even while the
                # data sits comfortably inside the band.
                if hi_u is not None:
                    y_range[1] = max(y_range[1], hi_u + pad)
                    fig.add_hrect(y0=hi_u, y1=y_range[1], line_width=0, layer="below",
                                  fillcolor="rgba(240,90,84,0.07)")
                    fig.add_hline(y=hi_u, line_dash="dash", line_width=1,
                                  line_color="#f05a54", opacity=0.5)
                if lo_u is not None:
                    y_range[0] = min(y_range[0], lo_u - pad)
                    fig.add_hrect(y0=y_range[0], y1=lo_u, line_width=0, layer="below",
                                  fillcolor="rgba(56,182,217,0.07)")
                    fig.add_hline(y=lo_u, line_dash="dash", line_width=1,
                                  line_color="#38b6d9", opacity=0.5)

            # Carry the computed y-fit (data padding + threshold bands) into the
            # axis through an invisible, hover-skipped anchor trace instead of an
            # explicit yaxis.range. An explicit range is re-sent on every 5 s
            # refresh and its value drifts with the data's min/max; Plotly treats
            # a *changed* programmatic range as an override and discards the
            # user's y-zoom (uirevision preserves a user edit only while the
            # figure's own specified value is unchanged). Feeding the range via
            # autorange-eligible trace data instead keeps the default view
            # auto-fitting while letting uirevision hold the zoom across refreshes.
            if y_range is not None:
                fig.add_trace(go.Scatter(
                    x=[df["_dt"].min(), df["_dt"].max()],
                    y=[y_range[0], y_range[1]], mode="markers",
                    marker=dict(opacity=0), hoverinfo="skip", showlegend=False,
                ))
        else:
            multi = False
            y_range = None

        # Plotly's own default tick/hover formatting for a datetime axis is
        # already 24-hour, so the 24h case needs no override (identical to
        # today's rendering); only the 12h case needs explicit AM/PM formats,
        # per Plotly's dtick-range tiers (ms of tick spacing -> format).
        xaxis_kwargs = {}
        if clock_format == "12h":
            xaxis_kwargs["hoverformat"] = "%b %d, %I:%M:%S %p"
            xaxis_kwargs["tickformatstops"] = [
                dict(dtickrange=[None, 1000], value="%I:%M:%S.%L %p"),
                dict(dtickrange=[1000, 60000], value="%I:%M:%S %p"),
                dict(dtickrange=[60000, 3600000], value="%I:%M %p"),
                dict(dtickrange=[3600000, 86400000], value="%I:%M %p"),
                dict(dtickrange=[86400000, 604800000], value="%b %d"),
                dict(dtickrange=[604800000, "M1"], value="%b %d"),
                dict(dtickrange=["M1", "M12"], value="%b '%y"),
                dict(dtickrange=["M12", None], value="%Y"),
            ]

        _axis = dict(gridcolor="rgba(255,255,255,0.06)",
                     zerolinecolor="rgba(255,255,255,0.10)",
                     linecolor="rgba(255,255,255,0.12)")
        # Margins are deliberately generous rather than minimal, and the y-axis
        # tick format is pinned. Both exist to stop the plot area moving while
        # the user zooms.
        #
        # Plotly's margin.autoexpand recomputes the plot rectangle whenever a
        # tick label changes width. Zooming does exactly that: the y labels gain
        # decimals ("-18" -> "-18.38" -> "-18.395") and the last x label
        # lengthens ("12:50" -> "12:05:00"), so the chart's left and right edges
        # slide under the cursor. Measured in Chromium at 900x360, that was 13-20 px
        # of left-edge travel and 14 px (24 h clock) to 24 px (12 h, whose
        # "12:05:00 PM" is the widest label the tickformatstops can produce).
        #
        # Larger margins alone do not fix the y side: there is always one more
        # decimal a deeper zoom can add, and it still moved 7 px at l=84. Pinning
        # tickformat to two decimals does fix it, because every label is then the
        # same width at every zoom level. Two decimals is also the honest
        # precision here -- the DS18B20 resolves 0.0625 C, so a third decimal is
        # noise. l=72 clears "-112.00" (a deep freezer in F) plus the axis title;
        # r=48 clears half of "12:05:00 PM" overhanging the final tick.
        # Verified 0 px of travel across C/F, room/freezer/deep-freezer, both
        # clock formats, and y-zooms down to 0.008 units.
        fig.update_layout(
            margin=dict(t=24, b=20, l=72, r=48), template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family=FONT_STACK, color="#9db0be", size=12),
            xaxis={**_axis, **xaxis_kwargs, "title": "Time"},
            # No explicit range: autorange (fed by the anchor trace above) fits
            # the data + bands by default, and uirevision keeps the user's zoom
            # across refreshes because the axis spec no longer changes each tick.
            yaxis={**_axis, "title": "Temp " + _unit_symbol(temp_unit),
                   "tickformat": ".2f"},
            hovermode="x unified", showlegend=multi,
            # Preserve the user's zoom/pan across the 5s auto-refresh: while
            # uirevision is unchanged Plotly keeps the interacted view instead of
            # snapping back to the default range. Keyed to range/unit/focus so it
            # DOES reset when the user changes what they're viewing (a new data
            # domain), but not on a plain data tick.
            uirevision=f"{time_range}|{temp_unit}|{focus}",
            hoverlabel=dict(bgcolor="#131f2b", bordercolor="rgba(255,255,255,0.14)",
                            font=dict(color="#e9f1f7", family=FONT_STACK)),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#9db0be"),
                        orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
        )

        # --- Statistics ---
        if filtered_points:
            stat_min = _fmt(stats["min"], temp_unit)
            stat_max = _fmt(stats["max"], temp_unit)
            stat_min_time = f"at {_fmt_clock(stats['min_ts'], clock_format)}"
            stat_max_time = f"at {_fmt_clock(stats['max_ts'], clock_format)}"
            # In the overview these are the coldest/hottest reading ANYWHERE, so
            # name the probe — otherwise the operator sees a real number and
            # cannot tell which unit it came from, which is most of its value.
            if focus is None and multi:
                if stats.get("min_probe"):
                    stat_min_time = (f"{_friendly_name(cfg, stats['min_probe'])} · "
                                     f"{stat_min_time}")
                if stats.get("max_probe"):
                    stat_max_time = (f"{_friendly_name(cfg, stats['max_probe'])} · "
                                     f"{stat_max_time}")
            if focus is None and multi:
                # An "average" across probes of different ranges (a −18 °C freezer
                # and a 22 °C room) is a number no probe is near — so the overview
                # doesn't headline a blended average. It points to the per-probe
                # breakdown just below instead. Global Min/Max stay meaningful as
                # the coldest / hottest reading anywhere.
                #
                # An em-dash, not the word "Per-probe". A word set in the big bold
                # slot the other two tiles fill with a temperature reads as a
                # failed render, not as "not applicable" — and this is the KPI
                # row, the part of the page people scan first. "—" is the glyph
                # _no_data() already uses for "nothing to show here"; the line
                # underneath carries the explanation.
                stat_avg = "—"
                # Names where the breakdown now lives: it moved behind the
                # dashboard's "More detail" fold, so "below" would send someone
                # looking at a section that is closed.
                stat_avg_info = "varies by probe — see “More detail”"
            else:
                stat_avg = _fmt(stats["avg"], temp_unit)
                stat_avg_info = f"{filtered_points:,} readings"
        else:
            stat_min = stat_max = stat_avg = "N/A"
            stat_min_time = stat_max_time = stat_avg_info = ""

        scope = f"{_friendly_name(cfg, focus)} · " if focus is not None else ""
        if time_range == "all":
            range_info = f"{scope}Showing all {filtered_points:,} data points"
        else:
            range_info = (f"{scope}Showing {filtered_points:,} of {total_points:,} data points "
                          f"({RANGE_LABELS.get(time_range, 'selected range')})")

        # --- Alerts (latest reading per probe vs thresholds) ---
        # Only ACTIVE (fresh) probes raise an alert. A probe that breached once
        # and then went silent must not keep showing a red banner for the whole
        # window — its per-probe card already reads "● stale" and Connected Probes
        # drops it, so the banner has to agree.
        alerts = []
        if thresholds and latest_each is not None:
            now_dt = datetime.datetime.now()
            for _, row in latest_each.iterrows():
                pid = row["probe_id"]
                t_c = row["temperature_c"]
                age = _row_age_seconds(row, now_dt)
                if age is not None and age > _probe_fresh_window(cfg, pid):
                    continue  # stale/offline probe — not an active alert
                cfgt = thresholds.get(pid, thresholds.get("default", {})) or {}
                hi, lo = cfgt.get("max"), cfgt.get("min")
                if hi is not None and t_c > hi:
                    alerts.append(dbc.Alert([html.Strong(f"▲ {_friendly_name(cfg, pid)}: "),
                                  f"{_fmt(t_c, temp_unit)} (above threshold: {_fmt(hi, temp_unit)})"],
                                  color="danger", className="mb-2"))
                elif lo is not None and t_c < lo:
                    # Low breaches read cool-blue ("info"), matching the LOW
                    # badge / gauge colouring — amber stays for cautions.
                    alerts.append(dbc.Alert([html.Strong(f"▼ {_friendly_name(cfg, pid)}: "),
                                  f"{_fmt(t_c, temp_unit)} (below threshold: {_fmt(lo, temp_unit)})"],
                                  color="info", className="mb-2"))

        # --- Heartbeat + human-friendly "Last Update" ---
        # In focus mode, base "Last Update"/heartbeat on the FOCUSED probe's own
        # latest reading, not the hub-wide newest — otherwise a silent focused
        # probe would read "Just now" because a different probe is still reporting.
        # A selected site is the same failure one level up: a store whose link has
        # dropped would read "Just now" off a sibling store that is still arriving.
        if focus is not None and focus_ts is not None:
            ts = focus_ts
        elif site_newest is not None:
            ts = site_newest["timestamp"]
        else:
            ts = latest["timestamp"]
        last_update = str(ts)
        try:
            last_dt = datetime.datetime.fromisoformat(str(ts).rstrip("Z"))
            delta = max(0.0, (datetime.datetime.now() - last_dt).total_seconds())
            hb = (f"Last sync {int(delta)} s ago" if delta < 60
                  else f"Last sync {int(delta // 60)} min ago")
            if delta < 10:
                hb += " ✓"
            # A relative, locale-neutral label reads far more professionally than
            # a raw ISO string (and never wraps mid-word on a phone).
            if delta < 5:
                last_update = "Just now"
            elif delta < 60:
                last_update = f"{int(delta)}s ago"
            elif delta < 3600:
                last_update = f"{int(delta // 60)} min ago"
            elif delta < 86400:
                last_update = f"{int(delta // 3600)} h ago"
            else:
                last_update = last_dt.strftime("%b %d, %I:%M %p" if clock_format == "12h"
                                               else "%b %d, %H:%M")
        except Exception:
            hb = f"Last reading: {ts}"

        if not filtered_points:
            stat_classes = STAT_EMPTY
        else:
            stat_classes = (
                # Cold is the natural reading of a minimum, so blue unless the
                # probe it came from was actually below its own floor.
                STAT_BREACH if _breached(stats.get("min"), stats.get("min_probe"), "min")
                else STAT_COLD,
                STAT_BREACH if _breached(stats.get("max"), stats.get("max_probe"), "max")
                else STAT_NEUTRAL,
                # Green claims "healthy". The overview's em-dash is not a value
                # and must not be dressed as a good one.
                STAT_OK if stat_avg != "—" else STAT_NEUTRAL,
            )
        return (gauge, fig, str(probes_online), last_update, logging_status, hb, range_info,
                stat_min, stat_min_time, stat_max, stat_max_time, stat_avg, stat_avg_info,
                alerts) + stat_classes

    except Exception:
        log.exception("dashboard update failed")
        return _no_data()


# --- Callbacks ---------------------------------------------------------------
def register_dashboard_callbacks(app, finder, cfg, db, public_base_func=None, token=""):
    @app.callback(
        Output("live-badge", "children"),
        Output("live-badge", "className"),
        Input("dash-refresh", "n_intervals"),
    )
    def _live_badge(_):
        """Keep the gauge's LIVE badge honest. Scoped to the dashboard because
        that is the only page the badge exists on."""
        from components.layout_main import live_badge_display
        from core.status import hub_status
        from components.dashboard_view import _reporting_probe_count as _rpc
        try:
            probes = (finder.list_probes() or {}).values()
            timeout = int(cfg.get("probe_online_timeout_sec", 60) or 60)
            status = hub_status(probes, timeout, db.count(),
                                reporting_online=_rpc(db, cfg, finder))
            return live_badge_display(status)
        except Exception:  # noqa: BLE001 - a badge must never break the page
            return "", "ms-2 text-muted small fw-bold"

    @app.callback(
        Output("dashboard-onboarding", "children"),
        Input("dash-refresh", "n_intervals"),
    )
    def _show_onboarding(_):
        # Guide the customer until the very first reading lands, then get out of
        # the way. has_any() is an O(1) EXISTS check, cheap to run every 5 s tick.
        try:
            if db.has_any():
                return None
            base = ""
            if public_base_func is not None:
                try:
                    base = public_base_func() or ""
                except Exception:  # noqa: BLE001 - never break onboarding
                    base = ""
            return _onboarding_card(base, needs_token=bool(token))
        except Exception:
            return None

    @app.callback(
        Output("demo-banner", "children"),
        Input("dash-refresh", "n_intervals"),
    )
    def _demo_banner(_n):
        try:
            return _demo_alert() if has_demo_data(db) else []
        except Exception:
            return []

    @app.callback(
        Output("demo-banner", "children", allow_duplicate=True),
        Input("demo-load-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _load_demo(n):
        if not n:
            return no_update
        try:
            load_demo_data(db, cfg)
            return _demo_alert()
        except Exception:
            log.exception("demo data load failed")
            return no_update

    @app.callback(
        Output("demo-banner", "children", allow_duplicate=True),
        Input("demo-clear-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _clear_demo(n):
        if not n:
            return no_update
        try:
            clear_demo_data(db, cfg)
            return []
        except Exception:
            log.exception("demo data clear failed")
            return no_update

    # --- Locale defaults ------------------------------------------------------
    # Both stores start empty, meaning "this browser has never chosen". While
    # that holds, take the answer from the browser instead of asking: a US
    # customer's first view is already °F on a 12-hour clock, and everyone else
    # keeps °C / 24 h. Runs clientside because the locale only exists there — the
    # server sees a request, not the reader. Once either store holds a value the
    # callback answers no_update forever, so an explicit choice is never
    # second-guessed, and any failure just leaves the °C / 24 h defaults.
    app.clientside_callback(
        """
        function (_n, unit, clock) {
            var nu = window.dash_clientside.no_update;
            var out = [nu, nu];
            try {
                if (!unit) {
                    var tag = (navigator.languages && navigator.languages[0])
                              || navigator.language || "";
                    var region = "";
                    try {
                        region = (new Intl.Locale(tag)).maximize().region || "";
                    } catch (e) {
                        var m = /[-_]([A-Za-z]{2})(?![A-Za-z])/.exec(tag);
                        region = m ? m[1] : "";
                    }
                    // The countries that use Fahrenheit for everyday temperature.
                    var F = ["US", "LR", "MM", "BS", "BZ", "KY", "PW", "FM", "MH"];
                    out[0] = (F.indexOf(region.toUpperCase()) >= 0)
                             ? "fahrenheit" : "celsius";
                }
                if (!clock) {
                    var h12 = (new Intl.DateTimeFormat(undefined, {hour: "numeric"}))
                              .resolvedOptions().hour12;
                    out[1] = h12 ? "12h" : "24h";
                }
            } catch (e) { /* leave the stores empty; the °C / 24 h defaults apply */ }
            return out;
        }
        """,
        Output("temp-unit-store", "data", allow_duplicate=True),
        Output("clock-format-store", "data", allow_duplicate=True),
        Input("dash-refresh", "n_intervals"),
        State("temp-unit-store", "data"),
        State("clock-format-store", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("temp-unit-store", "data"),
        Input("unit-celsius", "n_clicks"),
        Input("unit-fahrenheit", "n_clicks"),
        Input("unit-kelvin", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_unit(_c, _f, _k):
        from dash import callback_context
        button_id = clicked_id(callback_context.triggered)
        if button_id == "unit-celsius":
            return "celsius"
        if button_id == "unit-fahrenheit":
            return "fahrenheit"
        if button_id == "unit-kelvin":
            return "kelvin"
        return no_update

    # Which of °C / °F / K reads as selected, and 24h / 12h likewise.
    #
    # Both are clientside, and both take the 5 s tick as an Input they otherwise
    # have no use for. That is not decoration — it is the only reason they run at
    # all on a page load. dash-renderer queues a mounting subtree's callbacks by
    # INPUT, and these buttons' real input (the preference store) lives in the app
    # shell, which never remounts. With the store as the sole Input the callback
    # was never queued when the dashboard mounted, so on every reload the buttons
    # fell back to the layout's hard-coded °C / 24h while the gauge, chart, cards
    # and stats all correctly showed the saved preference. Reading °F everywhere
    # with °C lit up is indistinguishable, to the person looking at it, from the
    # setting not having been kept. dash-refresh lives on this page, so naming it
    # gets the pair queued on mount and they paint the truth immediately.
    #
    # Clientside because the tick would otherwise buy two server round-trips every
    # 5 s to answer a question that only changes on a click; in the browser it is
    # a string compare against props React already holds.
    app.clientside_callback(
        """
        function (_n, unit) {
            var u = unit || "celsius";
            // outline=true means "not the selected unit"
            return [u !== "celsius", u !== "fahrenheit", u !== "kelvin"];
        }
        """,
        Output("unit-celsius", "outline"),
        Output("unit-fahrenheit", "outline"),
        Output("unit-kelvin", "outline"),
        Input("dash-refresh", "n_intervals"),
        Input("temp-unit-store", "data"),
    )

    @app.callback(
        Output("clock-format-store", "data"),
        Input("clock-24h", "n_clicks"),
        Input("clock-12h", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_clock_format(_h24, _h12):
        from dash import callback_context
        button_id = clicked_id(callback_context.triggered)
        if button_id == "clock-24h":
            return "24h"
        if button_id == "clock-12h":
            return "12h"
        return no_update

    app.clientside_callback(
        """
        function (_n, fmt) {
            var twelve = (fmt || "24h") === "12h";
            return [twelve, !twelve];
        }
        """,
        Output("clock-24h", "outline"),
        Output("clock-12h", "outline"),
        Input("dash-refresh", "n_intervals"),
        Input("clock-format-store", "data"),
    )

    @app.callback(
        Output("download-btn", "href"),
        Input("time-range-selector", "value"),
        Input("focus-probe-selector", "value"),
    )
    def _csv_link(time_range, focus_probe):
        # "Download CSV" exports exactly what you're viewing: the selected time
        # range and, in focus mode, just that probe.
        from urllib.parse import quote
        tr = time_range or "24h"
        params = []
        if tr != "all":
            params.append(f"window={tr}")
        if focus_probe and focus_probe != "all":
            params.append("probe=" + quote(str(focus_probe)))
        return "/download/temperature_log.csv" + (("?" + "&".join(params)) if params else "")

    @app.callback(
        Output("export-modal", "is_open"),
        Input("export-open", "n_clicks"),
        Input("export-cancel", "n_clicks"),
        State("export-modal", "is_open"),
        prevent_initial_call=True,
    )
    def _toggle_export(_open, _cancel, is_open):
        return not is_open

    @app.callback(
        Output("export-probe", "options"),
        Input("export-open", "n_clicks"),
        prevent_initial_call=True,
    )
    def _export_probe_options(_n):
        opts = [{"label": "All probes", "value": "all"}]
        try:
            latest = db.latest_per_probe(window_seconds=30 * 86400)
            pids = [p for p in latest["probe_id"].tolist() if str(p).strip()]
            for pid in sorted(pids, key=lambda p: _friendly_name(cfg, p).lower()):
                opts.append({"label": _friendly_name(cfg, pid), "value": pid})
        except Exception:
            pass
        return opts

    @app.callback(
        Output("export-download", "href"),
        Output("export-download", "children"),
        Output("export-format-hint", "children"),
        Input("export-format", "value"),
        Input("export-probe", "value"),
        Input("export-from", "value"),
        Input("export-to", "value"),
    )
    def _export_href(fmt, probe, date_from, date_to):
        from urllib.parse import quote
        fmt = fmt if fmt in ("excel", "xlsx", "raw") else "excel"
        params = ["format=" + fmt]
        if probe and probe != "all":
            params.append("probe=" + quote(str(probe)))
        if date_from:
            params.append("from=" + quote(str(date_from)))
        if date_to:
            params.append("to=" + quote(str(date_to)))
        href = "/download/temperature_log.csv?" + "&".join(params)
        label = "Download .xlsx" if fmt == "xlsx" else "Download CSV"
        hints = {
            "excel": "Date and time in separate columns with the probe's friendly "
                     "name — opens ready to sort, filter and chart in Excel.",
            "xlsx":  "A native Excel workbook: typed date/time/number cells, a "
                     "frozen header row and filter dropdowns.",
            "raw":   "Full ISO-8601 timestamps and every column — the archival "
                     "system-of-record format for scripts and re-import.",
        }
        return href, label, hints[fmt]

    @app.callback(
        Output("probes-row", "children"),
        Input("dash-refresh", "n_intervals"),
        Input("temp-unit-store", "data"),
        Input("focus-probe-selector", "value"),
        Input("site-selector", "value"),
    )
    def _update_probe_cards(_n, temp_unit, focus_probe, site):
        # Logic lives in build_probe_cards (module level) so tests can call it
        # directly — e.g. with the HELD registry stubbed.
        return build_probe_cards(db, cfg, temp_unit, focus_probe, site)

    @app.callback(
        Output("probe-stats-row", "children"),
        Input("dash-refresh", "n_intervals"),
        Input("time-range-selector", "value"),
        Input("temp-unit-store", "data"),
        Input("focus-probe-selector", "value"),
        Input("site-selector", "value"),
        # An Input, not a State: opening "More detail" has to draw the section
        # now, not on the next tick. Closed, this skips a per-probe GROUP BY that
        # otherwise ran every 5 s over the whole selected range for nobody.
        Input("dash-details-collapse", "is_open"),
    )
    def _update_probe_stats(_n, time_range, temp_unit, focus_probe, site, details_open):
        if not details_open:
            return []
        # In focus mode the global StatsRow already shows the selected probe's
        # min/avg/max, so the per-probe breakdown would be redundant.
        if focus_probe and focus_probe != "all":
            return []
        return build_probe_stats(db, cfg, time_range, temp_unit, site)

    @app.callback(
        Output("env-row", "children"),
        Input("dash-refresh", "n_intervals"),
        Input("focus-probe-selector", "value"),
        Input("site-selector", "value"),
        Input("dash-details-collapse", "is_open"),
    )
    def _update_environment(_n, focus_probe, site, details_open):
        """Humidity + VPD cards for grow-variant probes (SHT4x). Empty for a
        temperature-only deployment so the layout is unchanged for most users."""
        if not details_open:
            return []
        focus = focus_probe if (focus_probe and focus_probe != "all") else None
        site_filter = _site_filter(site)
        try:
            latest_each = db.latest_per_probe(window_seconds=PROBE_PRESENCE_WINDOW,
                                              site=site_filter)
        except Exception:
            return []
        cards = []
        for _, row in latest_each.iterrows():
            if focus is not None and row["probe_id"] != focus:
                continue
            hum = row.get("humidity_pct")
            if hum is None or pd.isna(hum):
                continue
            vpd = row.get("vpd_kpa")
            vpd_txt = "—" if (vpd is None or pd.isna(vpd)) else f"{float(vpd):.2f} kPa"
            cards.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(_friendly_name(cfg, row["probe_id"]), className="text-muted mb-1"),
                html.Div([
                    html.Span(f"{float(hum):.0f}% RH", className="fw-bold me-3"),
                    html.Span(f"VPD {vpd_txt}", className="fw-bold text-info"),
                ]),
            ])), md=4, className="mb-2"))
        return dbc.Row(cards, className="g-3") if cards else []

    @app.callback(
        Output("events-row", "children"),
        Input("events-refresh", "n_intervals"),
        Input("site-selector", "value"),
        Input("dash-details-collapse", "is_open"),
        Input("temp-unit-store", "data"),
    )
    def _update_events(_n, site, details_open, temp_unit):
        """Recent alert-lifecycle events, refreshed on their own 30 s interval.
        Renders nothing (invisible section) while the event log is empty.

        Site is an Input, not State: switching store is a context switch the
        operator expects to see immediately, not up to 30 s later. So is the
        "More detail" state — otherwise opening the section could sit blank for
        30 s and read as "no events" when there are plenty.

        The unit is an Input for the same reason, and it stopped being optional
        once the unit could change by itself: locale inference sets °F shortly
        after first paint, which does not re-run a State-only callback, so this
        feed rendered "15.0 °C (limit 8.0)" beside cards already reading °F and
        only agreed with them 30 s later. Re-rendering on a unit change costs one
        pass of a section that is gated behind the fold anyway.
        """
        if not details_open:
            return []
        return build_events(db, cfg, temp_unit, site=site)

    # --- "More detail" toggle -------------------------------------------------
    @app.callback(
        Output("dash-details-store", "data"),
        Input("dash-details-toggle", "n_clicks"),
        State("dash-details-store", "data"),
        prevent_initial_call=True,
    )
    def _toggle_details(_n, is_open):
        return not bool(is_open)

    @app.callback(
        Output("dash-details-collapse", "is_open"),
        Output("dash-details-toggle", "children"),
        Input("dash-details-store", "data"),
    )
    def _sync_details(is_open):
        # Driven off the persisted store rather than the click, so the choice
        # survives a reload instead of snapping shut on every refresh.
        return bool(is_open), ("▾ Hide detail" if is_open else "▸ More detail")

    @app.callback(
        Output("details-empty", "children"),
        Input("events-row", "children"),
        Input("probe-stats-row", "children"),
        Input("env-row", "children"),
        Input("dash-details-collapse", "is_open"),
    )
    def _details_placeholder(events, stats, env, is_open):
        """Explain an empty "More detail" instead of opening onto nothing.

        All three sections legitimately render nothing on a young or single-probe
        hub, so without this the toggle can look broken the first time it's used.
        """
        if not is_open or any(bool(x) for x in (events, stats, env)):
            return None
        return html.Small(
            "Nothing extra yet — the per-probe breakdown appears once two or more "
            "probes are reporting, recent events once an alert has fired, and "
            "humidity for probes that measure it.", className="text-muted")

    @app.callback(
        Output("temp-gauge", "figure"),
        Output("graph-temp", "figure"),
        Output("metric-probes", "children"),
        Output("metric-lastupdate", "children"),
        Output("metric-logging", "children"),
        Output("heartbeat", "children"),
        Output("time-range-info", "children"),
        Output("stat-min", "children"),
        Output("stat-min-time", "children"),
        Output("stat-max", "children"),
        Output("stat-max-time", "children"),
        Output("stat-avg", "children"),
        Output("stat-avg-info", "children"),
        Output("alerts-container", "children"),
        # These three MUST stay last of build_dashboard's outputs and in this
        # order: it appends them to the end of its tuple, so an Output declared
        # earlier here would silently receive the alerts list instead.
        Output("stat-min", "className"),
        Output("stat-max", "className"),
        Output("stat-avg", "className"),
        Output("metric-logging", "className"),
        Output("dash-render-sig", "data"),
        Input("dash-refresh", "n_intervals"),
        Input("time-range-selector", "value"),
        Input("temp-unit-store", "data"),
        Input("focus-probe-selector", "value"),
        Input("clock-format-store", "data"),
        Input("site-selector", "value"),
        State("dash-render-sig", "data"),
    )
    def update_dashboard(_n, time_range, temp_unit, focus_probe, clock_format, site, prev_sig):
        from dash import callback_context
        # Tick gating: a 5 s interval tick that would redraw exactly what the
        # client already shows (no new reading, same view selectors, same 15 s
        # staleness bucket) answers no_update across the board — the browser
        # skips two Plotly redraws and the server skips the window scans. Any
        # user-driven trigger (range/unit/focus/clock) always renders.
        try:
            latest = db.latest()  # cheap LIMIT 1, shared with build_dashboard
        except Exception:
            latest = None
        sig = _render_sig(latest, time_range, temp_unit, focus_probe, clock_format, site=site)
        trigger = (callback_context.triggered[0]["prop_id"].split(".")[0]
                   if callback_context.triggered else "")
        if trigger == "dash-refresh" and prev_sig == sig:
            # Must equal the Output count above. A literal here silently 500s the
            # whole callback the moment an Output is added, which is exactly what
            # happened when the three stat classNames landed.
            return (no_update,) * 19
        out = build_dashboard(db, cfg, finder, time_range, temp_unit, focus_probe,
                              clock_format, latest=latest, site=site)
        # Colour the Logging KPI by state (its value is out[4]): green when ON,
        # amber when OFF — so "OFF" no longer renders in success-green.
        logging_class = "fw-bold mb-0 kpi-value " + ("text-success" if out[4] == "ON"
                                                     else "text-warning")
        return (*out, logging_class, sig)

    @app.callback(
        Output("site-selector", "options"),
        Output("site-selector-col", "style"),
        Input("dash-refresh", "n_intervals"),
    )
    def _site_options(_n):
        """Populate the site picker from whatever sites the store actually holds.

        A hub only has sites if another hub has forwarded readings to it, so a
        single-site hub — every hub, until someone runs a chain — keeps the row
        it always had and never learns this control exists. Returning a style of
        display:none rather than omitting the column keeps the Output target
        alive for the callback.
        """
        try:
            sites = db.sites()
        except Exception:  # noqa: BLE001 - a picker must not break the dashboard
            sites = []
        if not sites:
            return [{"label": "All sites", "value": "all"}], {"display": "none"}
        opts = [{"label": f"All sites ({len(sites)})", "value": "all"}]
        opts += [{"label": s, "value": s} for s in sites]
        return opts, {}

    @app.callback(
        Output("focus-probe-selector", "options"),
        Output("focus-probe-selector", "value"),
        Input("dash-refresh", "n_intervals"),
        Input("site-selector", "value"),
        State("focus-probe-selector", "value"),
    )
    def _focus_options(_n, site, focus):
        """Populate the focus dropdown with every probe that has data, keeping
        'All probes' first. Values are probe ids; labels are friendly names.

        Scoped to the selected site: focusing a Savannah probe while the site
        picker says Atlanta would AND two contradictory filters and draw an empty
        chart, so a site change that orphans the current focus resets it to
        'All probes' rather than leaving a dropdown pointing at nothing.
        """
        site_filter = _site_filter(site)
        opts = [{"label": "All probes (overview)", "value": "all"}]
        pids = []
        try:
            latest = db.latest_per_probe(window_seconds=PROBE_PRESENCE_WINDOW,
                                         site=site_filter)
            pids = [p for p in latest["probe_id"].tolist() if str(p).strip()]
            for pid in sorted(pids, key=lambda p: _friendly_name(cfg, p).lower()):
                opts.append({"label": _friendly_name(cfg, pid), "value": pid})
        except Exception:
            pass
        # Only ever WRITE the value when the current one has become invalid —
        # re-emitting it on every 5 s tick would fight the user's own selection.
        if focus and focus != "all" and focus not in pids:
            return opts, "all"
        return opts, no_update
