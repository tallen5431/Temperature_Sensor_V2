import datetime
import logging

from dash import html, dcc, Output, Input, State, no_update, ALL
import dash_bootstrap_components as dbc

from core.status import probe_fresh_window
from core.metrics import LATEST

log = logging.getLogger("hub.devices")

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
                html.Hr(),
                html.Label("Calibration Offset (°C):", className='fw-bold mb-2 mt-1 d-block'),
                dbc.Input(
                    id='edit-probe-cal-input',
                    type='number',
                    step=0.1,
                    placeholder='e.g. -0.5',
                    className='mb-1'
                ),
                html.Small("Added to every reading from this probe to correct sensor error", className='text-muted'),
            ])
        ]),
        dbc.ModalFooter([
            dbc.Button("🗑 Remove device", id='edit-probe-remove', color='danger',
                       outline=True, className='me-auto'),
            dbc.Button("Cancel", id='edit-probe-cancel', className='me-2', color='secondary'),
            dbc.Button("Save", id='edit-probe-save', color='primary')
        ])
    ], id='edit-probe-modal', is_open=False),
    dcc.Store(id='edit-probe-id-store', data=None),
    dcc.Store(id='remove-probe-id-store', data=None),
    # Confirmation dialog for the destructive "remove device" action.
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Remove device?")),
        dbc.ModalBody(id='remove-confirm-text'),
        dbc.ModalFooter([
            dbc.Button("Cancel", id='remove-confirm-cancel', color='secondary', className='me-2'),
            dbc.Button("Remove", id='remove-confirm-yes', color='danger'),
        ]),
    ], id='remove-confirm-modal', is_open=False),
    html.Div(id='device-remove-status', className='mt-3'),
])


def register_devices_callbacks(app, finder, cfg, db=None, public_base_func=None, token=""):
    @app.callback(Output('device-grid', 'children'), Input('device-refresh', 'n_intervals'))
    def update_devices(_):
        try:
            now = datetime.datetime.now()
            probe_names = cfg.get('probe_names', {})
            probe_intervals = cfg.get('probe_intervals', {})

            # Normalise every mDNS-discovered probe into a plain dict, keyed by id.
            merged = {}
            for p in (finder.list_probes() or {}).values():
                if isinstance(p, dict):
                    props = p.get('properties', {}) or {}
                    nm = p.get('name') or props.get('name') or props.get('id') or p.get('id') or 'Unknown'
                    pid = props.get('id') or p.get('probe_id') or p.get('id')
                    ipx = p.get('ip') or p.get('host') or 'N/A'
                    prt = p.get('port', 80)
                    lst = p.get('last_seen')
                else:
                    props = getattr(p, 'properties', {}) or {}
                    nm = getattr(p, 'name', None) or getattr(p, 'id', None) or props.get('name') or props.get('id') or 'Unknown'
                    pid = props.get('id') or getattr(p, 'probe_id', None) or getattr(p, 'id', None)
                    ipx = getattr(p, 'ip', None) or getattr(p, 'host', None) or 'N/A'
                    prt = getattr(p, 'port', 80)
                    lst = getattr(p, 'last_seen', None)
                key = pid or nm
                merged[key] = {'name': nm, 'probe_id': pid, 'ip': ipx, 'port': prt, 'last_seen': lst}

            # Add probes known only from ingest (e.g. deep-sleep probes whose radio
            # is off between readings, so mDNS never discovers them) so they are
            # still visible and manageable here.
            if db is not None:
                try:
                    for _, r in db.latest_per_probe(window_seconds=7 * 86400).iterrows():
                        pid = r['probe_id']
                        if not str(pid).strip() or pid in merged:
                            continue
                        last = None
                        try:
                            last = datetime.datetime.fromisoformat(
                                str(r['timestamp']).rstrip('Z')).timestamp()
                        except Exception:
                            pass
                        merged[pid] = {'name': pid, 'probe_id': pid, 'ip': 'via readings',
                                       'port': '', 'last_seen': last}
                except Exception:
                    log.debug('devices: DB probe merge failed', exc_info=True)

            cards = []
            for info in merged.values():
                name = info['name']
                probe_id = info['probe_id']
                ip = info['ip']
                port = info['port']
                last = info['last_seen']

                delta = ''
                status_color = 'secondary'
                if last:
                    try:
                        if isinstance(last, (int, float)):
                            dt = datetime.datetime.fromtimestamp(last)
                        else:
                            dt = datetime.datetime.fromisoformat(str(last).rstrip('Z'))
                        seconds = (now - dt).total_seconds()
                        # Colour by the SAME interval-aware freshness window the
                        # dashboard/footer/Diagnostics use, so a probe reporting on
                        # its normal (possibly slow deep-sleep) cadence is not shown
                        # red here while every other view calls it online.
                        fresh = seconds <= probe_fresh_window(cfg, probe_id)
                        status_color = 'success' if fresh else 'danger'
                        if seconds < 15:
                            delta = 'Just now'
                        elif seconds < 60:
                            delta = f'{int(seconds)} s ago'
                        elif seconds < 3600:
                            delta = f'{int(seconds // 60)} min ago'
                        else:
                            delta = f'{int(seconds // 3600)} h ago'
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
                    html.Small(f'{ip}:{port}' if port else str(ip), className='text-muted'),
                ]
                if interval_note:
                    card_body_children.append(interval_note)
                # Label the state in WORDS, not colour alone (WCAG 1.4.1) — and
                # consistently with Diagnostics ("online"/"offline") and the
                # Dashboard cards ("OK"/"stale"). A colourblind user (or anyone on
                # a poor display) could otherwise not tell two "5 min ago" probes
                # apart when one is offline.
                state_word = {'success': 'Online', 'danger': 'Offline',
                              'secondary': 'Unknown'}.get(status_color, '')
                status_text = f'{state_word} · {delta}' if (state_word and delta) \
                    else (state_word or delta or 'Unknown')
                card_body_children.append(
                    html.Div(html.Span(f'● {status_text}', className=f'status-dot text-{status_color} fw-bold mt-2'))
                )

                card = dbc.Col(dbc.Card(dbc.CardBody(card_body_children), className='h-100 probe-card'), width=12, lg=4, md=6)
                cards.append(card)

            if not cards:
                return [dbc.Alert([
                    html.H6('No probes discovered yet', className='alert-heading'),
                    html.P('Power on a probe on the same Wi-Fi network — it appears here '
                           'within ~20 seconds.', className='mb-1'),
                    html.Small('First-time setup? See Settings → Probe Setup Helper.',
                               className='text-muted'),
                ], color='secondary')]
            return cards
        except Exception as e:
            log.exception('Discovery service error')
            return [dbc.Alert(f'Discovery service error: {e}', color='danger')]

    # Open modal when edit button clicked, close on cancel/save
    @app.callback(
        Output('edit-probe-modal', 'is_open'),
        Output('edit-probe-id-store', 'data'),
        Output('edit-probe-id-display', 'children'),
        Output('edit-probe-name-input', 'value'),
        Output('edit-probe-interval-input', 'value'),
        Output('edit-probe-min-input', 'value'),
        Output('edit-probe-max-input', 'value'),
        Output('edit-probe-cal-input', 'value'),
        Input({'type': 'edit-probe-btn', 'index': ALL}, 'n_clicks'),
        Input('edit-probe-cancel', 'n_clicks'),
        Input('edit-probe-save', 'n_clicks'),
        State('edit-probe-modal', 'is_open'),
        State('edit-probe-id-store', 'data'),
        State('edit-probe-name-input', 'value'),
        State('edit-probe-interval-input', 'value'),
        State('edit-probe-min-input', 'value'),
        State('edit-probe-max-input', 'value'),
        State('edit-probe-cal-input', 'value'),
        prevent_initial_call=True
    )
    def toggle_edit_modal(edit_clicks, cancel_clicks, save_clicks, is_open,
                          stored_probe_id, name_value, interval_value,
                          min_value, max_value, cal_value):
        from dash import callback_context
        if not callback_context.triggered:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        button_id = callback_context.triggered[0]['prop_id']

        # Edit button clicked — open modal pre-populated with current values
        if 'edit-probe-btn' in button_id:
            try:
                triggered_val = callback_context.triggered[0].get('value', None)
                if not triggered_val:
                    return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
            except Exception:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

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

                # Per-probe calibration offset
                current_cal = (cfg.get('calibration_offsets', {}) or {}).get(probe_id, None)

                return True, probe_id, probe_id, current_name, current_interval_sec, current_min, current_max, current_cal
            except Exception:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        # Cancel button clicked
        elif 'edit-probe-cancel' in button_id:
            return False, None, '', '', no_update, no_update, no_update, no_update

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
                # Guard against an inverted range (min > max): threshold_breach
                # checks 'value > max' first, so with min=30/max=10 essentially
                # EVERY reading is classified as a breach and the probe alerts
                # forever. Swap so the stored range is always valid.
                if ('min' in probe_thresholds and 'max' in probe_thresholds
                        and probe_thresholds['min'] > probe_thresholds['max']):
                    probe_thresholds['min'], probe_thresholds['max'] = (
                        probe_thresholds['max'], probe_thresholds['min'])
                    log.warning('Probe %s: min > max on save, swapped to %s',
                                stored_probe_id, probe_thresholds)
                if probe_thresholds:
                    alert_thresholds[stored_probe_id] = probe_thresholds
                else:
                    alert_thresholds.pop(stored_probe_id, None)
                cfg.update({'alert_thresholds': alert_thresholds})

                # --- Save per-probe calibration offset ---
                calibration_offsets = cfg.get('calibration_offsets', {})
                try:
                    if cal_value not in (None, ''):
                        calibration_offsets[stored_probe_id] = float(cal_value)
                    else:
                        calibration_offsets.pop(stored_probe_id, None)
                except (TypeError, ValueError):
                    calibration_offsets.pop(stored_probe_id, None)
                cfg.update({'calibration_offsets': calibration_offsets})

                # --- Save per-probe interval (only when it actually differs) ---
                # The modal pre-fills this field with the EFFECTIVE interval
                # (override if present, else the global default), so writing it
                # unconditionally created a spurious per-probe override the first
                # time only a name/threshold was edited — silently decoupling the
                # probe from the global default and re-provisioning it every save.
                # Persist an override only when the value truly differs from global.
                global_interval_sec = cfg.get('interval_sec', 5)
                probe_intervals = cfg.get('probe_intervals', {})
                prev_override = probe_intervals.get(stored_probe_id)
                try:
                    prev_effective = float(prev_override if prev_override is not None
                                           else global_interval_sec)
                except (TypeError, ValueError):
                    prev_effective = float(global_interval_sec)

                if interval_value in (None, ''):
                    new_interval_sec = float(global_interval_sec)  # blank = inherit global
                else:
                    try:
                        new_interval_sec = max(0.5, float(interval_value))
                    except (TypeError, ValueError):
                        new_interval_sec = prev_effective

                if new_interval_sec == float(global_interval_sec):
                    probe_intervals.pop(stored_probe_id, None)  # inherit, no override stored
                else:
                    probe_intervals[stored_probe_id] = new_interval_sec
                cfg.update({'probe_intervals': probe_intervals})
                interval_changed = new_interval_sec != prev_effective
                if interval_changed:
                    log.info('Saved interval for %s: %s s', stored_probe_id, new_interval_sec)

                # --- Push new interval to the probe immediately (best-effort) ---
                # Only when the interval actually changed — a name/threshold-only
                # edit must not trigger an HTTP re-provision round-trip.
                if interval_changed and public_base_func is not None:
                    try:
                        from provisioning import provision_probe
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
                                    log.info('Provisioned %s with interval=%s s', stored_probe_id, new_interval_sec)
                                else:
                                    log.info('Could not reach %s — interval will apply on next auto-provision cycle', stored_probe_id)
                                break
                    except Exception as e:
                        log.warning('Provision-on-save failed: %s', e)

            return False, None, '', '', no_update, no_update, no_update, no_update

        return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

    # --- Remove device: confirm, then delete readings + config + discovery ----
    @app.callback(
        Output('remove-confirm-modal', 'is_open'),
        Output('remove-confirm-text', 'children'),
        Output('remove-probe-id-store', 'data'),
        Output('edit-probe-modal', 'is_open', allow_duplicate=True),
        Input('edit-probe-remove', 'n_clicks'),
        State('edit-probe-id-store', 'data'),
        prevent_initial_call=True,
    )
    def open_remove_confirm(n_clicks, probe_id):
        if not n_clicks or not probe_id:
            return no_update, no_update, no_update, no_update
        friendly = (cfg.get('probe_names', {}) or {}).get(probe_id, probe_id)
        heading = friendly if friendly == probe_id else f'{friendly} ({probe_id})'
        text = html.Div([
            html.P(html.Strong(heading), className='mb-2'),
            html.P("This permanently deletes all of this probe's readings and its saved "
                   "name, alert thresholds, calibration and interval. This cannot be undone.",
                   className='mb-2'),
            html.Small("If the probe is still powered on it will reappear on its next "
                       "reading — power it off first to remove it for good.",
                       className='text-muted'),
        ])
        # Close the edit modal and open the confirmation dialog for this probe.
        return True, text, probe_id, False

    @app.callback(
        Output('remove-confirm-modal', 'is_open', allow_duplicate=True),
        Output('device-remove-status', 'children'),
        Input('remove-confirm-yes', 'n_clicks'),
        Input('remove-confirm-cancel', 'n_clicks'),
        State('remove-probe-id-store', 'data'),
        prevent_initial_call=True,
    )
    def do_remove_device(yes_clicks, cancel_clicks, probe_id):
        from dash import callback_context
        trig = callback_context.triggered[0]['prop_id'] if callback_context.triggered else ''
        if 'remove-confirm-cancel' in trig:
            return False, no_update
        if 'remove-confirm-yes' not in trig or not probe_id:
            return no_update, no_update
        try:
            deleted = db.delete_probe(probe_id) if db is not None else 0
            # Drop this probe's entry from every per-probe config dict.
            for key in ('probe_names', 'probe_intervals', 'alert_thresholds', 'calibration_offsets'):
                d = cfg.get(key, {}) or {}
                if probe_id in d:
                    d.pop(probe_id, None)
                    cfg.update({key: d})
            forgotten = 0
            try:
                forgotten = finder.forget_probe(probe_id)
            except Exception:
                log.debug('forget_probe unavailable/failed for %s', probe_id, exc_info=True)
            # Drop the probe from the Prometheus latest-reading registry too, so
            # /metrics stops serving its frozen last temperature after removal
            # (every other surface drops it immediately — keep /metrics in step).
            try:
                LATEST.evict(probe_id)
            except Exception:
                log.debug('LATEST.evict failed for %s', probe_id, exc_info=True)
            log.info('Removed device %s (%d readings, %d discovery entries)',
                     probe_id, deleted, forgotten)
            msg = dbc.Alert(f"✅ Removed {probe_id} — deleted {deleted:,} reading(s). "
                            "The card disappears within a few seconds.",
                            color='success', dismissable=True, className='mb-0')
            return False, msg
        except Exception as e:
            log.exception('device removal failed')
            return False, dbc.Alert(f"Could not remove device: {e}", color='danger',
                                    dismissable=True, className='mb-0')
