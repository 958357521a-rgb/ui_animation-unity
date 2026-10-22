# 截图瘦身:裁掉纯色边、只留要看的区域、缩到长边 800,再给 Claude 看 —— 一张整屏截图能省一半以上的 token。
# 用法:
#   python dev/lite/shot.py --clip                  读剪贴板里的截图(她说「看剪贴板」时用)
#   python dev/lite/shot.py 图.png [--crop x,y,w,h] [--max 800]
#   python dev/lite/shot.py --latest 文件夹           取文件夹里最新的一张(比如系统截图文件夹)
# 输出 exports/lite/shots/<时间>.png,终端打印路径和尺寸,Claude 再 Read 这个小图。
import argparse, datetime, glob, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace"); sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def trim(im, tol=6):
    """裁掉四周和角落颜色一样的边(截图里的空白、深色背景)"""
    rgb = im.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 if v > tol else 0)
    box = diff.getbbox()
    return im.crop(box) if box and (box[2] - box[0]) * (box[3] - box[1]) > 0.05 * im.width * im.height else im


def slim(im, crop=None, max_side=800):
    if crop:
        x, y, w, h = crop
        im = im.crop((x, y, x + w, y + h))
    im = trim(im)
    im.thumbnail((max_side, max_side))
    return im


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="截图瘦身后再给 Claude 看")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--clip", action="store_true"); ap.add_argument("--latest")
    ap.add_argument("--crop", help="x,y,w,h(原图像素)"); ap.add_argument("--max", type=int, default=800)
    a = ap.parse_args()
    if a.clip:
        from PIL import ImageGrab
        im = ImageGrab.grabclipboard()
        if isinstance(im, list):
            im = Image.open(im[0]) if im else None
        if not isinstance(im, Image.Image):
            sys.exit("✗ 剪贴板里没有图片")
    elif a.latest:
        fs = [f for f in glob.glob(os.path.join(a.latest, "*")) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        if not fs:
            sys.exit("✗ 文件夹里没有图片")
        im = Image.open(max(fs, key=os.path.getmtime))
    elif a.file:
        im = Image.open(a.file)
    else:
        sys.exit("✗ 给一个图片文件,或用 --clip / --latest")
    src = im.size
    im = slim(im, tuple(int(v) for v in a.crop.split(",")) if a.crop else None, a.max)
    out = os.path.join(ROOT, "exports", "lite", "shots", datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3] + ".png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    print(f"✓ {src[0]}×{src[1]} → {im.width}×{im.height}:{os.path.relpath(out, ROOT).replace(os.sep, '/')}")
