from dash import html, dcc, Output, Input, State, no_update, ALL
import dash_bootstrap_components as dbc
import datetime

DevicesLayout = html.Div([
    html.H4('Connected Probes'),
    dcc.Interval(id='device-refresh', interval=5000, n_intervals=0),
    html.Div(id='device-grid', className='row g-3'),
    # Modal for editing probe name and read interval
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Edit Probe")),
        dbc.ModalBody([
            html.Div([
                html.Label("Probe ID:", className='fw-bold mb-2'),
                html.Div(id='edit-probe-id-display', className='mb-3 text-muted'),
                html.Label("Friendly Name:", className='fw-bold mb-2'),
                dbc.Input(id='edit-probe-name-input', type='text', placeholder='Enter friendly name...', className='mb-2'),
                html.Small("Leave empty to use probe ID as display name", className='text-muted'),
                html.Hr(),
                html.Label("Read Interval (seconds):", className='fw-bold mb-2 mt-1 d-block'),
                dbc.Input(
                    id='edit-probe-interval-input',
                    type='number',
                    min=0.5,
                    step=0.5,
                    placeholder='e.g. 5',
                    className='mb-2'
                ),
                html.Small("How often the probe sends a reading (minimum 0.5 s)", className='text-muted'),
                html.Hr(),
                html.Label("Alert Thresholds (°C):", className='fw-bold mb-2 mt-1 d-block'),
                dbc.Row([
                    dbc.Col([
                        html.Small("Min Temperature", className='text-muted d-block mb-1'),
                        dbc.Input(
                            id='edit-probe-min-input',
                            type='number',
                            step=0.5,
                            placeholder='e.g. 10',
                            className='mb-1'
                        ),
                        html.Small("Alert when below this value", className='text-muted'),
                    ], width=6),
                    dbc.Col([
                        html.Small("Max Temperature", className='text-muted d-block mb-1'),
                        dbc.Input(
                            id='edit-probe-max-input',
                            type='number',
                            step=0.5,
                            placeholder='e.g. 30',
                            className='mb-1'
                        ),
                        html.Small("Alert when above this value", className='text-muted'),
                    ], width=6),
                ]),
                html.Small("Leave blank to disable threshold alerts for this probe", className='text-muted d-block mt-1'),
            ])
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id='edit-probe-cancel', className='me-2', color='secondary'),
            dbc.Button("Save", id='edit-probe-save', color='primary')
        ])
    ], id='edit-probe-modal', is_open=False),
    dcc.Store(id='edit-probe-id-store', data=None)
])


def register_devices_callbacks(app, finder, cfg, public_base_func=None, token=""):
    @app.callback(Output('device-grid', 'children'), Input('device-refresh', 'n_intervals'))
    def update_devices(_):
        try:
            probes = (finder.list_probes() or {}).values()
            cards = []
            now = datetime.datetime.now()
            probe_names = cfg.get('probe_names', {})
            probe_intervals = cfg.get('probe_intervals', {})
            for p in probes:
                # Handle both dicts and object-style probes
                if isinstance(p, dict):
                    props = p.get('properties', {}) or {}
                    name = p.get('name') or props.get('name') or props.get('id') or p.get('id') or 'Unknown'
                    probe_id = props.get('id') or p.get('probe_id') or p.get('id')
                    ip = p.get('ip') or p.get('host') or 'N/A'
                    port = p.get('port', 80)
                    last = p.get('last_seen')
                else:
                    props = getattr(p, 'properties', {}) or {}
                    name = getattr(p, 'name', None) or getattr(p, 'id', None) or props.get('name') or props.get('id') or 'Unknown'
                    probe_id = props.get('id') or getattr(p, 'probe_id', None) or getattr(p, 'id', None)
                    ip = getattr(p, 'ip', None) or getattr(p, 'host', None) or 'N/A'
                    port = getattr(p, 'port', 80)
                    last = getattr(p, 'last_seen', None)

                delta = ''
                status_color = 'secondary'
                if last:
                    try:
                        if isinstance(last, (int, float)):
                            dt = datetime.datetime.fromtimestamp(last)
                        else:
                            dt = datetime.datetime.fromisoformat(str(last).rstrip('Z'))
                        seconds = (now - dt).total_seconds()
                        if seconds < 15:
                            status_color = 'success'
                            delta = 'Just now'
                        elif seconds < 60:
                            status_color = 'warning'
                            delta = f'{int(seconds)} s ago'
                        else:
                            status_color = 'danger'
                            delta = f'{int(seconds // 60)} min ago'
                    except Exception:
                        pass

                # Build display elements with friendly names and edit button
                friendly_name = probe_names.get(probe_id, None) if probe_id else None

                # Show current interval on the card if a per-probe override exists
                interval_note = None
                if probe_id and probe_id in probe_intervals:
                    interval_note = html.Small(
                        f'Interval: {probe_intervals[probe_id]} s',
                        className='text-muted d-block'
                    )

                # Create edit button (only if we have a probe_id)
                edit_button = html.Span(
                    '✏️',
                    id={'type': 'edit-probe-btn', 'index': probe_id or name},
                    n_clicks=0,
                    style={'cursor': 'pointer', 'fontSize': '1.2rem', 'marginLeft': '8px'},
                    title='Edit probe'
                ) if probe_id else html.Span()

                display_name = probe_id or name
                if friendly_name:
                    title_elements = [
                        html.Div([
                            html.H6([friendly_name, edit_button], className='fw-bold mb-1 d-inline-flex align-items-center')
                        ])
                    ]
                    title_elements.append(html.Small(display_name, className='text-info d-block mb-1'))
                else:
                    title_elements = [
                        html.Div([
                            html.H6([display_name, edit_button], className='fw-bold mb-1 d-inline-flex align-items-center')
                        ])
                    ]

                card_body_children = [
                    *title_elements,
                    html.Small(f'{ip}:{port}', className='text-muted'),
                ]
                if interval_note:
                    card_body_children.append(interval_note)
                card_body_children.append(
                    html.Div(html.Span(f'● {delta or "Unknown"}', className=f'status-dot text-{status_color} fw-bold mt-2'))
                )

                card = dbc.Col(dbc.Card(dbc.CardBody(card_body_children), className='h-100 probe-card'), width=12, lg=4, md=6)
                cards.append(card)

            if not cards:
                return [dbc.Alert('No probes discovered yet.', color='secondary')]
            return cards
        except Exception as e:
            import traceback
            error_msg = f'Discovery service error: {str(e)}'
            print(f'[devices_panel] {error_msg}\n{traceback.format_exc()}')
            return [dbc.Alert(error_msg, color='danger')]

    # Open modal when edit button clicked, close on cancel/save
    @app.callback(
        Output('edit-probe-modal', 'is_open'),
        Output('edit-probe-id-store', 'data'),
        Output('edit-probe-id-display', 'children'),
        Output('edit-probe-name-input', 'value'),
        Output('edit-probe-interval-input', 'value'),
        Output('edit-probe-min-input', 'value'),
        Output('edit-probe-max-input', 'value'),
        Input({'type': 'edit-probe-btn', 'index': ALL}, 'n_clicks'),
        Input('edit-probe-cancel', 'n_clicks'),
        Input('edit-probe-save', 'n_clicks'),
        State('edit-probe-modal', 'is_open'),
        State('edit-probe-id-store', 'data'),
        State('edit-probe-name-input', 'value'),
        State('edit-probe-interval-input', 'value'),
        State('edit-probe-min-input', 'value'),
        State('edit-probe-max-input', 'value'),
        prevent_initial_call=True
    )
    def toggle_edit_modal(edit_clicks, cancel_clicks, save_clicks, is_open,
                          stored_probe_id, name_value, interval_value,
                          min_value, max_value):
        from dash import callback_context
        if not callback_context.triggered:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update

        button_id = callback_context.triggered[0]['prop_id']

        # Edit button clicked — open modal pre-populated with current values
        if 'edit-probe-btn' in button_id:
            try:
                triggered_val = callback_context.triggered[0].get('value', None)
                if not triggered_val:
                    return no_update, no_update, no_update, no_update, no_update, no_update, no_update
            except Exception:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update

            import json
            try:
                button_dict = json.loads(button_id.split('.')[0])
                probe_id = button_dict['index']

                probe_names = cfg.get('probe_names', {})
                current_name = probe_names.get(probe_id, '')

                # Per-probe interval in seconds, falling back to the global default
                probe_intervals = cfg.get('probe_intervals', {})
                global_interval_sec = cfg.get('interval_sec', 5)
                current_interval_sec = probe_intervals.get(probe_id, global_interval_sec)

                # Per-probe alert thresholds
                alert_thresholds = cfg.get('alert_thresholds', {})
                probe_thresholds = alert_thresholds.get(probe_id, {})
                current_min = probe_thresholds.get('min', None)
                current_max = probe_thresholds.get('max', None)

                return True, probe_id, probe_id, current_name, current_interval_sec, current_min, current_max
            except Exception:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update

        # Cancel button clicked
        elif 'edit-probe-cancel' in button_id:
            return False, None, '', '', no_update, no_update, no_update

        # Save button clicked
        elif 'edit-probe-save' in button_id:
            if stored_probe_id:
                # --- Save friendly name ---
                probe_names = cfg.get('probe_names', {})
                if name_value and name_value.strip():
                    probe_names[stored_probe_id] = name_value.strip()
                else:
                    probe_names.pop(stored_probe_id, None)
                cfg.update({'probe_names': probe_names})

                # --- Save alert thresholds ---
                alert_thresholds = cfg.get('alert_thresholds', {})
                probe_thresholds = {}
                try:
                    if min_value not in (None, ''):
                        probe_thresholds['min'] = float(min_value)
                except (TypeError, ValueError):
                    pass
                try:
                    if max_value not in (None, ''):
                        probe_thresholds['max'] = float(max_value)
                except (TypeError, ValueError):
                    pass
                if probe_thresholds:
                    alert_thresholds[stored_probe_id] = probe_thresholds
                else:
                    alert_thresholds.pop(stored_probe_id, None)
                cfg.update({'alert_thresholds': alert_thresholds})
                print(f'[devices_panel] Saved thresholds for {stored_probe_id}: {probe_thresholds}')

                # --- Save per-probe interval ---
                global_interval_sec = cfg.get('interval_sec', 5)
                try:
                    new_interval_sec = float(interval_value) if interval_value not in (None, '') else global_interval_sec
                    new_interval_sec = max(0.5, new_interval_sec)
                except (TypeError, ValueError):
                    new_interval_sec = global_interval_sec

                probe_intervals = cfg.get('probe_intervals', {})
                probe_intervals[stored_probe_id] = new_interval_sec
                cfg.update({'probe_intervals': probe_intervals})
                print(f'[devices_panel] Saved interval for {stored_probe_id}: {new_interval_sec} s')

                # --- Push new interval to the probe immediately (best-effort) ---
                if public_base_func is not None:
                    try:
                        from auto_provision import provision_probe
                        probes = (finder.list_probes() or {}).values()
                        for p in probes:
                            if isinstance(p, dict):
                                props = p.get('properties', {}) or {}
                                pid = props.get('id') or p.get('probe_id') or p.get('id')
                                host = p.get('ip') or p.get('host') or ''
                                port = int(p.get('port', 80) or 80)
                            else:
                                props = getattr(p, 'properties', {}) or {}
                                pid = props.get('id') or getattr(p, 'probe_id', None) or getattr(p, 'id', None)
                                host = getattr(p, 'ip', None) or getattr(p, 'host', None) or ''
                                port = int(getattr(p, 'port', 80) or 80)

                            if pid == stored_probe_id and host:
                                base = public_base_func()
                                ok = provision_probe(
                                    host.rstrip('.'), port, base,
                                    token=token or '',
                                    interval_ms=int(new_interval_sec * 1000)
                                )
                                if ok:
                                    print(f'[devices_panel] Provisioned {stored_probe_id} with interval={new_interval_sec} s')
                                else:
                                    print(f'[devices_panel] Could not reach {stored_probe_id} — interval will apply on next auto-provision cycle')
                                break
                    except Exception as e:
                        print(f'[devices_panel] Provision-on-save failed: {e}')

            return False, None, '', '', no_update, no_update, no_update

        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
