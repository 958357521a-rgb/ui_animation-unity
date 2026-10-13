# 资源批处理 · 核心:任务(job)存档、Figma 中转箱、AI 重绘调度、规则检查、生成 .unitypackage。
# 本地服务 dev/studio_server.py 的 /api/pipeline/* 和 /api/bridge/* 都转到这里;也能在命令行里直接 import 使用。
# 任务存在 exports/pipeline/<任务 id>/:job.json + in/<资源>/<切图>.png(原图)+ out/<资源>/<切图>.png(AI 新图)+ build/(交付包)。
# 结构说明见 dev/pipeline/README.md。
import base64, datetime, glob, io, json, os, re, secrets, shutil, subprocess, sys, threading, time
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import unity_yaml as uy
from unitypackage import write_unitypackage

JOBS = os.path.join(ROOT, "exports", "pipeline")
BRIDGE = os.path.join(JOBS, "_bridge")
SETTINGS = os.path.join(HERE, "settings.local.json")          # 本机设置(主工程路径),不进仓库
BRIDGE_KEY_FILE = os.path.join(ROOT, "dev", "bridge_key.txt")  # Figma 插件配对码,不进仓库、不通过 HTTP 读文件
RESTYLE = os.path.join(ROOT, "dev", "restyle", "restyle.py")
_locks, _lock = {}, threading.Lock()


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe(name):
    """文件 / 文件夹名:去掉 Windows 不允许的字符,保留中文"""
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(name)).strip(" .")
    return s[:80] or "未命名"


def job_lock(jid):
    with _lock:
        return _locks.setdefault(jid, threading.Lock())


# ---------------- 设置 / 配对码 ----------------
def settings(patch=None):
    s = {}
    if os.path.exists(SETTINGS):
        s = json.load(open(SETTINGS, encoding="utf-8"))
    if patch:
        if "unityRoot" in patch:
            r = (patch["unityRoot"] or "").strip().strip('"').rstrip("\\/")
            if r and not os.path.isdir(os.path.join(r, "Assets")):
                raise ValueError("这个文件夹里没有 Assets:要选 Unity 工程根目录(含 Assets 的那层)")
            s["unityRoot"] = r
        json.dump(s, open(SETTINGS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return s


def bridge_key():
    try:
        k = open(BRIDGE_KEY_FILE, encoding="utf-8").read().strip()
    except OSError:
        k = ""
    if not re.fullmatch(r"[0-9a-f]{8}", k):
        k = secrets.token_hex(4)
        open(BRIDGE_KEY_FILE, "w", encoding="utf-8").write(k + "\n")
    return k


# ---------------- 标准 ----------------
def standards():
    out = []
    for f in sorted(glob.glob(os.path.join(HERE, "standards", "*.json"))):
        s = json.load(open(f, encoding="utf-8"))
        out.append({"id": s["id"], "name": s["name"], "replaceOnly": bool(s.get("replaceOnly")),
                    "roles": {k: v["label"] for k, v in s["roles"].items()}, "note": s.get("_说明", "")})
    return out


def standard(sid):
    p = os.path.join(HERE, "standards", safe(sid) + ".json")
    if not os.path.exists(p):
        raise ValueError("没有这个标准:" + sid)
    return json.load(open(p, encoding="utf-8"))


def guess_role(std, slice_name):
    n = slice_name.strip().lower()
    for k, r in std["roles"].items():
        if not r.get("default") and re.search(r.get("match", "^$"), n, re.I):
            return k
    return next((k for k, r in std["roles"].items() if r.get("default")), "skip")


def asset_id(std, name):
    if not std.get("idFrom"):
        return None
    m = re.search(std["idFrom"], name)
    return m.group(1) if m else None


# ---------------- 任务 ----------------
def job_dir(jid):
    if not re.fullmatch(r"[0-9A-Za-z_-]{6,64}", jid or ""):
        raise ValueError("任务 id 不对")
    return os.path.join(JOBS, jid)


def load(jid):
    return json.load(open(os.path.join(job_dir(jid), "job.json"), encoding="utf-8"))


def save(job):
    job["updated"] = now()
    d = job_dir(job["id"]); os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "job.json.tmp")
    json.dump(job, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "job.json"))
    return job


def list_jobs():
    out = []
    for f in glob.glob(os.path.join(JOBS, "*", "job.json")):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except ValueError:
            continue
        out.append({k: j.get(k) for k in ("id", "name", "standard", "mode", "created", "updated")} | {
            "assets": len(j.get("assets", [])), "slices": sum(len(a["slices"]) for a in j.get("assets", []))})
    return sorted(out, key=lambda x: x.get("updated") or "", reverse=True)


def create_job(name, sid, mode="new"):
    std = standard(sid)
    if std.get("replaceOnly"):
        mode = "replace"
    jid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    return save({"id": jid, "name": name or std["name"] + "批处理", "standard": sid, "mode": mode if mode in ("new", "replace") else "new",
                 "created": now(), "refs": [], "assets": [], "ai": {"state": "idle"}})


def delete_job(jid):
    shutil.rmtree(job_dir(jid), ignore_errors=True)
    return {"ok": True}


def _png(b64):
    data = base64.b64decode(b64)
    Image.open(io.BytesIO(data)).verify()
    return data


def _add_asset(job, std, name, w, h, slices, node_id=None, preview=None):
    """slices: [{name, x, y, w, h, data(bytes), nodeId}] —— 同名资源已存在就替换它(重新发送 = 更新)"""
    d = job_dir(job["id"]); aname = safe(name)
    job["assets"] = [a for a in job["assets"] if a["name"] != aname]
    shutil.rmtree(os.path.join(d, "in", aname), ignore_errors=True)
    shutil.rmtree(os.path.join(d, "out", aname), ignore_errors=True)
    os.makedirs(os.path.join(d, "in", aname), exist_ok=True)
    asset = {"name": aname, "id": asset_id(std, aname), "w": w, "h": h, "nodeId": node_id, "slices": []}
    if preview:
        open(os.path.join(d, "in", aname, "_preview.png"), "wb").write(preview); asset["preview"] = f"in/{aname}/_preview.png"
    used = set()
    for s in slices:
        sname = safe(s["name"]); base = sname; i = 2
        while sname.lower() in used:
            sname = f"{base}_{i}"; i += 1
        used.add(sname.lower())
        open(os.path.join(d, "in", aname, sname + ".png"), "wb").write(s["data"])
        role = guess_role(std, sname)
        sl = {"name": sname, "file": f"in/{aname}/{sname}.png", "x": s.get("x", 0), "y": s.get("y", 0), "w": s["w"], "h": s["h"],
              "nodeId": s.get("nodeId"), "role": role, "ai": role != "skip", "useNew": True, "status": "todo", "motion": None, "replacePath": ""}
        md = std.get("motionDefaults", {}).get(role)
        if md:
            sl["motion"] = {"preset": md} | {k: v for k, v in uy.PRESETS[md].items() if k != "label"}
        asset["slices"].append(sl)
    job["assets"].append(asset)
    return asset


def add_upload(jid, name, files):
    """本地上传(不经 Figma):files = [{name, b64}];没有位置信息,全部按居中摆放"""
    with job_lock(jid):
        job, std = load(jid), None
        std = standard(job["standard"])
        sl = []
        for f in files:
            data = _png(f["b64"]); w, h = Image.open(io.BytesIO(data)).size
            sl.append({"name": os.path.splitext(f["name"])[0], "data": data, "w": w, "h": h, "x": None, "y": None})
        W = max([s["w"] for s in sl] or [0]); H = max([s["h"] for s in sl] or [0])
        for s in sl:
            s["x"], s["y"] = (W - s["w"]) / 2, (H - s["h"]) / 2
        _add_asset(job, std, name, W, H, sl)
        return save(job)


def update(jid, patch):
    """patch: {name?, mode?, assets: {资源名: {id?, slices: {切图名: {role, ai, useNew, motion, replacePath}}}}}"""
    with job_lock(jid):
        job = load(jid)
        if patch.get("name"):
            job["name"] = patch["name"]
        if patch.get("mode") in ("new", "replace") and not standard(job["standard"]).get("replaceOnly"):
            job["mode"] = patch["mode"]
        for a in job["assets"]:
            ap = (patch.get("assets") or {}).get(a["name"])
            if not ap:
                continue
            if "id" in ap:
                a["id"] = str(ap["id"]).strip() or None
            for s in a["slices"]:
                sp = (ap.get("slices") or {}).get(s["name"])
                if sp:
                    for k in ("role", "ai", "useNew", "motion", "replacePath"):
                        if k in sp:
                            s[k] = sp[k]
        return save(job)


# ---------------- Figma 中转箱(插件 ↔ 工作台) ----------------
def bridge_inbox_add(payload):
    """插件「发送选中」:{file, page, assets: [{name, nodeId, w, h, preview(b64), slices: [{name, nodeId, x, y, w, h, png(b64)}]}]}"""
    os.makedirs(os.path.join(BRIDGE, "inbox"), exist_ok=True)
    assets = payload.get("assets") or []
    if not assets:
        raise ValueError("没有选中的资源")
    for a in assets:
        for s in a.get("slices") or []:
            _png(s["png"])
    bid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    payload = {"id": bid, "time": now(), "file": payload.get("file"), "page": payload.get("page"), "assets": assets}
    json.dump(payload, open(os.path.join(BRIDGE, "inbox", bid + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    return {"ok": True, "id": bid, "assets": len(assets), "slices": sum(len(a.get("slices") or []) for a in assets)}


def bridge_inbox_list():
    out = []
    for f in sorted(glob.glob(os.path.join(BRIDGE, "inbox", "*.json")), reverse=True):
        p = json.load(open(f, encoding="utf-8"))
        out.append({"id": p["id"], "time": p["time"], "file": p.get("file"), "page": p.get("page"),
                    "assets": [{"name": a["name"], "slices": len(a.get("slices") or [])} for a in p["assets"]]})
    return out


def import_inbox(jid, bid, remove=True):
    p = os.path.join(BRIDGE, "inbox", safe(bid) + ".json")
    payload = json.load(open(p, encoding="utf-8"))
    with job_lock(jid):
        job = load(jid); std = standard(job["standard"])
        for a in payload["assets"]:
            sl = [{"name": s["name"], "nodeId": s.get("nodeId"), "x": s["x"], "y": s["y"], "w": s["w"], "h": s["h"], "data": _png(s["png"])}
                  for s in a.get("slices") or []]
            _add_asset(job, std, a["name"], a["w"], a["h"], sl, a.get("nodeId"), _png(a["preview"]) if a.get("preview") else None)
        job.setdefault("figma", {"file": payload.get("file"), "page": payload.get("page")})
        save(job)
    if remove:
        os.remove(p)
    return job


def push_outbox(jid):
    """「放回 Figma」:把新图(没有就用原图)连同位置写进中转箱,插件「取回结果」时摆到原资源旁边"""
    job = load(jid); d = job_dir(jid)
    assets = []
    for a in job["assets"]:
        sl = []
        for s in a["slices"]:
            f = _final_file(d, a, s)
            sl.append({"name": s["name"], "x": s["x"], "y": s["y"], "w": s["w"], "h": s["h"], "isNew": f.startswith(os.path.join(d, "out")),
                       "png": base64.b64encode(open(f, "rb").read()).decode()})
        assets.append({"name": a["name"], "nodeId": a.get("nodeId"), "w": a["w"], "h": a["h"], "slices": sl})
    os.makedirs(os.path.join(BRIDGE, "outbox"), exist_ok=True)
    json.dump({"job": jid, "name": job["name"], "time": now(), "assets": assets},
              open(os.path.join(BRIDGE, "outbox", jid + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    return {"ok": True, "assets": len(assets)}


def bridge_outbox():
    return [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(BRIDGE, "outbox", "*.json")))]


def bridge_outbox_done(jid):
    p = os.path.join(BRIDGE, "outbox", safe(jid) + ".json")
    if os.path.exists(p):
        os.remove(p)
    return {"ok": True}


# ---------------- AI 重绘(后台线程,逐个资源调 dev/restyle/restyle.py) ----------------
def _python():
    return sys.executable if not sys.executable.lower().endswith("pythonw.exe") else sys.executable[:-5] + ".exe"


def run_ai(jid, only=None):
    """only: None = 全部勾了 AI 的切图;或 [[资源名, 切图名], ...]"""
    with job_lock(jid):
        job = load(jid)
        if job.get("ai", {}).get("state") == "running":
            raise ValueError("这个任务的 AI 重绘还在跑")
        want = {tuple(x) for x in only} if only else None
        todo = []
        for a in job["assets"]:
            for s in a["slices"]:
                if s["role"] != "skip" and s.get("ai") and (want is None or (a["name"], s["name"]) in want):
                    s["status"] = "queued"; todo.append((a["name"], s["name"]))
        if not todo:
            raise ValueError("没有要重绘的切图(勾上「AI」的切图才会重绘)")
        job["ai"] = {"state": "running", "started": now(), "total": len(todo), "done": 0, "failed": 0, "log": []}
        save(job)
    threading.Thread(target=_ai_worker, args=(jid, todo), daemon=True).start()
    return {"ok": True, "total": len(todo)}


def _ai_worker(jid, todo):
    d = job_dir(jid)
    job = load(jid); std = standard(job["standard"]); ai = std.get("ai", {})
    refs = [os.path.join(ROOT, r) for r in ai.get("refs", [])] + [os.path.join(d, r) for r in job.get("refs", [])]
    prompt = open(os.path.join(ROOT, ai["prompt"]), encoding="utf-8").read().strip() if ai.get("prompt") else None
    by_asset = {}
    for a, s in todo:
        by_asset.setdefault(a, []).append(s)
    for aname, snames in by_asset.items():
        out_dir = os.path.join(d, "out", aname); os.makedirs(out_dir, exist_ok=True)
        cmd = [_python(), RESTYLE] + [os.path.join(d, "in", aname, s + ".png") for s in snames] + ["--out", out_dir, "--refs"] + refs
        if ai.get("keepShape", True):
            cmd.append("--keep-shape")
        if prompt:
            cmd += ["--prompt", prompt]
        _set_status(jid, aname, snames, "running")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            text = (p.stdout or "") + (p.stderr or "")
        except (OSError, subprocess.SubprocessError) as e:
            text = f"✗ 启动重绘失败:{e}"
        lines = [l for l in text.splitlines() if l.strip() and "Deprecation" not in l and "return list(" not in l]
        with job_lock(jid):
            job = load(jid)
            a = next(x for x in job["assets"] if x["name"] == aname)
            for s in a["slices"]:
                if s["name"] in snames:
                    ok = os.path.exists(os.path.join(out_dir, s["name"] + ".png")) and any(l.startswith("✓ " + s["name"]) for l in lines)
                    s["status"] = "done" if ok else "failed"
                    if ok:
                        s["new"] = f"out/{aname}/{s['name']}.png"; s["compare"] = f"out/{aname}/_compare.png"
                    job["ai"]["done" if ok else "failed"] += 1
            job["ai"]["log"] = (job["ai"].get("log") or [])[-40:] + [f"[{aname}] " + l for l in lines[-12:]]
            save(job)
    with job_lock(jid):
        job = load(jid); job["ai"]["state"] = "idle"; job["ai"]["finished"] = now(); save(job)


def _set_status(jid, aname, snames, st):
    with job_lock(jid):
        job = load(jid)
        for a in job["assets"]:
            if a["name"] == aname:
                for s in a["slices"]:
                    if s["name"] in snames:
                        s["status"] = st
        save(job)


# ---------------- 规则检查 ----------------
def _final_file(d, a, s):
    new = os.path.join(d, "out", a["name"], s["name"] + ".png")
    return new if s.get("useNew", True) and s.get("new") and os.path.exists(new) else os.path.join(d, s["file"])


def _fill(t, mapping):
    return re.sub(r"\{(\w+)(?::\w+)?\}", lambda m: str(mapping.get(m.group(1), m.group(0))), t)


def check(jid):
    """逐张切图按标准检查:error 挡住打包,warn 只提示。结果写回 job.json 的 issues"""
    job = load(jid); std = standard(job["standard"]); rules = std.get("rules", {}); d = job_dir(jid)
    root = settings().get("unityRoot")
    total = {"error": 0, "warn": 0}
    for a in job["assets"]:
        a["issues"] = []
        def say(level, text, target=None):
            (target if target is not None else a["issues"]).append({"level": level, "text": text}); total[level] += 1
        live = [s for s in a["slices"] if s["role"] != "skip"]
        if not live:
            say("warn", "没有要导出的切图(全部标成了「不导出」)")
        if job["mode"] == "new" and std.get("idFrom"):
            if not a.get("id"):
                say("error", "缺编号:资源名末尾要带数字(如「头像框_40」),或在页面上填编号")
            elif root:
                for k, r in std["roles"].items():
                    if r.get("path") and os.path.exists(os.path.join(root, _fill(r["path"], {"id": a["id"]}))):
                        say("error", f"主工程里已有编号 {a['id']} 的{r['label']}:{_fill(r['path'], {'id': a['id']})}(要替换旧的就切到「替换」模式)")
                        break
            roles = [s["role"] for s in live]
            for k, r in std["roles"].items():
                if r.get("path") and roles.count(k) > 1:
                    say("error", f"有 {roles.count(k)} 张切图都是「{r['label']}」,只能有一张")
        if not root:
            say("warn", "没设主工程路径,跳过「编号重名 / 替换目标存在」检查")
        for s in a["slices"]:
            s["issues"] = []
            if s["role"] == "skip":
                continue
            f = _final_file(d, a, s)
            try:
                im = Image.open(f); im.load()
            except OSError:
                say("error", "图片读不了", s["issues"]); continue
            if s.get("ai") and s.get("status") == "failed":
                say("warn", "AI 重绘失败,会用原图", s["issues"])
            elif s.get("ai") and not s.get("new"):
                say("warn", "还没 AI 重绘,会用原图", s["issues"])
            if rules.get("requireAlpha") and "A" not in im.getbands():
                say("error", "没有透明通道(要 PNG 带透明)", s["issues"])
            if "A" in im.getbands() and im.getchannel("A").getbbox() is None:
                say("error", "整张是透明的", s["issues"])
            if rules.get("keepInputSize") and im.size != (s["w"], s["h"]) and f != os.path.join(d, s["file"]):
                say("error", f"新图尺寸 {im.size[0]}×{im.size[1]} 和原图 {s['w']}×{s['h']} 不一致", s["issues"])
            size = std["roles"].get(s["role"], {}).get("size")
            if size and list(im.size) != list(size):
                say("warn", f"{std['roles'][s['role']]['label']}按标准应是 {size[0]}×{size[1]},现在是 {im.size[0]}×{im.size[1]}", s["issues"])
            if rules.get("maxBytes") and os.path.getsize(f) > rules["maxBytes"]:
                say("warn", f"文件 {os.path.getsize(f) // 1024} KB,超过标准 {rules['maxBytes'] // 1024} KB", s["issues"])
            if f != os.path.join(d, s["file"]) and "A" in im.getbands():
                old = Image.open(os.path.join(d, s["file"])).convert("RGBA").getchannel("A")
                if old.size == im.size:
                    na, oa = im.convert("RGBA").getchannel("A").tobytes(), old.tobytes()
                    grow = sum(1 for x, y in zip(oa, na) if y > 8 and x <= 8) / max(1, len(na))
                    if grow > rules.get("maxOutlineGrowth", 0.002):
                        say("warn", f"新图有 {grow:.1%} 的像素画到了原图轮廓外面", s["issues"])
            if job["mode"] == "replace":
                rp = (s.get("replacePath") or "").replace("\\", "/")
                if not rp.startswith("Assets/") or not rp.lower().endswith(".png"):
                    say("error", "替换模式要填目标路径(Assets/… .png)", s["issues"])
                elif root:
                    tp = os.path.join(root, rp)
                    if not os.path.exists(tp) or not os.path.exists(tp + ".meta"):
                        say("error", "主工程里没有这张图或它的 .meta:" + rp, s["issues"])
                    elif Image.open(tp).size != im.size:
                        say("error", f"和主工程里的旧图尺寸不同(旧 {Image.open(tp).size[0]}×{Image.open(tp).size[1]}),原地换图要同尺寸", s["issues"])
            m = s.get("motion")
            if m and std["roles"].get(s["role"], {}).get("effect") is None and job["mode"] == "new":
                say("warn", f"「{std['roles'][s['role']]['label']}」不进特效 prefab,这张图上的动效不会导出", s["issues"])
            if m and job["mode"] == "replace":
                say("warn", "替换模式只换图,动效不会导出", s["issues"])
    job["checked"] = {"time": now(), **total}
    with job_lock(jid):
        cur = load(jid)
        for a, ca in zip(job["assets"], cur["assets"]):
            ca["issues"] = a.get("issues", [])
            for s, cs in zip(a["slices"], ca["slices"]):
                cs["issues"] = s.get("issues", [])
        cur["checked"] = job["checked"]
        save(cur)
    return cur


# ---------------- 生成交付包 ----------------
def build(jid):
    job = check(jid)
    if job["checked"]["error"]:
        raise ValueError(f"还有 {job['checked']['error']} 个必须处理的问题(红色),处理完再生成")
    std = standard(job["standard"]); d = job_dir(jid); root = settings().get("unityRoot")
    assets, notes, entries = [], [], []

    def png(path, src, border=(0, 0, 0, 0), guid=None, meta=None):
        im = Image.open(src); buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
        g = guid or uy.stable_guid(path)
        assets.append({"path": path, "guid": g, "data": buf.getvalue(), "meta": meta or uy.sprite_meta(g, border)})
        return g

    for a in job["assets"]:
        live = [s for s in a["slices"] if s["role"] != "skip"]
        if job["mode"] == "replace":
            for s in live:
                rp = s["replacePath"].replace("\\", "/")
                meta = open(os.path.join(root, rp) + ".meta", encoding="utf-8").read() if root else None
                if not meta:
                    raise ValueError("替换模式要先设主工程路径(要沿用旧图的 .meta)")
                g = re.search(r"^guid: ([0-9a-f]{32})", meta, re.M).group(1)
                png(rp, _final_file(d, a, s), guid=g, meta=meta)
                notes.append(f"- 换图:`{rp}`")
            continue
        aid = a["id"]; mp = {"id": aid, "name": a["name"]}
        for s in live:
            r = std["roles"][s["role"]]
            if r.get("path"):
                p = _fill(r["path"], mp); png(p, _final_file(d, a, s)); notes.append(f"- {r['label']}:`{p}`")
        made = {}
        ed = std.get("effectDirs", {}); u = float(ed.get("unitsPerPx", 1)); root_size = ed.get("rootSize", [100, 100])
        for ek, e in std.get("effects", {}).items():
            layers = [s for s in live if std["roles"][s["role"]].get("effect") == ek]
            if not layers:
                continue
            pname = _fill(e["prefab"], mp); sdir = _fill(ed["sprites"], mp)
            lay, motions = [], []
            used = set()
            for i, s in enumerate(layers, 1):
                # 节点名 = 动画路径(Unity 按名字的 CRC32 绑定)、贴图文件名:一律用英文,中文切图名换成 Layer_01…(只在工作台里显示中文)
                ln = s["name"] if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", s["name"]) and s["name"].lower() not in used else f"Layer_{i:02d}"
                used.add(ln.lower())
                g = png(f"{sdir}/{pname}_{ln}.png", _final_file(d, a, s))
                x = (s["x"] + s["w"] / 2 - a["w"] / 2) * u; y = (a["h"] / 2 - (s["y"] + s["h"] / 2)) * u
                lay.append({"name": ln, "sprite_guid": g, "x": x, "y": y, "w": s["w"] * u, "h": s["h"] * u})
                if s.get("motion") and s["motion"].get("preset"):
                    motions.append(dict(s["motion"], path=ln, base_x=x, base_y=y))
            ctrl_guid = None
            if motions:
                clip_p, ctrl_p = f"{sdir}/{pname}.anim", f"{sdir}/{pname}.controller"
                cg, ctrl_guid = uy.stable_guid(clip_p), uy.stable_guid(ctrl_p)
                assets.append({"path": clip_p, "guid": cg, "data": uy.anim_clip(pname, motions).encode("utf-8"), "meta": uy.native_meta(cg, 7400000)})
                assets.append({"path": ctrl_p, "guid": ctrl_guid, "data": uy.anim_controller(pname, cg).encode("utf-8"), "meta": uy.native_meta(ctrl_guid, 9100000)})
            src_p = f"{ed['source']}/{pname}.prefab"; sg = uy.stable_guid(src_p)
            text, go, rt = uy.effect_prefab(pname, lay, ctrl_guid, root_size)
            assets.append({"path": src_p, "guid": sg, "data": text.encode("utf-8"), "meta": uy.prefab_meta(sg)})
            shell_p = f"{ed['shell']}/{pname}.prefab"; shg = uy.stable_guid(shell_p)
            assets.append({"path": shell_p, "guid": shg, "data": uy.shell_prefab(pname, sg, go, rt, root_size).encode("utf-8"), "meta": uy.prefab_meta(shg)})
            made[ek] = pname
            notes.append(f"- 特效 `{pname}`:{len(lay)} 层、{len(motions)} 个动效 → 源 `{src_p}`,壳 `{shell_p}`")
        cfg = std.get("config")
        if cfg:
            roles = {s["role"] for s in live}
            entry = {}
            for k, v in cfg["entry"].items():
                opt = v.endswith("?"); v = v.rstrip("?")
                if opt and ((k == "PreviewSpriteName" and "preview" not in roles) or (k == "TopEffectName" and "top" not in made)
                            or (k == "BottomEffectName" and "bottom" not in made)):
                    continue
                entry[k] = int(aid) if v == "{id:int}" else _fill(v, mp)
            entries.append(entry)
    if not assets:
        raise ValueError("没有可导出的内容")
    os.makedirs(os.path.join(d, "build"), exist_ok=True)
    pkg = os.path.join(d, "build", safe(job["name"]) + ".unitypackage")
    write_unitypackage(pkg, assets)
    readme = [f"# {job['name']}", "", f"标准:{std['name']} · 模式:{'新增' if job['mode'] == 'new' else '替换'} · 生成于 {now()}", "",
              "## 包里有什么", ""] + notes
    if entries:
        readme += ["", f"## 还要手动加的配置({std['config']['file']})", "",
                   "交付包不会改已有的配置文件(避免覆盖别人同时加的条目),把下面的条目加进数组末尾:", "", "```json",
                   ",\n".join(json.dumps(e, ensure_ascii=False, indent=2) for e in entries), "```"]
    open(os.path.join(d, "build", "README.md"), "w", encoding="utf-8").write("\n".join(readme) + "\n")
    with job_lock(jid):
        cur = load(jid); cur["built"] = {"time": now(), "package": pkg.replace("\\", "/"), "assets": len(assets), "configEntries": entries}
        save(cur)
    return {"ok": True, "package": pkg, "assets": len(assets), "readme": os.path.join(d, "build", "README.md"), "configEntries": entries}
