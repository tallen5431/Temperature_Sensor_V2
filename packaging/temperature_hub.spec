# PyInstaller spec for the Temperature Hub — builds a single self-contained
# executable so customers don't need Python installed.
#
# Build:  pyinstaller --clean --noconfirm packaging/temperature_hub.spec
# Output: dist/temperature-hub  (or dist\temperature-hub.exe on Windows)
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPECPATH is injected by PyInstaller and points at this file's directory, so
# the build works regardless of the current working directory.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "config.example.json"), "."),
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
    excludes=["tkinter", "pytest", "_pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
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
