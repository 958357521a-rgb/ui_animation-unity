# 在桌面创建「BUD UI Studio」快捷方式(双击 = 后台启动本地服务 + 用默认浏览器的应用窗口打开工作台)
# 文件夹挪了位置就重新运行一次「创建桌面快捷方式.bat」
$root = Split-Path -Parent $PSScriptRoot
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "BUD UI Studio.lnk"
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
$s.Arguments = '"' + (Join-Path $root "dev\app_launch.vbs") + '"'
$s.WorkingDirectory = $root
$s.IconLocation = (Join-Path $root "dev\app.ico") + ",0"
$s.Description = "BUD UI Studio 预制体工作台"
$s.Save()
Write-Output "已创建:$lnk"
