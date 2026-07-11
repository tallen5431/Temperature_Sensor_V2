import datetime
import logging
import time

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objs as go
from dash import Input, Output, dcc, html, no_update

from core.storage import threshold_breach

log = logging.getLogger("hub.dashboard")

# Maps the UI time-range selector to a rolling window in seconds (None = all).
RANGE_SECONDS = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000, "all": None}
RANGE_LABELS = {"1h": "last hour", "6h": "last 6 hours", "24h": "last 24 hours",
                "7d": "last week", "30d": "last month", "all": "all time"}

# A probe counts as "connected" if seen within this many seconds.
ONLINE_TIMEOUT_SEC = 60

PROBE_COLORS = ["#00bcd4", "#ff6b6b", "#4ecdc4", "#45b7d1", "#f7b731", "#5f27cd"]

# --- Gauge Card ---
GaugeCard = dbc.Card(
    dbc.CardBody([
        html.H5(
            ["Current Temperature",
             html.Span(" 🟢 LIVE", id="live-badge", className="ms-2 text-success small fw-bold")],
            className="card-title",
        ),
        dcc.Graph(id="temp-gauge", style={"height": "230px"}),
    ]),
    className="h-100 gauge-card",
)

# --- Metrics Row ---
MetricsRow = dbc.Row([
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Connected Probes"),
        html.H2(id="metric-probes", className="fw-bold"),
    ]), className="h-100"), width=3),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Last Update"),
        html.H2(id="metric-lastupdate", className="fw-bold", style={"fontSize": "1.5rem"}),
    ]), className="h-100"), width=3),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Logging Status"),
        html.H2(id="metric-logging", className="fw-bold text-success"),
    ]), className="h-100"), width=3),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Unit"),
        dbc.ButtonGroup([
            dbc.Button("°C", id="unit-celsius", size="sm", color="primary", outline=False),
            dbc.Button("°F", id="unit-fahrenheit", size="sm", color="primary", outline=True),
        ], size="sm"),
    ]), className="h-100 text-center"), width=3),
], className="g-3 mb-3")

# --- Statistics Row ---
StatsRow = dbc.Row([
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Min Temperature", className="text-muted mb-1"),
        html.H4(id="stat-min", className="fw-bold text-info mb-0"),
        html.Small(id="stat-min-time", className="text-muted"),
    ]), className="h-100 text-center"), width=4),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Max Temperature", className="text-muted mb-1"),
        html.H4(id="stat-max", className="fw-bold text-danger mb-0"),
        html.Small(id="stat-max-time", className="text-muted"),
    ]), className="h-100 text-center"), width=4),
    dbc.Col(dbc.Card(dbc.CardBody([
        html.H6("Average Temperature", className="text-muted mb-1"),
        html.H4(id="stat-avg", className="fw-bold text-success mb-0"),
        html.Small(id="stat-avg-info", className="text-muted"),
    ]), className="h-100 text-center"), width=4),
], className="g-3 mb-3")

# --- Alerts Row ---
AlertsRow = html.Div(id="alerts-container", className="mb-3")

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
            dbc.Col(html.H5("Temperature History"), width="auto"),
            dbc.Col(
                dbc.Select(
                    id="time-range-selector",
                    options=[
                        {"label": "🕐 Last Hour", "value": "1h"},
                        {"label": "🕕 Last 6 Hours", "value": "6h"},
                        {"label": "📅 Last 24 Hours", "value": "24h"},
                        {"label": "📆 Last Week", "value": "7d"},
                        {"label": "📊 Last Month", "value": "30d"},
                        {"label": "🌍 All Time", "value": "all"},
                    ],
                    value="24h", size="sm", className="w-auto",
                ),
                width="auto", className="ms-auto",
            ),
        ], className="mb-2 align-items-center"),
        html.Small(id="time-range-info", className="text-muted d-block mb-2"),
        dcc.Graph(id="graph-temp", style={"height": "360px"}),
        html.Div(
            dbc.Button("📥 Download CSV", id="download-btn", color="secondary", size="sm",
                       className="mt-2", external_link=True, href="/download/temperature_log.csv"),
            className="text-end",
        ),
        html.Small(id="heartbeat", className="text-muted mt-2 d-block"),
        dcc.Interval(id="dash-refresh", interval=5000, n_intervals=0),
    ]),
    className="h-100 graph-card",
)

# --- First-run onboarding banner ---
def _onboarding_card():
    return dbc.Alert(
        [
            html.H5("👋 Waiting for your first reading…", className="alert-heading"),
            html.P("No data has arrived yet. To get a probe online:", className="mb-2"),
            html.Ol([
                html.Li("Power your probe on the same Wi-Fi network as this hub."),
                html.Li(["First-time setup? Join the probe’s ", html.B("TempSensor-XXXXXX"),
                         " Wi-Fi from your phone and choose your network."]),
                html.Li("It appears on the Devices page within ~20 seconds and readings begin."),
            ], className="mb-2"),
            html.Hr(),
            html.P(["Just exploring? Send a test reading from a terminal: ",
                    html.Code("curl \"http://localhost:8088/api/ingest?temperature_c=22.3\"")],
                   className="mb-0 small"),
        ],
        color="info", className="mb-3",
    )


# --- Dashboard Layout ---
DashboardLayout = html.Div([
    dcc.Store(id="temp-unit-store", storage_type="local", data="celsius"),
    html.Div(id="dashboard-onboarding"),
    MetricsRow,
    AlertsRow,
    ProbesRow,
    StatsRow,
    EnvironmentRow,
    dbc.Row([
        dbc.Col(GaugeCard, width=4),
        dbc.Col(GraphCard, width=8),
    ], className="g-3 align-items-stretch"),
])


# --- Helpers -----------------------------------------------------------------
def _convert(temp_c, unit):
    return (temp_c * 9.0 / 5.0) + 32.0 if unit == "fahrenheit" else temp_c


def _fmt(temp_c, unit):
    symbol = "°F" if unit == "fahrenheit" else "°C"
    return f"{_convert(temp_c, unit):.1f} {symbol}"


def _fmt_clock(ts_str):
    try:
        return pd.to_datetime(str(ts_str).rstrip("Z"), errors="coerce").strftime("%I:%M %p")
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


# A probe is "fresh" until it has been silent for this many times its own
# reporting interval — so a deep-sleep probe that wakes every few minutes is not
# flagged stale between wakes.
STALE_INTERVAL_MULTIPLIER = 2.5

# Fallback offline threshold, matching alert_monitor's ``offline_after_sec``
# default (5 min). The dashboard uses the same number so a probe never reads
# "stale" here while the alert engine still considers it online, and vice versa.
OFFLINE_AFTER_SEC = 300


def _probe_fresh_window(cfg, probe_id):
    """Seconds a probe may be silent before it counts as stale/offline.

    The larger of: the configured online timeout, the alert monitor's offline
    threshold (so the dashboard and the alerting engine agree on "offline"), and
    ~2.5x this probe's reporting interval (so a slow deep-sleep cadence doesn't
    read as offline between wakes). The 5-min floor means a typical battery probe
    counts as connected out of the box, with no per-probe configuration.
    """
    base = ONLINE_TIMEOUT_SEC
    for key, default in (("probe_online_timeout_sec", ONLINE_TIMEOUT_SEC),
                         ("offline_after_sec", OFFLINE_AFTER_SEC)):
        try:
            base = max(base, int(cfg.get(key, default) or default))
        except (TypeError, ValueError):
            pass
    try:
        intervals = cfg.get("probe_intervals", {}) or {}
        interval = float(intervals.get(probe_id, cfg.get("interval_sec", 5) or 5))
    except (TypeError, ValueError):
        interval = 5.0
    return max(base, interval * STALE_INTERVAL_MULTIPLIER)


def _reporting_probe_count(db, cfg, finder):
    """Count probes that reported recently — each judged against its OWN freshness
    window (interval-aware), keyed off ingest not mDNS.

    A deep-sleep battery probe keeps its radio off between readings so it is never
    mDNS-discovered, and a fixed 60 s timeout would flag it stale between wakes;
    both are handled here. Falls back to mDNS discovery if the DB query fails.
    """
    try:
        epochs = db.last_reading_epoch_per_probe(window_seconds=None)
        now = time.time()
        return sum(1 for pid, ep in epochs.items()
                   if pid and (now - ep) <= _probe_fresh_window(cfg, pid))
    except Exception:
        return _online_probe_count(
            finder, cfg.get("probe_online_timeout_sec", ONLINE_TIMEOUT_SEC))


def _empty_fig():
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      xaxis={"visible": False}, yaxis={"visible": False})
    return fig


def _friendly_name(cfg, probe_id):
    if not probe_id:
        return "Unknown"
    return cfg.get("probe_names", {}).get(probe_id, probe_id)


def _make_gauge(name, t_c, lo, hi, temp_unit, suffix):
    """A temperature gauge that shows ONE probe in context: coloured threshold
    zones (blue below min, green in the safe band, red above max), a bar coloured
    by state, and an axis ranged around the band (or the value) — so a −18 °C
    freezer and a 32 °C office each read sensibly instead of on a fixed 0–100.
    """
    val = _convert(t_c, temp_unit)
    breach = threshold_breach(t_c, lo, hi)
    bar = {"high": "#e74c3c", "low": "#45b7d1"}.get(breach, "#2ecc71")

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
            {"range": [ax[0], lo_u], "color": "rgba(69,183,209,0.25)"},
            {"range": [lo_u, hi_u], "color": "rgba(46,204,113,0.25)"},
            {"range": [hi_u, ax[1]], "color": "rgba(231,76,60,0.25)"},
        ]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val,
        number={"suffix": suffix, "font": {"size": 40}},
        title={"text": name, "font": {"size": 15}},
        gauge={"axis": {"range": ax}, "bar": {"color": bar, "thickness": 0.28},
               "steps": steps, "borderwidth": 0},
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(margin=dict(t=40, b=10, l=20, r=20), height=250,
                      paper_bgcolor="rgba(0,0,0,0)", font_color="white")
    return fig


def build_dashboard(db, cfg, finder, time_range, temp_unit):
    """Pure(ish) computation behind the dashboard refresh callback.

    Returns the 14-tuple the Dash callback emits.  Kept free of Dash specifics
    (only reads ``db``/``cfg``/``finder``) so it can be unit-tested directly.
    """
    temp_unit = temp_unit or "celsius"
    time_range = time_range or "24h"
    window = RANGE_SECONDS.get(time_range, 86400)
    suffix = " °F" if temp_unit == "fahrenheit" else " °C"
    logging_status = "ON" if cfg.get("pull_enabled", True) else "OFF"
    probes_online = _reporting_probe_count(db, cfg, finder)

    try:
        latest = db.latest()
        if not latest:
            raise ValueError("no data")

        # --- Gauge: the probe that needs attention (worst active breach), else
        # the latest reading overall — shown with its own threshold zones. ---
        thresholds = cfg.get("alert_thresholds", {}) or {}
        focus_pid = latest.get("probe_id")
        focus_c = float(latest["temperature_c"])
        thr = thresholds.get(focus_pid, thresholds.get("default", {})) or {}
        focus_lo, focus_hi = thr.get("min"), thr.get("max")
        try:
            best = None  # (severity, pid, t_c, lo, hi)
            for _, r in db.latest_per_probe(window).iterrows():
                pid = r["probe_id"]
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
        gauge = _make_gauge(_friendly_name(cfg, focus_pid), focus_c,
                            focus_lo, focus_hi, temp_unit, suffix)

        # --- Windowed series for the graph ---
        df = db.window_df(window_seconds=window)
        stats = db.window_stats(window_seconds=window)
        total_points = db.count()
        filtered_points = stats["count"]

        # --- Graph ---
        fig = go.Figure()
        if not df.empty:
            df = df.copy()
            df["_dt"] = pd.to_datetime(df["timestamp"].astype(str).str.rstrip("Z"), errors="coerce")
            probe_ids = list(df["probe_id"].unique())
            multi = len([p for p in probe_ids if str(p).strip()]) > 1
            for i, pid in enumerate(probe_ids):
                chunk = df[df["probe_id"] == pid]
                y = chunk["temperature_c"].apply(lambda x: _convert(x, temp_unit))
                fig.add_trace(go.Scatter(
                    x=chunk["_dt"], y=y, mode="lines",
                    name=_friendly_name(cfg, pid) if str(pid).strip() else ("°F" if temp_unit == "fahrenheit" else "°C"),
                    line=dict(color=PROBE_COLORS[i % len(PROBE_COLORS)], width=2),
                ))
            y_all = df["temperature_c"].apply(lambda x: _convert(x, temp_unit))
            pad = (y_all.max() - y_all.min()) * 0.1 if y_all.max() > y_all.min() else 5
            y_range = [y_all.min() - pad, y_all.max() + pad]
        else:
            multi = False
            y_range = None

        fig.update_layout(
            margin=dict(t=20, b=20, l=0, r=10), template="plotly_dark",
            xaxis_title="Time", yaxis_title="Temp °F" if temp_unit == "fahrenheit" else "Temp °C",
            yaxis=dict(range=y_range) if y_range else {},
            hovermode="x unified", showlegend=multi,
        )

        # --- Statistics ---
        if filtered_points:
            stat_min = _fmt(stats["min"], temp_unit)
            stat_max = _fmt(stats["max"], temp_unit)
            stat_avg = _fmt(stats["avg"], temp_unit)
            stat_min_time = f"at {_fmt_clock(stats['min_ts'])}"
            stat_max_time = f"at {_fmt_clock(stats['max_ts'])}"
            stat_avg_info = f"{filtered_points:,} readings"
        else:
            stat_min = stat_max = stat_avg = "N/A"
            stat_min_time = stat_max_time = stat_avg_info = ""

        if time_range == "all":
            range_info = f"Showing all {total_points:,} data points"
        else:
            range_info = (f"Showing {filtered_points:,} of {total_points:,} data points "
                          f"({RANGE_LABELS.get(time_range, 'selected range')})")

        # --- Alerts (latest reading per probe vs thresholds) ---
        alerts = []
        thresholds = cfg.get("alert_thresholds", {})
        if thresholds:
            latest_each = db.latest_per_probe(window_seconds=window)
            for _, row in latest_each.iterrows():
                pid = row["probe_id"]
                t_c = row["temperature_c"]
                cfgt = thresholds.get(pid, thresholds.get("default", {}))
                hi, lo = cfgt.get("max"), cfgt.get("min")
                if hi is not None and t_c > hi:
                    alerts.append(dbc.Alert([html.Strong(f"⚠️ {_friendly_name(cfg, pid)}: "),
                                  f"{_fmt(t_c, temp_unit)} (above threshold: {_fmt(hi, temp_unit)})"],
                                  color="danger", className="mb-2"))
                elif lo is not None and t_c < lo:
                    alerts.append(dbc.Alert([html.Strong(f"❄️ {_friendly_name(cfg, pid)}: "),
                                  f"{_fmt(t_c, temp_unit)} (below threshold: {_fmt(lo, temp_unit)})"],
                                  color="warning", className="mb-2"))

        # --- Heartbeat ---
        ts = latest["timestamp"]
        try:
            last_dt = datetime.datetime.fromisoformat(str(ts).rstrip("Z"))
            delta = (datetime.datetime.now() - last_dt).total_seconds()
            hb = (f"Last sync {int(delta)} s ago" if delta < 60
                  else f"Last sync {int(delta // 60)} min ago")
            if delta < 10:
                hb += " ✓"
        except Exception:
            hb = f"Last reading: {ts}"

        return (gauge, fig, str(probes_online), ts, logging_status, hb, range_info,
                stat_min, stat_min_time, stat_max, stat_max_time, stat_avg, stat_avg_info, alerts)

    except Exception:
        log.exception("dashboard update failed")
        return (_empty_fig(), _empty_fig(), str(probes_online), "(no data)", logging_status,
                "No signal", "No data available", "N/A", "", "N/A", "", "N/A", "", [])


# --- Callbacks ---------------------------------------------------------------
def register_dashboard_callbacks(app, finder, cfg, db):
    @app.callback(
        Output("dashboard-onboarding", "children"),
        Input("dash-refresh", "n_intervals"),
    )
    def _show_onboarding(_):
        # Guide the customer until the very first reading lands, then get out of
        # the way.  Cheap COUNT query; runs on the existing 5 s refresh tick.
        try:
            return _onboarding_card() if db.count() == 0 else None
        except Exception:
            return None

    @app.callback(
        Output("temp-unit-store", "data"),
        Input("unit-celsius", "n_clicks"),
        Input("unit-fahrenheit", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_unit(_c, _f):
        from dash import callback_context
        if not callback_context.triggered:
            return no_update
        button_id = callback_context.triggered[0]["prop_id"].split(".")[0]
        if button_id == "unit-celsius":
            return "celsius"
        if button_id == "unit-fahrenheit":
            return "fahrenheit"
        return no_update

    @app.callback(
        Output("unit-celsius", "outline"),
        Output("unit-fahrenheit", "outline"),
        Input("temp-unit-store", "data"),
    )
    def _sync_unit_buttons(temp_unit):
        return (True, False) if (temp_unit or "celsius") == "fahrenheit" else (False, True)

    @app.callback(
        Output("download-btn", "href"),
        Input("time-range-selector", "value"),
    )
    def _csv_link(time_range):
        tr = time_range or "24h"
        return "/download/temperature_log.csv" + ("" if tr == "all" else f"?window={tr}")

    @app.callback(
        Output("probes-row", "children"),
        Input("dash-refresh", "n_intervals"),
        Input("temp-unit-store", "data"),
    )
    def _update_probe_cards(_n, temp_unit):
        """One status card per probe: current temperature + OK/HIGH/LOW/stale."""
        temp_unit = temp_unit or "celsius"
        try:
            latest = db.latest_per_probe(window_seconds=7 * 86400)
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
            t_c = row["temperature_c"]
            age = None
            try:
                dt = datetime.datetime.fromisoformat(str(row["timestamp"]).rstrip("Z"))
                age = (now - dt).total_seconds()
            except Exception:
                pass
            thr = thresholds.get(pid, thresholds.get("default", {})) or {}
            breach = threshold_breach(t_c, thr.get("min"), thr.get("max"))
            if age is not None and age > _probe_fresh_window(cfg, pid):
                color, badge = "secondary", "● stale"
            elif breach == "high":
                color, badge = "danger", "▲ HIGH"
            elif breach == "low":
                color, badge = "info", "▼ LOW"
            else:
                color, badge = "success", "● OK"
            cards.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.Div([
                    html.Span(_friendly_name(cfg, pid), className="fw-bold text-truncate"),
                    dbc.Badge(badge, color=color, className="ms-2 flex-shrink-0"),
                ], className="d-flex justify-content-between align-items-center"),
                html.H3(_fmt(t_c, temp_unit), className=f"fw-bold text-{color} my-1"),
                html.Small(_age_text(age), className="text-muted"),
            ]), className="h-100"), xl=3, md=4, sm=6, className="mb-2"))
        return dbc.Row(cards, className="g-3")

    @app.callback(
        Output("env-row", "children"),
        Input("dash-refresh", "n_intervals"),
    )
    def _update_environment(_):
        """Humidity + VPD cards for grow-variant probes (SHT4x). Empty for a
        temperature-only deployment so the layout is unchanged for most users."""
        try:
            latest_each = db.latest_per_probe(window_seconds=86400)
        except Exception:
            return []
        cards = []
        for _, row in latest_each.iterrows():
            hum = row.get("humidity_pct")
            if hum is None or pd.isna(hum):
                continue
            vpd = row.get("vpd_kpa")
            vpd_txt = "—" if (vpd is None or pd.isna(vpd)) else f"{float(vpd):.2f} kPa"
            cards.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(_friendly_name(cfg, row["probe_id"]), className="text-muted mb-1"),
                html.Div([
                    html.Span(f"💧 {float(hum):.0f}% RH", className="fw-bold me-3"),
                    html.Span(f"VPD {vpd_txt}", className="fw-bold text-info"),
                ]),
            ])), md=4, className="mb-2"))
        return dbc.Row(cards, className="g-3") if cards else []

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
        Input("dash-refresh", "n_intervals"),
        Input("time-range-selector", "value"),
        Input("temp-unit-store", "data"),
    )
    def update_dashboard(_n, time_range, temp_unit):
        return build_dashboard(db, cfg, finder, time_range, temp_unit)
