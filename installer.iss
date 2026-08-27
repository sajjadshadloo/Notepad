; Inno Setup script for Notepad Plus
; Build:  ISCC.exe installer.iss   (after PyInstaller has produced dist\NotepadPlus\)

#define MyAppName "Notepad Plus"
#define MyAppVersion "3.9.0"
#define MyAppPublisher "Sajjad"
#define MyAppExeName "NotepadPlus.exe"

[Setup]
AppId={{8E1B7A64-4A0E-4A7B-9E1C-9C21D9F0A7B1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=NotepadPlus-Setup-{#MyAppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[InstallDelete]
; Drop earlier versions' icon files, so the folder does not collect one per
; release. Runs before the new files are copied.
Type: files; Name: "{app}\NotepadPlus.ico"
Type: files; Name: "{app}\NotepadPlus-*.ico"

[Files]
; onedir build: ship the whole PyInstaller output folder
Source: "dist\NotepadPlus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; The icon file carries the version in its NAME on purpose. Windows caches
; shell icons by path, so shipping a changed icon at the same path leaves
; every shortcut showing the old one until the user clears the icon cache.
; A new path each release means the cache can never be stale.
Source: "assets\icon.ico"; DestDir: "{app}"; DestName: "NotepadPlus-{#MyAppVersion}.ico"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\NotepadPlus-{#MyAppVersion}.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\NotepadPlus-{#MyAppVersion}.ico"; Tasks: desktopicon

[Registry]
; "Open with" entry for text files
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.txt\OpenWithList\{#MyAppExeName}"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.md\OpenWithList\{#MyAppExeName}"; ValueType: none; Flags: uninsdeletekey

[UninstallRun]
; Reminders registered with Windows would otherwise keep firing after the
; app is gone, pointing at an executable that no longer exists.
Filename: "{cmd}"; Parameters: "/C schtasks /Delete /TN ""NotepadPlus"" /F"; Flags: runhidden; RunOnceId: "DelReminderTasks"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
