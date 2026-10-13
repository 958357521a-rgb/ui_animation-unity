# 资源批处理 · 示例:不用 Figma、不用 ComfyUI,也能把整条流程看一遍。
# 用法:
#   python dev/pipeline_demo.py [示例名…]          把示例当成「Figma 插件发来的一批切图」放进中转箱 → 到「资源批处理」页面点「从 Figma 收件」
#   python dev/pipeline_demo.py --job [示例名…]    直接建好示例任务「示例 · <资源名>」:收件 + 配好动效 / 九宫格 / 配置字段(+ AI 示例新图),打开页面就能看、能检查、能生成交付包
#   python dev/pipeline_demo.py --all --job         全部示例(头像框、聊天气泡框、称号、昵称框、主页皮肤)都建好
#   加 --out:建好后生成交付包,连同 README 复制到 samples/pipeline/<示例名>/示例输出/(更新仓库里的示例输出时用)
# 示例在 samples/pipeline/<示例名>/(layout.json 写着每张切图的位置、示例动效、九宫格、配置字段、AI 示例图),默认 avatar_frame_9036。
# 同名的示例任务会先删掉再建(反复运行不会越堆越多)。
import base64, glob, json, os, shutil, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pipeline"))
import pipeline_core as pc
from PIL import Image

SAMPLES = os.path.join(pc.ROOT, "samples", "pipeline")
names = [a for a in sys.argv[1:] if not a.startswith("--")]
if "--all" in sys.argv:
    names = sorted(os.path.basename(os.path.dirname(f)) for f in glob.glob(os.path.join(SAMPLES, "*", "layout.json")))
names = names or ["avatar_frame_9036"]


def demo(name):
    S = os.path.join(SAMPLES, name)
    L = json.load(open(os.path.join(S, "layout.json"), encoding="utf-8"))
    b64 = lambda f: base64.b64encode(open(os.path.join(S, f), "rb").read()).decode()
    a = L["asset"]
    slices = []
    for s in a["slices"]:
        w, h = Image.open(os.path.join(S, s["file"])).size
        slices.append({"name": s["name"], "nodeId": None, "x": s["x"], "y": s["y"], "w": w, "h": h, "png": b64(s["file"])})
    r = pc.bridge_inbox_add({"file": "示例(samples/pipeline/" + name + ")", "page": "-", "assets": [
        {"name": a["name"], "nodeId": None, "w": a["w"], "h": a["h"], "preview": b64(a.get("preview") or a["slices"][0]["file"]), "slices": slices}]})
    std = pc.standard(L["standard"])
    print(f"[{name}] 已放进中转箱:{a['name']},{r['slices']} 张切图")
    if "--job" not in sys.argv:
        print(f"  下一步:任务首页「资源批处理」页签 → 新建任务(标准选「{std['name']}」、新增)→「从 Figma 收件」选这一批")
        return
    jname = "示例 · " + a["name"]
    for j in pc.list_jobs():   # 同名示例先删掉
        if j["name"] == jname:
            pc.delete_job(j["id"])
    job = pc.create_job(jname, L["standard"], "new")
    job = pc.import_inbox(job["id"], r["id"])
    sp = {k: {"motion": {kk: vv for kk, vv in dict(pc.uy.PRESETS[v["preset"]], **v).items() if kk != "label"}} for k, v in L.get("motions", {}).items()}
    for k, b in (L.get("borders") or {}).items():
        sp.setdefault(k, {})["border"] = b
    pc.update(job["id"], {"assets": {a["name"]: {"slices": sp, "fields": L.get("fields") or {}}}})
    # AI 示例图:当成已经重绘过的新图放进 out/(效果和真跑 AI 一样,只是不用等 ComfyUI);没有示例图的切图不勾 AI
    d = pc.job_dir(job["id"])
    with pc.job_lock(job["id"]):
        job = pc.load(job["id"])
        for s in job["assets"][0]["slices"]:
            if s["name"] in L.get("ai_examples", {}):
                out = os.path.join(d, "out", a["name"]); os.makedirs(out, exist_ok=True)
                shutil.copy(os.path.join(S, L["ai_examples"][s["name"]]), os.path.join(out, s["name"] + ".png"))
                s.update({"new": f"out/{a['name']}/{s['name']}.png", "status": "done", "ai": True})
            else:
                s["ai"] = False
        pc.save(job)
    job = pc.check(job["id"])
    print(f"  已建好示例任务「{job['name']}」(标准「{std['name']}」):动效 {len(L.get('motions', {}))} 个、AI 示例新图 {len(L.get('ai_examples', {}))} 张;"
          f"检查:{job['checked']['error']} 个必须处理、{job['checked']['warn']} 个提示")
    if "--out" in sys.argv:
        res = pc.build(job["id"])
        o = os.path.join(S, "示例输出")
        if os.path.isdir(o):
            for f in glob.glob(os.path.join(o, "*.unitypackage")):
                os.remove(f)
        os.makedirs(o, exist_ok=True)
        pkg = os.path.join(o, f"{name}_sample.unitypackage")
        shutil.copy(res["package"], pkg); shutil.copy(res["readme"], os.path.join(o, "README.md"))
        print(f"  交付包 {res['assets']} 个文件 → {os.path.relpath(pkg, pc.ROOT)}")


for n in names:
    demo(n)
if "--job" in sys.argv:
    print("下一步:工作台任务首页「资源批处理」页签 → 左边点示例任务 → 看动效预览、改参数 →「生成 unitypackage」")
