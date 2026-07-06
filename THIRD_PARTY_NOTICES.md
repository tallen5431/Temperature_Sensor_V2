# Third-Party Notices

ThermaHub bundles third-party open-source software. Each component is the
property of its respective authors and is distributed under its own license,
summarized below. The full, authoritative license text for each component ships
inside that package's own distribution (for Python packages, in the installed
package's `*.dist-info/` metadata / `LICENSE` file; for firmware libraries, in
the library's source tree).

This file is a convenience summary and is not a substitute for those full texts.

## Hub software — Python dependencies

| Component | Purpose | License |
| --- | --- | --- |
| Dash | Dashboard / web UI framework | MIT |
| dash-bootstrap-components | Bootstrap UI components for Dash | Apache-2.0 |
| Flask | Web framework underlying the REST API | BSD-3-Clause |
| Werkzeug | WSGI utilities used by Flask | BSD-3-Clause |
| pandas | CSV / time-series data handling | BSD-3-Clause |
| plotly | Charting library used by Dash | MIT |
| zeroconf | mDNS probe discovery | LGPL-2.1 |
| waitress | Production WSGI server (serves on port 8080) | ZPL-2.1 (Zope Public License) |
| requests | HTTP client (provisioning, pull ingest) | Apache-2.0 |

Transitive dependencies of the packages above (for example Jinja2, itsdangerous,
click, numpy, python-dateutil, ifaddr) are installed alongside them and are
distributed under their own permissive licenses (mostly MIT, BSD, and
Apache-2.0). Their full license texts ship with each installed package.

## Probe firmware — Arduino / ESP32 libraries

| Component | Purpose | License |
| --- | --- | --- |
| OneWire | 1-Wire bus communication for the DS18B20 sensor | MIT |
| DallasTemperature | DS18B20 temperature sensor driver | LGPL-2.1 |
| ArduinoJson | JSON encode/decode for HTTP payloads | MIT |

The ESP32 Arduino core and its bundled Wi-Fi, WebServer, and mDNS libraries are
distributed by Espressif and the Arduino project under their respective licenses
(primarily LGPL-2.1 and Apache-2.0); their full texts ship with the core.

---

The full text of every license referenced above is included with the
corresponding package or library as distributed. If you redistribute ThermaHub,
retain those license texts and this notice.
