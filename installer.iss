#define MyAppName "אפליקציה לשיבוץ חדרים לנבחנים"
#define MyAppVersion "9.0.0"
#define MyAppPublisher "Assi Vinberger"
#define MyAppExeName "ExamRoomApp.exe"

[Setup]
AppId={{F04DC68D-4D3C-4B9D-A67C-0E909EE67436}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\ExamRoomApp
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=ExamRoomApp_Setup_v9
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "יצירת קיצור דרך על שולחן העבודה"; GroupDescription: "קיצורי דרך:"; Flags: checkedonce

[Files]
Source: "dist\ExamRoomApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\Output"; Permissions: users-modify

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autoprograms}\הסרת {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "הפעל את האפליקציה"; Flags: nowait postinstall skipifsilent

[Code]
const
  PreviousUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{F04DC68D-4D3C-4B9D-A67C-0E909EE67436}_is1';

function FindPreviousUninstaller(var Uninstaller: String): Boolean;
begin
  Result :=
    RegQueryStringValue(HKCU, PreviousUninstallKey, 'UninstallString', Uninstaller) or
    RegQueryStringValue(HKLM64, PreviousUninstallKey, 'UninstallString', Uninstaller) or
    RegQueryStringValue(HKLM32, PreviousUninstallKey, 'UninstallString', Uninstaller);
  if Result then
    Uninstaller := RemoveQuotes(Uninstaller);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Uninstaller: String;
  ResultCode: Integer;
begin
  Result := '';
  if FindPreviousUninstaller(Uninstaller) and FileExists(Uninstaller) then
  begin
    WizardForm.StatusLabel.Caption := 'מסיר גרסה קודמת של האפליקציה...';
    if not Exec(Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Result := 'לא ניתן להפעיל את מסיר ההתקנה של הגרסה הקודמת.'
    else if ResultCode <> 0 then
      Result := Format('הסרת הגרסה הקודמת נכשלה (קוד %d).', [ResultCode]);
  end;
end;

procedure InitializeWizard;
begin
  WizardForm.Caption := '{#MyAppName} — התקנה';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpInstalling then
    WizardForm.StatusLabel.Caption := 'מתקין את האפליקציה במחשב...';
end;
