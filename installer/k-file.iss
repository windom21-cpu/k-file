; ============================================================================
;  k-file インストーラ (Inno Setup)
; ----------------------------------------------------------------------------
;  方針 (2026-06-21):
;   - ユーザー領域 (%LOCALAPPDATA%\Programs\k-file) に「管理者権限なし」で入れる。
;     法律事務所の非管理者 PC を前提とし、UAC を出さない。
;   - これにより既存の zip 上書き型 自動アップデート (案②) が install_dir を
;     そのまま書き換えられるため、updater を作り直さずに済む (両立する)。
;   - PyInstaller --onedir の出力 (dist/k-file/*) をそのまま配置する。
;   - WizardStyle=classic でレトロ寄り (Win95/98 風 UI 方針と整合)。
;
;  ビルド: CI (.github/workflows/build.yml) が ISCC で行い、VERSION を /D で渡す。
;   例) ISCC.exe /DMyAppVersion=0.1.0-beta.12 installer\k-file.iss
;   出力: dist\k-file-setup.exe
;
;  ※ コード署名は当面見送り (見送り判断 2026-06-21)。未署名のため初回起動時に
;     SmartScreen「発行元不明」警告が出る (「詳細情報」→「実行」で進める)。
; ============================================================================

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

#define MyAppName "k-file"
#define MyAppExeName "k-file.exe"
#define MyAppPublisher "windom21"
#define MyAppURL "https://github.com/windom21-cpu/k-file"

[Setup]
; AppId は固定 GUID (アップグレード時に同一アプリと認識させるため変更しない)
AppId={{8B5F2A40-3C7D-4E16-9A2B-7F1C0D6E54A9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases

; ── ユーザー領域インストール (管理者権限不要) ──
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto

; ── 出力 ──
OutputDir=..\dist
OutputBaseFilename=k-file-setup
SetupIconFile=..\resources\icons\favicon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; ── 圧縮 / 体裁 ──
Compression=lzma2
SolidCompression=yes
WizardStyle=classic
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにアイコンを作成する"; GroupDescription: "追加アイコン:"

[Files]
; PyInstaller --onedir の出力一式をそのまま配置
Source: "..\dist\k-file\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} をアンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "k-file を起動する"; Flags: nowait postinstall skipifsilent
