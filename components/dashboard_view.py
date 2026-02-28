from dash import html, dcc, Output, Input, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import pandas as pd, os, datetime
from urllib.parse import quote

CSV_FILE = os.getenv('CSV_FILE', 'temperature_log.csv')

# --- Gauge Card ---
GaugeCard = dbc.Card(
    dbc.CardBody([
        html.H5(
            [
                'Current Temperature',
                html.Span(' 🟢 LIVE', id='live-badge',
                          className='ms-2 text-success small fw-bold')
            ],
            className='card-title'
        ),
        dcc.Graph(id='temp-gauge', style={'height': '230px'})
    ]),
    className='h-100 gauge-card'
)

# --- Metrics Row ---
MetricsRow = dbc.Row([
    dbc.Col(
        dbc.Card(dbc.CardBody([
            html.H6('Connected Probes'),
            html.H2(id='metric-probes', className='fw-bold')
        ]), className='h-100'), width=3),
    dbc.Col(
        dbc.Card(dbc.CardBody([
            html.H6('Last Update'),
            html.H2(id='metric-lastupdate', className='fw-bold',
                    style={'fontSize': '1.5rem'})
        ]), className='h-100'), width=3),
    dbc.Col(
        dbc.Card(dbc.CardBody([
            html.H6('Logging Status'),
            html.H2(id='metric-logging',
                    className='fw-bold text-success')
        ]), className='h-100'), width=3),
    dbc.Col(
        dbc.Card(dbc.CardBody([
            html.H6('Unit'),
            dbc.ButtonGroup([
                dbc.Button('°C', id='unit-celsius', size='sm', color='primary', outline=False),
                dbc.Button('°F', id='unit-fahrenheit', size='sm', color='primary', outline=True)
            ], size='sm')
        ]), className='h-100 text-center'), width=3)
], className='g-3 mb-3')

# --- Statistics Row ---
StatsRow = dbc.Row([
    dbc.Col(
        dbc.Card(dbc.CardBody([
            html.H6('Min Temperature', className='text-muted mb-1'),
            html.H4(id='stat-min', className='fw-bold text-info mb-0'),
            html.Small(id='stat-min-time', className='text-muted')
        ]), className='h-100 text-center'), width=4),
    dbc.Col(
        dbc.Card(dbc.CardBody([
            html.H6('Max Temperature', className='text-muted mb-1'),
            html.H4(id='stat-max', className='fw-bold text-danger mb-0'),
            html.Small(id='stat-max-time', className='text-muted')
        ]), className='h-100 text-center'), width=4),
    dbc.Col(
        dbc.Card(dbc.CardBody([
            html.H6('Average Temperature', className='text-muted mb-1'),
            html.H4(id='stat-avg', className='fw-bold text-success mb-0'),
            html.Small(id='stat-avg-info', className='text-muted')
        ]), className='h-100 text-center'), width=4)
], className='g-3 mb-3')

# --- Alerts Row ---
AlertsRow = html.Div(id='alerts-container', className='mb-3')

# --- Graph Card ---
GraphCard = dbc.Card(
    dbc.CardBody([
        dbc.Row([
            dbc.Col(html.H5('Temperature History'), width='auto'),
            dbc.Col(
                dbc.Select(
                    id='time-range-selector',
                    options=[
                        {'label': '🕐 Last Hour', 'value': '1h'},
                        {'label': '🕕 Last 6 Hours', 'value': '6h'},
                        {'label': '📅 Last 24 Hours', 'value': '24h'},
                        {'label': '📆 Last Week', 'value': '7d'},
                        {'label': '📊 Last Month', 'value': '30d'},
                        {'label': '🌍 All Time', 'value': 'all'}
                    ],
                    value='24h',
                    size='sm',
                    className='w-auto'
                ),
                width='auto',
                className='ms-auto'
            )
        ], className='mb-2 align-items-center'),
        html.Small(id='time-range-info', className='text-muted d-block mb-2'),
        dcc.Graph(id='graph-temp', style={'height': '360px'}),
        html.Div(
            dbc.Button('📥 Download CSV', id='download-btn',
                       color='secondary', size='sm',
                       className='mt-2'),
            className='text-end'
        ),
        html.Small(id='heartbeat', className='text-muted mt-2 d-block'),
        dcc.Interval(id='dash-refresh', interval=5000, n_intervals=0)
    ]),
    className='h-100 graph-card'
)

# --- Dashboard Layout ---
DashboardLayout = html.Div([
    # Persist unit across reloads (uses browser localStorage)
    dcc.Store(id='temp-unit-store', storage_type='local', data='celsius'),
    dcc.Store(id='filtered-data-store', data=None),  # Store for filtered CSV data
    MetricsRow,
    AlertsRow,
    StatsRow,
    dbc.Row([
        dbc.Col(GaugeCard, width=4),
        dbc.Col(GraphCard, width=8)
    ], className='g-3 align-items-stretch')
])


# --- Callbacks ---
def register_dashboard_callbacks(app, finder, cfg):
    def get_friendly_name(probe_id):
        """Get friendly name for a probe from config."""
        if not probe_id:
            return 'Unknown'
        probe_names = cfg.get('probe_names', {})
        return probe_names.get(probe_id, probe_id)

    def filter_dataframe_by_time_range(df, time_range):
        """Filter dataframe based on selected time range."""
        if time_range == 'all' or df.empty:
            return df

        # Parse timestamps
        df['dt'] = pd.to_datetime(df['timestamp'])
        now = pd.Timestamp.now()

        # Calculate cutoff time based on range
        if time_range == '1h':
            cutoff = now - pd.Timedelta(hours=1)
        elif time_range == '6h':
            cutoff = now - pd.Timedelta(hours=6)
        elif time_range == '24h':
            cutoff = now - pd.Timedelta(hours=24)
        elif time_range == '7d':
            cutoff = now - pd.Timedelta(days=7)
        elif time_range == '30d':
            cutoff = now - pd.Timedelta(days=30)
        else:
            return df

        # Filter and return
        filtered = df[df['dt'] >= cutoff].copy()
        return filtered

    def convert_temp(temp_c, unit):
        """Convert temperature to desired unit."""
        if unit == 'fahrenheit':
            return (temp_c * 9.0 / 5.0) + 32.0
        return temp_c

    def format_temp(temp_c, unit):
        """Format temperature with unit symbol."""
        temp = convert_temp(temp_c, unit)
        symbol = '°F' if unit == 'fahrenheit' else '°C'
        return f"{temp:.1f} {symbol}"

    # --- Unit Toggle Callback ---
    # Store the selected unit (persisted in localStorage).
    @app.callback(
        Output('temp-unit-store', 'data'),
        Input('unit-celsius', 'n_clicks'),
        Input('unit-fahrenheit', 'n_clicks'),
        prevent_initial_call=True
    )
    def toggle_unit(celsius_clicks, fahrenheit_clicks):
        from dash import callback_context
        if not callback_context.triggered:
            return no_update

        button_id = callback_context.triggered[0]['prop_id'].split('.')[0]
        if button_id == 'unit-celsius':
            return 'celsius'
        if button_id == 'unit-fahrenheit':
            return 'fahrenheit'
        return no_update

    # Keep button visuals in sync with stored unit (runs on page load too).
    @app.callback(
        Output('unit-celsius', 'outline'),
        Output('unit-fahrenheit', 'outline'),
        Input('temp-unit-store', 'data'),
        prevent_initial_call=False
    )
    def _sync_unit_buttons(temp_unit):
        unit = (temp_unit or 'celsius')
        if unit == 'fahrenheit':
            return True, False
        return False, True

    @app.callback(
        Output('temp-gauge', 'figure'),
        Output('graph-temp', 'figure'),
        Output('metric-probes', 'children'),
        Output('metric-lastupdate', 'children'),
        Output('metric-logging', 'children'),
        Output('heartbeat', 'children'),
        Output('time-range-info', 'children'),
        Output('stat-min', 'children'),
        Output('stat-min-time', 'children'),
        Output('stat-max', 'children'),
        Output('stat-max-time', 'children'),
        Output('stat-avg', 'children'),
        Output('stat-avg-info', 'children'),
        Output('alerts-container', 'children'),
        Output('filtered-data-store', 'data'),
        Input('dash-refresh', 'n_intervals'),
        Input('time-range-selector', 'value'),
        Input('temp-unit-store', 'data')
    )
    def update_dashboard(_, time_range, temp_unit):
        temp_unit = temp_unit or 'celsius'
        try:
            df = pd.read_csv(CSV_FILE)
            if df.empty:
                raise ValueError('No data')

            # Get latest reading for gauge (always use most recent)
            row = df.tail(1).iloc[0]
            t_c = float(row['temperature_c'])
            ts = row['timestamp']

            # Gauge (with dynamic unit)
            gauge_value = convert_temp(t_c, temp_unit)
            gauge_suffix = ' °F' if temp_unit == 'fahrenheit' else ' °C'
            gauge_range = [32, 212] if temp_unit == 'fahrenheit' else [0, 100]

            gauge = go.Figure(go.Indicator(
                mode='gauge+number',
                value=gauge_value,
                number={'suffix': gauge_suffix},
                gauge={'axis': {'range': gauge_range},
                       'bar': {'color': '#00bcd4'}},
                domain={'x': [0, 1], 'y': [0, 1]}
            ))
            gauge.update_layout(
                margin=dict(t=10, b=30, l=10, r=10),
                height=250,
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='white'
            )

            # Filter data for graph based on time range
            df_filtered = filter_dataframe_by_time_range(df, time_range or '24h')

            # Calculate statistics on filtered data
            if not df_filtered.empty:
                min_temp_c = df_filtered['temperature_c'].min()
                max_temp_c = df_filtered['temperature_c'].max()
                avg_temp_c = df_filtered['temperature_c'].mean()

                min_row = df_filtered[df_filtered['temperature_c'] == min_temp_c].iloc[0]
                max_row = df_filtered[df_filtered['temperature_c'] == max_temp_c].iloc[0]

                stat_min = format_temp(min_temp_c, temp_unit)
                stat_max = format_temp(max_temp_c, temp_unit)
                stat_avg = format_temp(avg_temp_c, temp_unit)

                # Format times
                try:
                    min_time = pd.to_datetime(min_row['timestamp']).strftime('%I:%M %p')
                    max_time = pd.to_datetime(max_row['timestamp']).strftime('%I:%M %p')
                except Exception:
                    min_time = 'N/A'
                    max_time = 'N/A'

                stat_min_time = f'at {min_time}'
                stat_max_time = f'at {max_time}'
                stat_avg_info = f'{len(df_filtered):,} readings'
            else:
                stat_min = stat_max = stat_avg = 'N/A'
                stat_min_time = stat_max_time = stat_avg_info = ''

            # Create time range info message
            total_points = len(df)
            filtered_points = len(df_filtered)
            if time_range == 'all':
                range_info = f'Showing all {total_points:,} data points'
            else:
                range_labels = {
                    '1h': 'last hour',
                    '6h': 'last 6 hours',
                    '24h': 'last 24 hours',
                    '7d': 'last week',
                    '30d': 'last month'
                }
                range_info = f'Showing {filtered_points:,} of {total_points:,} data points ({range_labels.get(time_range, "selected range")})'

            # Graph with filtered data (with dynamic unit)
            fig = go.Figure()
            if not df_filtered.empty:
                y_col = 'temperature_c' if temp_unit == 'celsius' else 'temperature_f'
                y_data = df_filtered[y_col] if y_col in df_filtered.columns else df_filtered['temperature_c'].apply(lambda x: convert_temp(x, temp_unit))

                # Support multiple probes with different colors
                if 'probe_id' in df_filtered.columns:
                    probe_ids = df_filtered['probe_id'].unique()
                    colors = ['#00bcd4', '#ff6b6b', '#4ecdc4', '#45b7d1', '#f7b731', '#5f27cd']
                    for i, probe_id in enumerate(probe_ids):
                        probe_df = df_filtered[df_filtered['probe_id'] == probe_id]
                        if not probe_df.empty:
                            color = colors[i % len(colors)]
                            friendly_name = get_friendly_name(probe_id)
                            # Calculate y values for this probe
                            if temp_unit == 'fahrenheit':
                                probe_y = probe_df['temperature_c'].apply(lambda x: convert_temp(x, temp_unit))
                            else:
                                probe_y = probe_df['temperature_c']

                            fig.add_trace(go.Scatter(
                                x=probe_df['timestamp'],
                                y=probe_y,
                                mode='lines',
                                name=friendly_name,
                                line=dict(color=color, width=2)
                            ))
                else:
                    # No probe_id column, just plot all data
                    if temp_unit == 'fahrenheit':
                        plot_y = df_filtered['temperature_c'].apply(lambda x: convert_temp(x, temp_unit))
                    else:
                        plot_y = df_filtered['temperature_c']

                    fig.add_trace(go.Scatter(
                        x=df_filtered['timestamp'],
                        y=plot_y,
                        mode='lines',
                        name='°F' if temp_unit == 'fahrenheit' else '°C',
                        line=dict(color='#00bcd4', width=2)
                    ))

                # Auto-scale Y-axis based on actual data range
                y_min = y_data.min() if hasattr(y_data, 'min') else df_filtered['temperature_c'].min()
                y_max = y_data.max() if hasattr(y_data, 'max') else df_filtered['temperature_c'].max()
                y_padding = (y_max - y_min) * 0.1 if y_max > y_min else 5
                y_range = [y_min - y_padding, y_max + y_padding]
            else:
                y_range = None

            y_title = 'Temp °F' if temp_unit == 'fahrenheit' else 'Temp °C'
            fig.update_layout(
                margin=dict(t=20, b=20, l=0, r=10),
                template='plotly_dark',
                xaxis_title='Time',
                yaxis_title=y_title,
                yaxis=dict(range=y_range) if y_range else {},
                hovermode='x unified',
                showlegend=True if 'probe_id' in df_filtered.columns and len(df_filtered['probe_id'].unique()) > 1 else False
            )

            # Check for temperature alerts
            alerts = []
            alert_thresholds = cfg.get('alert_thresholds', {})
            if alert_thresholds and 'probe_id' in df_filtered.columns:
                for probe_id in df_filtered['probe_id'].unique():
                    probe_df = df_filtered[df_filtered['probe_id'] == probe_id]
                    if not probe_df.empty:
                        latest_temp = probe_df.tail(1)['temperature_c'].iloc[0]
                        friendly_name = get_friendly_name(probe_id)

                        threshold_config = alert_thresholds.get(probe_id, alert_thresholds.get('default', {}))
                        max_threshold = threshold_config.get('max')
                        min_threshold = threshold_config.get('min')

                        if max_threshold and latest_temp > max_threshold:
                            alerts.append(
                                dbc.Alert([
                                    html.Strong(f'⚠️ {friendly_name}: '),
                                    f'{format_temp(latest_temp, temp_unit)} (above threshold: {format_temp(max_threshold, temp_unit)})'
                                ], color='danger', className='mb-2')
                            )
                        elif min_threshold and latest_temp < min_threshold:
                            alerts.append(
                                dbc.Alert([
                                    html.Strong(f'❄️ {friendly_name}: '),
                                    f'{format_temp(latest_temp, temp_unit)} (below threshold: {format_temp(min_threshold, temp_unit)})'
                                ], color='warning', className='mb-2')
                            )

            alerts_container = alerts if alerts else []

            # Metrics
            probes = len((finder.list_probes() or {}))
            logging_status = 'ON' if cfg.get('pull_enabled', True) else 'OFF'
            last_dt = datetime.datetime.fromisoformat(ts)
            delta = (datetime.datetime.now() - last_dt).total_seconds()
            hb = (f'Last sync {int(delta)} s ago'
                  if delta < 60 else
                  f'Last sync {int(delta//60)} min ago')
            if delta < 10:
                hb += ' ✓'

            # Store filtered data for CSV export
            filtered_csv = df_filtered.to_json(date_format='iso', orient='split')

            return (gauge, fig, probes, ts, logging_status, hb, range_info,
                    stat_min, stat_min_time, stat_max, stat_max_time, stat_avg, stat_avg_info,
                    alerts_container, filtered_csv)

        except Exception as e:
            empty = go.Figure()
            empty.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis={'visible': False},
                yaxis={'visible': False}
            )
            return (empty, empty, '0', '(no data)', 'OFF', 'No signal', 'No data available',
                    'N/A', '', 'N/A', '', 'N/A', '', [], None)

    # --- CSV Download Button (exports filtered data) ---
    @app.callback(
        Output('download-btn', 'href'),
        Input('filtered-data-store', 'data')
    )
    def _csv_link(filtered_data_json):
        try:
            if not filtered_data_json:
                # Fallback to full CSV if no filtered data
                path = quote(str(CSV_FILE))
                return f'/download/{path}'

            # Create a download link for filtered data
            # Note: This still points to the full CSV file
            # For true filtered export, we'd need to implement a separate endpoint
            # For now, just return the full CSV path
            path = quote(str(CSV_FILE))
            return f'/download/{path}'
        except Exception:
            return None
