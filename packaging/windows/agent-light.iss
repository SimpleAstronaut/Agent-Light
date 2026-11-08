#define AppVersion "0.2.1"
[Setup]
AppId={{06901CEC-7671-468B-BEC5-82CB4897CCBB}
AppName=Agent Light
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\AgentLight
DefaultGroupName=Agent Light
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir=..\..\outputs\packages
OutputBaseFilename=AgentLight-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AgentLight.exe
SetupIconFile=agent-light.ico
AppMutex=Local\AgentLight.Desktop
CloseApplications=no
RestartApplications=no
LicenseFile=..\..\LICENSE
InfoBeforeFile=install-notes.txt

[Files]
Source: "..\..\pc\dist\AgentLight\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Agent Light"; Filename: "{app}\AgentLight.exe"
Name: "{userdesktop}\Agent Light"; Filename: "{app}\AgentLight.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\AgentLight.exe"; Description: "Open Agent Light"; Flags: nowait postinstall skipifsilent

[Code]
var
  ExitConfirmation: TInputOptionWizardPage;

function ProbeCreateFile(FileName: String; Access, Sharing, Security,
  Creation, Attributes, Template: LongWord): LongWord;
  external 'CreateFileW@kernel32.dll stdcall';
function ProbeCloseHandle(Handle: LongWord): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function InUse(FileName: String): Boolean;
var
  Handle: LongWord;
begin
  Result := False;
  if not FileExists(FileName) then Exit;
  Handle := ProbeCreateFile(FileName, $C0000000, 0, 0, 3, 128, 0);
  Result := Handle = $FFFFFFFF;
  if not Result then ProbeCloseHandle(Handle);
end;

function ProgramFilesInUse(): Boolean;
begin
  Result := InUse(ExpandConstant('{app}\AgentLight.exe')) or
    InUse(ExpandConstant('{app}\agent-light.exe')) or
    InUse(ExpandConstant('{app}\_internal\python314.dll'));
end;

procedure InitializeWizard();
begin
  ExitConfirmation := CreateInputOptionPage(wpSelectDir,
    'Close running hosts before installation',
    'Program files and the external DSH plugin must be replaced together.',
    'Exit Agent Light and all DSH Web backends that load this plugin. Setup never stops them automatically.', False, False);
  ExitConfirmation.Add('I have exited Agent Light and all DSH Web backends using this plugin.');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = ExitConfirmation.ID) and not ExitConfirmation.Values[0] then begin
    MsgBox('Exit the running programs and confirm before continuing.', mbInformation, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if CheckForMutexes('Local\AgentLight.Desktop') or ProgramFilesInUse() then
    Result := 'Agent Light is running. Exit it from the tray menu before installation.';
  if WizardSilent then
    Result := 'Unattended installation is disabled: explicit confirmation that DSH is stopped is required.';
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if CheckForMutexes('Local\AgentLight.Desktop') or ProgramFilesInUse() then begin
    MsgBox('Exit Agent Light normally before uninstalling.', mbInformation, MB_OK);
    Exit;
  end;
  if not Exec(ExpandConstant('{app}\AgentLight.exe'), '--prepare-uninstall',
      ExpandConstant('{app}'), SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) then begin
    MsgBox('Could not run the integration precheck. No program files were removed.', mbError, MB_OK);
    Exit;
  end;
  if ResultCode <> 0 then begin
    MsgBox('Integration cleanup was cancelled or needs attention. No program files were removed.', mbInformation, MB_OK);
    Exit;
  end;
  Result := True;
end;
