# 新电脑上手自检(双击「安装与自检.bat」运行):逐项检查工作台要用的环境,缺什么用中文说怎么补;能自动补的(Pillow)直接补。
# 用法:python dev/setup_check.py [--smoke 试跑一张 AI 重绘(约半分钟起)]
# 只读检查,不改系统设置;唯一会做的修改是缺 Pillow 时 pip 安装它。
import json, os, shutil, socket, subprocess, sys, tempfile, urllib.error, urllib.request
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

print("\n[3] AI 重绘(ComfyUI + Qwen Image 2.1)")
cfg_path = os.path.join(ROOT, "dev", "ai_remote.json")
remote = {}
if os.path.exists(cfg_path):
    try:
        remote = json.load(open(cfg_path, encoding="utf-8-sig"))
    except ValueError:
        bad("dev/ai_remote.json 格式不对", '内容应是 {"server": "http://<共享电脑 IP>:8790", "key": "<口令>"}')
base = remote["server"].rstrip("/") + "/api/ai" if remote.get("server") else "http://127.0.0.1:8188"
hdr = {"X-BudUI-AI-Key": remote.get("key", "")} if remote.get("server") else {}
where = f"共享的 ComfyUI({remote['server']})" if remote.get("server") else "本机 ComfyUI(127.0.0.1:8188)"
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base + path, headers=hdr), timeout=10) as r:
        return json.load(r)
ai_ok = False
try:
    st = get("/system_stats")
    dev = (st.get("devices") or [{}])[0]
    ok(f"{where} 连得上:{dev.get('name', '?')},显存 {dev.get('vram_total', 0) / 2**30:.0f} GB")
    missing = []
    for node, (field, fname) in MODELS.items():
        info = get("/object_info/" + node).get(node, {})
        opts = info.get("input", {}).get("required", {}).get(field, [[]])[0]
        if fname not in opts:
            missing.append(fname)
    if not get("/object_info/TextEncodeQwenImage21"):
        bad("ComfyUI 太旧,没有 Qwen Image 2.1 节点", "更新 ComfyUI 到 0.37 或更新版本")
    elif missing:
        bad("ComfyUI 缺模型:" + "、".join(missing), "从原作者电脑拷这几个模型到 ComfyUI/models 对应目录(diffusion_models / text_encoders / vae)")
    else:
        ok("模型齐全:Qwen Image 2.1 int8、Qwen3-VL 8B 文本编码、VAE")
        ai_ok = True
except urllib.error.HTTPError as e:
    msg = e.read().decode("utf-8", "replace")
    try:
        msg = json.loads(msg)["error"]
    except (ValueError, KeyError, TypeError):
        msg = msg[:200]
    bad(f"{where} 拒绝了请求(HTTP {e.code}):{msg}", "向共享 AI 的那台电脑要「启动局域网共享.bat」窗口里打印的口令(也在它的 dev/ai_share_key.txt),改自己的 dev/ai_remote.json")
except (OSError, ValueError) as e:
    if remote.get("server"):
        bad(f"连不上{where}", "让共享方双击「启动局域网共享.bat」并打开 ComfyUI;两台电脑要在同一个局域网;地址以对方窗口里打印的为准")
    else:
        warn("本机没有 ComfyUI", "没有 16GB 以上 NVIDIA 显卡就用同事电脑共享的:把 dev/ai_remote.example.json 复制成 dev/ai_remote.json,"
             "填上共享方「启动局域网共享.bat」窗口里打印的地址和口令。AI 重绘只是可选功能,工作台其他功能不受影响")
if ai_ok and "--smoke" in sys.argv:
    from PIL import Image, ImageDraw
    tmp = tempfile.mkdtemp(prefix="budui_smoke_")
    src = os.path.join(tmp, "smoke_card.png")
    im = Image.new("RGBA", (160, 96), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((4, 4, 155, 91), 22, fill=(255, 205, 40, 255), outline=(20, 20, 20, 255), width=5)
    im.save(src)
    print("  … 试跑一张重绘(共享 ComfyUI 忙的时候要排队,最多等 15 分钟)")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "dev", "restyle", "restyle.py"), src, "--out", tmp, "--keep-shape",
                        "--refs", os.path.join(ROOT, "dev", "restyle", "templates", "style_swatch.png")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if os.path.exists(os.path.join(tmp, "smoke_card.raw.png")):
        ok(f"试跑成功,对比图:{os.path.join(tmp, '_compare.png')}")
    else:
        bad("试跑失败", (r.stdout + r.stderr).strip()[-300:])

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
