#define MyAppName "夏期講習 時間割作成"
#define MyAppExeName "SummerCourseScheduler.exe"
#define MyAppPublisher "SummerScheduler"
#define MyAppId "{{69E193A4-8240-49BD-9933-0E175303A4EE}"

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif

#ifndef MyAppFileVersion
  #define MyAppFileVersion "1.1.0.0"
#endif

#ifndef SourceDirectory
  #define SourceDirectory "..\build\portable\SummerCourseScheduler"
#endif

#ifndef OutputDirectory
  #define OutputDirectory "..\dist"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SummerCourseScheduler
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDirectory}
OutputBaseFilename=SummerCourseScheduler-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppFileVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} セットアップ
VersionInfoProductName=SummerCourseScheduler
VersionInfoProductVersion={#MyAppFileVersion}
VersionInfoProductTextVersion={#MyAppVersion}
InfoBeforeFile={#SourceDirectory}\PRIVACY.md

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成する"; GroupDescription: "追加アイコン:"; Flags: unchecked

[Files]
Source: "{#SourceDirectory}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} を起動する"; Flags: nowait postinstall skipifsilent

; .jukuschedule association is intentionally not registered in this release.
; The application does not yet accept a project path on its command line, so
; registering an association would make double-click appear to succeed while
; silently opening a different workspace. Add it only with an end-to-end open test.
;
; User data lives under %LOCALAPPDATA%\SummerScheduler, outside {app}. There is
; deliberately no [UninstallDelete] section: uninstall and in-place upgrades
; preserve projects, settings, logs, and backups.
