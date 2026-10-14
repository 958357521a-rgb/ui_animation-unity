# BUD UI Studio 本地开发服务
# - 静态托管整个 Studio 文件夹(浏览器打开 http://localhost:<端口>/,自动跳到 BUD_UI_Studio.html)
# - GET /api/projects:列出 projects/ 里的工程文件(工作台「从共享文件夹载入」用,局域网也能读)
# - POST /api/save-project?name=<模块名>:把工作台工程(含贴图)写入 projects/<模块名>.budui.json
# - POST /api/save-export?name=<文件名>.unitypackage:把导出的交付包另存到 exports/(工作台「导出交付包」时自动调用)
# - POST /api/unity/sprites|file:「沿用旧资源」用:按名字找主工程里的 UI 切图(带 GUID、尺寸)、读一张 PNG 做缩略图
# - POST /api/unity/search|match|scan|apply:「覆盖到 Unity」用(JSON 请求体,只接受本机工作台页面发起的请求):
#     search 按文件名 / 面板名 / PanelId / 一句中文找主工程里的 prefab;match 用模块的全部界面文字找最像的旧 prefab;scan 读目标 prefab、已有 meta 的 GUID、引用它的壳/配置、代码里的 Find 节点名;
#     apply 把生成的文件写进主工程(已有 .meta 一律保留 → GUID 不变),被覆盖/删除的旧文件先备份到 backups/<时间>/
#   直接双击打开的工作台(file://)也能用:服务每次启动生成随机口令写进 dev/local_token_<端口>.js,
#   file:// 页面用 <script> 读这个本机文件、请求时带上口令;这个文件不通过 HTTP 提供,网站拿不到
# 用法:python dev/studio_server.py [端口,默认 8791] [--once 保存一次工程后自动退出] [--lan 局域网共享]
# --lan:监听所有网卡,同一局域网的同事用 http://<本机局域网 IP>:<端口>/ 直接打开工作台(工程存在各自浏览器里)。
#   别的电脑只能读工作台页面、projects/ 工程文件、figma-plugin/、docs/、README.md;
#   写接口(覆盖到 Unity、写回工程、另存交付包)和其余文件(backups/、dev/、主工程相关)只认本机(127.0.0.1)。
# 资源批处理(pipeline.html,逻辑在 dev/pipeline/core.py):
#   POST /api/pipeline/<动作>:只认本机工作台页面(同「覆盖到 Unity」的口令 / Origin 校验);
#   /api/bridge/*:Figma 插件「资源批处理」命令和工作台之间的中转箱(插件把选中的切图发进来、把处理结果取回去),
#   只认本机 + 配对码(请求头 X-BudUI-Bridge = dev/bridge_key.txt,第一次用时生成,在批处理页面上显示,插件里填一次)。
#   POST /api/bridge/screens:界面改版插件「发送到工作台」(配对码,整包存 exports/bridge_screens/ 留最近 5 个,上限 200MB);
#   GET /api/figma-inbox、GET /api/figma-inbox/<id>、POST /api/figma-inbox/<id>/done:工作台收件(只认本机工作台页面,口令 / Origin 同 /api/unity/*)。
import base64, datetime, glob, http.server, json, os, re, secrets, shutil, socket, sys, urllib.parse

# pythonw 启动(桌面应用在后台无窗口起服务)时没有控制台,stdout/stderr 是 None:请求日志一写就抛异常、连接被掐断
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
# 非中文区域设置的电脑上,控制台/管道编码可能写不了中文:替换掉写不了的字符,别让服务一启动就崩
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "dev", "pipeline"))   # 资源批处理核心(用到时才 import:没装 Pillow 也不影响工作台其他功能)
PROJECTS = os.path.join(ROOT, "projects")
EXPORTS = os.path.join(ROOT, "exports")
BACKUPS = os.path.join(ROOT, "backups")
REFERENCE = os.path.join(ROOT, "unity-reference")
ONCE = "--once" in sys.argv
LAN = "--lan" in sys.argv
PORT = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8791)
TOKEN = secrets.token_hex(16)
TOKEN_FILE = os.path.join(ROOT, "dev", f"local_token_{PORT}.js")
saved = False


def safe_name(raw, default):
    return re.sub(r"[^\w一-鿿.-]", "_", os.path.basename(raw)) or default


# ---------------- 覆盖到 Unity ----------------
GUID_RE = re.compile(r"^guid: ([0-9a-f]{32})\s*$", re.M)
FIND_RE = re.compile(r'\b(?:Find|FindChild|FindDeepChild|FindChildByName|FindTransform)\s*(?:<[^>]*>)?\s*\(\s*"([^"]+)"')


def unity_root(raw):
    root = os.path.abspath(os.path.expanduser((raw or "").strip().strip('"')))
    if not (os.path.isdir(os.path.join(root, "Assets")) and os.path.isfile(os.path.join(root, "ProjectSettings", "ProjectVersion.txt"))):
        raise ValueError("不是 Unity 工程目录(要有 Assets/ 和 ProjectSettings/ProjectVersion.txt):" + root)
    return root


def asset_abs(root, rel):
    """主工程内 Assets/... 相对路径 → 绝对路径;越出 Assets/ 的一律拒绝"""
    rel = (rel or "").replace("\\", "/")
    if not rel.startswith("Assets/") or any(p in ("", ".", "..") for p in rel.split("/")):
        raise ValueError("路径必须是 Assets/ 下的相对路径:" + rel)
    p = os.path.normpath(os.path.join(root, rel))
    if not p.startswith(os.path.join(root, "Assets") + os.sep):
        raise ValueError("路径越界:" + rel)
    return p


def to_rel(root, p):
    return os.path.relpath(p, root).replace("\\", "/")


def read_text(p):
    with open(p, "rb") as f:
        return f.read().decode("utf-8", "replace")


def meta_guid(p):
    try:
        m = GUID_RE.search(read_text(p + ".meta"))
        return m.group(1) if m else None
    except OSError:
        return None


def walk_files(root, rel_dir, ext, skip=()):
    base = os.path.join(root, rel_dir)
    for r, ds, fs in os.walk(base):
        if skip:   # 剪掉不需要的大目录(美术资源十几万个文件,冷启动时一遍就是几分钟)
            ds[:] = [d for d in ds if to_rel(root, os.path.join(r, d)) not in skip]
        for f in fs:
            if f.endswith(ext):
                yield os.path.join(r, f)


NO_SCRIPT_DIRS = {"Assets/Arts", "Assets/Loadable", "Assets/StreamingAssets", "Assets/Resources", "Assets/AddressableAssetsData"}
_script_index = {}   # 工程目录 → (建立时间, {脚本 GUID: 路径});10 分钟内复用


def script_index(root):
    hit = _script_index.get(root)
    if hit and datetime.datetime.now().timestamp() - hit[0] < 600:
        return hit[1]
    idx = {}
    for f in walk_files(root, "Assets", ".cs.meta", NO_SCRIPT_DIRS):
        g = meta_guid(f[:-5])
        if g:
            idx[g] = to_rel(root, f[:-5])
    _script_index[root] = (datetime.datetime.now().timestamp(), idx)
    return idx


def root_source_guid(text):
    """变体:根是一个 PrefabInstance(m_TransformParent 为 0),返回它的源 prefab GUID;不是变体返回 None"""
    for doc in re.split(r"\n(?=--- !u!)", text):
        if doc.startswith("--- !u!1001 ") and re.search(r"m_TransformParent: \{fileID: 0\}", doc):
            m = re.search(r"m_SourcePrefab: \{fileID: \d+, guid: ([0-9a-f]{32})", doc)
            if m:
                return m.group(1)
    return None


# ---- 按界面文字 / 面板名找旧 prefab(接手的人不知道旧资源放在哪) ----
UI_DIRS = ("Assets/Arts/UI", "Assets/Loadable/UI")
TEXT_RE = re.compile(r"^[ \t]*m_[Tt]ext: (\"(?:[^\"\\]|\\.)*\"|'(?:[^']|'')*'|[^\n]*)", re.M)
CJK_RE = re.compile(r"[一-鿿]")
_ESC = {"n": "\n", "t": "\t", "r": "", "0": "", '"': '"', "\\": "\\", "/": "/", " ": " ", "_": " "}


def yaml_scalar(s):
    """Unity YAML 里的字符串值 → 原文(中文多半存成 "\\uXXXX" 转义,长串会折行)"""
    s = s.strip()
    if s.startswith('"') and s.endswith('"') and len(s) > 1:
        body = re.sub(r"\\\r?\n[ \t]*", "", s[1:-1])        # 行尾 \ 续行
        body = re.sub(r"[ \t]*\r?\n[ \t]*", " ", body)     # 普通折行 = 一个空格
        return re.sub(r"\\(u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|x[0-9a-fA-F]{2}|.)",
                      lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1)[0] in "uUx" and len(m.group(1)) > 1 else _ESC.get(m.group(1), m.group(1)), body)
    if s.startswith("'") and s.endswith("'") and len(s) > 1:
        return s[1:-1].replace("''", "'")
    return s


def norm_text(s):
    return re.sub(r"\s+", "", s or "")


_ui_cache = {}   # 工程目录 → {prefab 绝对路径: (mtime, size, {texts, variant_of, guid})};按修改时间增量刷新


def ui_index(root):
    cache = _ui_cache.setdefault(root, {})
    seen = set()
    for d in UI_DIRS:
        for p in walk_files(root, d, ".prefab"):
            p = os.path.normpath(p)   # 统一分隔符,和配置表路径拼出来的键对得上
            seen.add(p)
            st = os.stat(p)
            hit = cache.get(p)
            if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
                continue
            t = read_text(p)
            texts = {norm_text(yaml_scalar(m.group(1))) for m in TEXT_RE.finditer(t)}
            cache[p] = (st.st_mtime, st.st_size, {"texts": {x for x in texts if x}, "source": root_source_guid(t), "guid": meta_guid(p)})
    for p in list(cache):
        if p not in seen:
            del cache[p]
    return cache


def panel_entries(root):
    """UIPanel 配置表:[{id, name, path}]"""
    cfg = os.path.join(root, "Assets", "Arts", "Config", "Asset", "UIPanel.asset")
    if not os.path.isfile(cfg):
        return []
    out, cur = [], {}
    for ln in read_text(cfg).split("\n"):
        m = re.match(r"\s*-?\s*_(PanelId|Name|ResPath):\s*(.*)$", ln)
        if not m:
            continue
        if m.group(1) == "PanelId":
            cur = {"id": m.group(2).strip()}
            out.append(cur)
        else:
            cur[{"Name": "name", "ResPath": "path"}[m.group(1)]] = m.group(2).strip()
    return [e for e in out if e.get("path")]


def panels_by_prefab(root, idx):
    """prefab 相对路径 → 加载它的面板(配置表直接指向它,或指向以它为源的 Loadable 壳)"""
    by_guid = {v[2]["guid"]: to_rel(root, p) for p, v in idx.items() if v[2]["guid"]}
    res = {}
    for e in panel_entries(root):
        res.setdefault(e["path"], []).append(e)
        info = idx.get(os.path.normpath(os.path.join(root, e["path"])))
        src = info and info[2]["source"] and by_guid.get(info[2]["source"])
        if src:
            res.setdefault(src, []).append(e)
    return res


def describe(root, idx, panels, p):
    rel = to_rel(root, p)
    return {"path": rel, "variant": bool(idx[p][2]["source"]), "panels": [f'{e["id"]} {e.get("name", "")}' for e in panels.get(rel, [])]}


def similar(a, b):
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return short in long_ and len(CJK_RE.findall(short)) >= 3 and len(short) * 2 >= len(long_)


def unity_match(root, texts):
    """模块里的界面文字 → 最像的旧 prefab:整句相同算 2 分,互相包含算 1 分(每句只算一次)。
    包含要求短的一句至少 3 个汉字、且不短于长句的一半,免得「充值」「领取」这种词把不相干的面板都算进来"""
    want = [t for t in {norm_text(x) for x in texts or []} if len(CJK_RE.findall(t)) >= 2]
    idx = ui_index(root)
    scored = []
    for p, (_, _, info) in idx.items():
        if info["source"] or not info["texts"]:
            continue
        score, hits = 0, []
        for w in want:
            if w in info["texts"]:
                score += 2
                hits.append(w)
            elif any(similar(w, t) for t in info["texts"]):
                score += 1
                hits.append(w)
        if score:
            scored.append((score, p, hits))
    scored.sort(key=lambda x: -x[0])
    panels = panels_by_prefab(root, idx)
    return [dict(describe(root, idx, panels, p), score=s, matched=hits[:8], total=len(want)) for s, p, hits in scored[:12]]


def unity_search(root, q):
    """关键字可以是:prefab 文件名的一部分、面板名或 PanelId,或者界面上的一句中文"""
    q = (q or "").strip()
    if CJK_RE.search(q):
        return unity_match(root, [q])
    idx = ui_index(root)
    panels = panels_by_prefab(root, idx)
    ql = q.lower()
    hits = {p for p in idx if not ql or ql in os.path.basename(p).lower()}
    for e in panel_entries(root):
        if ql and (ql in e.get("name", "").lower() or ql == e["id"]):
            hits.update(os.path.normpath(os.path.join(root, r)) for r, es in panels.items() if e in es)
    return [describe(root, idx, panels, p) for p in sorted(hits) if p in idx][:60]


# ---------------- 沿用旧资源:在主工程里找旧切图 ----------------
SPRITE_DIRS = ("Assets/Arts/UI", "Assets/Loadable/UI")   # UI 切图只在这两处(约一万张,遍历不到 1 秒)


def png_size(p):
    try:
        with open(p, "rb") as f:
            h = f.read(24)
        if h[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(h[16:20], "big"), int.from_bytes(h[20:24], "big")
    except OSError:
        pass
    return 0, 0


def sprite_info(root, rel):
    """主工程里一张切图:GUID、是否单张 Sprite(多切片的图集纹理暂不支持)、像素尺寸"""
    p = asset_abs(root, rel)
    if not os.path.isfile(p) or not os.path.isfile(p + ".meta"):
        return {"path": rel, "exists": False}
    meta = read_text(p + ".meta")
    mode = re.search(r"^\s*spriteMode: (\d+)", meta, re.M)
    ttype = re.search(r"^\s*textureType: (\d+)", meta, re.M)
    w, h = png_size(p)
    return {"path": rel, "exists": True, "guid": meta_guid(p), "single": bool(ttype and ttype.group(1) == "8" and mode and mode.group(1) == "1"), "w": w, "h": h}


def unity_sprites(root, q):
    """按文件名 / 路径片段找 UI 切图(不区分大小写,空格分隔的多个词都要命中)"""
    words = [w for w in (q or "").lower().replace("\\", "/").split() if w]
    if not words:
        return []
    hits = []
    for d in SPRITE_DIRS:
        for f in walk_files(root, d, ".png"):
            rel = to_rel(root, f)
            if all(w in rel.lower() for w in words):
                hits.append(rel)
    hits.sort(key=lambda r: (not all(w in os.path.basename(r).lower() for w in words), r.lower()))
    return [sprite_info(root, r) for r in hits[:80]]


def unity_file(root, rel):
    """读主工程里的一张 PNG(工作台显示缩略图、预览旧资源用)"""
    p = asset_abs(root, rel)
    if not rel.lower().endswith(".png") or not os.path.isfile(p):
        raise ValueError("只能读 Assets/ 里的 PNG:" + rel)
    with open(p, "rb") as f:
        return {"path": rel, "data": base64.b64encode(f.read()).decode()}


def unity_scan(root, req):
    res = {"unityVersion": (re.search(r"m_EditorVersion: (\S+)", read_text(os.path.join(root, "ProjectSettings", "ProjectVersion.txt"))) or [None, "?"])[1]}
    target = req.get("prefab", "")
    p = asset_abs(root, target)
    text = read_text(p) if os.path.isfile(p) else None
    src = root_source_guid(text) if text else None
    if src:   # 选中的是 Loadable 变体壳:真正要覆盖的是它指向的源 prefab
        metas = (x for d in ("Assets/Arts", "Assets/Loadable", "Assets") for x in walk_files(root, d, ".prefab.meta"))   # 常见位置先找,最后全工程兜底
        hit = next((x[:-5] for x in metas if meta_guid(x[:-5]) == src), None)
        if not hit:
            raise ValueError(f"{target} 是变体,但找不到它的源 prefab(GUID {src})")
        res["redirect"] = {"from": target, "to": to_rel(root, hit)}
        target, p, text = to_rel(root, hit), hit, read_text(hit)
        if root_source_guid(text):
            raise ValueError(f"源 prefab {target} 本身也是变体,不能直接覆盖")
    guid = meta_guid(p) if text is not None else None
    res["target"] = {"path": target, "exists": text is not None, "guid": guid, "text": text}
    # 已有文件的 GUID(沿用它们,引用才不断):目标 prefab + 贴图目录 + 脚本目录
    existing = {}
    if guid:
        existing[target] = guid
    for d in (req.get("art"), req.get("scripts")):
        if d:
            asset_abs(root, d + "/x")
            for f in walk_files(root, d, ""):
                if not f.endswith(".meta") and os.path.isfile(f + ".meta"):
                    existing[to_rel(root, f)] = meta_guid(f)
    res["existing"] = existing
    # 标了「沿用旧资源」并指定了旧切图的节点:核对这些切图还在不在、GUID 有没有变
    res["spriteRefs"] = {r: sprite_info(root, r) for r in (req.get("sprites") or []) if isinstance(r, str)}
    # 手写业务逻辑的副本(unity-reference/<模块名>/*.Logic.cs):主工程里没有时,工作台随本次覆盖一起写进去
    # (Logic 是 partial,单独先放进主工程会因为外壳类还不存在而编译失败;删过模块目录时也靠它找回)
    mod = re.sub(r"[^A-Za-z0-9_]", "", req.get("module") or "")
    ref_dir = os.path.join(REFERENCE, mod) if mod else None
    res["logicCopies"] = {os.path.basename(f): read_text(f) for f in glob.glob(os.path.join(ref_dir, "*.Logic.cs"))} if ref_dir and os.path.isdir(ref_dir) else {}
    # 谁引用了目标:Loadable 壳(变体)和嵌套使用它的 prefab,以及它们对目标里哪些对象做了 override
    refs = []
    if guid:
        key = guid.encode()
        for d in ("Assets/Loadable", "Assets/Arts"):
            for f in walk_files(root, d, ".prefab"):
                if f == p:
                    continue
                with open(f, "rb") as fh:
                    data = fh.read()
                if key not in data:
                    continue
                t = data.decode("utf-8", "replace")
                mods = re.findall(r"target: \{fileID: (-?\d+), guid: " + guid, t)
                refs.append({"path": to_rel(root, f), "shell": root_source_guid(t) == guid, "targets": sorted(set(mods)), "mods": len(mods)})
    res["refs"] = refs
    # 面板配置表里指向这些路径的条目
    cfg = os.path.join(root, "Assets", "Arts", "Config", "Asset", "UIPanel.asset")
    panels = []
    if os.path.isfile(cfg):
        lines = read_text(cfg).split("\n")
        paths = {target} | {r["path"] for r in refs}
        for i, ln in enumerate(lines):
            if "_ResPath:" in ln and ln.split("_ResPath:", 1)[1].strip() in paths:
                name = next((lines[j].split(":", 1)[1].strip() for j in range(i - 1, max(i - 6, -1), -1) if "_Name:" in lines[j]), "?")
                pid = next((lines[j].split(":", 1)[1].strip() for j in range(i - 1, max(i - 6, -1), -1) if "_PanelId:" in lines[j]), "?")
                panels.append({"name": name, "id": pid, "path": ln.split("_ResPath:", 1)[1].strip()})
    res["panels"] = panels
    # 目标 prefab 上挂的脚本 GUID → 脚本路径(找出覆盖后会消失的业务脚本)
    scripts = {}
    if text:
        idx = script_index(root)
        scripts = {g: idx[g] for g in set(re.findall(r"m_Script: \{fileID: 11500000, guid: ([0-9a-f]{32})", text)) if g in idx}
    res["scripts"] = scripts
    # 哪些是面板脚本(继承 BasePanel):只有根节点挂的是面板脚本,才需要给新 prefab 带面板外壳;
    # 子视图(如充值界面的钻石页 GemPackView,根上是普通 MonoBehaviour)带了 BasePanel 反而会被框架当成面板
    res["panelScripts"] = [g for g, rel in scripts.items() if re.search(r":\s*BasePanel\s*<", read_text(os.path.join(root, rel)))]
    # 代码里用字符串查找的节点名(Find("xxx")),只看 UI 代码
    finds = []
    for f in walk_files(root, "Assets/Scripts", ".cs"):
        for i, ln in enumerate(read_text(f).split("\n"), 1):
            for m in FIND_RE.finditer(ln):
                finds.append([m.group(1), to_rel(root, f), i])
    res["finds"] = finds
    return res


def unity_apply(root, req):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(BACKUPS, stamp)
    done = {"written": 0, "metaWritten": 0, "removed": 0, "backedUp": 0, "backup": bdir}
    files = req.get("files") or []
    remove = req.get("remove") or []
    plan = [(asset_abs(root, f["path"]), f) for f in files] + [(asset_abs(root, r), None) for r in remove]   # 先全部校验路径,再动手

    def backup(path):
        if os.path.isfile(path):
            dst = os.path.join(bdir, to_rel(root, path))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(path, dst)
            done["backedUp"] += 1

    for path, f in plan:
        backup(path)
        if f is None:
            backup(path + ".meta")
            for x in (path, path + ".meta"):
                if os.path.isfile(x):
                    os.remove(x)
            done["removed"] += 1
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(f["data"]))
        done["written"] += 1
        if not os.path.isfile(path + ".meta") and f.get("meta"):   # 已有 meta 不动:GUID 和导入设置都保留
            with open(path + ".meta", "wb") as fh:
                fh.write(f["meta"].encode("utf-8"))
            done["metaWritten"] += 1
    if not done["backedUp"]:
        done["backup"] = None
    return done


# ---------------- Figma 插件 → 工作台:界面改版的「发送到工作台」收件箱 ----------------
SCREENS_DIR = os.path.join(EXPORTS, "bridge_screens")
SCREENS_KEEP = 5
SCREENS_MAX = 200 * 1024 * 1024   # 只对 /api/bridge/screens 放宽到 200MB(整包含全部切图的 base64)
SCREENS_ID_RE = re.compile(r"^\d{8}-\d{9}$")


def screens_store(raw):
    """把插件包原样存成 exports/bridge_screens/<时间戳>.budfig.json(旁边一个 .meta.json 放列表用的摘要),只留最近 5 个"""
    pkg = json.loads(raw)
    if not isinstance(pkg, dict) or pkg.get("format") != "bud-ui-studio/figma-export" or not isinstance(pkg.get("screens"), list):
        raise ValueError("不是 BUD UI Studio 插件导出包(format 应为 bud-ui-studio/figma-export)")
    names = [str((s.get("frame") or {}).get("name") or "") for s in pkg["screens"] if isinstance(s, dict)]
    os.makedirs(SCREENS_DIR, exist_ok=True)
    now = datetime.datetime.now()
    sid = now.strftime("%Y%m%d-%H%M%S") + f"{now.microsecond // 1000:03d}"
    with open(os.path.join(SCREENS_DIR, sid + ".budfig.json"), "wb") as f:
        f.write(raw)
    with open(os.path.join(SCREENS_DIR, sid + ".meta.json"), "w", encoding="utf-8") as f:
        json.dump({"id": sid, "file": str(pkg.get("fileName") or ""), "screens": names, "time": now.isoformat(timespec="seconds"), "size": len(raw)}, f, ensure_ascii=False)
    for old in sorted(glob.glob(os.path.join(SCREENS_DIR, "*.budfig.json")))[:-SCREENS_KEEP]:
        base = old[:-len(".budfig.json")]
        for ext in (".budfig.json", ".meta.json", ".done"):
            try:
                os.remove(base + ext)
            except OSError:
                pass
    return {"ok": True, "id": sid, "screens": len(names)}


def screens_list():
    items = []
    for p in sorted(glob.glob(os.path.join(SCREENS_DIR, "*.meta.json")), reverse=True):
        base = p[:-len(".meta.json")]
        if os.path.exists(base + ".done") or not os.path.isfile(base + ".budfig.json"):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                items.append(json.load(f))
        except (OSError, ValueError):
            pass
    return items


def screens_path(sid):
    if not SCREENS_ID_RE.match(sid or ""):
        raise ValueError("收件箱编号不对")
    p = os.path.join(SCREENS_DIR, sid + ".budfig.json")
    if not os.path.isfile(p):
        raise FileNotFoundError("收件箱里没有这个包(可能已被新的包顶掉,让插件重新发送)")
    return p


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-BudUI-Token, X-BudUI-Bridge")
        self.send_header("Access-Control-Allow-Private-Network", "true")   # Chrome/Edge:file:// 页面访问本机服务要这个许可
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-cache")   # 每次都向服务确认是否有新版,工作台更新后不会拿到浏览器缓存的旧页面
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/bridge/"):
            return self.do_bridge("GET")
        if urllib.parse.urlparse(self.path).path.startswith("/api/figma-inbox"):
            return self.do_figma_inbox("GET")
        if urllib.parse.urlparse(self.path).path == "/api/projects":   # 工作台「从共享文件夹载入」:列出 projects/ 里的工程文件
            items = [{"name": os.path.basename(f), "bytes": os.path.getsize(f), "mtime": int(os.path.getmtime(f) * 1000)}
                     for f in glob.glob(os.path.join(PROJECTS, "*.budui.json"))]
            return self.reply(200, {"items": sorted(items, key=lambda x: -x["mtime"])})
        if urllib.parse.urlparse(self.path).path == "/":   # 打开根地址直接进工作台(预览面板默认打开的就是根地址)
            self.send_response(302)
            self.send_header("Location", "/BUD_UI_Studio.html")
            self.end_headers()
            return
        super().do_GET()

    def is_local(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def lan_readable(self, p):
        """局域网里别的电脑能读的文件:工作台页面、工程文件、Figma 插件、文档"""
        if not os.path.isfile(p):
            return False
        rp, top = os.path.normcase(os.path.realpath(p)), lambda *a: os.path.normcase(os.path.realpath(os.path.join(ROOT, *a)))
        if rp in (top("BUD_UI_Studio.html"), top("README.md")):
            return True
        if rp.startswith(top("projects") + os.sep) and rp.endswith(".budui.json"):
            return True
        return any(rp.startswith(top(d) + os.sep) for d in ("figma-plugin", "docs"))

    def send_head(self):
        p = self.translate_path(self.path)
        if not self.is_local() and not self.lan_readable(p):
            self.send_error(403, "LAN clients can only open the workbench")
            return None
        # 口令文件只给本机 file:// 页面用 <script> 读,不通过 HTTP 提供(按"同一个文件"判断,大小写、短文件名都绕不过去)
        if os.path.isfile(p) and any(os.path.samefile(p, t) for t in glob.glob(os.path.join(ROOT, "dev", "local_token_*.js"))):
            self.send_error(403)
            return None
        return super().send_head()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def reply(self, code, data=None):
        self.send_response(code)
        if data is not None:
            self.send_header("Content-Type", "application/json")
        self.end_headers()
        if data is not None:
            self.wfile.write(json.dumps(data).encode())

    def trusted(self):
        # 写主工程的接口只认本机工作台页面:别的网站也能向 localhost 发 POST,浏览器会带上它自己的 Origin。
        # file:// 页面的 Origin 是 "null"(沙箱 iframe 也是),所以它要靠口令
        if secrets.compare_digest(self.headers.get("X-BudUI-Token", ""), TOKEN):
            return True
        o = self.headers.get("Origin")
        if not o:
            return True
        u = urllib.parse.urlparse(o)
        return u.hostname in ("localhost", "127.0.0.1") and u.port == PORT

    def do_unity(self, path):
        if not self.trusted():
            return self.reply(403, {"error": "只接受本机工作台页面的请求(直接打开的工作台要先刷新页面拿到本次服务的口令)"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            root = unity_root(req.get("root"))
            if path == "/api/unity/search":
                return self.reply(200, {"items": unity_search(root, req.get("q"))})
            if path == "/api/unity/match":
                return self.reply(200, {"items": unity_match(root, req.get("texts"))})
            if path == "/api/unity/sprites":
                return self.reply(200, {"items": unity_sprites(root, req.get("q"))})
            if path == "/api/unity/file":
                return self.reply(200, unity_file(root, req.get("path") or ""))
            if path == "/api/unity/scan":
                return self.reply(200, unity_scan(root, req))
            return self.reply(200, unity_apply(root, req))
        except (ValueError, OSError) as e:
            return self.reply(400, {"error": str(e)})

    def do_bridge(self, method):
        """Figma 插件 ↔ 工作台中转箱:只认本机 + 配对码"""
        import pipeline_core as pc
        if not self.is_local():
            return self.reply(403, {"error": "中转箱只给本机的 Figma 插件用"})
        if not secrets.compare_digest(self.headers.get("X-BudUI-Bridge", ""), pc.bridge_key()):
            return self.reply(403, {"error": "配对码不对:在工作台「资源批处理」页面右上角看配对码,填进 Figma 插件"})
        path = urllib.parse.urlparse(self.path).path
        try:
            if method == "GET" and path == "/api/bridge/ping":
                return self.reply(200, {"ok": True, "name": "BUD UI Studio"})
            if method == "GET" and path == "/api/bridge/outbox":
                return self.reply(200, {"items": pc.bridge_outbox()})
            if method == "POST" and path == "/api/bridge/screens":   # 界面改版插件包:原样存盘,不解析切图
                n = int(self.headers.get("Content-Length", 0))
                if n > SCREENS_MAX:
                    return self.reply(413, {"error": f"包太大({n // 1048576} MB,上限 {SCREENS_MAX // 1048576} MB):少选几个界面分批发送"})
                return self.reply(200, screens_store(self.rfile.read(n)))
            body =json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}") if method == "POST" else {}
            if method == "POST" and path == "/api/bridge/inbox":
                return self.reply(200, pc.bridge_inbox_add(body))
            if method == "POST" and path == "/api/bridge/outbox/done":
                return self.reply(200, pc.bridge_outbox_done(body.get("job", "")))
        except (ValueError, KeyError, OSError) as e:
            return self.reply(400, {"error": str(e)})
        return self.reply(404)

    def do_figma_inbox(self, method):
        """工作台取插件发来的界面包:只认本机工作台页面(同 /api/unity/*)"""
        if not self.is_local():
            return self.reply(403, {"error": "收件箱只给本机工作台用"})
        if not self.trusted():
            return self.reply(403, {"error": "只接受本机工作台页面的请求(直接打开的工作台要先刷新页面拿到本次服务的口令)"})
        parts = urllib.parse.urlparse(self.path).path[len("/api/figma-inbox"):].strip("/").split("/")
        try:
            if method == "GET" and parts == [""]:
                return self.reply(200, {"items": screens_list()})
            if method == "GET" and len(parts) == 1:
                with open(screens_path(parts[0]), "rb") as f:
                    raw = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if method == "POST" and len(parts) == 2 and parts[1] == "done":
                p = screens_path(parts[0])
                open(p[:-len(".budfig.json")] + ".done", "w").close()
                return self.reply(200, {"ok": True})
        except FileNotFoundError as e:
            return self.reply(404, {"error": str(e)})
        except (ValueError, OSError) as e:
            return self.reply(400, {"error": str(e)})
        return self.reply(404)

    def do_pipeline(self, action):
        """资源批处理页面的接口:只认本机工作台页面"""
        import pipeline_core as pc
        if not self.trusted():
            return self.reply(403, {"error": "只接受本机工作台页面的请求(直接打开的页面要先刷新拿到本次服务的口令)"})
        try:
            q = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            jid = q.get("job")
            fn = {
                "info": lambda: {"key": pc.bridge_key(), "settings": pc.settings(), "standards": pc.standards(), "presets": pc.uy.PRESETS},
                "settings": lambda: pc.settings(q.get("settings") or {}),
                "jobs": lambda: {"items": pc.list_jobs()},
                "job": lambda: pc.load(jid),
                "create": lambda: pc.create_job(q.get("name"), q.get("standard"), q.get("mode", "new"), q.get("note", "")),
                "delete": lambda: pc.delete_job(jid),              # 彻底删除
                "trash": lambda: pc.trash_job(jid),                # 删除 = 进回收站
                "restore": lambda: pc.trash_job(jid, restore=True),
                "duplicate": lambda: pc.duplicate_job(jid),
                "export": lambda: pc.export_jobs(q.get("jobs") or []),   # 任务包 .zip(空 = 全部)
                "importJobs": lambda: pc.import_jobs(q.get("zip") or ""),
                "reveal": lambda: pc.reveal(jid, q.get("what", "build")),
                "inbox": lambda: {"items": pc.bridge_inbox_list()},
                "import": lambda: pc.import_inbox(jid, q.get("inbox")),
                "upload": lambda: pc.add_upload(jid, q.get("name"), q.get("files") or []),
                "update": lambda: pc.update(jid, q.get("patch") or {}),
                "ai": lambda: pc.run_ai(jid, q.get("only")),
                "check": lambda: pc.check(jid),
                "build": lambda: pc.build(jid),
                "push": lambda: pc.push_outbox(jid),
            }.get(action)
            if not fn:
                return self.reply(404, {"error": "没有这个动作:" + action})
            return self.reply(200, fn())
        except (ValueError, KeyError, OSError, StopIteration, json.JSONDecodeError) as e:
            return self.reply(400, {"error": str(e) or type(e).__name__})

    def do_POST(self):
        global saved
        url = urllib.parse.urlparse(self.path)
        if url.path.startswith("/api/bridge/"):
            return self.do_bridge("POST")
        if url.path.startswith("/api/pipeline/") and self.is_local():
            return self.do_pipeline(url.path[len("/api/pipeline/"):])
        if not self.is_local():   # 局域网共享时:写主工程、写文件夹的接口只给主机自己用
            return self.reply(403, {"error": "局域网打开的工作台不能用这个功能:覆盖到 Unity、写回工程只能在共享工作台的那台电脑上操作。可以「导出交付包」或「保存工程」发给对方。"})
        if url.path.startswith("/api/figma-inbox/"):
            return self.do_figma_inbox("POST")
        if url.path in ("/api/unity/search", "/api/unity/match", "/api/unity/scan", "/api/unity/apply", "/api/unity/sprites", "/api/unity/file"):
            return self.do_unity(url.path)
        name = urllib.parse.parse_qs(url.query).get("name", [""])[0]
        if url.path not in ("/api/save-project", "/api/save-export"):
            return self.reply(404)
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if url.path == "/api/save-project":
            try:
                json.loads(body)
            except ValueError:
                return self.reply(400)
            os.makedirs(PROJECTS, exist_ok=True)
            path = os.path.join(PROJECTS, safe_name(name, "project") + ".budui.json")
        else:
            if body[:2] != b"\x1f\x8b":   # 只收 .unitypackage(gzip 压缩的 tar)
                return self.reply(400)
            fname = safe_name(name, "export.unitypackage")
            if not fname.lower().endswith(".unitypackage"):
                fname += ".unitypackage"
            os.makedirs(EXPORTS, exist_ok=True)
            path = os.path.join(EXPORTS, fname)
        with open(path, "wb") as f:
            f.write(body)
        self.reply(200, {"ok": True, "path": path, "bytes": len(body)})
        if url.path == "/api/save-project":
            saved = True


def lan_ips():
    """本机的局域网 IPv4 地址:先取默认出口网卡(不真的发包),再补上主机名解析到的其他私网地址"""
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        ips += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    private = lambda ip: ip.startswith(("10.", "192.168.")) or (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31)
    return [ip for i, ip in enumerate(ips) if private(ip) and ip not in ips[:i]]


# 多线程:浏览器会预先开空连接(预连接),单线程服务会一直卡在等它发请求,后面的保存/导出全被堵住
# timeout:handle_request() 每 0.5 秒返回一次,--once 模式下主循环才能及时看到 saved 标记并退出
if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("0.0.0.0" if LAN else "127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    server.timeout = 0.5
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(f'window.__BUDUI_SERVICE = {{port: {PORT}, token: "{TOKEN}"}};\n')
    print(f"BUD UI Studio 服务:http://localhost:{PORT}/BUD_UI_Studio.html", flush=True)
    if LAN:
        ips = lan_ips()
        for i, ip in enumerate(ips):
            print(f"{'局域网链接(发给同事)' if i == 0 else '其他网卡(虚拟机等,一般用不到)'}:http://{ip}:{PORT}/", flush=True)
        print("别的电脑打不开的话:Windows 防火墙要允许 Python 在「专用网络」上接收连接(第一次启动时弹窗点「允许访问」)", flush=True)
    while not (ONCE and saved):
        server.handle_request()
