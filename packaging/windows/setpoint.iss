; Inno Setup script for the Setpoint hub — wraps the PyInstaller onedir build
; (dist\temperature-hub\) into a one-click Windows installer.
;
; Build (after packaging\build.bat has produced dist\temperature-hub\):
;   iscc /DAppVersion=2.4.0 packaging\windows\setpoint.iss
; Output: dist\installer\Setpoint-Setup-<version>.exe
;
; Design notes:
;  * PrivilegesRequired=lowest — installs per-user, no admin prompt. Combined
;    with the app writing its data to %LOCALAPPDATA%\Setpoint (see app.py
;    _default_data_dir), the whole thing works without administrator rights.
;  * The launched exe opens the dashboard in the browser on its own (the frozen
;    build defaults OPEN_BROWSER=1). A second launch while a hub is already
;    running just opens that hub's dashboard (core/single_instance.py), so the
;    Start-menu icon is safe to click when the hub runs in the background.
;  * Firewall: probes must reach the hub on TCP 8088, and discovery uses mDNS
;    (UDP 5353). Adding a rule needs administrator rights, so it is added only
;    when the person chooses "Install for all users" (the dialog that
;    PrivilegesRequiredOverridesAllowed=dialog offers). A per-user install relies
;    on the Windows Firewall prompt the first time the hub starts — docs/INSTALL.md
;    tells them to allow it on Private networks.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\temperature-hub"
#endif

#define AppName "Setpoint"
#define AppPublisher "Setpoint"
#define AppExe "temperature-hub.exe"
#define AppUrl "https://github.com/tallen5431/Temperature_Sensor_V2"

[Setup]
AppId={{8F3A1C2E-5B7D-4E9A-9C1F-2A6B3D4E5F60}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppSupportURL={#AppUrl}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=Setpoint-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
; Checked by default: a monitoring hub that is not running after a reboot raises
; no alarms, and the customer who leaves this box unticked has no way to notice.
; It starts at SIGN-IN, so a PC that reboots unattended also needs Windows
; automatic sign-in (docs/INSTALL.md) or the heartbeat in Settings to catch it.
Name: "startup"; Description: "Start {#AppName} automatically when I sign in (recommended)"; GroupDescription: "Startup:"

[Files]
; The whole PyInstaller onedir folder (exe + _internal\).
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
; Admin installs only (see the note at the top). Delete first so an upgrade or a
; reinstall to a new folder never leaves a stale rule behind. A program rule
; covers both the dashboard/ingest port and mDNS, on Private networks only.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Setpoint hub"""; Flags: runhidden; Check: IsAdminInstallMode
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Setpoint hub"" dir=in action=allow program=""{app}\{#AppExe}"" enable=yes profile=private"; Flags: runhidden; Check: IsAdminInstallMode; StatusMsg: "Allowing Setpoint through Windows Firewall (private networks)..."
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Setpoint hub"""; Flags: runhidden; Check: IsAdminInstallMode; RunOnceId: "SetpointFirewallRule"
