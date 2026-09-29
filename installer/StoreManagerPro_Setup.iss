#define MyAppName "Store Manager Pro"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "Store Manager"
#define MyAppExeName "StoreManagerPro.exe"

[Setup]
AppId={{B9D0FBD8-3F4D-4A15-8E64-7E2D4A3B2C11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Store Manager Pro
DefaultGroupName={#MyAppName}
OutputDir=..\dist-installer
OutputBaseFilename=StoreManagerPro_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\StoreManagerPro.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "اجرای {#MyAppName}"; Flags: nowait postinstall skipifsilent
