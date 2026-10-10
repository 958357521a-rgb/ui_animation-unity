# 新电脑上手自检(双击「安装与自检.bat」运行):逐项检查工作台要用的环境,缺什么用中文说怎么补;能自动补的(Pillow)直接补。
# 用法:python dev/setup_check.py [--smoke 试跑一张 AI 重绘(4090 约半分钟,小显存显卡要几分钟)]
# 只读检查,不改系统设置;唯一会做的修改是缺 Pillow 时 pip 安装它。
import json, os, socket, subprocess, sys, tempfile, urllib.request
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = {"UNETLoader": ("unet_name", "qwen_image_2.1_int8_convrot.safetensors"),
          "CLIPLoader": ("clip_name", "qwen3vl_8b_int8_convrot.safetensors"),
          "VAELoader": ("vae_name", "qwen_image_2.1_vae_bf16.safetensors")}
problems, warnings = [], []
ok = lambda m: print("  ✓ " + m)
def bad(m, fix):
    print("  ✗ " + m + "\n      → " + fix); problems.append(m)
def warn(m, fix):
    print("  ! " + m + "\n      → " + fix); warnings.append(m)
def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""

print("\n[1] 基础软件")
if sys.version_info >= (3, 9):
    ok(f"Python {sys.version.split()[0]}({sys.executable})")
else:
    bad(f"Python 版本太旧({sys.version.split()[0]})", "装 Python 3.12:https://www.python.org/downloads/ ,安装时勾选 Add python.exe to PATH")
try:
    import PIL
    ok(f"Pillow {PIL.__version__}(AI 重绘、切图工具要用)")
except ImportError:
    print("  … 没有 Pillow,正在安装(pip install pillow)")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "pillow"], capture_output=True, text=True)
    if r.returncode == 0:
        ok("Pillow 已装好")
    else:
        bad("Pillow 安装失败", f"手动运行:{sys.executable} -m pip install pillow(公司网络装不上就让 IT 开一下 pypi.org)")
node = run(["node", "--version"])
if node:
    ok(f"Node.js {node}(体检脚本、Figma 上传脚本要用)")
else:
    warn("没有 Node.js", "装 LTS 版:https://nodejs.org/ 。不装也能用工作台,只是 dev/offline_check.js 等脚本跑不了")
git = run(["git", "--version"])
if git:
    ok(git + ("" if not os.path.isdir(os.path.join(ROOT, ".git")) else f"(当前分支 {run(['git', '-C', ROOT, 'branch', '--show-current']) or '?'})"))
else:
    warn("没有 Git", "装 Git for Windows:https://git-scm.com/download/win ,以后更新工作台用 git pull")
browsers = [p for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")) if os.path.exists(p)]
if browsers:
    ok("浏览器:" + os.path.basename(browsers[0]))
else:
    bad("没找到 Edge / Chrome", "工作台要用 Edge 或 Chrome 打开(桌面快捷方式按 Edge 应用窗口建)")

print("\n[2] 工作台")
for f in ("BUD_UI_Studio.html", "dev/studio_server.py", "ONBOARDING.md"):
    if not os.path.exists(os.path.join(ROOT, f)):
        bad(f"缺文件 {f}", "文件夹不完整:重新 git clone 或拷一份完整的")
with socket.socket() as s:
    s.settimeout(0.5)
    if s.connect_ex(("127.0.0.1", 8791)) == 0:
        ok("工作台服务已在运行:http://localhost:8791/")
    else:
        warn("工作台服务(8791)没在运行", "双击「创建桌面快捷方式.bat」建好桌面图标,以后双击桌面「BUD UI Studio」就会自动起服务并打开工作台")
desktop = run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"]) or os.path.join(os.path.expanduser("~"), "Desktop")
if os.path.exists(os.path.join(desktop, "BUD UI Studio.lnk")):
    ok("桌面快捷方式已建好")
else:
    warn("桌面还没有「BUD UI Studio」", "双击「创建桌面快捷方式.bat」")

print("\n[3] AI 重绘(可选:本机 ComfyUI + Qwen Image 2.1,环境包从原作者的 U 盘拷)")
import ctypes
class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in
               ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]
ram_gb = 0
try:
    m = _MEM(); m.dwLength = ctypes.sizeof(_MEM); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); ram_gb = m.ullTotalPhys / 2**30
except (AttributeError, OSError):
    pass
gpu = run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"]).splitlines()
vram_gb = 0
if gpu:
    name, mem, drv = [x.strip() for x in gpu[0].split(",")[:3]]
    vram_gb = float(mem) / 1024
    print(f"  · 显卡 {name},显存 {vram_gb:.0f} GB,驱动 {drv};内存 {ram_gb:.0f} GB")
    if float(drv.split(".")[0]) < 580:
        bad(f"NVIDIA 驱动太旧({drv})", "AI 环境包里的 PyTorch 基于 CUDA 13,要 580 以上的驱动:到 https://www.nvidia.cn/drivers/ 下载这张显卡的最新驱动,装完重启")
    if vram_gb < 16:
        warn(f"显存只有 {vram_gb:.0f} GB(模型约 16 GB)", "ComfyUI 会把放不下的部分放在内存里来回搬:能跑但慢,分辨率高了可能爆显存。"
             "试跑会按显存自动降到 768 分辨率,看耗时和效果再决定用不用")
    if ram_gb and ram_gb < 32:
        warn(f"内存只有 {ram_gb:.0f} GB", "显存不够时模型要放在内存里,内存最好 32 GB 以上,否则可能卡死或报内存不足")
else:
    warn("没检测到 NVIDIA 显卡(或没装驱动)", "AI 重绘要 NVIDIA 显卡;没有的话这一项用不了,工作台其他功能不受影响")
def get(path):
    with urllib.request.urlopen("http://127.0.0.1:8188" + path, timeout=10) as r:
        return json.load(r)
ai_ok = False
try:
    st = get("/system_stats")
    dev = (st.get("devices") or [{}])[0]
    ok(f"本机 ComfyUI 在运行:{dev.get('name', '?')}")
    missing = []
    for node, (field, fname) in MODELS.items():
        info = get("/object_info/" + node).get(node, {})
        opts = info.get("input", {}).get("required", {}).get(field, [[]])[0]
        if fname not in opts:
            missing.append(fname)
    if not get("/object_info/TextEncodeQwenImage21"):
        bad("ComfyUI 太旧,没有 Qwen Image 2.1 节点", "用原作者 U 盘里的 AI 环境包")
    elif missing:
        bad("ComfyUI 缺模型:" + "、".join(missing), "从原作者 U 盘的 AI 环境包里拷,放进 ComfyUI/models 对应目录(diffusion_models / text_encoders / vae);拷完运行环境包里的「校验模型.bat」")
    else:
        ok("模型齐全:Qwen Image 2.1 int8、Qwen3-VL 8B 文本编码、VAE")
        ai_ok = True
except (OSError, ValueError):
    warn("本机 ComfyUI 没在运行(端口 8188)", "装了原作者 U 盘里的 AI 环境包的话,先双击里面的「启动 ComfyUI.bat」,窗口别关,再跑一次自检;"
         "没装就忽略,AI 重绘只是可选功能")
if ai_ok and "--smoke" in sys.argv:
    import time
    from PIL import Image, ImageDraw
    tmp = tempfile.mkdtemp(prefix="budui_smoke_")
    src = os.path.join(tmp, "smoke_card.png")
    im = Image.new("RGBA", (160, 96), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((4, 4, 155, 91), 22, fill=(255, 205, 40, 255), outline=(20, 20, 20, 255), width=5)
    im.save(src)
    res = "1024" if vram_gb >= 12 or not gpu else "768"
    print(f"  … 试跑一张重绘(分辨率 {res};大显存显卡约半分钟,显存小要几分钟,最多等 15 分钟)")
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "dev", "restyle", "restyle.py"), src, "--out", tmp, "--keep-shape", "--res", res,
                        "--refs", os.path.join(ROOT, "dev", "restyle", "templates", "style_swatch.png")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if os.path.exists(os.path.join(tmp, "smoke_card.raw.png")):
        ok(f"试跑成功,用时 {time.time() - t0:.0f} 秒(原作者的 4090 约 25 秒);对比图:{os.path.join(tmp, '_compare.png')}")
        print("      把用时和对比图发给原作者,一起决定这台电脑上 AI 重绘用不用、用多大分辨率(restyle.py 加 --res 768)")
    else:
        out = (r.stdout + r.stderr).strip()
        oom = "out of memory" in out.lower() or "outofmemory" in out.lower()
        hint = ("爆显存了:先关掉其他占显卡的程序(游戏、浏览器硬件加速等)再试;还不行就说明这张卡跑不动,AI 重绘交给有大显存显卡的电脑做"
                if oom else "把下面的报错发给原作者")
        bad("试跑失败", hint + "\n      " + out[-400:])

print("\n[4] Unity(覆盖到 Unity 只需要主工程文件夹;Unity 里截图验收才需要装编辑器)")
hub = os.path.expandvars(r"%ProgramFiles%\Unity\Hub\Editor\2022.3.32f1\Editor\Unity.exe")
if os.path.exists(hub):
    ok("Unity 2022.3.32f1 已安装")
else:
    warn("没找到 Unity 2022.3.32f1(Unity Hub 默认位置)", "装在别处可以忽略;要做 Unity 截图验收(dev/unity_preview.py)时再装")
print("  · 主工程 BUD_CHINA:各自从公司仓库拉到自己电脑,工作台「覆盖到 Unity」里选它的文件夹(路径不用和原作者一样)")

print("\n" + ("全部通过。" if not problems and not warnings else
              f"{len(problems)} 项必须处理、{len(warnings)} 项建议处理(见上面的 ✗ / !)。"))
print("下一步:读 ONBOARDING.md 的「第一次打开」;用 Claude Code 打开这个文件夹,它会按 CLAUDE.md / ONBOARDING.md 帮你操作。")
sys.exit(1 if problems else 0)
