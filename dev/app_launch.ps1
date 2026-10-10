# 桌面应用启动器(桌面快捷方式「BUD UI Studio」→ dev/app_launch.vbs → 本脚本)
# 1. 本地服务(8791)没在跑就在后台无窗口启动,「覆盖到 Unity」要用它;
# 2. 用 Edge 以「应用窗口」(无地址栏、无标签页)打开 file:// 的工作台。
#    工程数据存在"浏览器 + 地址"对应的本地存储里:应用窗口和 Edge 里直接打开这个 html 是同一份;
#    从别的浏览器(如夸克)搬过来:原浏览器任务首页「导出全部任务」→ 应用窗口里「从工程文件导入」。
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$port = 8791

if (-not (Get-NetTCPConnection -LocalPort $port -State Listen)) {
    $py = (Get-Command pythonw).Source
    if (-not $py) { $py = (Get-Command python).Source }
    if ($py) {
        Start-Process -FilePath $py -ArgumentList "dev\studio_server.py", "$port" -WorkingDirectory $root -WindowStyle Hidden
        for ($i = 0; $i -lt 20 -and -not (Get-NetTCPConnection -LocalPort $port -State Listen); $i++) { Start-Sleep -Milliseconds 150 }
    }
}

$html = Join-Path $root "BUD_UI_Studio.html"
$url = ([Uri]$html).AbsoluteUri

# 用 Edge(没有就 Chrome)的「应用窗口」:独立窗口、任务栏单独一个图标。夸克等国产浏览器不支持 --app,只会开成标签页
$browser = $null
foreach ($name in "msedge.exe", "chrome.exe") {
    $p = (Get-ItemProperty "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\$name").'(default)'
    if (-not $p) { $p = (Get-ItemProperty "Registry::HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\$name").'(default)' }
    if ($p -and (Test-Path $p.Trim('"'))) { $browser = $p.Trim('"'); break }
}
if (-not $browser) {
    foreach ($p in "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") {
        if (Test-Path $p) { $browser = $p; break }
    }
}
if ($browser) {
    Start-Process -FilePath $browser -ArgumentList "--app=$url", "--start-maximized"
} else {
    Start-Process $html
}
