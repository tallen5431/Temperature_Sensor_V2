# PyInstaller spec for the Temperature Hub — builds a self-contained, no-Python
# distribution so customers don't need Python installed.
#
# This is a ONEDIR build (dist/temperature-hub/ containing the executable plus an
# _internal/ folder of dependencies).  Onedir keeps the LGPL-licensed `zeroconf`
# module as replaceable files on disk, which is the clean way to honour LGPL's
# "user may modify and relink" requirement (see THIRD-PARTY-LICENSES.md).
#
# Build:  pyinstaller --clean --noconfirm packaging/temperature_hub.spec
# Output: dist/temperature-hub/temperature-hub  (…/temperature-hub.exe on Windows)
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPECPATH is injected by PyInstaller and points at this file's directory, so
# the build works regardless of the current working directory.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "config.example.json"), "."),
    # Ship the licences inside the bundle so the product always carries them.
    (os.path.join(ROOT, "LICENSE"), "."),
    (os.path.join(ROOT, "THIRD-PARTY-LICENSES.md"), "."),
]
binaries = []
hiddenimports = []

# Third-party packages that ship data files / use dynamic imports.
for pkg in ("dash", "dash_bootstrap_components", "plotly", "zeroconf", "waitress", "pandas"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Our own packages — included explicitly in case of lazy (in-function) imports.
for pkg in ("components", "core", "api"):
    hiddenimports += collect_submodules(pkg)
hiddenimports += ["provisioner", "provisioning", "alert_monitor", "probe_discovery", "wifi_scan"]

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # The hub does TLS via stdlib ssl/smtplib (and urllib3 falls back to it), so
    # the optional `cryptography` package is not needed — excluding it slims the
    # bundle and avoids urllib3's optional-pyOpenSSL hook chain.
    excludes=["tkinter", "pytest", "_pytest", "cryptography", "OpenSSL"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir: binaries/datas are gathered by COLLECT below
    name="temperature-hub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # a server: keep the console so logs are visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="temperature-hub",
)

# On macOS, also wrap the onedir output in a double-clickable TempSensor.app so it
# can be shipped as a signed/notarized .dmg. The .app writes its data to
# ~/Library/Application Support/TempSensor (see app.py _default_data_dir), so it
# runs fine from a read-only /Applications.
import sys as _sys  # noqa: E402

if _sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="TempSensor.app",
        icon=None,
        bundle_identifier="com.tempsensor.hub",
        version=os.getenv("TEMPSENSOR_VERSION", "0.0.0"),
        info_plist={
            "CFBundleName": "TempSensor",
            "CFBundleDisplayName": "TempSensor",
            "CFBundleShortVersionString": os.getenv("TEMPSENSOR_VERSION", "0.0.0"),
            "NSHighResolutionCapable": True,
            "LSUIElement": False,
        },
    )
