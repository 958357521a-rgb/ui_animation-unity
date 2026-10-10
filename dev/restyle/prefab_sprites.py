# 列出一个 prefab 用到的全部 UI 切图(含 Loadable 壳指向的源 prefab、嵌套 prefab),给 AI 重绘做清单。只读主工程。
# 用法:python dev/restyle/prefab_sprites.py <Unity 工程> <Assets/....prefab> [--json 输出.json]
# 输出每张切图:路径、像素尺寸、九宫格边距(spriteBorder)、用到它的节点名、建议(重绘 / 跳过:图标·光效·角色 / 九宫格)。
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image

root, target = sys.argv[1], sys.argv[2]
out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "exports", "restyle_guid_index.json")

def guid_index():
    """Assets/Arts 与 Assets/Loadable 下 .png/.prefab 的 GUID → 相对路径(按 meta 修改时间缓存)"""
    idx = {}
    try:
        idx = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        pass
    if idx.get("_root") != root:
        idx = {"_root": root}
    fresh = {"_root": root}
    for top in ("Assets/Arts", "Assets/Loadable"):
        for dp, _, fs in os.walk(os.path.join(root, top)):
            for f in fs:
                if not (f.endswith(".png.meta") or f.endswith(".prefab.meta")):
                    continue
                p = os.path.join(dp, f); rel = os.path.relpath(p, root).replace("\\", "/")[:-5]
                m = os.path.getmtime(p); old = idx.get("p:" + rel)
                if old and old[1] == m:
                    g = old[0]
                else:
                    t = open(p, encoding="utf-8", errors="replace").read(400)
                    mm = re.search(r"^guid: ([0-9a-f]{32})", t, re.M); g = mm.group(1) if mm else None
                fresh["p:" + rel] = [g, m]
                if g: fresh[g] = rel
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(fresh, open(CACHE, "w", encoding="utf-8"))
    return fresh

idx = guid_index()
seen, sprites = set(), {}

def scan(rel, depth=0):
    if rel in seen or depth > 6: return
    seen.add(rel)
    t = open(os.path.join(root, rel), encoding="utf-8", errors="replace").read()
    names = {m.group(1): m.group(2).strip().strip('"') for m in re.finditer(r"--- !u!1 &(-?\d+)\nGameObject:[\s\S]*?m_Name: (.*)", t)}
    # 按文档块解析(Image 的 m_Sprite、RawImage 的 m_Texture),避免跨块匹配到别的节点
    for doc in re.split(r"\n(?=--- !u!)", t):
        if not doc.startswith("--- !u!114 "): continue
        go = re.search(r"m_GameObject: \{fileID: (-?\d+)\}", doc)
        for g in re.findall(r"m_(?:Sprite|Texture): \{fileID: \d+, guid: ([0-9a-f]{32})", doc):
            if g in idx and idx[g].endswith(".png"): sprites.setdefault(idx[g], set()).add(names.get(go.group(1) if go else "", "?"))
    for g in re.findall(r"propertyPath: m_Sprite\s+value:\s+objectReference: \{fileID: \d+, guid: ([0-9a-f]{32})", t):
        if g in idx: sprites.setdefault(idx[g], set()).add("(override)")
    for g in set(re.findall(r"m_SourcePrefab: \{fileID: \d+, guid: ([0-9a-f]{32})", t)):
        if g in idx and idx[g].endswith(".prefab"): scan(idx[g], depth + 1)

scan(target)
rows = []
ICON = re.compile(r"(^|[_\-\s])(icon|coin|gem|reward|item|avatar|head|role|char|glow|fx|effect|star|particle)|(?<![a-z])light|图标|道具|光", re.I)
for rel, users in sorted(sprites.items()):
    p = os.path.join(root, rel)
    try: w, h = Image.open(p).size
    except Exception: w = h = 0
    meta = open(p + ".meta", encoding="utf-8", errors="replace").read()
    b = re.search(r"spriteBorder: \{x: (\d+), y: (\d+), z: (\d+), w: (\d+)\}", meta)
    border = [int(x) for x in b.groups()] if b else [0, 0, 0, 0]
    shared = "/CommonSprite/" in rel or "/Common/" in rel or "BaseWidgets" in rel
    kind = "跳过:图标/光效" if ICON.search(os.path.basename(rel)) else "九宫格" if any(border) else "重绘"
    rows.append({"path": rel, "w": w, "h": h, "border": border, "users": sorted(users)[:4], "kind": kind, "shared": shared})
for r in rows:
    print(f'{r["kind"]:<8} {"[公共]" if r["shared"] else "      "} {r["w"]:>4}x{r["h"]:<4} {r["border"] if any(r["border"]) else ""} {r["path"]}  ← {", ".join(r["users"])}')
print(f"共 {len(rows)} 张;扫描了 {len(seen)} 个 prefab")
if out_json: json.dump(rows, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
