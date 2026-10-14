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
    files = [(json.load(open(f, encoding="utf-8")), f) for f in glob.glob(os.path.join(HERE, "standards", "*.json"))]
    for s, f in sorted(files, key=lambda x: (x[0].get("order", 50), x[1])):
        out.append({"id": s["id"], "name": s["name"], "replaceOnly": bool(s.get("replaceOnly")),
                    "roles": {k: v["label"] for k, v in s["roles"].items()}, "note": s.get("_说明", ""),
                    # 页面用:哪些角色要填九宫格边距、不叠在动效预览上、能配动效;资源级的配置字段
                    "roleInfo": {k: {"border": bool(v.get("border")), "stage": v.get("stage", True), "motion": _motion_ok(v)} for k, v in s["roles"].items()},
                    "roleHelp": s.get("_角色说明", ""), "fields": s.get("fields", []), "idHint": s.get("idHint", "")})
    return out


def _motion_ok(role):
    """这个角色的切图会进带 Animator 的 prefab(动效能导出)"""
    return bool(role.get("effect") or role.get("corner") or role.get("deco") or role.get("motion"))


def _paths(role):
    p = role.get("path")
    return [p] if isinstance(p, str) else list(p or [])


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


def _thumb(j):
    """任务卡片缩略图:第一个资源的整体预览(Figma 插件发来的),没有就用它的第一张切图"""
    for a in j.get("assets", []):
        if a.get("preview"):
            return a["preview"]
        live = [s for s in a.get("slices", []) if s.get("role") != "skip"] or a.get("slices", [])
        if live:
            return live[0]["file"]
    return None


def list_jobs():
    """任务中心用:每个任务的概况(含回收站里的,deleted 有值 = 在回收站)"""
    out = []
    for f in glob.glob(os.path.join(JOBS, "*", "job.json")):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except ValueError:
            continue
        b = j.get("built") or {}
        out.append({k: j.get(k) for k in ("id", "name", "standard", "mode", "created", "updated", "note", "status", "deleted")} | {
            "assets": len(j.get("assets", [])), "slices": sum(len(a["slices"]) for a in j.get("assets", [])),
            "ids": [a.get("id") for a in j.get("assets", []) if a.get("id")], "thumb": _thumb(j),
            "built": {"time": b.get("time"), "file": os.path.basename(b["package"])} if b.get("package") and os.path.exists(b["package"]) else None,
            "checked": j.get("checked")})
    return sorted(out, key=lambda x: x.get("updated") or "", reverse=True)


def create_job(name, sid, mode="new", note=""):
    std = standard(sid)
    if std.get("replaceOnly"):
        mode = "replace"
    jid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    return save({"id": jid, "name": name or std["name"] + "批处理", "standard": sid, "mode": mode if mode in ("new", "replace") else "new",
                 "created": now(), "note": note or "", "status": "doing", "refs": [], "assets": [], "ai": {"state": "idle"}})


def delete_job(jid):
    """彻底删除(原图、新图、交付包都删掉)"""
    shutil.rmtree(job_dir(jid), ignore_errors=True)
    return {"ok": True}


def trash_job(jid, restore=False):
    """删除 = 先进回收站(任务中心里能恢复);restore=True 从回收站恢复"""
    with job_lock(jid):
        job = load(jid)
        if restore:
            job.pop("deleted", None)
        else:
            job["deleted"] = now()
        return save(job)


def duplicate_job(jid):
    """复制一份(原图、AI 新图、动效、配置字段都带上;交付包不带),名字加「副本」"""
    src = job_dir(jid); job = load(jid)
    nid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    shutil.copytree(src, job_dir(nid), ignore=shutil.ignore_patterns("build", "job.json.tmp"))
    job.update({"id": nid, "name": job["name"] + "(副本)", "created": now(), "status": "doing", "ai": {"state": "idle"}})
    for k in ("built", "deleted", "checked"):
        job.pop(k, None)
    return save(job)


def _exports_dir():
    return os.path.join(JOBS, "_exports")   # 跟着 JOBS 走(自测时 JOBS 换成临时目录)


def export_jobs(ids):
    """导出任务包(.zip):每个任务一个文件夹(job.json + 原图 + AI 新图 + 交付包),同事那边「导入任务」就能接着做。
    ids 为空 = 全部(不含回收站);返回包的路径(本地服务能直接下载 exports/pipeline/_exports/…)"""
    import zipfile
    jobs = [j for j in list_jobs() if (j["id"] in ids if ids else not j.get("deleted"))]
    if not jobs:
        raise ValueError("没有可导出的任务")
    os.makedirs(_exports_dir(), exist_ok=True)
    name = (safe(jobs[0]["name"]) if len(jobs) == 1 else f"资源批处理_全部任务_{len(jobs)}个") + "_" + datetime.datetime.now().strftime("%m%d-%H%M") + ".zip"
    path = os.path.join(_exports_dir(), name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", "BUD UI Studio 资源批处理任务包:工作台「资源批处理」→ 任务中心 →「导入任务」选这个文件。\n")
        for j in jobs:
            d = job_dir(j["id"])
            for root, _, files in os.walk(d):
                for f in files:
                    if f.endswith(".tmp"):
                        continue
                    full = os.path.join(root, f)
                    z.write(full, j["id"] + "/" + os.path.relpath(full, d).replace("\\", "/"))
    return {"ok": True, "jobs": len(jobs), "file": name, "url": "exports/pipeline/_exports/" + name, "path": path}


def import_jobs(b64):
    """导入任务包:每个任务都换一个新 id(不会覆盖本机已有的任务);同名的加「(导入)」"""
    import zipfile
    data = base64.b64decode(b64)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("不是任务包(.zip)")
    names = z.namelist()
    tops = sorted({n.split("/", 1)[0] for n in names if n.count("/") >= 1 and n.split("/", 1)[1] == "job.json"})
    if not tops:
        raise ValueError("任务包里没有任务(找不到 job.json)")
    have = {j["name"] for j in list_jobs()}
    out = []
    for t in tops:
        job = json.loads(z.read(t + "/job.json").decode("utf-8"))
        standard(job.get("standard", ""))   # 本机没有这个标准就报错
        nid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        d = job_dir(nid); base = os.path.realpath(d)
        for n in names:
            if not n.startswith(t + "/") or n.endswith("/") or n == t + "/job.json":
                continue
            dst = os.path.realpath(os.path.join(d, n[len(t) + 1:]))
            if not dst.startswith(base + os.sep):   # 防止包里的路径跳出任务文件夹
                raise ValueError("任务包里有不安全的路径:" + n)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(z.read(n))
        job.update({"id": nid, "ai": {"state": "idle"}})
        if job["name"] in have:
            job["name"] += "(导入)"
        job.pop("deleted", None)
        b = job.get("built") or {}
        if b.get("package"):
            b["package"] = os.path.join(d, "build", os.path.basename(b["package"])).replace("\\", "/")
        save(job); out.append({"id": nid, "name": job["name"]})
    return {"ok": True, "jobs": out}


def reveal(jid=None, what="build"):
    """在资源管理器里打开:任务的交付包(what=build)、导出的任务包文件夹(what=exports)"""
    if what == "exports":
        target = _exports_dir(); os.makedirs(target, exist_ok=True)
    else:
        b = (load(jid).get("built") or {}).get("package")
        if not b or not os.path.exists(b):
            raise ValueError("这个任务还没生成交付包")
        target = b
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(target)] if os.path.isfile(target) else ["explorer", os.path.normpath(target)])
    return {"ok": True, "path": target}


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
              "nodeId": s.get("nodeId"), "role": role, "ai": role != "skip" and not std["roles"].get(role, {}).get("placeOnly"), "useNew": True, "status": "todo", "motion": None, "replacePath": ""}
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
        if "note" in patch:
            job["note"] = str(patch["note"] or "")[:500]
        if patch.get("status") in ("doing", "done"):
            job["status"] = patch["status"]
        if patch.get("mode") in ("new", "replace") and not standard(job["standard"]).get("replaceOnly"):
            job["mode"] = patch["mode"]
        for a in job["assets"]:
            ap = (patch.get("assets") or {}).get(a["name"])
            if not ap:
                continue
            if "id" in ap:
                a["id"] = str(ap["id"]).strip() or None
            if isinstance(ap.get("fields"), dict):   # 配置字段(颜色、说明文字……)
                a["fields"] = {**(a.get("fields") or {}), **{str(k): v for k, v in ap["fields"].items()}}
            for s in a["slices"]:
                sp = (ap.get("slices") or {}).get(s["name"])
                if sp:
                    for k in ("role", "ai", "useNew", "motion", "replacePath"):
                        if k in sp:
                            s[k] = sp[k]
                    if "border" in sp:   # 九宫格边距 [左, 下, 右, 上](像素,和 Unity spriteBorder 同顺序)
                        b = sp["border"]
                        s["border"] = [max(0, int(float(x or 0))) for x in b][:4] if isinstance(b, list) and len(b) == 4 else None
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
    """{id} → 编号;{id+150100000} → 编号加上这个数(各类 PgcId 的号段);{name} → 资源名"""
    def rep(m):
        v = mapping.get(m.group(1))
        if v is None:
            return m.group(0)
        return str(int(v) + int(m.group(2))) if m.group(2) else str(v)
    return re.sub(r"\{(\w+)(?:\+(\d+))?(?::\w+)?\}", rep, t)


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
                taken = ([(_fill(p, {"id": a["id"]}), "") for p in std.get("exists", [])]
                         or [(_fill(p, {"id": a["id"]}), r["label"]) for r in std["roles"].values() for p in _paths(r)])
                for p, label in taken:
                    if os.path.exists(os.path.join(root, p)):
                        say("error", f"主工程里已有编号 {a['id']} 的{label or '资源'}:{p}(要替换旧的就切到「替换」模式)")
                        break
            roles = [s["role"] for s in live]
            for k, r in std["roles"].items():
                if r.get("path") and roles.count(k) > 1:
                    say("error", f"有 {roles.count(k)} 张切图都是「{r['label']}」,只能有一张")
            for k in std.get("required", []):
                if k not in roles:
                    say("error", f"缺「{std['roles'][k]['label']}」:这类资源必须有")
            for k in std.get("recommended", []):
                if k not in roles:
                    say("warn", f"没有「{std['roles'][k]['label']}」" + (std.get("recommendedNote", {}).get(k) or ""))
        if not root:
            say("warn", "没设主工程路径,跳过「编号重名 / 替换目标存在」检查")
        if job["mode"] == "new" and std.get("config"):
            fv = {f["key"]: f.get("default", "") for f in std.get("fields", [])} | (a.get("fields") or {})
            for f in std.get("fields", []):
                v = str(fv.get(f["key"], "")).strip()
                if f.get("required") and not v:
                    say("warn", f"配置字段「{f['label']}」没填(写进配置条目会是空的)")
                elif f.get("type") == "color" and v and _hex(v) is None:
                    say("error", f"配置字段「{f['label']}」要填颜色,如 #FFAA00")
                elif f.get("type") == "number":
                    try:
                        float(v)
                    except ValueError:
                        say("error", f"配置字段「{f['label']}」要填数字")
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
            role = std["roles"].get(s["role"], {})
            if role.get("border") and job["mode"] == "new" and not any(s.get("border") or []):
                say("warn", "九宫格边距没填(左 / 下 / 右 / 上):拉伸时四角会变形", s["issues"])
            m = s.get("motion")
            if m and m.get("preset") and not _motion_ok(role) and job["mode"] == "new":
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
class Ctx:
    """一个资源的生成上下文:写贴图 / prefab / 动画进交付包(同一路径只写一次),记 README 说明。builders.py 里的各类生成函数用它"""
    def __init__(self, std, job, a, live, d, assets, notes):
        self.std, self.job, self.asset, self.live, self.d, self._assets, self._notes = std, job, a, live, d, assets, notes
        self.mp = {"id": a.get("id"), "name": a["name"]}
        self._by_path = {}

    def role(self, s):
        return self.std["roles"].get(s["role"], {})

    def of(self, role):
        return [s for s in self.live if s["role"] == role]

    def first(self, role):
        return next(iter(self.of(role)), None)

    def dirs(self):
        return {k: _fill(v, self.mp) for k, v in (self.std.get("dirs") or self.std.get("effectDirs") or {}).items() if isinstance(v, str)}

    def note(self, text):
        self._notes.append(text)

    def guid_of(self, path):
        return self._by_path[path.lower()]

    def _put(self, path, data, meta_fn, guid=None):
        key = path.lower()
        if key in self._by_path:
            return self._by_path[key]
        g = guid or uy.stable_guid(path)
        self._assets.append({"path": path, "guid": g, "data": data, "meta": meta_fn(g)})
        self._by_path[key] = g
        return g

    def png(self, path, s, border=None, astc=None):
        """s:切图(用它的最终图:AI 新图或原图)"""
        im = Image.open(_final_file(self.d, self.asset, s)); buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
        r = self.role(s)
        border = border or (s.get("border") if r.get("border") else None) or (0, 0, 0, 0)
        astc = astc if astc is not None else r.get("astc", self.std.get("astc", []))
        return self._put(path, buf.getvalue(), lambda g: uy.sprite_meta(g, border, astc))

    def add(self, path, text, meta_fn):
        return self._put(path, text.encode("utf-8"), meta_fn)

    def anim(self, clip_path, ctrl_path, motions, **kw):
        """写 .anim + .controller,返回控制器 GUID;片段 / 状态名取文件名"""
        clip_name = os.path.splitext(os.path.basename(clip_path))[0]; ctrl_name = os.path.splitext(os.path.basename(ctrl_path))[0]
        cg = self._put(clip_path, uy.anim_clip(clip_name, motions, **kw).encode("utf-8"), lambda g: uy.native_meta(g, 7400000))
        return self._put(ctrl_path, uy.anim_controller(ctrl_name, cg).encode("utf-8"), lambda g: uy.native_meta(g, 9100000))


def _hex(c):
    c = (c or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", c):
        return None
    return [int(c[i:i + 2], 16) / 255 for i in range(0, len(c), 2)] + ([1.0] if len(c) == 6 else [])


def _entry(tpl, mp, fields, present):
    """配置条目模板 → 条目。叶子字符串:"{id:int}" → 数字;"{num:字段}" → 数字;"{rgba:字段}" → {r,g,b,a}(字段是 #RRGGBB[AA]);
    "{list:变量}" → 生成时得到的列表(如气泡实际做了哪些角);"{f:字段}" 嵌在文字里 → 字段值;其余 {id} / {id+N} / {name} 照 _fill。
    值末尾 "?角色或变量名" = 有这个角色的切图 / 做出了这个特效 / 变量非空才写这一项"""
    def leaf(v):
        if v == "{id:int}":
            return int(mp["id"])
        m = re.fullmatch(r"\{(num|rgba|list):(\w+)\}", v)
        if m:
            kind, key = m.groups()
            if kind == "list":
                return list(mp.get(key) or [])
            if kind == "num":
                try:
                    x = float(fields.get(key, 0)); return int(x) if x == int(x) else x
                except (TypeError, ValueError):
                    raise ValueError(f"配置字段「{key}」要填数字")
            rgba = _hex(fields.get(key))
            if rgba is None:
                raise ValueError(f"配置字段「{key}」要填颜色(#RRGGBB)")
            return {ch: round(x, 6) for ch, x in zip("rgba", rgba)}
        return _fill(re.sub(r"\{f:(\w+)\}", lambda m: str(fields.get(m.group(1), "")), v), mp)

    def walk(t):
        if isinstance(t, dict):
            out = {}
            for k, v in t.items():
                if isinstance(v, str) and "?" in v and re.search(r"\?(\w+)$", v):
                    cond = re.search(r"\?(\w+)$", v).group(1)
                    if cond not in present:
                        continue
                    v = v[:-len(cond) - 1]
                out[k] = walk(v)
            return out
        if isinstance(t, list):
            return [walk(x) for x in t]
        return leaf(t) if isinstance(t, str) else t
    return walk(tpl)


def build(jid):
    import builders
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
        ctx = Ctx(std, job, a, live, d, assets, notes)
        # 单张图:角色带 path 的切图按落点写(path 可以是几个落点,同一张图复制几份,如气泡的大厅底图 + 游戏内底图)
        for s in live:
            r = std["roles"][s["role"]]
            for p in _paths(r):
                p = _fill(p, mp); ctx.png(p, s); notes.append(f"- {r['label']}:`{p}`")
        made = {}
        if std.get("builder"):
            mp.update(builders.BUILDERS[std["builder"]](ctx) or {})
        else:   # 头像框:Arts 源 + Loadable 壳 + Animator(逐字段对齐 HeadTopEffect_36)
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
                    g = ctx.png(f"{sdir}/{pname}_{ln}.png", s)
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
                src_p = f"{_fill(ed['source'], mp)}/{pname}.prefab"; sg = uy.stable_guid(src_p)
                text, go, rt = uy.effect_prefab(pname, lay, ctrl_guid, root_size)
                assets.append({"path": src_p, "guid": sg, "data": text.encode("utf-8"), "meta": uy.prefab_meta(sg)})
                shell_p = f"{_fill(ed['shell'], mp)}/{pname}.prefab"; shg = uy.stable_guid(shell_p)
                assets.append({"path": shell_p, "guid": shg, "data": uy.shell_prefab(pname, sg, go, rt, root_size).encode("utf-8"), "meta": uy.prefab_meta(shg)})
                made[ek] = pname
                notes.append(f"- 特效 `{pname}`:{len(lay)} 层、{len(motions)} 个动效 → 源 `{src_p}`,壳 `{shell_p}`")
        cfg = std.get("config")
        if cfg:
            fields = {f["key"]: f.get("default", "") for f in std.get("fields", [])} | (a.get("fields") or {})
            present = {s["role"] for s in live} | set(made) | {k for k, v in mp.items() if v}
            entries.append(_entry(cfg["entry"], mp, fields, present))
    if not assets:
        raise ValueError("没有可导出的内容")
    os.makedirs(os.path.join(d, "build"), exist_ok=True)
    # 交付包文件名只用英文:Unity 解包时经 7-Zip 走短路径,中文文件名会「Couldn't decompress package」(2026-10-13 空白工程实测)
    ids = "_".join(sorted({re.sub(r"[^0-9A-Za-z]", "", str(a.get("id") or "")) for a in job["assets"]} - {""}))[:60]
    pkg = os.path.join(d, "build", f"{std['id']}_{ids or job['mode']}_{jid[-4:]}.unitypackage")
    for old in glob.glob(os.path.join(d, "build", "*.unitypackage")):   # 换了名字的旧包删掉,build 里只留最新一个
        if os.path.normcase(old) != os.path.normcase(pkg):
            os.remove(old)
    write_unitypackage(pkg, assets)
    readme = [f"# {job['name']}", "", f"标准:{std['name']} · 模式:{'新增' if job['mode'] == 'new' else '替换'} · 生成于 {now()}", "",
              "## 包里有什么", ""] + notes
    if entries:
        readme += ["", f"## 还要手动加的配置({std['config']['file']})", "",
                   std["config"].get("howto") or "交付包不会改已有的配置文件(避免覆盖别人同时加的条目),把下面的条目加进数组末尾:", "", "```json",
                   ",\n".join(json.dumps(e, ensure_ascii=False, indent=2) for e in entries), "```"]
    if std.get("afterImport"):
        readme += ["", "## 导入后", ""] + [f"- {t}" for t in std["afterImport"]]
    open(os.path.join(d, "build", "README.md"), "w", encoding="utf-8").write("\n".join(readme) + "\n")
    with job_lock(jid):
        cur = load(jid); cur["built"] = {"time": now(), "package": pkg.replace("\\", "/"), "assets": len(assets), "configEntries": entries}
        save(cur)
    return {"ok": True, "package": pkg, "assets": len(assets), "readme": os.path.join(d, "build", "README.md"), "configEntries": entries}
