# 资源批处理 · 各类资源自测(聊天气泡框 / 称号 / 昵称框 / 主页皮肤):不碰主工程、不开浏览器、不跑 AI。
# 每类用合成切图建一个任务 → 配动效 / 九宫格 / 配置字段 → 检查 → 生成 .unitypackage,再拆包校验:落点、GUID 与 meta 一致、
# YAML 里的 fileID / GUID 引用都能解析(主工程已有的脚本 / 字体 / 嵌套 prefab 列在 KNOWN)、UI 层 / 场景层、动画绑定能对上节点、
# 曲线首尾相等、贴图导入设置(九宫格 / ASTC)、配置条目。任一项失败返回码为 1。
# 用法:python dev/pipeline_types_selftest.py [--keep 输出目录(保留交付包,拿去 Unity 里导入)]
import base64, gzip, io, json, os, re, shutil, sys, tarfile, tempfile, zlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "pipeline"))
import pipeline_core as core

tmp = tempfile.mkdtemp(prefix="budui_pipeline_types_")
core.JOBS = os.path.join(tmp, "pipeline"); core.BRIDGE = os.path.join(core.JOBS, "_bridge")
core.SETTINGS = os.path.join(tmp, "settings.json")
KNOWN = {"fe87c0e1cc204ed48ad3b37840f39efc": "UGUI Image", "306cc8c2b49d7114eaa3623786fc2126": "LayoutElement",
         "5f7201a12d95ffc409449d95f23cf332": "UGUI Text", "0000000000000000f000000000000000": "内置 Sprite 材质",
         "a8a7f613b75754a2482d29704e24e840": "SizeToFitBgView", "cd683830507e42e4582ff721fde66026": "昵称框头像占位",
         "2d1f06229702c49f6a7d8597bb583434": "思源黑体 Heavy"}
fails, kept = [], []


def ok(cond, text):
    print(("  ✓ " if cond else "  ✗ ") + text)
    if not cond:
        fails.append(text)


def png_b64(w, h, color, shape="ellipse"):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
    (dr.ellipse if shape == "ellipse" else dr.rectangle)((1, 1, w - 2, h - 2), fill=color)
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def sl(name, x, y, w, h, color=(200, 150, 255, 255), shape="rect"):
    return {"name": name, "nodeId": name, "x": x, "y": y, "w": w, "h": h, "png": png_b64(w, h, color, shape)}


def make(std, asset, slices, patch):
    """中转箱 → 任务 → 改角色 / 动效 / 字段 → 检查 → 生成;返回 (任务, 生成结果, {路径: 文件内容}, {路径: meta})"""
    w, h = asset[1], asset[2]
    r = core.bridge_inbox_add({"file": "自测", "page": "1", "assets": [{"name": asset[0], "nodeId": "1:1", "w": w, "h": h, "slices": slices}]})
    job = core.create_job("自测" + asset[0], std, "new")
    job = core.import_inbox(job["id"], r["id"])
    core.update(job["id"], {"assets": {asset[0]: patch}})
    job = core.check(job["id"])
    errs = [i["text"] for a in job["assets"] for i in a.get("issues", []) if i["level"] == "error"] + \
           [i["text"] for a in job["assets"] for s in a["slices"] for i in s.get("issues", []) if i["level"] == "error"]
    ok(not errs, f"检查没有必须处理的问题" + ("" if not errs else ":" + "; ".join(errs)))
    res = core.build(job["id"])
    files = {}
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(open(res["package"], "rb").read()))) as t:
        for m in t.getmembers():
            g, _, kind = m.name.partition("/")
            files.setdefault(g, {})[kind] = t.extractfile(m).read()
    paths = {v["pathname"].decode(): v["asset"] for v in files.values()}
    metas = {v["pathname"].decode(): v["asset.meta"].decode() for v in files.values()}
    ok(all(re.search(r"^guid: " + g + "$", v["asset.meta"].decode(), re.M) for g, v in files.items()), "每个 GUID 目录和它的 meta 一致")
    ok(all(re.fullmatch(r"[\x20-\x7e]+", p) for p in paths), "包里所有路径都是英文")
    guids = set(files)
    bad = []
    for p, data in paths.items():
        if not p.endswith((".prefab", ".anim", ".controller")):
            continue
        text = data.decode()
        anchors = set(re.findall(r"^--- !u!\d+ &(-?\d+)", text, re.M))
        for fidv, gg in re.findall(r"\{fileID: (-?\d+)(?:, guid: ([0-9a-f]{32}))?", text):
            if gg:
                if gg not in guids and gg not in KNOWN:
                    bad.append(f"{p} → guid {gg}")
            elif fidv != "0" and fidv not in anchors and not (p.endswith(".controller") and fidv == "9100000"):
                bad.append(f"{p} → fileID {fidv}")
        for m in re.finditer(r"target: \{fileID: (\d+), guid: ([0-9a-f]{32})", text):   # 壳 / 嵌套实例改的对象要在源 prefab 里
            src = next((paths[q].decode() for q in paths if q.endswith(".prefab") and files_guid(files, q) == m.group(2)), None)
            if src is not None and not re.search(r"^--- !u!\d+ &" + m.group(1) + "$", src, re.M):
                bad.append(f"{p} → 源 prefab 里没有 {m.group(1)}")
    ok(not bad, "所有 fileID / GUID 引用都能解析" + ("" if not bad else ":" + "; ".join(bad[:5])))
    for p, data in paths.items():
        if p.endswith(".anim"):
            check_anim(p, data.decode(), paths)
    if "--keep" in sys.argv:
        kept.append(res["package"])
    return job, res, paths, metas


def files_guid(files, path):
    return next(g for g, v in files.items() if v["pathname"].decode() == path)


def hierarchy_paths(text):
    """prefab 里每个挂 Animator 的节点 → 它下面所有节点的相对路径集合(动画按这个路径的 CRC32 绑定)"""
    docs = re.split(r"^--- !u!(\d+) &(-?\d+).*$", text, flags=re.M)
    go_name, tr_go, tr_father, animators = {}, {}, {}, []
    for i in range(1, len(docs), 3):
        cls, fidv, body = docs[i], docs[i + 1], docs[i + 2]
        if cls == "1":
            go_name[fidv] = re.search(r"m_Name: (.+)", body).group(1).strip().strip('"')
        elif cls in ("4", "224") and "m_GameObject:" in body:   # 嵌套 prefab 的 stripped 对象没有 m_GameObject,跳过
            tr_go[fidv] = re.search(r"m_GameObject: \{fileID: (-?\d+)", body).group(1)
            tr_father[fidv] = re.search(r"m_Father: \{fileID: (-?\d+)", body).group(1)
        elif cls == "95":
            animators.append(re.search(r"m_GameObject: \{fileID: (-?\d+)", body).group(1))
    out = {}
    for ago in animators:
        root_tr = next(t for t, g in tr_go.items() if g == ago)
        rel = set()
        for t in tr_go:
            parts, cur = [], t
            while cur != "0" and cur != root_tr and cur in tr_go:
                parts.append(go_name[tr_go[cur]]); cur = tr_father[cur]
            if cur == root_tr and parts:
                rel.add("/".join(reversed(parts)))
        out[ago] = rel
    return out


def check_anim(p, anim, paths):
    base = os.path.splitext(p)[0]
    folder = os.path.dirname(p)
    # 用了这个片段的 prefab:同目录 / 同任务里 Animator 指向的控制器引用了这个片段
    rel = set()
    for q, data in paths.items():
        if q.endswith(".prefab"):
            for s in hierarchy_paths(data.decode()).values():
                rel |= s
    hashes = {str(zlib.crc32(x.encode())) for x in rel}
    binds = re.findall(r"^      path: (\d+)$", anim, re.M)
    ok(binds and all(h in hashes for h in binds), f"{os.path.basename(p)}:{len(binds)} 条绑定都指向 prefab 里存在的节点")
    curves = re.split(r"\n  - (?:serializedVersion: 2\n    )?curve:\n", anim.split("m_ClipBindingConstant")[0])[1:]
    seam = [1 for cv in curves if (lambda v: v and v[0] != v[-1])(re.findall(r"^\s+value: (.+)$", cv, re.M))]
    ok(curves and not seam, f"{os.path.basename(p)}:{len(curves)} 条曲线首尾相等")


def layers(text):
    return set(re.findall(r"m_Layer: (\d+)", text))


def entry_of(res):
    return res["configEntries"][0]


print("[1] 聊天气泡框")
B = "Assets/Arts/UI/UIWidgets/UserInfoView"
job, res, P, M = make("chat_bubble", ("聊天气泡_9039", 220, 160), [
    sl("底图", 30, 30, 150, 100, (255, 240, 220, 255)), sl("图标", 0, 0, 195, 133), sl("左上_花", 10, 10, 40, 40, shape="ellipse"),
    sl("星星", 160, 110, 30, 30, shape="ellipse"), sl("右上_铃铛", 160, 10, 30, 40), sl("参考_整图", 0, 0, 220, 160)],
    {"fields": {"title": "自测聊天气泡", "txtColor": "#785745"}, "slices": {
        "底图": {"border": [30, 25, 32, 20]},
        "右上_铃铛": {"motion": {"preset": "float", "amp": 4, "period": 2}},
        "星星": {"motion": {"preset": "blink", "amp": 0.5, "period": 1}}}})
roles = {s["name"]: s["role"] for s in job["assets"][0]["slices"]}
ok(roles == {"底图": "bubble", "图标": "icon", "左上_花": "lu", "星星": "corner", "右上_铃铛": "ru", "参考_整图": "skip"}, "按切图名认出角色 " + json.dumps(roles, ensure_ascii=False))
E = f"{B}/ChatBubblePrefabs/ChatBubbleEff_9039"; L = "Assets/Loadable/UI/UIWidgets/UserInfoView/ChatBubblePrefabs/ChatBubbleEff_9039"
want = [f"{B}/Textures/CreatorBubbles/HallChatBubble_9039.png", "Assets/Loadable/UI/UIWidgets/CreatorBubbles/GameChatBubble_9039.png",
        f"{B}/Textures/CreatorBubbles/ChatBubbleIcon_9039.png"] + [f"{d}/{c}{g}.prefab" for d in (E, L) for c in ("LeftUp", "RightUp", "RightDown") for g in ("", "_Game")] + \
       [f"{E}/LeftUp.controller", f"{E}/LeftUp_animation.anim", f"{E}/RightUp_Game.controller", f"{E}/RightDown.controller"]
ok(all(w in P for w in want), "底图两份 / 图标 / 三个角的 UGUI 版 + _Game 版(源 + 壳)/ 动画都在包里" + "".join(f"\n      缺 {w}" for w in want if w not in P))
ok(not any("LeftDown" in p for p in P), "没有切图的角(左下)不生成")
hall = M[want[0]]; game = M[want[1]]; icon = M[want[2]]
ok("spriteBorder: {x: 30, y: 25, z: 32, w: 20}" in hall and "spriteBorder: {x: 30, y: 25, z: 32, w: 20}" in game, "底图两份都带九宫格边距")
ok("spriteBorder: {x: 0, y: 0, z: 0, w: 0}" in icon, "图标不切九宫格")
ok(hall.count("textureFormat: 50") == 2 and hall.count("overridden: 1") == 2, "Android / iPhone 覆盖成 ASTC 6x6(对照 ChatBubbleIcon_38)")
ui, gm = P[f"{E}/LeftUp.prefab"].decode(), P[f"{E}/LeftUp_Game.prefab"].decode()
ok(layers(ui) == {"5"} and layers(gm) == {"0"}, "UGUI 版在 UI 层、_Game 版在默认层(对照 ChatBubbleEff_38)")
ok("m_AnchorMin: {x: 0, y: 1}" in ui and "m_IgnoreLayout: 1" in ui, "左上角饰锚在气泡左上角、忽略布局")
ok("!u!212" in gm and "m_SortingOrder: 2" in gm and "!u!4 &" in gm, "_Game 版根节点 Transform、子节点 SpriteRenderer")
ok(f"{E}/RightUp_Game_animation.anim" in P, "用了浮动(位置类)的角,_Game 版单独一份动画(单位差 100 倍)")
ok(f"{E}/RightDown_Game.controller" not in P and "classID: 212" in P[f"{E}/RightDown_animation.anim"].decode(), "只有闪烁的角两版共用控制器,曲线同时写 Image 和 SpriteRenderer")
e = entry_of(res)
ok(e["Id"] == 9039 and e["PgcId"] == "120109039" and e["IconName"] == "ChatBubbleIcon_9039" and e["Name"] == "自测聊天气泡", "配置条目:Id / PgcId / IconName / 名称")
ok(e["CornerEffectPrefabPaths"] == ["LeftUp", "RightUp", "RightDown"], "配置条目:CornerEffectPrefabPaths = 实际做出来的角")
ok(e["TxtColor"] == {"r": 0.470588, "g": 0.341176, "b": 0.270588, "a": 1.0} and e["LayoutOffset"] == {"left": 80, "right": 100, "top": 20, "bottom": 15}, "配置条目:颜色转成 r/g/b/a、数字字段")
ok("Desc" not in e, "可选字段(获取途径)没填就不写")

print("[2] 称号(带动画)")
T = "Assets/Loadable/UI/UIWidgets/Title"
job, res, P, M = make("title", ("称号_9044", 304, 72), [
    sl("图标", 0, 0, 304, 72), sl("底板", 32, 0, 240, 72), sl("星星", 230, 5, 40, 40, shape="ellipse")],
    {"fields": {"title": "自测称号", "desc": "自测"}, "slices": {"星星": {"motion": {"preset": "sway", "amp": 8, "period": 2}},
                                                              "底板": {"motion": {"preset": "float", "amp": 3, "period": 1}}}})
want = [f"{T}/Icon/Title_9044.png", f"{T}/Prefab/Title_9044/2D.prefab", f"{T}/Prefab/Title_9044/3D.prefab", f"{T}/Prefab/Title_9044/Image_01.png",
        f"{T}/Prefab/Title_9044/2d_animation.anim", f"{T}/Prefab/Title_9044/3d_animation.controller"]
ok(all(w in P for w in want), "图标 / 2D / 3D / 部件 / 2D、3D 两份动画都在包里")
d2, d3 = P[want[1]].decode(), P[want[2]].decode()
ok(layers(d2) == {"5"} and layers(d3) == {"0"}, "2D 在 UI 层、3D 在默认层(对照 Title_43)")
ok("m_Name: animation" in d2 and "m_Name: animation" in d3 and "!u!212" in d3 and "!u!114" in d2, "带动画:animation 节点挂 Animator;2D 用 Image、3D 用 SpriteRenderer")
a3 = P[f"{T}/Prefab/Title_9044/3d_animation.anim"].decode()
ok("m_PositionCurves:\n  - curve" in a3 and "attribute: m_LocalPosition.y" in a3 and "classID: 4" in a3, "3D 版的浮动动 Transform 的 localPosition(单位 / 100)")
e = entry_of(res)
ok(e["PgcId"] == "190109044" and e["Size"] == {"x": 0.5, "y": 0.5, "z": 0.5} and e["GamePrefab"].endswith("Title_9044/3D.prefab"), "配置条目:PgcId / Size / 2D、3D 路径")
print("[2b] 称号(静态,只有图标)")
job, res, P, M = make("title", ("称号_9045", 304, 72), [sl("图标", 0, 0, 304, 72)], {"fields": {"title": "静态称号"}})
ok(f"{T}/Prefab/Title_9045/image.png" in P and "m_Name: Bg" in P[f"{T}/Prefab/Title_9045/2D.prefab"].decode()
   and not any(p.endswith(".anim") for p in P), "静态称号:图标复制成 image.png,2D / 3D 下一个 Bg,没有动画(对照 Title_41)")

print("[3] 昵称框")
N = "Assets/Loadable/UI/UIWidgets/Nickname"
job, res, P, M = make("nickname_frame", ("昵称框_9020", 447, 130), [
    sl("框", 0, 0, 447, 130, (250, 220, 180, 255)), sl("预览底图", 0, 0, 925, 250), sl("蝴蝶", 380, 5, 50, 40, shape="ellipse")],
    {"fields": {"title": "自测昵称框"}, "slices": {"蝴蝶": {"motion": {"preset": "tint", "color": "#ff6fa8", "period": 2}}}})
want = [f"{N}/Icon/NicknameIcon9020.png", f"{N}/Prefab/Nickname9020/Image.png", f"{N}/Prefab/Nickname9020/Nickname9020.prefab",
        f"{N}/Prefab/Nickname9020/Image_01.png", f"{N}/Prefab/Nickname9020/animation.controller",
        f"{N}/Preview/NicknamePreview9020/Image.png", f"{N}/Preview/NicknamePreview9020/NicknamePreview9020.prefab"]
ok(all(w in P for w in want), "图标 / 框图 / prefab / 部件 / 动画 / 预览底图 / 预览 prefab 都在包里")
pv = P[want[-1]].decode()
ok("stripped" in pv and "m_Font: {fileID: 12800000, guid: 2d1f06229702c49f6a7d8597bb583434" in pv and 'm_Text: "一二三四五六七"' in pv,
   "预览:嵌套昵称框 prefab、白名单字体、示例文字(中文双引号)")
e = entry_of(res)
ok(e["PgcId"] == "180109020" and e["SpriteName"] == "NicknameIcon9020" and e["NameColor"] == "#B8663B", "配置条目:PgcId / SpriteName / 默认昵称颜色")

print("[4] 主页皮肤")
A = "Assets/Arts/UI/Themes/Theme_9046"; LL = "Assets/Loadable/UI/Themes/Theme_9046"
job, res, P, M = make("home_skin", ("主页皮肤_9046", 2436, 1125), [
    sl("背景", 0, 0, 2436, 1125, (255, 247, 203, 255)), sl("底栏", 0, 1009, 2436, 116), sl("底栏上层", 0, 900, 2436, 80),
    sl("卡片1_头部", 120, 100, 925, 250), sl("卡片1_主体", 110, 140, 947, 874), sl("卡片1_位置", 130, 150, 896, 862),
    sl("灯笼", 1800, 40, 160, 220, shape="ellipse"), sl("兔子", 300, 800, 200, 200, shape="ellipse"),
    sl("合成效果图", 0, 0, 2436, 1125), sl("缩略图", 0, 0, 300, 300)],
    {"fields": {"title": "自测主页皮肤", "previewTitle": "<color=#6E3D9E>自测</color>"},
     "slices": {"灯笼": {"motion": {"preset": "sway", "amp": 5, "period": 2}}, "兔子": {"motion": {"preset": "float", "amp": 6, "period": 2}}}})
roles = {s["name"]: s["role"] for s in job["assets"][0]["slices"]}
ok(roles["卡片1_头部"] == "card1_top" and roles["卡片1_主体"] == "card1_body" and roles["卡片1_位置"] == "card1_slot" and roles["底栏上层"] == "bottom2" and roles["灯笼"] == "deco",
   "按切图名认出角色(卡片头 / 主体 / 位置、底栏上层、装饰)")
ok(not next(s for s in job["assets"][0]["slices"] if s["name"] == "卡片1_位置")["ai"], "「卡片位置」只定位,不跑 AI")
want = [f"{A}/bg.png", f"{A}/Image_Bottom0.png", f"{A}/Image_Bottom1.png", f"{A}/Frame01_Top.png", f"{A}/Frame01_Bottom.png", f"{A}/Image_UP.png",
        f"{A}/Image_00.png", f"{A}/Image_01.png", f"{A}/ThemeBg.prefab", f"{A}/animation.anim", f"{A}/animation.controller",
        "Assets/Arts/UI/UIPanel/ProfileTheme/Textures/theme_icon_9046.png", f"{LL}/ThemeBg9046/ThemeBg9046.prefab"] + \
       [f"{d}/Bg{k}.prefab" for d in (A, LL) for k in range(1, 6)] + [f"{LL}/ThemeBg.prefab"]
ok(all(w in P for w in want), "背景 / 底栏 / 卡片框 / 装饰 / 合成图 / 缩略图 / ThemeBg + Bg1~5(源 + 壳)/ 预览 / 动画都在包里" + "".join(f"\n      缺 {w}" for w in want if w not in P))
ok(not any("位置" in p or "Frame02" in p for p in P), "「卡片位置」不导出;没给的卡片框不生成贴图")
tb = P[f"{A}/ThemeBg.prefab"].decode()
ok("m_Name: LeftUp" in tb and "m_Name: LeftDown" in tb and "stripped" in tb and "propertyPath: m_Texture" in tb, "ThemeBg:左上 / 左下装饰组、嵌套 SizeToFitBgView 换成本皮肤的背景")
an = P[f"{A}/animation.anim"].decode()
ok(str(zlib.crc32(b"LeftUp/Image_00")) in an or str(zlib.crc32(b"LeftUp/Image_01")) in an, "动画路径带分组(LeftUp/Image_xx)")
bg1 = P[f"{A}/Bg1.prefab"].decode()
ok("m_SizeDelta: {x: 896, y: 862}" in bg1 and bg1.count("!u!114") == 2, "Bg1:按「卡片1位置」定尺寸,头部 + 主体两张框图")
ok(P[f"{A}/Bg2.prefab"].decode().count("!u!114") == 0, "没给框图的卡片 Bg2:空 prefab(卡片背景透明)")
e = entry_of(res)
ok(e["themeId"] == 9046 and e["pgcId"] == "150109046" and e["colorInfo"]["info_bg5"].endswith("Theme_9046/Bg5.prefab")
   and e["localPath"].endswith("ThemeBg9046/ThemeBg9046.prefab") and e["colorInfo"]["titleBgColor"] == "#F0836C00", "配置条目:themeId / pgcId / colorInfo / localPath")
readme = open(res["readme"], encoding="utf-8").read()
ok('{"configs": [...]}' in readme and "## 导入后" in readme, "README 说明加进 configs 数组、导入后要做的事")

if "--keep" in sys.argv:
    dst = sys.argv[sys.argv.index("--keep") + 1]; os.makedirs(dst, exist_ok=True)
    for k in kept:
        shutil.copy(k, dst)
    print("交付包留在:", dst)
shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("全部通过" if not fails else f"{len(fails)} 项失败"))
sys.exit(1 if fails else 0)
