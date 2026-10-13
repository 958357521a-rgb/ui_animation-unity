# 资源批处理 · 各类资源的 prefab / 动画生成(标准里 "builder" 指定用哪个;头像框走 pipeline_core.build 里原来的特效流程)。
# 每个函数拿到 ctx(见 pipeline_core.Ctx):单张图(角色带 path 的)已经写好,这里只写 prefab、部件图、动画,返回给配置条目用的变量。
# 结构逐项对照主工程 2026-10-13 的最新同类资产(E:\BUDGCB\BUD_CHINA),出处写在每个函数的说明里;改之前先去主工程对照,不要凭记忆改。
# 坐标:切图的 x / y 是设计稿里相对资源画框左上角的像素(y 向下);Unity 里 y 向上,1 设计像素 = 1 UGUI 单位 = 0.01 场景单位(PPU 100)。
import unity_yaml as uy

POS_PRESETS = ("float", "shake")


def _center(s):
    return s["x"] + s["w"] / 2, s["y"] + s["h"] / 2


def _rel(s, ox, oy):
    """切图中心相对 (ox, oy) 的 Unity 坐标(y 向上)"""
    cx, cy = _center(s)
    return cx - ox, oy - cy


def _motion(s):
    m = s.get("motion")
    return m if m and m.get("preset") else None


def _scaled(m, k):
    """场景版(单位 = 像素 / 100):位置类动效的幅度跟着缩小,其余(角度 / 倍数 / 透明度 / 颜色)不变"""
    m = dict(m)
    if m["preset"] in POS_PRESETS:
        m["amp"] = float(m["amp"] if m.get("amp") is not None else uy.PRESETS[m["preset"]]["amp"]) * k
    return m


def _round(v):
    return round(v, 3)


# ---------------- 聊天气泡:角饰特效(对照 ChatBubbleEff_38 的 LeftUp / LeftUp_Game 及其 Loadable 壳) ----------------
# 每个角一个 UGUI 版 <角>.prefab(大厅聊天,根节点锚在气泡对应角上、LayoutElement 忽略布局)和一个 <角>_Game.prefab(3D 头顶气泡,
# 根节点 Transform、子节点 SpriteRenderer;位置由 AvatarChatBox.SetText 按角写死的内缩量摆,所以这里按同样的内缩量换算)。
# 两个版本共用 <角>.controller / <角>_animation.anim(主工程做法);用了浮动 / 抖动(位置类)时 _Game 版单独一份,因为两边单位差 100 倍。
CORNERS = {  # 角色 → (节点名, UGUI 锚点, AvatarChatBox 里的内缩量(场景单位,y 向上))
    "lu": ("LeftUp", (0, 1), (0.35, -0.30)),
    "ru": ("RightUp", (1, 1), (-0.25, -0.25)),
    "ld": ("LeftDown", (0, 0), (0.35, 0.25)),
    "rd": ("RightDown", (1, 0), (-0.25, 0.30)),
}


def build_chat_bubble(ctx):
    a, ed = ctx.asset, ctx.dirs()
    base = ctx.first("bubble")
    bx, by, bw, bh = (base["x"], base["y"], base["w"], base["h"]) if base else (0, 0, a["w"], a["h"])
    pts = {"lu": (bx, by), "ru": (bx + bw, by), "ld": (bx, by + bh), "rd": (bx + bw, by + bh)}
    groups = {k: [] for k in CORNERS}
    for s in ctx.live:
        c = ctx.role(s).get("corner")
        if c == "auto":   # 按位置归到最近的角
            cx, cy = _center(s)
            c = min(pts, key=lambda k: (pts[k][0] - cx) ** 2 + (pts[k][1] - cy) ** 2)
        if c:
            groups[c].append(s)
    n, made = 0, []
    for k, (cname, anchor, inset) in CORNERS.items():
        if not groups[k]:
            continue
        lay, mot_ui, mot_game = [], [], []
        for s in groups[k]:
            n += 1; ln = f"Image_{n:02d}"
            g = ctx.png(f"{ed['sprites']}/{ln}.png", s)
            x, y = _rel(s, *pts[k])
            gx, gy = _round(x / 100 - inset[0]), _round(y / 100 - inset[1])
            lay.append((ln, g, x, y, s["w"], s["h"], gx, gy))
            m = _motion(s)
            if m:
                mot_ui.append(dict(m, path=ln, base_x=x, base_y=y))
                mot_game.append(dict(_scaled(m, 0.01), path=ln, base_x=gx, base_y=gy))
        ctrl_ui = ctrl_game = None
        if mot_ui:
            split = any(m["preset"] in POS_PRESETS for m in mot_ui)
            ctrl_ui = ctx.anim(f"{ed['sprites']}/{cname}_animation.anim", f"{ed['sprites']}/{cname}.controller", mot_ui,
                               colors=("image",) if split else ("image", "sprite"))
            ctrl_game = ctx.anim(f"{ed['sprites']}/{cname}_Game_animation.anim", f"{ed['sprites']}/{cname}_Game.controller", mot_game,
                                 colors=("sprite",)) if split else ctrl_ui
        W = max(10, round(max(2 * (abs(l[2]) + l[4] / 2) for l in lay)))
        H = max(10, round(max(2 * (abs(l[3]) + l[5] / 2) for l in lay)))
        ui = {"name": cname, "anchor_min": anchor, "size": (W, H), "animator": ctrl_ui, "layout_ignore": True,
              "children": [{"name": ln, "image": {"guid": g}, "pos": (x, y), "size": (w, h)} for ln, g, x, y, w, h, _, _ in lay]}
        game = {"name": cname + "_Game", "rect": False, "layer": 0, "animator": ctrl_game,
                "children": [{"name": ln, "pos": (gx, gy), "size": (w, h), "sprite": {"guid": g, "size": (w / 100, h / 100), "order": 2}}
                             for ln, g, x, y, w, h, gx, gy in lay]}
        for tree, rect in ((ui, True), (game, False)):
            text, ids = uy.prefab_tree(tree)
            sg = ctx.add(f"{ed['source']}/{tree['name']}.prefab", text, uy.prefab_meta)
            go, rt = ids[tree["name"]]
            ctx.add(f"{ed['shell']}/{tree['name']}.prefab", uy.shell_prefab(tree["name"], sg, go, rt, (W, H), anchor, rect=rect), uy.prefab_meta)
        made.append(cname)
        ctx.note(f"- 角饰 `{cname}`:{len(lay)} 层、{len(mot_ui)} 个动效 → 源 `{ed['source']}/{cname}.prefab` + `{cname}_Game.prefab`,壳在 `{ed['shell']}/`")
    return {"corners": made}


# ---------------- 称号:2D.prefab(界面)+ 3D.prefab(场景头顶)(对照 Title_41 静态、Title_42 / 43 带动画) ----------------
# 只放在 Loadable(称号没有 Arts 源 + 壳的拆分)。没有部件 = 静态称号:图标原样复制成 image.png,2D 下一个 Bg(Image)、3D 下一个 Bg(SpriteRenderer)。
# 有部件:每个部件一张 Image_XX.png;有动效时加 animation 节点挂 Animator,2D / 3D 各一份 2d_animation / 3d_animation(Title_42 的命名)。
def build_title(ctx):
    a, pd = ctx.asset, ctx.dirs()["prefab"]
    icon = ctx.first("icon")
    parts = ctx.of("part")
    ox, oy = a["w"] / 2, a["h"] / 2
    lay = []
    if parts:
        for i, s in enumerate(parts, 1):
            ln = f"Image_{i:02d}"
            x, y = _rel(s, ox, oy)
            lay.append((ln, ctx.png(f"{pd}/{ln}.png", s), x, y, s["w"], s["h"], _motion(s)))
    elif icon:
        lay.append(("Bg", ctx.png(f"{pd}/image.png", icon), 0, 0, icon["w"], icon["h"], None))
    if not lay:
        raise ValueError(f"{a['name']}:称号要有图标或部件")
    mots = [(ln, x, y, m) for ln, g, x, y, w, h, m in lay if m]
    ctrl2d = ctrl3d = None
    if mots:
        ctrl2d = ctx.anim(f"{pd}/2d_animation.anim", f"{pd}/2d_animation.controller",
                          [dict(m, path=ln, base_x=x, base_y=y) for ln, x, y, m in mots])
        ctrl3d = ctx.anim(f"{pd}/3d_animation.anim", f"{pd}/3d_animation.controller",
                          [dict(_scaled(m, 0.01), path=ln, base_x=_round(x / 100), base_y=_round(y / 100)) for ln, x, y, m in mots],
                          rect=False, colors=("sprite",))
    k2 = [{"name": ln, "image": {"guid": g}, "pos": (x, y), "size": (w, h)} for ln, g, x, y, w, h, m in lay]
    k3 = [{"name": ln, "rect": False, "pos": (_round(x / 100), _round(y / 100)), "sprite": {"guid": g, "size": (w / 100, h / 100), "order": i}}
          for i, (ln, g, x, y, w, h, m) in enumerate(lay)]
    wrap = lambda kids, ctrl: [{"name": "animation", "rect": False, "animator": ctrl, "children": kids}] if ctrl else kids
    for name, layer, kids, ctrl in (("2D", 5, k2, ctrl2d), ("3D", 0, k3, ctrl3d)):
        text, _ = uy.prefab_tree({"name": name, "rect": False, "layer": layer, "children": wrap(kids, ctrl)})
        ctx.add(f"{pd}/{name}.prefab", text, uy.prefab_meta)
    ctx.note(f"- 称号 prefab:`{pd}/2D.prefab`(界面)、`3D.prefab`(场景头顶),{len(lay)} 层、{len(mots)} 个动效")
    return {}


# ---------------- 昵称框:Nickname<id>.prefab + NicknamePreview<id>.prefab(对照 Nickname19 / NicknamePreview19) ----------------
# 只放在 Loadable。Nickname<id>:根节点(图标尺寸 + CanvasRenderer)下一个 Image(框图 = 图标同一张,复制成 Prefab/Nickname<id>/Image.png);
# 有部件时加在 Image 后面,有动效就在根节点挂 Animator(animation.anim / animation.controller)。
# 预览:根节点 261×83 → 预览底图、头像占位(主工程 Preview/Mask group.png)、嵌套 Nickname<id>、示例文字(思源黑体 Heavy,白名单字体)。
def build_nickname(ctx):
    a, dd, refs = ctx.asset, ctx.dirs(), ctx.std.get("refs", {})
    nid = a["id"]; name = f"Nickname{nid}"
    icon = ctx.first("icon")
    if not icon:
        raise ValueError(f"{a['name']}:昵称框要有一张「图标」")
    W, H = icon["w"], icon["h"]
    img = ctx.guid_of(f"{dd['prefab']}/Image.png")
    ox, oy = _center(icon)
    kids, mots = [{"name": "Image", "image": {"guid": img}, "size": (W, H)}], []
    for i, s in enumerate(ctx.of("part"), 1):
        ln = f"Image_{i:02d}"; x, y = _rel(s, ox, oy)
        kids.append({"name": ln, "image": {"guid": ctx.png(f"{dd['prefab']}/{ln}.png", s)}, "pos": (x, y), "size": (s["w"], s["h"])})
        if _motion(s):
            mots.append(dict(_motion(s), path=ln, base_x=x, base_y=y))
    ctrl = ctx.anim(f"{dd['prefab']}/animation.anim", f"{dd['prefab']}/animation.controller", mots) if mots else None
    text, ids = uy.prefab_tree({"name": name, "size": (W, H), "canvas_renderer": True, "animator": ctrl, "children": kids})
    ng = ctx.add(f"{dd['prefab']}/{name}.prefab", text, uy.prefab_meta)
    go, rt = ids[name]
    pv = ctx.first("previewBg")
    if pv:
        pg, psize = ctx.png(f"{dd['preview']}/Image.png", pv), (pv["w"], pv["h"])
    else:   # 没给预览底图:用框图放大(主工程预览里框图约放大 2.13 倍)
        pg, psize = ctx.png(f"{dd['preview']}/Image.png", icon), (round(W * 952 / 447), round(H * 273 / 130))
        ctx.note("- 没有「预览底图」,预览里用框图放大代替")
    rect_mods = [(rt, p, v, None) for p, v in (
        ("m_Pivot.x", "0.5"), ("m_Pivot.y", "0.5"), ("m_AnchorMax.x", "0.5"), ("m_AnchorMax.y", "0.5"), ("m_AnchorMin.x", "0.5"),
        ("m_AnchorMin.y", "0.5"), ("m_SizeDelta.x", uy.num(W)), ("m_SizeDelta.y", uy.num(H)), ("m_LocalPosition.x", "0"),
        ("m_LocalPosition.y", "0"), ("m_LocalPosition.z", "0"), ("m_LocalRotation.w", "1"), ("m_LocalRotation.x", "0"),
        ("m_LocalRotation.y", "0"), ("m_LocalRotation.z", "0"), ("m_AnchoredPosition.x", "0"), ("m_AnchoredPosition.y", "0"),
        ("m_LocalEulerAnglesHint.x", "0"), ("m_LocalEulerAnglesHint.y", "0"), ("m_LocalEulerAnglesHint.z", "0"))]
    preview = {"name": f"NicknamePreview{nid}", "size": (261, 83), "canvas_renderer": True, "children": [
        {"name": "Image (1)", "image": {"guid": pg}, "size": psize},
        {"name": "Image (1)", "image": {"guid": refs["avatarPlaceholder"]}, "pos": (-309.2, 0), "size": (164, 164)},
        {"name": name, "nested": {"guid": ng, "root_rt": rt, "mods": rect_mods + [(go, "m_Name", name, None)]}},
        {"name": "Text (Legacy)", "pos": (0, -3), "size": (307.09, 50.43), "text": {"text": refs.get("sampleText", "一二三四五六七"), "font": refs["font"], "size": 40}}]}
    text, _ = uy.prefab_tree(preview)
    ctx.add(f"{dd['preview']}/NicknamePreview{nid}.prefab", text, uy.prefab_meta)
    ctx.note(f"- 昵称框 prefab `{dd['prefab']}/{name}.prefab`({len(kids) - 1} 个部件、{len(mots)} 个动效)、预览 `{dd['preview']}/NicknamePreview{nid}.prefab`")
    return {}


# ---------------- 主页皮肤:ThemeBg + Bg1~5 + 预览 ThemeBg<id>(对照 Theme_45) ----------------
# Arts/UI/Themes/Theme_<id>/:bg.png(全屏背景,挂在嵌套的 SizeToFitBgView 上)、装饰 Image_XX(按位置分到 LeftUp / LeftDown 两个锚点组,
# 一个 Animator 动全部装饰)、底栏 Image_Bottom0 / 1、卡片框 Frame0<k>_Top / _Bottom → Bg<k>.prefab;
# Loadable/UI/Themes/Theme_<id>/:ThemeBg / Bg1~5 的壳,预览 ThemeBg<id>/ThemeBg<id>.prefab(2436×1125,底栏换成合成效果图 Image_UP)。
def build_home_skin(ctx):
    a, dd, refs = ctx.asset, ctx.dirs(), ctx.std.get("refs", {})
    W, H = a["w"], a["h"]
    decos = {"LeftUp": [], "LeftDown": []}
    for s in ctx.live:
        r = ctx.role(s).get("deco")
        if r:
            up = r == "up" or (r == "auto" and _center(s)[1] < H / 2)
            decos["LeftUp" if up else "LeftDown"].append(s)
    groups, mots, i = {}, [], 0
    for gname, ls in decos.items():
        kids = []
        for s in ls:
            ln = f"Image_{i:02d}"; i += 1
            x, y = _rel(s, 0, 0 if gname == "LeftUp" else H)
            kids.append({"name": ln, "image": {"guid": ctx.png(f"{dd['arts']}/{ln}.png", s)}, "pos": (x, y), "size": (s["w"], s["h"])})
            if _motion(s):
                mots.append(dict(_motion(s), path=f"{gname}/{ln}", base_x=x, base_y=y))
        groups[gname] = {"name": gname, "anchor_min": (0, 0) if gname == "LeftDown" else (0, 1), "size": (100, 100), "children": kids}
    ctrl = ctx.anim(f"{dd['arts']}/animation.anim", f"{dd['arts']}/animation.controller", mots) if mots else None
    bgs = ctx.first("bg")
    sizefit = None
    if bgs:
        sf = refs["sizeToFitBgView"]; bgg = ctx.guid_of(f"{dd['arts']}/bg.png")
        root_mods = [(sf["root_rt"], p, v, None) for p, v in (
            ("m_Pivot.x", "0.5"), ("m_Pivot.y", "0.5"), ("m_AnchorMax.x", "1"), ("m_AnchorMax.y", "1"), ("m_AnchorMin.x", "0"),
            ("m_AnchorMin.y", "0"), ("m_SizeDelta.x", "0"), ("m_SizeDelta.y", "0"), ("m_LocalScale.x", "1"), ("m_LocalScale.y", "1"),
            ("m_LocalScale.z", "1"), ("m_LocalPosition.x", "0"), ("m_LocalPosition.y", "0"), ("m_LocalPosition.z", "0"),
            ("m_LocalRotation.w", "1"), ("m_LocalRotation.x", "0"), ("m_LocalRotation.y", "0"), ("m_LocalRotation.z", "0"),
            ("m_AnchoredPosition.x", "0"), ("m_AnchoredPosition.y", "0"), ("m_LocalEulerAnglesHint.x", "0"),
            ("m_LocalEulerAnglesHint.y", "0"), ("m_LocalEulerAnglesHint.z", "0"))]
        sizefit = {"name": "SizeToFitBgView", "nested": {"guid": sf["guid"], "root_rt": sf["root_rt"], "mods":
                   [(sf["raw_image"], "m_Texture", "", f"{{fileID: 2800000, guid: {bgg}, type: 3}}")] + root_mods
                   + [(sf["root_go"], "m_Name", "SizeToFitBgView", None), (sf["image_rt"], "m_SizeDelta.x", uy.num(W), None),
                      (sf["image_rt"], "m_SizeDelta.y", uy.num(H), None)]}}
    bottom = None
    b0, b1 = ctx.first("bottom"), ctx.first("bottom2")
    if b0:
        bottom = {"name": "Image_Bottom", "anchor_min": (0, 0), "anchor_max": (1, 0), "pos": (0, b0["h"] / 2), "size": (0, b0["h"]),
                  "image": {"guid": ctx.guid_of(f"{dd['arts']}/Image_Bottom0.png")}, "children": []}
        if b1:
            bottom["children"].append({"name": "Image", "anchor_min": (0, 0), "anchor_max": (1, 0), "pos": (0, H - _center(b1)[1]),
                                       "size": (0, b1["h"]), "image": {"guid": ctx.guid_of(f"{dd['arts']}/Image_Bottom1.png")}})
    body = [c for c in (sizefit, groups["LeftDown"], groups["LeftUp"], bottom) if c]
    text, ids = uy.prefab_tree({"name": "ThemeBg", "anchor_min": (0, 0), "anchor_max": (1, 1), "size": (0, 0), "animator": ctrl, "children": body})
    sg = ctx.add(f"{dd['arts']}/ThemeBg.prefab", text, uy.prefab_meta)
    go, rt = ids["ThemeBg"]
    ctx.add(f"{dd['loadable']}/ThemeBg.prefab", uy.shell_prefab("ThemeBg", sg, go, rt, (0, 0), (0, 0), (1, 1)), uy.prefab_meta)
    # 卡片框 Bg1~5:有「卡片 k 位置」就以它为中心和尺寸,否则以框主体为中心、尺寸用标准里的默认值(Theme_45 的壳)
    sizes = ctx.std.get("cardSizes", {})
    for k in range(1, 6):
        top, bd, slot = ctx.first(f"card{k}_top"), ctx.first(f"card{k}_body"), ctx.first(f"card{k}_slot")
        ref = slot or bd or top
        size = (slot["w"], slot["h"]) if slot else tuple(sizes.get(str(k), (100, 100)))
        kids = []
        for s, nm, fn in ((bd, "Image", f"Frame0{k}_Bottom"), (top, "Image (1)", f"Frame0{k}_Top")):
            if s:
                kids.append({"name": nm, "image": {"guid": ctx.guid_of(f"{dd['arts']}/{fn}.png")}, "pos": _rel(s, *_center(ref)), "size": (s["w"], s["h"])})
        text, ids = uy.prefab_tree({"name": f"Bg{k}", "size": size, "children": kids})
        g = ctx.add(f"{dd['arts']}/Bg{k}.prefab", text, uy.prefab_meta)
        go, rt = ids[f"Bg{k}"]
        ctx.add(f"{dd['loadable']}/Bg{k}.prefab", uy.shell_prefab(f"Bg{k}", g, go, rt, size), uy.prefab_meta)
        if not kids:
            ctx.note(f"- 卡片 {k} 没有框图:Bg{k} 是空的(卡片背景透明)")
    # 预览:同一套装饰 + 合成效果图(没有就用底栏)
    up = ctx.first("composite")
    pbottom = ({"name": "Image_Bottom", "size": (W, H), "image": {"guid": ctx.guid_of(f"{dd['arts']}/Image_UP.png")}} if up else bottom)
    pv = f"ThemeBg{a['id']}"
    text, _ = uy.prefab_tree({"name": pv, "size": (W, H), "animator": ctrl,
                              "children": [c for c in (sizefit, groups["LeftDown"], groups["LeftUp"], pbottom) if c]})
    ctx.add(f"{dd['loadable']}/{pv}/{pv}.prefab", text, uy.prefab_meta)
    ctx.note(f"- 主页皮肤:`{dd['arts']}/ThemeBg.prefab`(装饰 {i} 个、动效 {len(mots)} 个)、Bg1~5,壳在 `{dd['loadable']}/`,预览 `{dd['loadable']}/{pv}/{pv}.prefab`")
    return {}


BUILDERS = {"chat_bubble": build_chat_bubble, "title": build_title, "nickname": build_nickname, "home_skin": build_home_skin}
