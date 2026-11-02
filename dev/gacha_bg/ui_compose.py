"""扭蛋 UI 件合成:绿幕单件 → 抠图 → 按 layout.json 的 zones 坐标贴到游戏内截图上。

python dev/gacha_bg/ui_compose.py --dir 出图目录 --shot 游戏内截图_2436.png --prefix ui2_A [--once 抽取1次 --round 抽取1轮]
出图目录里要有 <prefix>_logo.png / _reward.png / _btn_once.png / _btn_round.png(绿幕 #00FF00 底)。
输出:<dir>/<prefix>_切图/*.png(透明底,已缩到 zone 尺寸内)和 <dir>/<prefix>_效果图.png。
位置一律取 layout.json,不手填坐标。
"""
import argparse, json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ZONES = {z["key"]: z["rect"] for z in json.load(open(os.path.join(HERE, "layout.json"), encoding="utf-8"))["zones"]}
FONT = r"C:\Windows\Fonts\msyhbd.ttc"


def key_green(im):
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    dom = g - np.maximum(r, b)                      # 绿幕 ≈ 255,物体 ≤ 0
    alpha = 1 - np.clip((dom - 25) / 110, 0, 1)
    g2 = np.minimum(g, np.maximum(r, b) + 10)       # 去绿边
    out = np.dstack([r, g2, b, alpha * 255]).clip(0, 255).astype(np.uint8)
    im = Image.fromarray(out, "RGBA")
    return im.crop(im.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox())


def drop_ghosts(im):
    """AI 偶尔在主体旁多画半截重影:留最大连通块,去掉面积 >20% 的其余大块(小星星等装饰保留)。"""
    from scipy import ndimage
    a = np.asarray(im.getchannel("A")) > 60
    lab, n = ndimage.label(ndimage.binary_dilation(a, iterations=3))
    if n < 2:
        return im
    area = ndimage.sum(a, lab, range(1, n + 1)); big = area.max()
    drop = [i + 1 for i, s in enumerate(area) if s != big and s > big * 0.2]
    if not drop:
        return im
    arr = np.asarray(im).copy(); arr[np.isin(lab, drop)] = 0
    im = Image.fromarray(arr, "RGBA")
    return im.crop(im.getchannel("A").getbbox())


def logo_box():
    """标题区去掉和活动时间、视频预览重叠的部分(模板里它们叠在标题区上方)。"""
    x, y, w, h = ZONES["title"]
    top = max(y, ZONES["time"][1] + ZONES["time"][3] + 12)
    right = min(x + w, ZONES["video"][0] - 20)
    return [x, top, right - x, y + h - top]


def fit(im, w, h):
    s = min(w / im.width, h / im.height)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    c = Image.new("RGBA", (w, h))
    c.alpha_composite(im, ((w - im.width) // 2, (h - im.height) // 2))
    return c


def glow(im, color=(255, 61, 154), radius=14, strength=0.85):
    pad = radius * 2
    big = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2))
    big.alpha_composite(im, (pad, pad))
    a = big.getchannel("A").filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(min(255, v * strength * 1.6)))
    g = Image.new("RGBA", big.size, color + (0,)); g.putalpha(a)
    g.alpha_composite(big)
    return g.crop((pad, pad, pad + im.width, pad + im.height))


def label(im, text, size_ratio=0.30):
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, int(im.height * size_ratio))
    bw = d.textbbox((0, 0), text, font=f, stroke_width=6)
    x = (im.width - (bw[2] - bw[0])) // 2 - bw[0]; y = (im.height - (bw[3] - bw[1])) // 2 - bw[1] - int(im.height * 0.03)
    d.text((x, y), text, font=f, fill="white", stroke_width=6, stroke_fill=(74, 16, 52))
    return im


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", required=True); p.add_argument("--shot", required=True); p.add_argument("--prefix", required=True)
    p.add_argument("--once", default="抽取1次"); p.add_argument("--round", default="抽取1轮")
    a = p.parse_args()
    src = lambda k: Image.open(os.path.join(a.dir, f"{a.prefix}_{k}.png"))
    cut = os.path.join(a.dir, f"{a.prefix}_切图"); os.makedirs(cut, exist_ok=True)
    pieces = {}
    ZONES["logo"] = logo_box()
    x, y, w, h = ZONES["logo"]; pieces["logo"] = glow(fit(drop_ghosts(key_green(src("logo"))), w - 30, h - 20))
    x, y, w, h = ZONES["reward_tl"]; pieces["reward"] = fit(key_green(src("reward")), w, h)
    for k, t in (("btn_once", a.once), ("btn_round", a.round)):
        x, y, w, h = ZONES[k]; pieces[k] = label(fit(key_green(src(k)), w, h), t)
    for k, im in pieces.items():
        im.save(os.path.join(cut, f"{k}.png"))
    bg = Image.open(a.shot).convert("RGBA")
    assert bg.size == (2436, 1125), bg.size
    def put(im, key):
        x, y, w, h = ZONES[key]
        bg.alpha_composite(im, (x + (w - im.width) // 2, y + (h - im.height) // 2))
    put(pieces["logo"], "logo")
    for k in ("reward_tl", "reward_bl", "reward_tr", "reward_br"):
        put(pieces["reward"], k)
    put(pieces["btn_once"], "btn_once"); put(pieces["btn_round"], "btn_round")
    out = os.path.join(a.dir, f"{a.prefix}_效果图.png")
    bg.convert("RGB").save(out); print(out)


if __name__ == "__main__":
    main()
