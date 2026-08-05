import datetime
import logging

import pandas as pd
from dash import html, dcc, Output, Input, State, no_update, ALL
import dash_bootstrap_components as dbc

from core.probes import discovered_probes, probe_address
from core.status import probe_fresh_window
from core.metrics import LATEST
from core.alerts import HELD
from core import units

log = logging.getLogger("hub.devices")


# --- Unit conversion helpers -------------------------------------------------
# The dashboard's unit toggle (temp-unit-store) affects DISPLAY only; config
# always stores Celsius. The arithmetic lives in core.units; these thin aliases
# pin the 2-decimal rounding the edit form wants, so an operator sees 35.6 in a
# number input rather than 35.60000000000001. Absolute temperatures (thresholds)
# and temperature DELTAS (the calibration offset) convert differently -- see
# core.units for why.

def _unit_symbol(unit):
    return units.unit_symbol(unit)


def temp_c_to_unit(temp_c, unit):
    """Convert an absolute Celsius temperature to ``unit`` for display."""
    return units.to_unit(temp_c, unit, ndigits=2)


def temp_unit_to_c(value, unit):
    """Convert an absolute temperature entered in ``unit`` back to Celsius."""
    return units.from_unit(value, unit, ndigits=2)


def delta_c_to_unit(delta_c, unit):
    """Convert a Celsius temperature DELTA (calibration offset) to ``unit``."""
    return units.delta_to_unit(delta_c, unit, ndigits=2)


def delta_unit_to_c(value, unit):
    """Convert a temperature DELTA entered in ``unit`` back to Celsius."""
    return units.delta_from_unit(value, unit, ndigits=2)


def _humanize_seconds(seconds):
    """Render a reporting interval the way an operator would say it.

    Intervals here span 0.5 s to hours, so a bare seconds count stops being
    readable fast ("reports every 3600 s"). Pure and module-level so it can be
    unit-tested alongside the conversion helpers above.
    """
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "a while"
    if s < 60:
        return f"{s:g} s"
    if s < 3600:
        m = s / 60.0
        return f"{m:g} minute" + ("" if m == 1 else "s")
    h = s / 3600.0
    return f"{h:g} hour" + ("" if h == 1 else "s")


DevicesLayout = html.Div([
    html.H4('Connected Probes'),
    # Mirror of the dashboard's unit picker. Only one page renders at a time, so
    # the id never collides; storage_type='local' means both stores read the
    # SAME persisted browser value, letting the edit modal know the active unit
    # even though the dashboard (and its store) is not mounted on this page.
    # No default, matching the dashboard's store: seeding 'celsius' here would
    # write a choice the user never made, and the dashboard's locale probe would
    # then never run for anyone who happened to open Devices first.
    dcc.Store(id='temp-unit-store', storage_type='local'),
    dcc.Interval(id='device-refresh', interval=5000, n_intervals=0),
    html.Div(id='device-grid', className='row g-3'),
    # Modal for editing a probe. What almost every edit is actually for — the
    # name and the two alert limits — is visible; the sensor-level tuning that
    # only a handful of deployments ever touch (resolution, calibration) is
    # folded behind "Advanced". The fields stay mounted either way, so the Save
    # callback's States resolve whether or not it was opened.
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
                html.Label("Alert Thresholds (°C):", id='edit-probe-thresholds-label',
                           className='fw-bold mb-2 mt-1 d-block'),
                dbc.Row([
                    dbc.Col([
                        html.Small("Min Temperature", className='text-muted d-block mb-1'),
                        dbc.Input(
                            id='edit-probe-min-input',
                            type='number',
                            step=0.5,
                            placeholder='e.g. 1',
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
                            placeholder='e.g. 5',
                            className='mb-1'
                        ),
                        html.Small("Alert when above this value", className='text-muted'),
                    ], width=6),
                ]),
                html.Small("Leave blank to disable threshold alerts for this probe", className='text-muted d-block mt-1'),
                html.Small(
                    "Breaches always show on the dashboard; email/webhook "
                    "notifications are configured in Settings → Alerts & notifications.",
                    id='edit-probe-alerts-breadcrumb', className='text-muted d-block mt-1'),
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

                # Wrapped so the toggle starts its own line rather than tucking
                # itself onto the end of the interval field's help text.
                html.Div(dbc.Button("▸ Advanced", id='device-advanced-toggle',
                                    color='link', size='sm',
                                    className='p-0 advanced-toggle'),
                         className='mt-3'),
                dbc.Collapse(html.Div([
                    html.Label("Sensor Resolution:", className='fw-bold mb-2 mt-1 d-block'),
                    dbc.Select(
                        id='edit-probe-resolution-input',
                        options=[
                            {'label': '9-bit — 0.5 °C steps (fastest, ~94 ms)', 'value': '9'},
                            {'label': '10-bit — 0.25 °C steps (~188 ms)', 'value': '10'},
                            {'label': '11-bit — 0.125 °C steps (default, ~375 ms)', 'value': '11'},
                            {'label': '12-bit — 0.0625 °C steps (finest, ~750 ms)', 'value': '12'},
                        ],
                        value='11',
                        className='mb-1',
                    ),
                    html.Small("Higher resolution resolves finer detail but converts slower. "
                               "12-bit (750 ms) exceeds a 0.5 s interval and caps the max sample "
                               "rate. Changes the step size, not absolute accuracy (~±0.5 °C).",
                               className='text-muted'),
                    html.Hr(),
                    html.Label("Calibration Offset (°C):", id='edit-probe-cal-label',
                               className='fw-bold mb-2 mt-1 d-block'),
                    dbc.Input(
                        id='edit-probe-cal-input',
                        type='number',
                        step=0.1,
                        placeholder='e.g. -0.5',
                        className='mb-1'
                    ),
                    html.Small("Added to every reading from this probe to correct sensor error", className='text-muted'),
                ], className='advanced-body'), id='device-advanced-collapse', is_open=False),
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
    # Filled by report_save_delivery(). A settings change is delivered by the
    # probe PULLING it off an /api/ingest reply, so on a long deep-sleep interval
    # it lands on the probe's next check-in, not on Save. Without this the modal
    # just closes and the operator has no way to tell a slow delivery from a
    # broken one -- the hub cannot query a sleeping probe to confirm.
    html.Div(id='device-save-status', className='mt-3'),
])


def register_devices_callbacks(app, finder, cfg, db=None, public_base_func=None, token=""):
    @app.callback(
        Output('device-advanced-collapse', 'is_open'),
        Output('device-advanced-toggle', 'children'),
        Input('device-advanced-toggle', 'n_clicks'),
        State('device-advanced-collapse', 'is_open'),
        prevent_initial_call=True,
    )
    def toggle_device_advanced(_n, is_open):
        return (not is_open), ('▾ Advanced' if not is_open else '▸ Advanced')

    @app.callback(Output('device-grid', 'children'),
                  Input('device-refresh', 'n_intervals'),
                  Input('temp-unit-store', 'data'))
    def update_devices(_, temp_unit):
        try:
            now = datetime.datetime.now()
            probe_names = cfg.get('probe_names', {})
            probe_intervals = cfg.get('probe_intervals', {})

            # Normalise every mDNS-discovered probe into a plain dict, keyed by id.
            # core.probes owns the dict-or-dataclass reading rule for every
            # surface, so this grid can never disagree with /api/probes or
            # Diagnostics about which probe it is looking at.
            merged = {}
            for p in discovered_probes(finder):
                nm = p['name'] or 'Unknown'
                pid = p['probe_id'] or None
                merged[pid or nm] = {'name': nm, 'probe_id': pid,
                                     'ip': probe_address(p) or 'N/A',
                                     'port': p['port'], 'last_seen': p['last_seen']}

            # The latest reading for EVERY probe, not just the ones mDNS missed.
            # This page is where an operator looks after a probe, and it could
            # not tell them the one thing they came to find out — what it reads
            # right now — so every question sent them back to the dashboard.
            if db is not None:
                try:
                    for _, r in db.latest_per_probe(window_seconds=7 * 86400).iterrows():
                        pid = r['probe_id']
                        if not str(pid).strip():
                            continue
                        last = None
                        try:
                            last = datetime.datetime.fromisoformat(
                                str(r['timestamp']).rstrip('Z')).timestamp()
                        except Exception:
                            pass
                        reading = {'temperature_c': r.get('temperature_c'),
                                   'battery_pct': r.get('battery_pct')}
                        if pid in merged:
                            merged[pid].update(reading)
                            # A probe reporting by ingest is live even when mDNS
                            # last saw it minutes ago (deep sleep); take the newer
                            # of the two so the status word matches the reading.
                            if last and (not merged[pid].get('last_seen')
                                         or last > merged[pid]['last_seen']):
                                merged[pid]['last_seen'] = last
                        else:
                            merged[pid] = {'name': pid, 'probe_id': pid,
                                           'ip': '', 'port': '', 'last_seen': last,
                                           **reading}
                except Exception:
                    log.debug('devices: DB probe merge failed', exc_info=True)

            cards = []
            for info in merged.values():
                name = info['name']
                probe_id = info['probe_id']
                ip = info['ip']
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

                # Create edit button (only if we have a probe_id)
                edit_button = dbc.Button(
                    'Edit',
                    id={'type': 'edit-probe-btn', 'index': probe_id or name},
                    n_clicks=0,
                    size='sm',
                    outline=True,
                    color='secondary',
                    className='ms-2',
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

                # --- the reading, which is why anyone opens this page ---------
                t_c = info.get('temperature_c')
                thr = (cfg.get('alert_thresholds', {}) or {}).get(probe_id) or {}
                watched = thr.get('min') is not None or thr.get('max') is not None
                reading_row = None
                if t_c is not None and pd.notna(t_c):
                    breach = HELD.get(probe_id) if probe_id else None
                    if breach in ('high', 'low'):
                        val_cls, badge, badge_cls = 'text-danger', 'ALARM', 'text-danger'
                    elif status_color != 'success':
                        val_cls, badge, badge_cls = 'text-muted', 'STALE', 'text-warning'
                    elif not watched:
                        # "OK" means "inside its limits". With no limits set,
                        # nothing is checking this probe, and calling it OK is a
                        # judgement the hub is not in a position to make -- it is
                        # also the exact case an operator most wants flagged.
                        val_cls, badge, badge_cls = 'text-body', 'NO ALARM SET', 'text-muted'
                    else:
                        val_cls, badge, badge_cls = 'text-success', 'OK', 'text-success'
                    reading_row = html.Div([
                        html.Span(f'{temp_c_to_unit(t_c, temp_unit):.1f} {_unit_symbol(temp_unit)}',
                                  className=f'probe-reading {val_cls}'),
                        html.Span(f'● {badge}',
                                  className=f'{badge_cls} small fw-bold ms-2 align-middle'),
                    ], className='d-flex align-items-baseline justify-content-between mt-1 mb-2')

                # --- the range it is held to, and how often it reports ---------
                facts = []
                lo, hi = thr.get('min'), thr.get('max')
                if lo is not None or hi is not None:
                    lo_s = (f'{temp_c_to_unit(lo, temp_unit):.1f}' if lo is not None else '—')
                    hi_s = (f'{temp_c_to_unit(hi, temp_unit):.1f}' if hi is not None else '—')
                    facts.append(('Alarm range', f'{lo_s} to {hi_s} {_unit_symbol(temp_unit)}'))
                else:
                    facts.append(('Alarm range', 'not set'))
                # Always shown. Previously only a per-probe OVERRIDE appeared, so
                # the common case — every probe on the global interval — showed
                # nothing, and the page looked like it did not know.
                try:
                    secs = float(probe_intervals.get(probe_id, cfg.get('interval_sec', 5)))
                    facts.append(('Reports', f'every {_humanize_seconds(secs)}'))
                except (TypeError, ValueError):
                    pass
                offset = (cfg.get('calibration_offsets', {}) or {}).get(probe_id)
                if offset:
                    try:
                        facts.append(('Calibration',
                                      f'{delta_c_to_unit(float(offset), temp_unit):+.2f} '
                                      f'{_unit_symbol(temp_unit)}'))
                    except (TypeError, ValueError):
                        pass

                card_body_children = [*title_elements]
                if reading_row is not None:
                    card_body_children.append(reading_row)
                card_body_children.append(html.Div([
                    html.Div([html.Span(k, className='probe-fact-k'),
                              html.Span(v, className='probe-fact-v')],
                             className='probe-fact')
                    for k, v in facts
                ], className='mb-2'))
                # Identity last and muted: useful when it matters, never the
                # headline. "via readings" was internal jargon for "mDNS never
                # saw this one", which is not a fact a customer needs on a card.
                # The IP only, never ip:port. core.probes.probe_port defaults to 80,
                # so a probe the hub knows only from its ingest posts rendered
                # "127.0.0.1:80" — a port it has never advertised, shown as fact.
                addr = str(ip).strip() if ip else ''
                if addr in ('N/A', 'via readings'):
                    addr = ''
                card_body_children.append(
                    html.Small(addr or 'Reporting over Wi-Fi', className='text-muted d-block'))
                # Battery level rides along DB-merged rows (latest_per_probe);
                # mDNS-only entries have no reading and therefore no battery.
                # Same presentation as the dashboard probe cards.
                batt = info.get('battery_pct')
                if batt is not None and pd.notna(batt):
                    batt_cls = 'text-warning' if float(batt) < 20 else 'text-muted'
                    card_body_children.append(
                        html.Small(f'Batt {float(batt):.0f}%', className=f'd-block {batt_cls}'))
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
                    html.Small('First-time setup? See Settings → Set up a new probe.',
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
        Output('edit-probe-resolution-input', 'value'),
        Output('edit-probe-thresholds-label', 'children'),
        Output('edit-probe-cal-label', 'children'),
        Output('edit-probe-alerts-breadcrumb', 'children'),
        # Appended LAST because the handler appends them last. Dash matches
        # Outputs to the returned tuple positionally, so an Output added in the
        # middle silently takes a neighbour's value -- which is exactly what
        # happened here: the placeholders received the calibration label.
        Output('edit-probe-min-input', 'placeholder'),
        Output('edit-probe-max-input', 'placeholder'),
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
        State('edit-probe-resolution-input', 'value'),
        State('temp-unit-store', 'data'),
        prevent_initial_call=True
    )
    def toggle_edit_modal(edit_clicks, cancel_clicks, save_clicks, is_open,
                          stored_probe_id, name_value, interval_value,
                          min_value, max_value, cal_value, resolution_value,
                          temp_unit):
        from dash import callback_context
        # Config always stores Celsius; the modal displays/accepts the unit the
        # dashboard is currently showing so users never convert by hand.
        unit = temp_unit or 'celsius'
        # Must equal the Output count of this callback.
        noup = (no_update,) * 14
        if not callback_context.triggered:
            return noup

        button_id = callback_context.triggered[0]['prop_id']

        # Edit button clicked — open modal pre-populated with current values
        if 'edit-probe-btn' in button_id:
            try:
                triggered_val = callback_context.triggered[0].get('value', None)
                if not triggered_val:
                    return noup
            except Exception:
                return noup

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

                # Per-probe DS18B20 resolution (Select value is a string), else global default
                from provisioning import clamp_resolution_bits
                probe_resolutions = cfg.get('probe_resolutions', {})
                global_res = cfg.get('resolution_bits', 11)
                current_res = str(clamp_resolution_bits(
                    probe_resolutions.get(probe_id, global_res), default=global_res))

                # Display the stored Celsius values in the dashboard's active
                # unit; note the offset is a DELTA (different F conversion).
                disp_min = temp_c_to_unit(current_min, unit)
                disp_max = temp_c_to_unit(current_max, unit)
                disp_cal = delta_c_to_unit(current_cal, unit)
                sym = _unit_symbol(unit)
                thresholds_label = f"Alert Thresholds ({sym}):"
                cal_label = f"Calibration Offset ({sym}):"

                # What is this probe reading RIGHT NOW? Setting a safety limit
                # without it means doing arithmetic in your head against a number
                # on the page behind the modal — and a range typed in the wrong
                # unit looks perfectly reasonable until it is next to the reading.
                now_note = ''
                if db is not None:
                    try:
                        df = db.latest_per_probe(window_seconds=7 * 86400)
                        row = df[df['probe_id'] == probe_id]
                        if not row.empty:
                            t_c = row.iloc[0]['temperature_c']
                            if t_c is not None and pd.notna(t_c):
                                now_note = (f"This probe currently reads "
                                            f"{temp_c_to_unit(float(t_c), unit):.1f} {sym}. ")
                    except Exception:  # noqa: BLE001 - a hint must not block editing
                        now_note = ''

                # Breadcrumb: where notifications live + the LIVE master-switch
                # state, read from config at open so it is never stale.
                alerts_on = bool((cfg.get('notifications', {}) or {}).get('enabled', False))
                breadcrumb = (now_note +
                              "Breaches always show on the dashboard; email/webhook "
                              "notifications are configured in Settings → Alerts & notifications — "
                              f"currently {'On' if alerts_on else 'Off'}.")

                # A walk-in cooler, in whichever unit the operator reads. Rounded:
                # it is an EXAMPLE, and "e.g. 33.8" reads like a measurement
                # someone should match rather than a number to replace.
                ph_min = f"e.g. {round(temp_c_to_unit(1.0, unit)):g}"
                ph_max = f"e.g. {round(temp_c_to_unit(5.0, unit)):g}"
                return (True, probe_id, probe_id, current_name, current_interval_sec,
                        disp_min, disp_max, disp_cal, current_res,
                        thresholds_label, cal_label, breadcrumb, ph_min, ph_max)
            except Exception:
                return noup

        # Cancel button clicked
        elif 'edit-probe-cancel' in button_id:
            return (False, None, '', '', no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update)

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

                # --- Save alert thresholds (entered in the display unit,
                # stored in Celsius) ---
                alert_thresholds = cfg.get('alert_thresholds', {})
                probe_thresholds = {}
                try:
                    if min_value not in (None, ''):
                        probe_thresholds['min'] = temp_unit_to_c(float(min_value), unit)
                except (TypeError, ValueError):
                    pass
                try:
                    if max_value not in (None, ''):
                        probe_thresholds['max'] = temp_unit_to_c(float(max_value), unit)
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

                # --- Save per-probe calibration offset (a DELTA: convert with
                # the scale factor only — no +32 shift for Fahrenheit) ---
                calibration_offsets = cfg.get('calibration_offsets', {})
                try:
                    if cal_value not in (None, ''):
                        calibration_offsets[stored_probe_id] = delta_unit_to_c(
                            float(cal_value), unit)
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

                # --- Save per-probe DS18B20 resolution (only when it differs from
                # the global default), mirroring the interval logic so a
                # name/threshold-only edit never writes a spurious override. ---
                from provisioning import clamp_resolution_bits
                global_res = int(cfg.get('resolution_bits', 11) or 11)
                probe_resolutions = cfg.get('probe_resolutions', {})
                prev_res_bits = clamp_resolution_bits(
                    probe_resolutions.get(stored_probe_id, global_res), default=global_res)
                new_res_bits = clamp_resolution_bits(resolution_value, default=global_res)
                if new_res_bits == global_res:
                    probe_resolutions.pop(stored_probe_id, None)  # inherit global
                else:
                    probe_resolutions[stored_probe_id] = new_res_bits
                cfg.update({'probe_resolutions': probe_resolutions})
                resolution_changed = new_res_bits != prev_res_bits
                if resolution_changed:
                    log.info('Saved resolution for %s: %s-bit', stored_probe_id, new_res_bits)

                # --- Push new interval/resolution to the probe immediately (best-effort) ---
                # Only when the interval OR resolution actually changed — a
                # name/threshold-only edit must not trigger an HTTP re-provision.
                if (interval_changed or resolution_changed) and public_base_func is not None:
                    try:
                        from provisioning import provision_probe
                        for p in discovered_probes(finder):
                            pid = p['probe_id']
                            host = probe_address(p)
                            port = p['port']
                            if pid == stored_probe_id and host:
                                base = public_base_func()
                                ok = provision_probe(
                                    host.rstrip('.'), port, base,
                                    token=token or '',
                                    interval_ms=int(new_interval_sec * 1000),
                                    resolution_bits=new_res_bits,
                                )
                                if ok:
                                    log.info('Provisioned %s with interval=%s s, res=%s-bit',
                                             stored_probe_id, new_interval_sec, new_res_bits)
                                else:
                                    # Not a failure: a deep-sleeping probe is
                                    # unreachable almost all the time. The hub
                                    # returns the desired config on every
                                    # /api/ingest reply, so the probe applies it
                                    # on its own next check-in without the hub
                                    # ever having to catch it awake.
                                    log.info('Could not reach %s now (likely asleep) — '
                                             'the change will be applied on its next '
                                             'check-in, within one reporting interval',
                                             stored_probe_id)
                                break
                    except Exception as e:
                        log.warning('Provision-on-save failed: %s', e)

            return (False, None, '', '', no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update)

        return noup

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
            for key in ('probe_names', 'probe_intervals', 'alert_thresholds',
                        'calibration_offsets', 'probe_resolutions'):
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

    # --- Tell the operator WHEN a settings change will actually land ----------
    # Deliberately a separate callback rather than a 13th Output on the
    # open/close callback above: that one has twelve Outputs and a return in
    # every branch, and widening its arity to add a status line is a lot of
    # churn on the path that saves real settings. This only reads state.
    @app.callback(
        Output('device-save-status', 'children'),
        Input('edit-probe-save', 'n_clicks'),
        State('edit-probe-id-store', 'data'),
        State('edit-probe-interval-input', 'value'),
        State('edit-probe-min-input', 'value'),
        State('edit-probe-max-input', 'value'),
        State('temp-unit-store', 'data'),
        prevent_initial_call=True,
    )
    def report_save_delivery(n_clicks, probe_id, interval_value,
                             min_value=None, max_value=None, temp_unit=None):
        if not n_clicks or not probe_id:
            return no_update

        # An inverted range is silently swapped on save (see the save handler:
        # threshold_breach tests 'value > max' first, so min>max would make every
        # reading a breach forever). Swapping is right, but only the log said so
        # -- the operator saw a plain "Saved" and a card showing limits they had
        # not typed. On a product whose job is a safety limit, quietly storing
        # something other than what was entered has to be said out loud.
        swapped = None
        try:
            if min_value not in (None, '') and max_value not in (None, ''):
                lo, hi = float(min_value), float(max_value)
                if lo > hi:
                    swapped = (hi, lo)
        except (TypeError, ValueError):
            swapped = None
        sym = _unit_symbol(temp_unit)
        swap_note = ([html.Br(),
                      html.Strong("Note: Min was above Max, so they were swapped — "),
                      f"this probe now alarms outside {swapped[0]:g} to {swapped[1]:g} {sym}."]
                     if swapped else [])

        # The off-switch wins over everything else: with auto_provision false the
        # hub omits `config` from every /api/ingest reply, so a sleeping probe
        # never receives this change at all. That is a deliberate "don't manage
        # my probes" setting, but silently dropping the save is a trap -- say so.
        if not cfg.get('auto_provision', True):
            return dbc.Alert(
                [html.Strong("Saved on the hub, but it will not reach the probe. "),
                 "Automatic provisioning is switched off, so the hub does not send "
                 "settings to probes. Turn it on in Settings, or configure this "
                 "probe directly through its own setup page."],
                color='warning', dismissable=True, className='mb-0')

        try:
            interval_sec = float(interval_value)
        except (TypeError, ValueError):
            interval_sec = float(cfg.get('probe_intervals', {}).get(
                probe_id, cfg.get('interval_sec', 5) or 5) or 5)

        # A probe that is awake most of the time picks the change up almost at
        # once and a "check back later" note would just be noise.
        if interval_sec < 60:
            return dbc.Alert(["✅ Saved. The probe applies this on its next reading."]
                             + swap_note,
                             color='warning' if swapped else 'success',
                             dismissable=True, className='mb-0')

        # Worst case is one full interval: the probe may have checked in just
        # before Save, so it reads the new value on the check-in after that.
        due = datetime.datetime.now() + datetime.timedelta(seconds=interval_sec)
        return dbc.Alert(
            [html.Strong("✅ Saved — the probe picks this up on its next check-in. "),
             f"It reports every {_humanize_seconds(interval_sec)}, so expect it to be "
             f"running the new settings by about {due.strftime('%H:%M')}. ",
             html.Span("The probe is asleep between check-ins, so the hub cannot "
                       "confirm delivery until then.", className='text-muted')]
            + swap_note,
            color='warning' if swapped else 'info', dismissable=True, className='mb-0')
