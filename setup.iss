; 脚本由 Inno Setup 脚本向导生成
#define MyAppName "大佐翻译官"
#define MyAppVersion "1.1.0"
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
OutputBaseFilename=dazuofanyiguan_setup.for.windows
Compression=lzma
SolidCompression=yes
SetupIconFile=src\ziyuan\logo.ico
UninstallDisplayIcon={app}\src\ziyuan\logo.ico

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; 主程序
Source: "dist\大佐翻译官.exe"; DestDir: "{app}"; Flags: ignoreversion
; 图标和资源文件
Source: "src\ziyuan\*"; DestDir: "{app}\src\ziyuan"; Flags: ignoreversion recursesubdirs createallsubdirs
; 配置文件和目录
Source: "src\config\*"; DestDir: "{app}\src\config"; Flags: ignoreversion recursesubdirs createallsubdirs
; 确保配置目录存在
[Dirs]
Name: "{app}\src\config"; Flags: uninsalwaysuninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\src\ziyuan\logo.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\src\ziyuan\logo.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent 