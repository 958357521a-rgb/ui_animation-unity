# 原地换图:把重绘好的新切图按原路径写回主工程(同名同尺寸替换 PNG,.meta 一律不动 → GUID、九宫格、图集、prefab 引用全不变)。
# 默认只演练(列出计划和检查结果,不写任何文件);加 --apply 才写,写之前把旧图备份到 backups/<时间>-restyle/(带 manifest.json),
# 用 --undo <备份目录> 原样还原。
# 用法:python dev/restyle/swap_in_place.py <Unity 工程> <新图目录> <切图清单.json> [--only 名字 ...] [--apply]
#        python dev/restyle/swap_in_place.py <Unity 工程> --undo backups/<时间>-restyle
# 切图清单 = prefab_sprites.py --json 的输出;新图按文件名(不含 .png)对上清单里的路径,.raw.png / _compare.png 不算。
# 检查:旧图和 .meta 存在、尺寸完全一致、是单张 Sprite(textureType 8 + spriteMode 1)、透明轮廓不超出旧图;
# 并按 GUID 搜整个 Assets,列出还有哪些 prefab / asset 在用这张图(换了它们也会变)。不通过的不写。
import json, os, re, shutil, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.abspath(os.path.join(HERE, "..", ".."))
args = sys.argv[1:]
root = args[0].rstrip("/\\")

def rel_ok(rel):
    p = os.path.normpath(os.path.join(root, rel))
    return p.startswith(os.path.normpath(os.path.join(root, "Assets")) + os.sep)

if "--undo" in args:
    bdir = args[args.index("--undo") + 1]
    man = json.load(open(os.path.join(bdir, "manifest.json"), encoding="utf-8"))
    for e in man["files"]:
        assert rel_ok(e["path"]), e["path"]
        shutil.copy2(os.path.join(bdir, e["path"]), os.path.join(root, e["path"]))
        print("还原", e["path"])
    print(f"已还原 {len(man['files'])} 张(.meta 没动过,不用还原)")
    sys.exit(0)

new_dir, list_json = args[1], args[2]
apply = "--apply" in args
only = set()
if "--only" in args:
    i = args.index("--only") + 1
    while i < len(args) and not args[i].startswith("--"):
        only.add(args[i]); i += 1

rows = json.load(open(list_json, encoding="utf-8"))
by_name = {}
for r in rows:
    by_name.setdefault(os.path.basename(r["path"])[:-4], []).append(r["path"])

def users_of(guids):
    """按 GUID 一次搜完 Assets 下的序列化资产(不含 .meta 和编辑器图片搜索缓存)→ {guid: [路径]}"""
    exts = ("*.prefab", "*.asset", "*.unity", "*.mat", "*.spriteatlas", "*.spriteatlasv2", "*.controller", "*.anim", "*.playable")
    hits = {g: set() for g in guids}
    if not guids: return {}
    cmd = ["rg", "-o", "-F", "--no-line-number", "--with-filename"] + sum((["-e", g] for g in guids), []) \
        + sum((["-g", e] for e in exts), []) + [os.path.join(root, "Assets")]
    try:
        for line in subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8").stdout.splitlines():
            p, _, g = line.rpartition(":")
            if g in hits: hits[g].add(p)
    except FileNotFoundError:
        for dp, _, fs in os.walk(os.path.join(root, "Assets")):
            for f in fs:
                if f.endswith(tuple(e[1:] for e in exts)):
                    p = os.path.join(dp, f)
                    try:
                        t = open(p, encoding="utf-8", errors="ignore").read()
                    except OSError:
                        continue
                    for g in guids:
                        if g in t: hits[g].add(p)
    res = {}
    for g, ps in hits.items():
        rs = (os.path.relpath(p, root).replace("\\", "/") for p in ps)
        res[g] = sorted(r for r in rs if "/Editor/UIImageSearch/Cache/" not in r)
    return res

plan, problems = [], []
for f in sorted(os.listdir(new_dir)):
    if not f.endswith(".png") or f.endswith(".raw.png") or f.startswith("_"): continue
    name = f[:-4]
    if only and name not in only: continue
    paths = by_name.get(name)
    if not paths:
        problems.append(f"{name}:清单里没有同名切图,跳过"); continue
    if len(paths) > 1:
        problems.append(f"{name}:清单里有 {len(paths)} 个同名切图({', '.join(paths)}),不知道换哪个,跳过"); continue
    rel = paths[0]
    if not rel_ok(rel):
        problems.append(f"{name}:路径不在 Assets 内,跳过"); continue
    old_p, new_p = os.path.join(root, rel), os.path.join(new_dir, f)
    if not os.path.exists(old_p) or not os.path.exists(old_p + ".meta"):
        problems.append(f"{name}:主工程里没有 {rel} 或它的 .meta,跳过"); continue
    meta = open(old_p + ".meta", encoding="utf-8", errors="replace").read()
    guid = re.search(r"^guid: ([0-9a-f]{32})", meta, re.M).group(1)
    tt = re.search(r"textureType: (\d+)", meta); sm = re.search(r"spriteMode: (\d+)", meta)
    if not (tt and tt.group(1) == "8" and sm and sm.group(1) == "1"):
        problems.append(f"{name}:不是单张 Sprite(textureType {tt and tt.group(1)} / spriteMode {sm and sm.group(1)}),跳过"); continue
    o, n = Image.open(old_p).convert("RGBA"), Image.open(new_p).convert("RGBA")
    if o.size != n.size:
        problems.append(f"{name}:尺寸不一致 旧 {o.size} / 新 {n.size},跳过"); continue
    oa, na = o.getchannel("A").tobytes(), n.getchannel("A").tobytes()
    over = sum(1 for x, y in zip(oa, na) if y > 8 and x <= 8)
    if over > 0.002 * len(oa):
        problems.append(f"{name}:新图有 {over} 个像素超出旧图透明轮廓,跳过"); continue
    same = open(old_p, "rb").read() == open(new_p, "rb").read()
    plan.append({"name": name, "path": rel, "new": new_p, "guid": guid, "size": o.size, "same": same})

users = users_of([e["guid"] for e in plan])
for e in plan:
    e["users"] = users.get(e["guid"], [])

for e in plan:
    tag = "(与主工程现有文件相同,不用换)" if e["same"] else ""
    print(f"{'换' if not e['same'] else '同'} {e['path']}  {e['size'][0]}×{e['size'][1]}  {tag}")
    print(f"     在用它的:{', '.join(e['users']) if e['users'] else '(没搜到引用)'}")
for p in problems:
    print("✗", p)
todo = [e for e in plan if not e["same"]]
print(f"可换 {len(todo)} 张,跳过 {len(problems)} 张")

if not apply:
    print("这是演练,没写任何文件;确认后加 --apply 写入")
    sys.exit(1 if problems else 0)
if not todo:
    sys.exit(0)
bdir = os.path.join(STUDIO, "backups", time.strftime("%Y%m%d-%H%M%S") + "-restyle")
for e in todo:
    dst = os.path.join(bdir, e["path"]); os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(os.path.join(root, e["path"]), dst)
json.dump({"unity": root, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "files": [{"path": e["path"], "guid": e["guid"], "from": e["new"]} for e in todo]},
          open(os.path.join(bdir, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for e in todo:
    shutil.copyfile(e["new"], os.path.join(root, e["path"]))
    print("已写入", e["path"])
print(f"旧图备份在 {bdir};还原:python dev/restyle/swap_in_place.py {root} --undo {bdir}")
