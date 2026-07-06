from dash import html, dcc, Output, Input, State, no_update, ALL
import dash_bootstrap_components as dbc
import datetime

DevicesLayout = html.Div([
    html.H4('Connected Probes'),
    html.P('Click ✏️ on a probe to rename it, calibrate it, or set alert thresholds.',
           className='text-muted small'),
    dcc.Interval(id='device-refresh', interval=5000, n_intervals=0),
    html.Div(id='device-grid', className='row g-3'),
    # Modal for editing probe name / calibration / thresholds
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Edit Probe")),
        dbc.ModalBody([
            html.Label("Probe ID:", className='fw-bold mb-1'),
            html.Div(id='edit-probe-id-display', className='mb-3 text-muted'),

            html.Label("Friendly name:", className='fw-bold mb-1'),
            dbc.Input(id='edit-probe-name-input', type='text',
                      placeholder='e.g. Kitchen Fridge', className='mb-1'),
            html.Small("Leave empty to use the probe ID.", className='text-muted d-block mb-3'),

            html.Label("Calibration offset (°C):", className='fw-bold mb-1'),
            dbc.Input(id='edit-probe-offset-input', type='number', step=0.1, value=0,
                      className='mb-1'),
            html.Small("Added to every reading. Trim to a reference (e.g. 0 °C ice bath). 0 = none.",
                       className='text-muted d-block mb-3'),

            html.Label("Alert thresholds (°C):", className='fw-bold mb-1'),
            dbc.Row([
                dbc.Col([dbc.Label("Low", className='small'),
                         dbc.Input(id='edit-probe-min-input', type='number', step=0.5)], width=6),
                dbc.Col([dbc.Label("High", className='small'),
                         dbc.Input(id='edit-probe-max-input', type='number', step=0.5)], width=6),
            ]),
            html.Small("Leave blank to use the default thresholds.", className='text-muted'),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id='edit-probe-cancel', className='me-2', color='secondary'),
            dbc.Button("Save", id='edit-probe-save', color='primary'),
        ]),
    ], id='edit-probe-modal', is_open=False),
    dcc.Store(id='edit-probe-id-store', data=None),
])


def register_devices_callbacks(app, finder, cfg):
    @app.callback(Output('device-grid', 'children'), Input('device-refresh', 'n_intervals'))
    def update_devices(_):
        try:
            probes = (finder.list_probes() or {}).values()
            cards = []
            now = datetime.datetime.now()
            probe_names = cfg.get('probe_names', {})
            calibration = cfg.get('calibration', {}) or {}
            for p in probes:
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
                            dt = datetime.datetime.fromisoformat(str(last))
                        seconds = (now - dt).total_seconds()
                        if seconds < 15:
                            status_color, delta = 'success', 'Just now'
                        elif seconds < 60:
                            status_color, delta = 'warning', f'{int(seconds)} s ago'
                        else:
                            status_color, delta = 'danger', f'{int(seconds // 60)} min ago'
                    except Exception:
                        pass

                friendly_name = probe_names.get(probe_id, None) if probe_id else None
                cal = calibration.get(probe_id, {}) if probe_id else {}
                offset = cal.get('offset_c') if isinstance(cal, dict) else None

                edit_button = html.Span(
                    '✏️',
                    id={'type': 'edit-probe-btn', 'index': probe_id or name},
                    n_clicks=0,
                    style={'cursor': 'pointer', 'fontSize': '1.2rem', 'marginLeft': '8px'},
                    title='Edit probe',
                ) if probe_id else html.Span()

                if friendly_name:
                    title_elements = [html.Div([html.H6([friendly_name, edit_button],
                                      className='fw-bold mb-1 d-inline-flex align-items-center')])]
                    if probe_id != name:
                        title_elements.append(html.Small(f'{name} (ID: {probe_id})', className='text-info d-block mb-1'))
                    else:
                        title_elements.append(html.Small(f'ID: {probe_id}', className='text-info d-block mb-1'))
                else:
                    title_elements = [html.Div([html.H6([name, edit_button],
                                      className='fw-bold mb-1 d-inline-flex align-items-center')])]
                    if probe_id and probe_id != name:
                        title_elements.append(html.Small(f'ID: {probe_id}', className='text-info d-block mb-1'))

                extra = []
                if offset:
                    extra.append(html.Small(f'Calibration: {offset:+.1f} °C', className='text-muted d-block'))

                card = dbc.Col(dbc.Card(dbc.CardBody([
                    *title_elements,
                    html.Small(f'{ip}:{port}', className='text-muted'),
                    *extra,
                    html.Div(html.Span(f'● {delta or "Unknown"}',
                             className=f'status-dot text-{status_color} fw-bold mt-2')),
                ]), className='h-100 probe-card'), width=12, lg=4, md=6)
                cards.append(card)

            if not cards:
                return [dbc.Alert('No probes discovered yet. See Settings for setup help.', color='secondary')]
            return cards
        except Exception as e:
            import traceback
            error_msg = f'Discovery service error: {str(e)}'
            print(f'[devices_panel] {error_msg}\n{traceback.format_exc()}')
            return [dbc.Alert(error_msg, color='danger')]

    @app.callback(
        Output('edit-probe-modal', 'is_open'),
        Output('edit-probe-id-store', 'data'),
        Output('edit-probe-id-display', 'children'),
        Output('edit-probe-name-input', 'value'),
        Output('edit-probe-offset-input', 'value'),
        Output('edit-probe-min-input', 'value'),
        Output('edit-probe-max-input', 'value'),
        Input({'type': 'edit-probe-btn', 'index': ALL}, 'n_clicks'),
        Input('edit-probe-cancel', 'n_clicks'),
        Input('edit-probe-save', 'n_clicks'),
        State('edit-probe-id-store', 'data'),
        State('edit-probe-name-input', 'value'),
        State('edit-probe-offset-input', 'value'),
        State('edit-probe-min-input', 'value'),
        State('edit-probe-max-input', 'value'),
        prevent_initial_call=True,
    )
    def toggle_edit_modal(edit_clicks, cancel_clicks, save_clicks, stored_probe_id,
                          name_value, offset_value, min_value, max_value):
        from dash import callback_context
        nothing = (no_update,) * 7
        if not callback_context.triggered:
            return nothing

        button_id = callback_context.triggered[0]['prop_id']

        if 'edit-probe-btn' in button_id:
            # device-grid rebuilds every refresh; ignore phantom triggers where
            # the clicked value is falsy (only act on a real click).
            try:
                if not callback_context.triggered[0].get('value', None):
                    return nothing
            except Exception:
                return nothing
            import json
            try:
                probe_id = json.loads(button_id.split('.')[0])['index']
                cur_name = (cfg.get('probe_names', {}) or {}).get(probe_id, '')
                cal = (cfg.get('calibration', {}) or {}).get(probe_id, {}) or {}
                thr = (cfg.get('alert_thresholds', {}) or {}).get(probe_id, {}) or {}
                return (True, probe_id, probe_id, cur_name,
                        cal.get('offset_c', 0) or 0, thr.get('min'), thr.get('max'))
            except Exception:
                return nothing

        elif 'edit-probe-cancel' in button_id:
            return (False, None, '', '', 0, None, None)

        elif 'edit-probe-save' in button_id:
            if stored_probe_id:
                try:
                    # Friendly name
                    probe_names = cfg.get('probe_names', {}) or {}
                    if name_value and name_value.strip():
                        probe_names[stored_probe_id] = name_value.strip()
                    else:
                        probe_names.pop(stored_probe_id, None)

                    # Calibration offset
                    calibration = cfg.get('calibration', {}) or {}
                    try:
                        off = float(offset_value or 0)
                    except (TypeError, ValueError):
                        off = 0.0
                    if off:
                        calibration[stored_probe_id] = {"offset_c": off,
                                                        "gain": calibration.get(stored_probe_id, {}).get("gain", 1.0)}
                    else:
                        calibration.pop(stored_probe_id, None)

                    # Per-probe thresholds
                    thresholds = cfg.get('alert_thresholds', {}) or {}
                    entry = {}
                    if min_value is not None and min_value != '':
                        entry['min'] = float(min_value)
                    if max_value is not None and max_value != '':
                        entry['max'] = float(max_value)
                    if entry:
                        thresholds[stored_probe_id] = entry
                    else:
                        thresholds.pop(stored_probe_id, None)

                    cfg.update({
                        'probe_names': probe_names,
                        'calibration': calibration,
                        'alert_thresholds': thresholds,
                    })
                except Exception as e:
                    print(f'[devices_panel] save failed: {e}')
            return (False, None, '', '', 0, None, None)

        return nothing
