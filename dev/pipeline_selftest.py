# 资源批处理自测:不碰主工程、不开浏览器、不跑 AI。用合成切图模拟「Figma 发来一个头像框 → 配动效 → 检查 → 生成 .unitypackage」,
# 再拆包逐项校验:GUID 目录与 meta 一致、YAML 里的 fileID / GUID 引用都能解析、Layer 全是 5、动画绑定的路径哈希能对上 prefab 节点、
# 动画每条曲线首尾相等(循环无缝)。任一项失败返回码为 1。用法:python dev/pipeline_selftest.py [--keep 输出目录(保留交付包,拿去 Unity 里导入)]
import base64, gzip, io, json, os, re, shutil, sys, tarfile, tempfile, zlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pipeline"))
import pipeline_core as core

tmp = tempfile.mkdtemp(prefix="budui_pipeline_test_")
core.JOBS = os.path.join(tmp, "pipeline"); core.BRIDGE = os.path.join(core.JOBS, "_bridge")
core.SETTINGS = os.path.join(tmp, "settings.json")   # 不读本机设置:没有主工程路径,重名检查只出提示
fails = []
def ok(cond, text):
    print(("  ✓ " if cond else "  ✗ ") + text)
    if not cond:
        fails.append(text)

def png_b64(w, h, color, shape="ellipse"):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
    (dr.ellipse if shape == "ellipse" else dr.rectangle)((2, 2, w - 3, h - 3), fill=color)
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()

print("[1] Figma 中转箱 → 任务")
payload = {"file": "测试文件", "page": "第 1 页", "assets": [{
    "name": "头像框_9001", "nodeId": "1:2", "w": 256, "h": 256, "preview": png_b64(256, 256, (200, 160, 255, 255)),
    "slices": [
        {"name": "底框", "nodeId": "1:3", "x": 0, "y": 0, "w": 256, "h": 256, "png": png_b64(256, 256, (180, 140, 255, 255))},
        {"name": "预览", "nodeId": "1:4", "x": 28, "y": 31, "w": 199, "h": 193, "png": png_b64(199, 193, (180, 140, 255, 255))},
        {"name": "上_星星", "nodeId": "1:5", "x": 150, "y": 20, "w": 40, "h": 40, "png": png_b64(40, 40, (255, 220, 60, 255))},
        {"name": "上_蝴蝶结", "nodeId": "1:6", "x": 20, "y": 180, "w": 60, "h": 50, "png": png_b64(60, 50, (255, 120, 160, 255), "rect")},
        {"name": "上_光点", "nodeId": "1:7", "x": 200, "y": 200, "w": 24, "h": 24, "png": png_b64(24, 24, (255, 255, 255, 255))},
        {"name": "下_底光", "nodeId": "1:8", "x": 48, "y": 48, "w": 160, "h": 160, "png": png_b64(160, 160, (120, 200, 255, 160))},
        {"name": "Ribbon", "nodeId": "1:9", "x": 90, "y": 0, "w": 76, "h": 30, "png": png_b64(76, 30, (255, 90, 90, 255), "rect")},
        {"name": "参考_整图", "nodeId": "1:10", "x": 0, "y": 0, "w": 256, "h": 256, "png": png_b64(256, 256, (0, 0, 0, 255), "rect")}]}]}
r = core.bridge_inbox_add(payload)
ok(r["slices"] == 8, "插件发来 1 个资源 8 张切图")
ok(len(core.bridge_inbox_list()) == 1, "中转箱里能列出这一批")
job = core.create_job("自测头像框", "avatar_frame", "new")
job = core.import_inbox(job["id"], r["id"])
a = job["assets"][0]
roles = {s["name"]: s["role"] for s in a["slices"]}
ok(a["id"] == "9001", "从资源名「头像框_9001」认出编号 9001")
ok(roles == {"底框": "frame", "预览": "preview", "上_星星": "top", "上_蝴蝶结": "top", "上_光点": "top", "下_底光": "bottom", "Ribbon": "top", "参考_整图": "skip"},
   "按切图名认出角色:底框 / 预览 / 上层 / 下层 / 不导出 " + json.dumps(roles, ensure_ascii=False))
ok(not core.bridge_inbox_list(), "导入后中转箱清空")

print("[2] 配动效 + 检查")
jid = job["id"]
core.update(jid, {"assets": {"头像框_9001": {"slices": {
    "上_星星": {"motion": {"preset": "sway", "amp": 10, "period": 2}},
    "上_蝴蝶结": {"motion": {"preset": "tint", "color": "#ff6fa8", "period": 1}},
    "上_光点": {"motion": {"preset": "blink", "period": 0.5, "delay": 0.2}},
    "下_底光": {"motion": {"preset": "breathe", "amp": 0.1, "period": 2}},
    "Ribbon": {"motion": {"preset": "float", "amp": 5, "period": 1, "delay": 0.25}}}}}})
job = core.check(jid)
ok(job["checked"]["error"] == 0, f"检查没有必须处理的问题(提示 {job['checked']['warn']} 条:没跑 AI、没设主工程路径)")
dup = core.create_job("重名测试", "avatar_frame", "new")
core.add_upload(dup["id"], "头像框", [{"name": "底框.png", "b64": png_b64(256, 256, (1, 2, 3, 255))}, {"name": "边框.png", "b64": png_b64(256, 256, (1, 2, 3, 255))}])
c = core.check(dup["id"])
ok(c["checked"]["error"] >= 1 and any("缺编号" in i["text"] for i in c["assets"][0]["issues"]), "资源名不带编号时检查报错、不能打包")

print("[3] 生成交付包并拆包校验")
res = core.build(jid)
ok(os.path.exists(res["package"]), "生成了 .unitypackage")
files = {}
with tarfile.open(fileobj=io.BytesIO(gzip.decompress(open(res["package"], "rb").read()))) as t:
    for m in t.getmembers():
        g, _, kind = m.name.partition("/")
        files.setdefault(g, {})[kind] = t.extractfile(m).read()
paths = {v["pathname"].decode(): g for g, v in files.items()}
for p in sorted(paths):
    print("     ", p)
want = ["Assets/Arts/UI/UIWidgets/UserInfoView/Textures/CreatorHeadCycle/HeadCycle_9001.png",
        "Assets/Arts/UI/UIWidgets/UserInfoView/Textures/CreatorHeadCycle/HeadCycle_9001_Pre.png",
        "Assets/Arts/UI/UIWidgets/UserInfoView/HeadCyclePrefabs/HeadTopEffect_9001.prefab",
        "Assets/Loadable/UI/UIWidgets/UserInfoView/HeadCyclePrefabs/HeadTopEffect_9001.prefab",
        "Assets/Arts/UI/UIWidgets/UserInfoView/HeadCyclePrefabs/HeadBottomEffect_9001.prefab",
        "Assets/Loadable/UI/UIWidgets/UserInfoView/HeadCyclePrefabs/HeadBottomEffect_9001.prefab",
        "Assets/Arts/UI/UIWidgets/UserInfoView/HeadCyclePrefabs/HeadEffect_9001/HeadTopEffect_9001.anim",
        "Assets/Arts/UI/UIWidgets/UserInfoView/HeadCyclePrefabs/HeadEffect_9001/HeadTopEffect_9001.controller"]
ok(all(w in paths for w in want), "底框 / 预览 / 上下层特效源 + 壳 / 动画 / 控制器都在包里,落点按标准")
ok(not any("参考" in p for p in paths), "「不导出」的切图没进包")
ok(all(re.fullmatch(r"[\x20-\x7e]+", p) for p in paths), "包里所有路径都是英文(中文切图名换成了 Layer_xx)")
ok(all(re.search(r"^guid: " + g + "$", v["asset.meta"].decode(), re.M) for g, v in files.items()), "每个 GUID 目录和它的 meta 一致")
guids = set(files)
bad_refs, bad_layer = [], []
for p, g in paths.items():
    if not p.endswith((".prefab", ".anim", ".controller")):
        continue
    text = files[g]["asset"].decode()
    anchors = set(re.findall(r"^--- !u!\d+ &(-?\d+)", text, re.M))
    for fidv, gg in re.findall(r"\{fileID: (-?\d+)(?:, guid: ([0-9a-f]{32}))?", text):
        if gg:
            if gg not in guids and gg != "fe87c0e1cc204ed48ad3b37840f39efc":
                bad_refs.append(f"{p} → guid {gg}")
        elif fidv != "0" and fidv not in anchors and not (p.endswith(".controller") and fidv == "9100000"):
            bad_refs.append(f"{p} → fileID {fidv}")
    bad_layer += [p for x in re.findall(r"m_Layer: (\d+)", text) if x != "5"]
ok(not bad_refs, "所有 fileID / GUID 引用都能解析" + ("" if not bad_refs else ":" + "; ".join(bad_refs[:5])))
ok(not bad_layer, "所有 GameObject 都在 UI 层(Layer 5)")
top = files[paths[want[2]]]["asset"].decode(); anim = files[paths[want[6]]]["asset"].decode()
names = re.findall(r"m_Name: (\S+)", top)
hashes = {str(zlib.crc32(n.encode())) for n in names}
bind_paths = re.findall(r"^      path: (\d+)$", anim, re.M)
ok(bind_paths and all(h in hashes for h in bind_paths), f"动画的 {len(bind_paths)} 条绑定都指向 prefab 里存在的节点")
curves = re.split(r"\n  - (?:serializedVersion: 2\n    )?curve:\n", anim.split("m_ClipBindingConstant")[0])[1:]
seam = []
for cv in curves:
    vals = re.findall(r"^\s+value: (.+)$", cv, re.M)
    if vals and vals[0] != vals[-1]:
        seam.append(vals[0] + " ≠ " + vals[-1])
ok(curves and not seam, f"{len(curves)} 条动画曲线首尾相等,循环不跳" + ("" if not seam else ":" + "; ".join(seam[:3])))
ok("m_StopTime: 2" in anim and "m_LoopTime: 1" in anim, "动画长度 = 最长周期 2 秒,循环播放")
ok("m_Controller: {fileID: 9100000, guid: " + paths[want[7]] in top, "上层特效根节点的 Animator 指向生成的控制器")
bottom = files[paths[want[4]]]["asset"].decode()
ok("!u!95" in bottom, "下层特效(底光呼吸)也带了 Animator")
readme = open(res["readme"], encoding="utf-8").read()
ok('"Id": 9001' in readme and "HeadTopEffect_9001.prefab" in readme and "HeadBottomEffect_9001.prefab" in readme and "HeadCycle_9001_Pre" in readme,
   "README 给出要手动加进 HeadCycleConfig.json 的条目")

print("[4] 放回 Figma(中转箱 outbox)")
core.push_outbox(jid)
ob = core.bridge_outbox()
ok(len(ob) == 1 and len(ob[0]["assets"][0]["slices"]) == 8, "outbox 里有这个任务的 8 张切图和位置")
core.bridge_outbox_done(jid)
ok(not core.bridge_outbox(), "插件取回后 outbox 清空")

if "--keep" in sys.argv:
    dst = sys.argv[sys.argv.index("--keep") + 1]; os.makedirs(dst, exist_ok=True)
    shutil.copy(res["package"], dst); print("交付包留在:", os.path.join(dst, os.path.basename(res["package"])))
shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("全部通过" if not fails else f"{len(fails)} 项失败"))
sys.exit(1 if fails else 0)
