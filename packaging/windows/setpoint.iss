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
;    build defaults OPEN_BROWSER=1).

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
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startup"; Description: "Start {#AppName} automatically when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; The whole PyInstaller onedir folder (exe + _internal\).
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent
