from dash import html, dcc, Output, Input, State, no_update, ALL
import dash_bootstrap_components as dbc
import datetime

DevicesLayout = html.Div([
    html.H4('Connected Probes'),
    dcc.Interval(id='device-refresh', interval=5000, n_intervals=0),
    html.Div(id='device-grid', className='row g-3'),
    # Modal for editing probe name
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Edit Probe Name")),
        dbc.ModalBody([
            html.Div([
                html.Label("Probe ID:", className='fw-bold mb-2'),
                html.Div(id='edit-probe-id-display', className='mb-3 text-muted'),
                html.Label("Friendly Name:", className='fw-bold mb-2'),
                dbc.Input(id='edit-probe-name-input', type='text', placeholder='Enter friendly name...', className='mb-2'),
                html.Small("Leave empty to use probe ID as display name", className='text-muted')
            ])
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id='edit-probe-cancel', className='me-2', color='secondary'),
            dbc.Button("Save", id='edit-probe-save', color='primary')
        ])
    ], id='edit-probe-modal', is_open=False),
    dcc.Store(id='edit-probe-id-store', data=None)
])

def register_devices_callbacks(app, finder, cfg):
    @app.callback(Output('device-grid', 'children'), Input('device-refresh', 'n_intervals'))
    def update_devices(_):
        try:
            probes = (finder.list_probes() or {}).values()
            cards = []
            now = datetime.datetime.now()
            probe_names = cfg.get('probe_names', {})
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
                            dt = datetime.datetime.fromisoformat(str(last))
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

                # Create edit button (only if we have a probe_id)
                edit_button = html.Span(
                    '✏️',
                    id={'type': 'edit-probe-btn', 'index': probe_id or name},
                    n_clicks=0,
                    style={'cursor': 'pointer', 'fontSize': '1.2rem', 'marginLeft': '8px'},
                    title='Edit probe name'
                ) if probe_id else html.Span()

                if friendly_name:
                    # Show friendly name as primary, with probe_id as secondary
                    title_elements = [
                        html.Div([
                            html.H6([friendly_name, edit_button], className='fw-bold mb-1 d-inline-flex align-items-center')
                        ])
                    ]
                    if probe_id != name:
                        title_elements.append(html.Small(f'{name} (ID: {probe_id})', className='text-info d-block mb-1'))
                    else:
                        title_elements.append(html.Small(f'ID: {probe_id}', className='text-info d-block mb-1'))
                else:
                    # No friendly name, use original logic
                    title_elements = [
                        html.Div([
                            html.H6([name, edit_button], className='fw-bold mb-1 d-inline-flex align-items-center')
                        ])
                    ]
                    # Show probe_id if it differs from name (fixes ID mismatch issue)
                    if probe_id and probe_id != name:
                        title_elements.append(html.Small(f'ID: {probe_id}', className='text-info d-block mb-1'))

                card = dbc.Col(dbc.Card(dbc.CardBody([
                    *title_elements,
                    html.Small(f'{ip}:{port}', className='text-muted'),
                    html.Div(html.Span(f'● {delta or "Unknown"}', className=f'status-dot text-{status_color} fw-bold mt-2'))
                ]), className='h-100 probe-card'), width=12, lg=4, md=6)
                cards.append(card)

            if not cards:
                return [dbc.Alert('No probes discovered yet.', color='secondary')]
            return cards
        except Exception as e:
            import traceback
            error_msg = f'Discovery service error: {str(e)}'
            print(f'[devices_panel] {error_msg}\n{traceback.format_exc()}')
            return [dbc.Alert(error_msg, color='danger')]

    # Open modal when edit button clicked
    @app.callback(
        Output('edit-probe-modal', 'is_open'),
        Output('edit-probe-id-store', 'data'),
        Output('edit-probe-id-display', 'children'),
        Output('edit-probe-name-input', 'value'),
        Input({'type': 'edit-probe-btn', 'index': ALL}, 'n_clicks'),
        Input('edit-probe-cancel', 'n_clicks'),
        Input('edit-probe-save', 'n_clicks'),
        State('edit-probe-modal', 'is_open'),
        State('edit-probe-id-store', 'data'),
        State('edit-probe-name-input', 'value'),
        prevent_initial_call=True
    )
    def toggle_edit_modal(edit_clicks, cancel_clicks, save_clicks, is_open, stored_probe_id, input_value):
        from dash import callback_context
        if not callback_context.triggered:
            return no_update, no_update, no_update, no_update

        button_id = callback_context.triggered[0]['prop_id']

        # Edit button clicked
        if 'edit-probe-btn' in button_id:
            # IMPORTANT: device-grid is rebuilt every refresh. Pattern-matching inputs can
            # "trigger" on refresh even when the user didn't click. Only open the modal
            # when the triggered n_clicks value is truthy (>0).
            try:
                triggered_val = callback_context.triggered[0].get('value', None)
                if not triggered_val:
                    return no_update, no_update, no_update, no_update
            except Exception:
                return no_update, no_update, no_update, no_update

            # Extract the probe_id from the clicked button
            import json
            try:
                # Parse the pattern matching ID
                button_dict = json.loads(button_id.split('.')[0])
                probe_id = button_dict['index']

                # Get current friendly name if it exists
                probe_names = cfg.get('probe_names', {})
                current_name = probe_names.get(probe_id, '')

                return True, probe_id, probe_id, current_name
            except Exception:
                return no_update, no_update, no_update, no_update

        # Cancel button clicked
        elif 'edit-probe-cancel' in button_id:
            return False, None, '', ''

        # Save button clicked
        elif 'edit-probe-save' in button_id:
            if stored_probe_id:
                # Save the name to config
                probe_names = cfg.get('probe_names', {})
                if input_value and input_value.strip():
                    probe_names[stored_probe_id] = input_value.strip()
                else:
                    # Remove the friendly name if empty
                    probe_names.pop(stored_probe_id, None)

                cfg.update({'probe_names': probe_names})
                print(f'[devices_panel] Saved friendly name for {stored_probe_id}: {input_value}')

            return False, None, '', ''

        return no_update, no_update, no_update, no_update
