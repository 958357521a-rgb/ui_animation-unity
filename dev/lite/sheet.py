# 拼图:把多张图(参考图、几版生图结果)拼成一张带编号的小图,Claude 只看这一张 —— 10 张图 ≈ 1 张图的 token。
# 用法:python dev/lite/sheet.py 图或文件夹 ... [--out 文件] [--width 1024] [--cols 列数]
# 输出默认 exports/lite/sheets/<时间>.png;终端打印路径和「编号 = 文件名」对照(之后用编号说话,不用再看原图)。
import argparse, datetime, glob, math, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace"); sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def files_of(items):
    out = []
    for it in items:
        if os.path.isdir(it):
            out += sorted(f for f in glob.glob(os.path.join(it, "*")) if f.lower().endswith(IMG_EXT) and not os.path.basename(f).startswith("_"))
        elif os.path.isfile(it):
            out.append(it)
    return out


def _font(size):
    for f in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def make(paths, out=None, width=1024, cols=None):
    n = len(paths)
    cols = cols or (math.ceil(math.sqrt(n * 1.4)) if n > 9 else min(n, 4 if n > 6 else 3 if n > 2 else n))   # 张数多时更宽、不要拉得太长
    rows = math.ceil(n / cols)
    cell = width // cols; label = max(14, cell // 10)
    sheet = Image.new("RGB", (cell * cols, (cell + label + 4) * rows), (40, 40, 48))
    chk = Image.new("RGB", (cell, cell), (60, 60, 70)); d = ImageDraw.Draw(chk)
    for y in range(0, cell, 16):
        for x in range(0, cell, 16):
            if (x // 16 + y // 16) % 2:
                d.rectangle((x, y, x + 15, y + 15), fill=(75, 75, 86))
    draw = ImageDraw.Draw(sheet); font = _font(label - 2)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGBA"); im.thumbnail((cell - 8, cell - 8))
        x, y = (i % cols) * cell, (i // cols) * (cell + label + 4)
        sheet.paste(chk, (x, y))
        sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2), im)
        draw.text((x + 6, y + cell + 1), f"{i + 1}  {os.path.basename(p)[:24]}", fill=(230, 230, 240), font=font)
    out = out or os.path.join(ROOT, "exports", "lite", "sheets", datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3] + ".png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="多张图拼成一张带编号的小图")
    ap.add_argument("items", nargs="+")
    ap.add_argument("--out"); ap.add_argument("--width", type=int, default=1024); ap.add_argument("--cols", type=int)
    a = ap.parse_args()
    fs = files_of(a.items)
    if not fs:
        sys.exit("✗ 没有图片")
    p = make(fs, a.out, a.width, a.cols)
    w, h = Image.open(p).size
    print(f"✓ {len(fs)} 张拼成 1 张({w}×{h})→ {os.path.relpath(p, ROOT).replace(os.sep, '/')}")
    for i, f in enumerate(fs, 1):
        print(f"  {i} = {os.path.relpath(f, ROOT).replace(os.sep, '/') if os.path.abspath(f).startswith(ROOT) else f}")
