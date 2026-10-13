# 资源批处理 · 示例:不用 Figma、不用 ComfyUI,也能把整条流程看一遍。
# 用法:
#   python dev/pipeline_demo.py            把示例头像框当成「Figma 插件发来的一批切图」放进中转箱 → 到「资源批处理」页面点「从 Figma 收件」
#   python dev/pipeline_demo.py --job      直接建好示例任务「示例 · 头像框_9036」:收件 + 配好 6 种动效 + 放上 3 张 AI 示例新图,打开页面就能看、能检查、能生成交付包
# 示例在 samples/pipeline/<示例名>/(layout.json 写着每张切图的位置、示例动效、AI 示例图),默认 avatar_frame_9036。
import base64, json, os, shutil, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pipeline"))
import pipeline_core as pc
from PIL import Image

name = next((a for a in sys.argv[1:] if not a.startswith("--")), "avatar_frame_9036")
S = os.path.join(pc.ROOT, "samples", "pipeline", name)
L = json.load(open(os.path.join(S, "layout.json"), encoding="utf-8"))
b64 = lambda f: base64.b64encode(open(os.path.join(S, f), "rb").read()).decode()
a = L["asset"]
slices = []
for s in a["slices"]:
    w, h = Image.open(os.path.join(S, s["file"])).size
    slices.append({"name": s["name"], "nodeId": None, "x": s["x"], "y": s["y"], "w": w, "h": h, "png": b64(s["file"])})
r = pc.bridge_inbox_add({"file": "示例(samples/pipeline/" + name + ")", "page": "-", "assets": [
    {"name": a["name"], "nodeId": None, "w": a["w"], "h": a["h"], "preview": b64(a.get("preview") or a["slices"][0]["file"]), "slices": slices}]})
print(f"已放进中转箱:{a['name']},{r['slices']} 张切图")
if "--job" not in sys.argv:
    print("下一步:工作台工具栏「资源批处理」→ 新建任务(标准选「头像框」、新增)→「从 Figma 收件」选这一批")
    sys.exit(0)

job = pc.create_job("示例 · " + a["name"], L["standard"], "new")
job = pc.import_inbox(job["id"], r["id"])
pc.update(job["id"], {"assets": {a["name"]: {"slices": {k: {"motion": dict(pc.uy.PRESETS[v["preset"]], **v)} for k, v in L.get("motions", {}).items()}}}})
# AI 示例图:当成已经重绘过的新图放进 out/(效果和真跑 AI 一样,只是不用等 ComfyUI)
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
    for m in job["assets"][0]["slices"]:
        m["motion"] = {k: v for k, v in (m.get("motion") or {}).items() if k != "label"} or None
    pc.save(job)
job = pc.check(job["id"])
print(f"已建好示例任务「{job['name']}」:动效 {len(L.get('motions', {}))} 个、AI 示例新图 {len(L.get('ai_examples', {}))} 张;"
      f"检查:{job['checked']['error']} 个必须处理、{job['checked']['warn']} 个提示")
print("下一步:工作台工具栏「资源批处理」→ 左边点这个任务 → 看动效预览、改参数 →「生成 unitypackage」")
