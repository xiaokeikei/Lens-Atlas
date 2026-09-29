; Build with scripts/build_installer.py, using a verified portable release.
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef BuildOutput
  #error BuildOutput is required
#endif
#ifdef InstallerQA
  #define ProductId "LensAtlas.InstallerQA"
  #define ProductName "Lens Atlas Installer QA"
  #define ProductDirectory "LensAtlasInstallerQA"
  #define OutputName "LensAtlas-" + AppVersion + "-Setup-QA-x64"
#else
  #define ProductId "LensAtlas.Desktop"
  #define ProductName "镜迹 · Lens Atlas"
  #define ProductDirectory "LensAtlas"
  #define OutputName "LensAtlas-" + AppVersion + "-Setup-x64"
#endif

[Setup]
AppId={#ProductId}
AppName={#ProductName}
AppVersion={#AppVersion}
AppPublisher=xiaokei
AppCopyright=power by xiaokei
DefaultDirName={localappdata}\Programs\{#ProductDirectory}
DefaultGroupName={#ProductName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableDirPage=no
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
OutputDir={#BuildOutput}
OutputBaseFilename={#OutputName}
SetupIconFile={#BundleDir}\_internal\assets\lens-atlas.ico
UninstallDisplayIcon={app}\LensAtlas.exe
LicenseFile={#BundleDir}\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#ProductName}"; Filename: "{app}\LensAtlas.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\{#ProductName}"; Filename: "{app}\LensAtlas.exe"; WorkingDir: "{app}"; Tasks: desktopicon

#ifndef InstallerQA
[Run]
Filename: "{app}\LensAtlas.exe"; Description: "Launch Lens Atlas"; Flags: nowait postinstall skipifsilent unchecked
#endif

; No UninstallDelete/InstallDelete entries: remove only installer-owned files.
; Indexes, credentials, caches and user libraries are outside the install tree.
[Code]
function ReadFileAttributes(const FileName: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';
function ReadDriveType(const RootPathName: String): LongWord;
  external 'GetDriveTypeW@kernel32.dll stdcall';

function NormalPath(const Value: String): String;
begin
  Result := RemoveBackslashUnlessRoot(ExpandFileName(Value));
end;

function SameOrChild(const Value, Parent: String): Boolean;
var
  NormalValue, NormalParent: String;
begin
  NormalValue := AddBackslash(NormalPath(Value));
  NormalParent := AddBackslash(NormalPath(Parent));
  Result := CompareText(Copy(NormalValue, 1, Length(NormalParent)), NormalParent) = 0;
end;

function DirectoryHasEntries(const Directory: String): Boolean;
var
  Item: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Directory) + '*', Item) then
  begin
    try
      repeat
        if (Item.Name <> '.') and (Item.Name <> '..') then
        begin
          Result := True;
          Exit;
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
end;

function PreviousInstallDirectory: String;
begin
  Result := '';
  RegQueryStringValue(HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#ProductId}_is1',
    'Inno Setup: App Path', Result);
end;

function UserMediaFolder(const Name, Fallback: String): String;
begin
  if not RegQueryStringValue(HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders',
    Name, Result) then
    Result := AddBackslash(GetEnv('USERPROFILE')) + Fallback;
end;

function ValidateInstallDirectory(const Selected: String): String;
var
  Target, Parent, Previous, DataDirectory: String;
  Attributes: LongWord;
begin
  Result := '';
  Target := NormalPath(Selected);
  if (Length(Target) <= 3) or (Copy(Target, 2, 2) <> ':\') then
  begin
    Result := 'Choose a dedicated folder on a local drive, for example D:\Apps\LensAtlas.';
    Exit;
  end;
  if ReadDriveType(Copy(Target, 1, 3)) = 4 then
  begin
    Result := 'Choose a local program folder, not an SMB or NAS share.';
    Exit;
  end;
  DataDirectory := ExpandConstant('{localappdata}\LensAtlas');
  if SameOrChild(Target, DataDirectory) or
     SameOrChild(Target, ExpandConstant('{win}')) or
     SameOrChild(Target, UserMediaFolder('My Pictures', 'Pictures')) or
     SameOrChild(Target, UserMediaFolder('My Video', 'Videos')) then
  begin
    Result := 'Choose a separate program folder, outside application data, Windows, Pictures and Videos.';
    Exit;
  end;
  DataDirectory := GetEnv('LENS_DATA_DIR');
  if (DataDirectory <> '') and SameOrChild(Target, DataDirectory) then
  begin
    Result := 'The application data directory cannot be used for program installation.';
    Exit;
  end;
  Parent := Target;
  while Length(Parent) > 3 do
  begin
    Attributes := ReadFileAttributes(Parent);
    if (Attributes <> $FFFFFFFF) and ((Attributes and $400) <> 0) then
    begin
      Result := 'Choose a direct folder path without symbolic links or directory junctions.';
      Exit;
    end;
    if FileExists(AddBackslash(Parent) + 'library.sqlite3') then
    begin
      Result := 'Choose a program folder outside the application data directory.';
      Exit;
    end;
    Parent := RemoveBackslashUnlessRoot(ExtractFileDir(Parent));
  end;
  Previous := PreviousInstallDirectory;
  if (Previous <> '') and FileExists(AddBackslash(Previous) + 'unins000.exe') then
  begin
    if CompareText(Target, NormalPath(Previous)) <> 0 then
      Result := 'An installation already exists at ' + Previous +
        '. To move it, uninstall that copy first. Your application data will be kept.';
    Exit;
  end;
  if FileExists(Target) or (DirExists(Target) and DirectoryHasEntries(Target)) then
    Result := 'This folder already contains files. Choose a new or empty program folder; do not select a photo library.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ErrorMessage: String;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and (not WizardSilent) then
  begin
    ErrorMessage := ValidateInstallDirectory(WizardDirValue);
    if ErrorMessage <> '' then
    begin
      MsgBox(ErrorMessage, mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { Repeat the same guard for silent /DIR installs and changes after the page. }
  Result := ValidateInstallDirectory(ExpandConstant('{app}'));
end;
