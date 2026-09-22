#define MyAppName "אפליקציה לשיבוץ חדרים לנבחנים"
#define MyAppVersion "7.0.0"
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
OutputBaseFilename=ExamRoomApp_Setup_v7
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
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

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "הפעל את האפליקציה"; Flags: nowait postinstall skipifsilent

[Code]
var
  CreditLabel: TNewStaticText;

procedure InitializeWizard;
begin
  WizardForm.Caption := '{#MyAppName} — התקנה';
  CreditLabel := TNewStaticText.Create(WizardForm);
  CreditLabel.Parent := WizardForm;
  CreditLabel.Caption := 'נוצר על ידי אסי וינברגר';
  CreditLabel.AutoSize := False;
  CreditLabel.Width := WizardForm.ClientWidth - ScaleX(40);
  CreditLabel.Left := ScaleX(20);
  CreditLabel.Top := WizardForm.ClientHeight - ScaleY(24);
  CreditLabel.Alignment := taCenter;
  CreditLabel.Font.Color := clGray;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpInstalling then
    WizardForm.StatusLabel.Caption := 'מתקין את האפליקציה במחשב...';
end;
