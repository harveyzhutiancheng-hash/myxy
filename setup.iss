; 梦幻西游五开日常助手 - Inno Setup 安装脚本

[Setup]
AppName=梦幻日常助手
AppVersion=1.0
AppPublisher=私人工具
DefaultDirName={autopf}\梦幻日常助手
DefaultGroupName=梦幻日常助手
OutputDir=Output
OutputBaseFilename=梦幻日常助手_安装包
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; 安装后直接运行
UninstallDisplayIcon={app}\梦幻日常助手.exe

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
; 主程序（PyInstaller 打包好的 exe）
Source: "dist\梦幻日常助手.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 开始菜单
Name: "{group}\梦幻日常助手"; Filename: "{app}\梦幻日常助手.exe"
Name: "{group}\卸载梦幻日常助手"; Filename: "{uninstallexe}"
; 桌面图标（可选）
Name: "{autodesktop}\梦幻日常助手"; Filename: "{app}\梦幻日常助手.exe"; Tasks: desktopicon

[Run]
; 安装完成后可选择立即启动
Filename: "{app}\梦幻日常助手.exe"; Description: "立即运行梦幻日常助手"; Flags: nowait postinstall skipifsilent
