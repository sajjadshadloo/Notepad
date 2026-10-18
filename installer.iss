; Inno Setup script for Notepad Plus
; Build:  ISCC.exe installer.iss   (after PyInstaller has produced dist\NotepadPlus\)

#define MyAppName "Notepad Plus"
#define MyAppVersion "4.6.1"
#define MyAppPublisher "Sajjad"
#define MyAppExeName "NotepadPlus.exe"

[Setup]
AppId={{8E1B7A64-4A0E-4A7B-9E1C-9C21D9F0A7B1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/sajjadshadloo/Notepad
AppSupportURL=https://github.com/sajjadshadloo/Notepad/issues
AppUpdatesURL=https://github.com/sajjadshadloo/Notepad/releases/latest
LicenseFile=LICENSE
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
; The editor exits through its normal save prompts. Never force-close it.
CloseApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[InstallDelete]
; Runs before the new files are copied.
;
; Inno only overwrites what it ships, so a file a release stops shipping stays
; behind forever. Upgrading 3.11 to 4.0 left Qt6PrintSupport.dll and its .pyd
; -- dropped along with the PDF exporter -- plus assets\build_icon.py, dead
; since 3.x. Clearing the whole PyInstaller folder makes every install match
; what was actually built, with no list to keep up to date.
Type: filesandordirs; Name: "{app}\_internal"
; The per-release icon files, so the folder does not collect one per version.
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
; 3.x registered reminders with Windows Task Scheduler. 4.0 removed that, but
; an upgrade from an older version can still leave tasks behind, so the
; uninstaller keeps clearing them.
Filename: "{cmd}"; Parameters: "/C schtasks /Delete /TN ""NotepadPlus"" /F"; Flags: runhidden; RunOnceId: "DelReminderTasks"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent; Check: not IsAppUpdate
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: IsAppUpdate

[Code]
function IsAppUpdate: Boolean;
begin
  Result := ExpandConstant('{param:NOTEPADUPDATE|0}') = '1';
end;

function InitializeSetup: Boolean;
var
  Attempts: Integer;
begin
  { The updater starts Setup at the very end of shutdown. Wait for the
    editor's OS-owned mutex to disappear before touching application files. }
  Attempts := 0;
  while IsAppUpdate and CheckForMutexes('Local\NotepadPlus.Running') and (Attempts < 300) do
  begin
    Sleep(100);
    Attempts := Attempts + 1;
  end;
  Result := not CheckForMutexes('Local\NotepadPlus.Running');
  if not Result then
  begin
    Log('Editor is still running; installation cancelled without replacing files.');
    if not WizardSilent then
      MsgBox('Please exit Notepad Plus before installing the update.', mbInformation, MB_OK);
  end;
end;

function InitializeUninstall: Boolean;
begin
  Result := not CheckForMutexes('Local\NotepadPlus.Running');
  if not Result and not UninstallSilent then
    MsgBox('Please exit Notepad Plus before uninstalling.', mbInformation, MB_OK);
end;
