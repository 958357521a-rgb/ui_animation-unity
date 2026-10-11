# 按模板风格重绘旧 UI 切图(本机 ComfyUI + Qwen Image 2.1,接法照官方模板 image_qwen_image_2_1_image_edit)
# 用法:python dev/restyle/restyle.py 旧图1.png 旧图2.png ... --out <输出目录> --refs dev/restyle/templates/template_gempack.png dev/restyle/templates/template_sign.png [--keep-shape] [--max-aspect 2.5] [--seed N] [--port 8188]
# 用哪几个模型、加载节点、缓存放哪、默认分辨率:读 dev/restyle/models.json + 本机的 models.local.json(见 models_config.py)。
# 模板图 = 207 / 钻石页新稿用主工程字体合成后裁出的内容区(原作者 2026-10-10 指定的统一风格模板)。Python 用真实解释器 %LOCALAPPDATA%\Python\bin\python(PATH 里的 WindowsApps python 是占位程序)。
# 每张旧图:image_1 = 旧图(输出尺寸跟随它),image_2.. = 模板参考图 → 重绘 → 缩回原尺寸(保留 RGBA)→ <out>/<名字>.png,
# 再拼一张新旧对比图 <out>/_compare.png。只读旧图,不写主工程。
import argparse, io, json, os, random, sys, time, uuid, urllib.request
from models_config import load_models, loader_nodes
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True); ap.add_argument("--refs", nargs="+", required=True)
ap.add_argument("--seed", type=int, default=20261010); ap.add_argument("--port", default="8188")
ap.add_argument("--res", type=int, default=None, help="默认用模型配置里的 res"); ap.add_argument("--steps", type=int, default=25)
ap.add_argument("--prompt", default=None); ap.add_argument("olds", nargs="+")
ap.add_argument("--max-aspect", type=float, default=2.5, help="长宽比超过它的旧图先补透明边再送进模型,出图后裁回原区域")
ap.add_argument("--neg", default=None, help="反向提示词(整屏重绘时要去掉 text,否则界面文字会被抹掉)")
ap.add_argument("--keep-shape", action="store_true", help="新图透明通道 = min(新, 旧):轮廓严格不超出旧图")
a = ap.parse_args()
MODELS = load_models()
RES = a.res or int(MODELS.get("res", 1024))
BASE = f"http://127.0.0.1:{a.port}"
os.makedirs(a.out, exist_ok=True)

PROMPT = a.prompt or (
    "Redraw the game UI element in <image1> in the art style of the reference UI screens <image2> and <image3>. "
    "Keep exactly the same silhouette, outline shape, proportions, layout and transparent areas as <image1>; it is the same element, only restyled. "
    "Keep the main color family of <image1> (a red element stays red / pink-red, a yellow one stays yellow, a purple one stays purple), only adapt it to the reference palette and material. "
    "Target style: soft glossy glassmorphism, white-to-lavender gradient card faces with subtle holographic iridescence, "
    "violet / purple accents, bright lemon-yellow highlight bands, rounded corners, clean thin light borders, soft drop shadow, "
    "subtle diamond-pattern texture, bright and clean mobile game UI. "
    "Do not add any text, letters, numbers, logos or new objects. Output a PNG image with a transparent background.")
NEG = a.neg if a.neg is not None else "text, letters, watermark, logo, extra objects, characters, photo, realistic photo, blurry, low quality, distorted shape"

def post(path, data, headers):
    return json.load(urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=headers), timeout=60))

def upload(path):
    name = "budui_" + uuid.uuid4().hex[:8] + "_" + os.path.basename(path)
    b = "----budui" + uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n").encode() \
        + open(path, "rb").read() + (f"\r\n--{b}\r\nContent-Disposition: form-data; name=\"subfolder\"\r\n\r\nbudui\r\n"
        f"--{b}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{b}--\r\n").encode()
    r = post("/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={b}"})
    return (r["subfolder"] + "/" + r["name"]) if r.get("subfolder") else r["name"]

def graph(img_names, prompt, seed):
    ld = loader_nodes(MODELS)
    g = {
        "1": {"class_type": ld["unet"][0], "inputs": ld["unet"][1]},
        "2": {"class_type": "QwenImage21Cache", "inputs": {"model": ["1", 0], "device": MODELS.get("cache_device", "auto"), "dtype": MODELS.get("cache_dtype", "default")}},
        "3": {"class_type": ld["clip"][0], "inputs": ld["clip"][1]},
        "4": {"class_type": ld["vae"][0], "inputs": ld["vae"][1]},
        "8": {"class_type": "TextEncodeQwenImage21", "inputs": {"clip": ["3", 0], "vae": ["4", 0], "prompt": prompt, "negative_prompt": NEG, "resolution": RES}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["8", 0], "negative": ["8", 1], "latent_image": ["8", 2],
              "seed": seed, "steps": a.steps, "cfg": 1, "sampler_name": "euler", "scheduler": "simple", "denoise": 1}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "budui_restyle/out"}},
    }
    for i, n in enumerate(img_names, 1):
        g[str(100 + i)] = {"class_type": "LoadImage", "inputs": {"image": n}}
        g["8"]["inputs"][f"images.image_{i}"] = [str(100 + i), 0]
    return g

def run(g):
    pid = post("/prompt", json.dumps({"prompt": g, "client_id": "budui"}).encode(), {"Content-Type": "application/json"})["prompt_id"]
    t0 = time.time()
    while True:
        time.sleep(2)
        h = json.load(urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=30))
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st.get("messages", [])[-1:], ensure_ascii=False)[:1500])
            outs = [im for o in h[pid]["outputs"].values() for im in o.get("images", [])]
            if outs:
                im = outs[0]
                q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"], "type": im["type"]})
                return Image.open(io.BytesIO(urllib.request.urlopen(f"{BASE}/view?{q}", timeout=60).read())), time.time() - t0
        if time.time() - t0 > 900: raise TimeoutError(pid)

import urllib.parse
from PIL import ImageFilter

def structure_sim(x, y, n=48):
    """两张图的轮廓结构相似度(灰度边缘图的相关系数),不看颜色:换风格时颜色本来就会变"""
    def edges(im):
        g = im.convert("RGBA"); bg = Image.new("RGBA", g.size, (128, 128, 128, 255)); bg.alpha_composite(g)
        e = bg.convert("L").resize((n, n)).filter(ImageFilter.FIND_EDGES)
        return list(e.getdata())
    p, q = edges(x), edges(y)
    mp, mq = sum(p) / len(p), sum(q) / len(q)
    cov = sum((u - mp) * (v - mq) for u, v in zip(p, q))
    vp = sum((u - mp) ** 2 for u in p) ** 0.5; vq = sum((v - mq) ** 2 for v in q) ** 0.5
    return cov / (vp * vq) if vp and vq else 0.0

refs = [upload(r) for r in a.refs]
ref_imgs = [Image.open(r) for r in a.refs]
rows = []
for old in a.olds:
    src = Image.open(old).convert("RGBA")
    name = os.path.splitext(os.path.basename(old))[0]
    # 极端长宽比(如 265×31 的横条)直接送进去模型会失控:居中补透明边到 max-aspect,出图后按比例裁回
    W, H = src.size; pw, ph = W, H
    if W / H > a.max_aspect: ph = round(W / a.max_aspect)
    elif H / W > a.max_aspect: pw = round(H / a.max_aspect)
    feed, box = src, None
    if (pw, ph) != (W, H):
        feed = Image.new("RGBA", (pw, ph), (0, 0, 0, 0)); ox, oy = (pw - W) // 2, (ph - H) // 2
        feed.paste(src, (ox, oy)); box = (ox / pw, oy / ph, (ox + W) / pw, (oy + H) / ph)
        feed_path = os.path.join(a.out, name + ".feed.png"); feed.save(feed_path)
    # 防照抄:画面很花的旧图有时整张照搬参考图。按轮廓结构比,出图更像参考图就换种子重跑(最多 3 次)
    src_up = upload(feed_path if box else old)
    try:
        for attempt in range(3):
            out, sec = run(graph([src_up] + refs, PROMPT, a.seed + attempt * 7919))
            s_src, s_ref = structure_sim(out, feed), max([structure_sim(out, r) for r in ref_imgs] or [0])
            if s_src >= s_ref: break
            print(f"  {name}:第 {attempt + 1} 次出图更像参考图(原图 {s_src:.2f} / 参考 {s_ref:.2f}),换种子重跑")
        else:
            print(f"✗ {name}: 3 次都在照抄参考图,跳过"); continue
    except Exception as e:
        print(f"✗ {name}: {e}"); continue
    raw = out.convert("RGBA"); raw.save(os.path.join(a.out, name + ".raw.png"))
    if box: raw = raw.crop((round(box[0] * raw.width), round(box[1] * raw.height), round(box[2] * raw.width), round(box[3] * raw.height)))
    fit = raw.resize(src.size, Image.LANCZOS)
    if a.keep_shape:
        from PIL import ImageChops
        fit.putalpha(ImageChops.darker(fit.getchannel("A"), src.getchannel("A")))
    fit.save(os.path.join(a.out, name + ".png"))
    print(f"✓ {name} {src.size} ← 生成 {out.size} {out.mode} · {sec:.0f}s")
    rows.append((name, src, fit))

# 新旧对比图:棋盘格底(看得出透明区),左旧右新
if rows:
    H = 300
    def board(w, h):
        im = Image.new("RGBA", (w, h), (235, 235, 240, 255)); s = 16
        for y in range(0, h, s):
            for x in range(0, w, s):
                if (x // s + y // s) % 2: im.paste((205, 205, 215, 255), (x, y, x + s, y + s))
        return im
    cells = []
    for name, o, n in rows:
        k = H / max(o.height, 1); w = max(1, round(o.width * k))
        pair = board(w * 2 + 30, H)
        pair.alpha_composite(o.resize((w, H)), (0, 0)); pair.alpha_composite(n.resize((w, H)), (w + 30, 0))
        cells.append(pair)
    W = max(c.width for c in cells)
    sheet = Image.new("RGBA", (W, sum(c.height + 20 for c in cells)), (255, 255, 255, 255)); y = 0
    for c in cells: sheet.paste(c, (0, y)); y += c.height + 20
    sheet.convert("RGB").save(os.path.join(a.out, "_compare.png"))
