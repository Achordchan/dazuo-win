; 脚本由 Inno Setup 脚本向导生成
#define MyAppName "大佐翻译官"
#include "version.generated.iss"
#define MyAppPublisher "大佐翻译官"
#define MyAppURL "https://gitee.com/Achordchan/dazuofanyiguan"
#define MyAppExeName "大佐翻译官.exe"

[Setup]
AppId={{YOUR-GUID-HERE}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=dazuofanyiguan_setup.for.windows_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
SetupIconFile=src\ziyuan\logo.ico
UninstallDisplayIcon={app}\src\ziyuan\logo.ico

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Nuitka 运行时依赖与资源（含主程序）
Source: "dist_nuitka\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 确保配置目录存在
[Dirs]
Name: "{app}\src\config"; Flags: uninsalwaysuninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\src\ziyuan\logo.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\src\ziyuan\logo.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent 
