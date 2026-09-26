#define MyAppName "אפליקציה לשיבוץ חדרים לנבחנים"
#define MyAppVersion "14.0.0"
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
OutputBaseFilename=ExamRoomApp_Setup_v14
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
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

[InstallDelete]
; Clean only old program files. Preserve the user's Output directory.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\ExamRoomApp.exe"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autoprograms}\הסרת {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "הפעל את האפליקציה"; Flags: nowait postinstall skipifsilent

[Code]
const
  PreviousUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{F04DC68D-4D3C-4B9D-A67C-0E909EE67436}_is1';

procedure StopRunningApplication;
var
  ResultCode: Integer;
  PowerShellArgs: String;
begin
  { Close all packaged application processes, including multiprocessing children. }
  Exec(ExpandConstant('{cmd}'),
    '/C taskkill /F /T /IM ExamRoomApp.exe >nul 2>&1', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode);

  { Close only legacy Python or command processes launched from this app folder. }
  PowerShellArgs :=
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ' +
    '"$root=[Environment]::ExpandEnvironmentVariables(''%LOCALAPPDATA%\Programs\ExamRoomApp\'');' +
    'Get-CimInstance Win32_Process | Where-Object {' +
    '($_.Name -in @(''python.exe'',''pythonw.exe'',''cmd.exe'')) -and ' +
    '($_.CommandLine -like (''*''+$root+''*''))' +
    '} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"';
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    PowerShellArgs, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);
end;

function FindPreviousUninstaller(var Uninstaller: String): Boolean;
var
  Candidate: String;
begin
  Result :=
    RegQueryStringValue(HKCU, PreviousUninstallKey, 'UninstallString', Uninstaller) or
    RegQueryStringValue(HKLM64, PreviousUninstallKey, 'UninstallString', Uninstaller) or
    RegQueryStringValue(HKLM32, PreviousUninstallKey, 'UninstallString', Uninstaller);

  if Result then
  begin
    Uninstaller := RemoveQuotes(Uninstaller);
    if FileExists(Uninstaller) then
      Exit;
  end;

  Candidate := ExpandConstant('{localappdata}\Programs\ExamRoomApp\unins000.exe');
  if FileExists(Candidate) then
  begin
    Uninstaller := Candidate;
    Result := True;
    Exit;
  end;

  Candidate := ExpandConstant('{localappdata}\Programs\ExamRoomApp\unins001.exe');
  if FileExists(Candidate) then
  begin
    Uninstaller := Candidate;
    Result := True;
    Exit;
  end;

  Candidate := ExpandConstant('{localappdata}\Programs\ExamRoomApp\unins002.exe');
  if FileExists(Candidate) then
  begin
    Uninstaller := Candidate;
    Result := True;
    Exit;
  end;

  Result := False;
end;

function CleanPreviousRuntime: Boolean;
var
  AppDir: String;
  Attempt: Integer;
begin
  AppDir := ExpandConstant('{localappdata}\Programs\ExamRoomApp');
  Result := False;

  { Antivirus scanners can hold a file briefly; retry before reporting failure. }
  for Attempt := 1 to 10 do
  begin
    DeleteFile(AppDir + '\ExamRoomApp.exe');
    DelTree(AppDir + '\_internal', True, True, True);
    if (not FileExists(AppDir + '\ExamRoomApp.exe')) and
       (not DirExists(AppDir + '\_internal')) then
    begin
      Result := True;
      Exit;
    end;
    Sleep(700);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Uninstaller: String;
  ResultCode: Integer;
begin
  Result := '';
  NeedsRestart := False;

  WizardForm.StatusLabel.Caption := 'סוגר את הגרסה הקודמת...';
  StopRunningApplication;

  if FindPreviousUninstaller(Uninstaller) then
  begin
    WizardForm.StatusLabel.Caption := 'מסיר את הגרסה הקודמת...';
    if not Exec(Uninstaller,
      '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /NORESTARTAPPLICATIONS', '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      Result := 'לא ניתן להפעיל את מסיר ההתקנה של הגרסה הקודמת.';
      Exit;
    end;

    if ResultCode <> 0 then
    begin
      Result := Format('הסרת הגרסה הקודמת נכשלה (קוד %d).', [ResultCode]);
      Exit;
    end;
  end;

  Sleep(1500);
  StopRunningApplication;

  WizardForm.StatusLabel.Caption := 'מנקה את קובצי הגרסה הקודמת...';
  if not CleanPreviousRuntime then
  begin
    Result := 'לא ניתן להסיר קבצים של הגרסה הקודמת. יש לסגור את האפליקציה ולנסות שוב.';
    Exit;
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
