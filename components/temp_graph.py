import pandas as pd
from pathlib import Path
from dash import html, dcc, Input, Output, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objs as go

# ---- UI section -------------------------------------------------------------
GraphSection = dbc.Card(
    dbc.CardBody([
        html.H5("Temperature Graph"),

        # Display controls
        dbc.Row([
            dbc.Col([
                html.Small("Window", className="text-muted"),
                dcc.Dropdown(
                    id="temp-window",
                    options=[
                        {"label": "Last 1 hour", "value": "1h"},
                        {"label": "Last 6 hours", "value": "6h"},
                        {"label": "Last 24 hours", "value": "24h"},
                        {"label": "Last 7 days", "value": "7d"},
                        {"label": "All", "value": "all"},
                    ],
                    value="24h",
                    clearable=False,
                    searchable=False,
                ),
            ], xs=12, sm=6, md=4, lg=3),

            dbc.Col([
                html.Small("Navigation", className="text-muted"),
                dcc.Checklist(
                    id="temp-nav",
                    options=[
                        {"label": "Show range slider", "value": "rangeslider"},
                    ],
                    value=["rangeslider"],
                    inputStyle={"marginRight": "0.4rem"},
                ),
            ], xs=12, sm=6, md=4, lg=3, className="mt-2 mt-sm-0"),
        ], className="mb-2", align="end"),

        html.Div(id="probe-badges", className="mb-2"),
        dcc.Graph(id="temp-graph", config={"displayModeBar": False}),
    ])
)

# ---- Helpers ----------------------------------------------------------------

def _safe_read(csv_file: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(csv_file)
        for col in ("timestamp", "temperature_c", "temperature_f"):
            if col not in df.columns:
                return pd.DataFrame(columns=["timestamp","temperature_c","temperature_f","probe_id"])  # empty
        if "probe_id" not in df.columns:
            df["probe_id"] = "(default)"
        return df
    except Exception:
        return pd.DataFrame(columns=["timestamp","temperature_c","temperature_f","probe_id"])  # empty


def _apply_window(df: pd.DataFrame, window: str) -> pd.DataFrame:
    """Filter dataframe to a rolling window based on parsed datetime column '_ts'."""
    if df.empty:
        return df
    if window == "all":
        return df

    # pick an end time (use latest timestamp in the file)
    end = df["_ts"].max()
    if pd.isna(end):
        return df

    if window == "1h":
        start = end - pd.Timedelta(hours=1)
    elif window == "6h":
        start = end - pd.Timedelta(hours=6)
    elif window == "24h":
        start = end - pd.Timedelta(hours=24)
    elif window == "7d":
        start = end - pd.Timedelta(days=7)
    else:
        return df

    return df[df["_ts"] >= start]


def _build_figure(df: pd.DataFrame, window: str = "24h", show_rangeslider: bool = True) -> go.Figure:
    fig = go.Figure()

    if df.empty:
        fig.update_layout(
            template="plotly_dark",
            margin=dict(l=20, r=10, t=10, b=30),
            height=360,
            showlegend=False,
            xaxis_title="Time",
            yaxis_title="Temperature (°C)",
        )
        return fig

    df = df.copy()
    df["_ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["_ts"]).sort_values(["probe_id", "_ts"])
    df = _apply_window(df, window)

    for pid, chunk in df.groupby("probe_id"):
        label = str(pid).strip() if pd.notna(pid) and str(pid).strip() else "(default)"
        fig.add_trace(go.Scatter(
            x=chunk["_ts"], y=chunk["temperature_c"],
            mode="lines+markers",
            name=label,
            line=dict(width=2),
            marker=dict(size=6),
            hovertemplate=(
                "<b>%{text}</b><br>"  # probe id
                "%{x|%Y-%m-%d %H:%M:%S}<br>"
                "%{y:.2f} °C<extra></extra>"
            ),
            text=[label] * len(chunk),
        ))

    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=20, r=10, t=10, b=30),
        height=360,
        legend_title_text="Probe",
        xaxis_title="Time",
        yaxis_title="Temperature (°C)",
    )

    # Better time navigation + quick window buttons
    fig.update_xaxes(
        showgrid=False,
        type="date",
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1h", step="hour", stepmode="backward"),
                dict(count=6, label="6h", step="hour", stepmode="backward"),
                dict(count=24, label="24h", step="hour", stepmode="backward"),
                dict(count=7, label="7d", step="day", stepmode="backward"),
                dict(step="all", label="All"),
            ]
        ),
        rangeslider=dict(visible=bool(show_rangeslider)),
    )

    fig.update_yaxes(zeroline=False)
    return fig


def _badge_row(df: pd.DataFrame):
    if df.empty:
        return html.Small("(no data yet)", className="text-muted")

    last_by_probe = (
        df.assign(_ts=pd.to_datetime(df["timestamp"], errors="coerce"))
          .sort_values(["probe_id","_ts"]).groupby("probe_id").tail(1)
    )
    badges = []
    for _, row in last_by_probe.iterrows():
        pid = str(row.get("probe_id", "(default)"))
        ts  = str(row.get("timestamp", ""))
        c   = row.get("temperature_c", None)
        label = f"{pid} — {ts}"
        title = f"Last: {c:.2f}°C at {ts}" if c is not None else label
        badges.append(dbc.Badge(label, color="info", className="me-2 mb-2", title=title))
    return html.Div(badges)


# ---- Callbacks --------------------------------------------------------------

def register_callbacks(app, csv_path: Path):
    @app.callback(
        Output("temp-graph", "figure"),
        Output("probe-badges", "children"),
        Input("ui-refresh", "n_intervals"),
        Input("temp-window", "value"),
        Input("temp-nav", "value"),
        prevent_initial_call=False,
    )
    def _refresh(_n, window, nav_values):
        df = _safe_read(csv_path)
        show_rangeslider = isinstance(nav_values, list) and ("rangeslider" in nav_values)
        window = window or "24h"
        return _build_figure(df, window=window, show_rangeslider=show_rangeslider), _badge_row(df)
