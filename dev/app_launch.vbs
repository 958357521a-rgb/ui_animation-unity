' Desktop shortcut target: runs app_launch.ps1 without a console window (ASCII only: VBScript reads files as ANSI)
Set sh = CreateObject("WScript.Shell")
dir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & dir & "\app_launch.ps1""", 0, False
