#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppIconSource SourcePath + "..\assets\icons\app.ico"
#define AppIconName "app-" + GetSHA256OfFile(AppIconSource) + ".ico"
#ifdef AcceptanceTest
  #define AppIdentity "ZoteroFileExplorer.AcceptanceTest"
  #define AppSuffix " Acceptance Test"
#else
  #define AppIdentity "{{6C9D5EAB-4F0F-433B-A6B6-A7E06484D807}"
  #define AppSuffix ""
#endif
[Setup]
AppId={#AppIdentity}
AppName=Zotero File Explorer
AppVersion={#AppVersion}
AppPublisher=Zotero File Explorer
DefaultDirName={localappdata}\Programs\ZoteroFileExplorer
DefaultGroupName=Zotero File Explorer
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=ZoteroFileExplorer-{#AppVersion}-Setup-x64{#AppSuffix}
SetupIconFile=..\assets\icons\app.ico
UninstallDisplayIcon={app}\icons\{#AppIconName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\build\release\ZoteroFileExplorer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppIconSource}"; DestDir: "{app}\icons"; DestName: "{#AppIconName}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Zotero File Explorer{#AppSuffix}"; Filename: "{app}\ZoteroFileExplorer.exe"; IconFilename: "{app}\icons\{#AppIconName}"; IconIndex: 0; AppUserModelID: "ZoteroFileExplorer.Desktop.1"
Name: "{autoprograms}\Zotero File Explorer Quick{#AppSuffix}"; Filename: "{app}\ZoteroFileExplorer.exe"; Parameters: "--quick"; IconFilename: "{app}\icons\{#AppIconName}"; IconIndex: 0; AppUserModelID: "ZoteroFileExplorer.Desktop.1"
Name: "{autodesktop}\Zotero File Explorer{#AppSuffix}"; Filename: "{app}\ZoteroFileExplorer.exe"; IconFilename: "{app}\icons\{#AppIconName}"; IconIndex: 0; AppUserModelID: "ZoteroFileExplorer.Desktop.1"; Check: ShouldCreateDesktopIcon

[Run]
Filename: "{app}\ZoteroFileExplorer.exe"; Description: "{cm:LaunchProgram,Zotero File Explorer}"; Flags: nowait postinstall skipifsilent

[Code]
procedure SHChangeNotify(EventId: Integer; Flags: Cardinal; Item1, Item2: String);
  external 'SHChangeNotify@shell32.dll stdcall';

function ShouldCreateDesktopIcon: Boolean;
var
  LinkPath: String;
  Shell, Shortcut: Variant;
begin
  Result := WizardIsTaskSelected('desktopicon');
  if Result then Exit;
  { Refresh our existing link on reinstall even when the optional task is off.
    Preserve a same-named link to an unrelated executable. }
  LinkPath := ExpandConstant('{autodesktop}\Zotero File Explorer{#AppSuffix}.lnk');
  if not FileExists(LinkPath) then Exit;
  try
    Shell := CreateOleObject('WScript.Shell');
    Shortcut := Shell.CreateShortcut(LinkPath);
    Result := CompareText(Shortcut.TargetPath,
      ExpandConstant('{app}\ZoteroFileExplorer.exe')) = 0;
  except
    Log('Cannot inspect existing desktop shortcut; preserving it: ' + GetExceptionMessage);
  end;
end;

procedure NotifyShortcutChanged(const LinkPath: String);
begin
  if FileExists(LinkPath) then
    { SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSH: only this item, no cache purge. }
    SHChangeNotify($00002000, $00001005, LinkPath, '');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    NotifyShortcutChanged(ExpandConstant('{autoprograms}\Zotero File Explorer{#AppSuffix}.lnk'));
    NotifyShortcutChanged(ExpandConstant('{autoprograms}\Zotero File Explorer Quick{#AppSuffix}.lnk'));
    NotifyShortcutChanged(ExpandConstant('{autodesktop}\Zotero File Explorer{#AppSuffix}.lnk'));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command: String;
begin
#ifndef AcceptanceTest
  if CurUninstallStep = usPostUninstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'ZoteroFileExplorer', Command) then
      if Pos(ExpandConstant('{app}'), Command) > 0 then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'ZoteroFileExplorer');
#endif
end;
