# nano banana(Gemini 图像模型)生图 / 改图:结果直接存文件,终端只打印路径和一句话 —— 图片和 base64 都不进 Claude 的对话(省 token)。
# 用法:
#   python dev/lite/nano.py "提示词" [--ref 参考图或文件夹 ...] [--n 张数] [--name 名字] [--aspect 1:1] [--out 目录] [--sheet]
#   python dev/lite/nano.py --prompt-file 提示词.txt --ref 原图.png --ref docs/风格卡/xxx_参考/   (改图:原图也当 --ref 传)
# 输出在 exports/nano/<时间>_<名字>/:01.png、02.png …,加 --sheet 再出一张带编号的小对比图 _sheet.png(要看效果时只看这一张)。
# 配置(本机,不进仓库):dev/lite/nano.local.json —— {"api_key": "...", "base_url": "https://generativelanguage.googleapis.com",
#   "model": "gemini-2.5-flash-image", "auth": "header"};也可以用环境变量 NANO_API_KEY / GEMINI_API_KEY。
#   用中转地址时改 base_url;中转要求 Bearer 头就把 auth 设成 "bearer",要求 ?key= 就设成 "query"。
import argparse, base64, datetime, glob, io, json, os, re, sys, time, urllib.error, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace"); sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONF = os.path.join(HERE, "nano.local.json")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def config():
    c = {"base_url": "https://generativelanguage.googleapis.com", "model": "gemini-2.5-flash-image", "auth": "header", "timeout": 180}
    if os.path.exists(CONF):
        c.update(json.load(open(CONF, encoding="utf-8")))
    c["api_key"] = c.get("api_key") or os.environ.get("NANO_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
    c["base_url"] = os.environ.get("NANO_BASE_URL") or c["base_url"]
    c["model"] = os.environ.get("NANO_MODEL") or c["model"]
    if not c["api_key"]:
        sys.exit("✗ 没有 API Key:在 dev/lite/nano.local.json 里填 {\"api_key\": \"…\"},或设环境变量 NANO_API_KEY")
    return c


def ref_files(items):
    out = []
    for it in items or []:
        if os.path.isdir(it):
            out += sorted(f for f in glob.glob(os.path.join(it, "*")) if f.lower().endswith(IMG_EXT))
        elif os.path.isfile(it):
            out.append(it)
        else:
            sys.exit(f"✗ 找不到参考图:{it}")
    return out


def encode(path, max_side=1536):
    """参考图上传前缩到长边 1536(够模型看清,少传数据、快)"""
    im = Image.open(path)
    im.thumbnail((max_side, max_side))
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    b = io.BytesIO(); im.save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


def call(c, prompt, refs, aspect):
    parts = [{"text": prompt}] + [{"inline_data": {"mime_type": "image/png", "data": encode(r)}} for r in refs]
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    if aspect:
        body["generationConfig"]["imageConfig"] = {"aspectRatio": aspect}
    url = f"{c['base_url'].rstrip('/')}/v1beta/models/{c['model']}:generateContent"
    headers = {"Content-Type": "application/json"}
    if c["auth"] == "query":
        url += "?key=" + c["api_key"]
    elif c["auth"] == "bearer":
        headers["Authorization"] = "Bearer " + c["api_key"]
    else:
        headers["x-goog-api-key"] = c["api_key"]
    req = urllib.request.Request(url, json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(req, timeout=c["timeout"]) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}:{e.read()[:300].decode('utf-8', 'replace')}")
    imgs, texts = [], []
    for cand in data.get("candidates") or []:
        for p in (cand.get("content") or {}).get("parts") or []:
            d = p.get("inlineData") or p.get("inline_data")
            if d and d.get("data"):
                imgs.append(base64.b64decode(d["data"]))
            elif p.get("text"):
                texts.append(p["text"])
    if not imgs:
        why = (data.get("promptFeedback") or {}).get("blockReason") or " ".join(texts)[:200] or json.dumps(data)[:200]
        raise RuntimeError("没有返回图片:" + why)
    return imgs, " ".join(texts)


def main():
    ap = argparse.ArgumentParser(description="nano banana 生图(结果只存文件)")
    ap.add_argument("prompt", nargs="?", default="")
    ap.add_argument("--prompt-file")
    ap.add_argument("--ref", action="append", help="参考图 / 要改的原图,可以是文件夹;可写多次")
    ap.add_argument("--n", type=int, default=1, help="生成几张(逐张请求)")
    ap.add_argument("--name", default="", help="输出文件夹名后缀")
    ap.add_argument("--aspect", default="", help="画面比例,如 1:1、16:9、9:16")
    ap.add_argument("--out", help="输出目录(默认 exports/nano/<时间>_<名字>)")
    ap.add_argument("--sheet", action="store_true", help="另出一张带编号的小对比图 _sheet.png")
    a = ap.parse_args()
    prompt = open(a.prompt_file, encoding="utf-8").read().strip() if a.prompt_file else a.prompt.strip()
    if not prompt:
        sys.exit("✗ 没有提示词")
    c = config(); refs = ref_files(a.ref)
    out = a.out or os.path.join(ROOT, "exports", "nano", datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                                + ("_" + re.sub(r'[\\/:*?"<>|\s]+', "_", a.name) if a.name else ""))
    os.makedirs(out, exist_ok=True)
    saved, note, fails = [], "", []
    for i in range(max(1, a.n)):
        for attempt in range(2):
            try:
                imgs, note = call(c, prompt, refs, a.aspect)
                for b in imgs:
                    p = os.path.join(out, f"{len(saved) + 1:02d}.png")
                    Image.open(io.BytesIO(b)).save(p); saved.append(p)
                break
            except (RuntimeError, OSError, urllib.error.URLError) as e:
                if attempt:
                    fails.append(str(e)[:300])
                else:
                    time.sleep(2)
    json.dump({"prompt": prompt, "refs": refs, "model": c["model"], "aspect": a.aspect, "files": [os.path.basename(p) for p in saved],
               "time": datetime.datetime.now().isoformat(timespec="seconds")}, open(os.path.join(out, "_info.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")
    if saved:
        sizes = Image.open(saved[0]).size
        print(f"✓ {len(saved)} 张({sizes[0]}×{sizes[1]},参考图 {len(refs)} 张)→ {rel(out)}/")
        for p in saved:
            print("  " + rel(p))
        if a.sheet and len(saved) > 1:
            sys.path.insert(0, HERE); import sheet
            print("  对比图:" + rel(sheet.make(saved, os.path.join(out, "_sheet.png"))))
        if note:
            print("  模型说明:" + note[:150])
    for f in fails:
        print("✗ " + f)
    sys.exit(0 if saved else 1)


if __name__ == "__main__":
    main()
