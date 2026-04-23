; 梦幻西游五开日常助手 - Inno Setup 安装脚本

[Setup]
AppName=MH Daily Bot
AppVersion=1.0
DefaultDirName={autopf}\MH Daily Bot
DefaultGroupName=MH Daily Bot
OutputDir=Output
OutputBaseFilename=梦幻日常助手_安装包
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\梦幻日常助手.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\梦幻日常助手.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\梦幻日常助手"; Filename: "{app}\梦幻日常助手.exe"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"
Name: "{autodesktop}\梦幻日常助手"; Filename: "{app}\梦幻日常助手.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\梦幻日常助手.exe"; Description: "Launch now"; Flags: nowait postinstall skipifsilent
