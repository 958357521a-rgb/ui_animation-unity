"""扭蛋 UI 件合成(第3轮起):按钮 / 角色格照 Figma 730:3575「圣羽降临」组件的尺寸和内部排布。

python dev/gacha_bg/ui3_compose.py --dir 出图目录 --shot 游戏内截图_2436.png --tag 名字 \
    --logo X.png --once X.png --round X.png --hex X.png [--figma 目录(内含 raw2.png 优优币)]
--once/--round/--hex 可以是绿幕 AI 图(自动抠图),也可以写 recolor:raw1.png 这种 = 直接把 Figma 原件换色。
按钮上的币图标、原价删除线、现价、文字、「首次6折」角标都由脚本按 Figma 偏移画(相对按钮左上角,531×171)。
"""
import argparse, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ui_compose import ZONES, key_green, drop_ghosts, logo_box, fit, glow

FONT = r"C:\Windows\Fonts\msyhbd.ttc"
BTN = (531, 171)
PLATE = (434, 110)       # 用户定:按钮体(看得见的部分)434×110,和旧按钮体量一致
PLATE_C = (265, 89)      # 旧按钮 raw1 不透明区中心
# Figma 748:987(隐藏备份)里按钮内部件,相对按钮左上角
COIN = (115, 50, 66, 65)
OLD = (192, 34)          # 原价 x168(删除线)
NEW = (186, 58)          # 现价 x128
LABEL = (276, 56, 168, 58)
TAG = (385, 7, 132, 35)
HUE = {"raw1.png": 50, "raw3.png": -80, "hexraw1.png": 65}   # 蓝→粉紫 / 黄→亮粉 / 淡紫→粉


def recolor(path, shift):
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    hsv = np.asarray(im.convert("RGB").convert("HSV")).astype(np.int32)
    hsv[..., 0] = (hsv[..., 0] + round(shift * 255 / 360)) % 256
    out = Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGBA"); out.putalpha(a)
    return out


def split_pair(im):
    """按列上有没有像素把一对按钮切开:找中间最宽的空列段。"""
    cols = (np.asarray(im.getchannel("A")) > 60).any(axis=0)
    w = len(cols); best = (0, w // 2, w // 2)
    i = w // 4
    while i < w * 3 // 4:
        if not cols[i]:
            j = i
            while j < w and not cols[j]:
                j += 1
            if j - i > best[0]:
                best = (j - i, i, j)
            i = j
        i += 1
    l, r = im.crop((0, 0, best[1], im.height)), im.crop((best[2], 0, w, im.height))
    return [x.crop(x.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()) for x in (l, r)]


def keep_main(im):
    """只留最大的一块(AI 会在按钮上方画半透明重影、飘着的小角,或者多画一排)。"""
    from scipy import ndimage
    lab, n = ndimage.label(ndimage.binary_dilation(np.asarray(im.getchannel("A")) > 60, iterations=3))
    if n > 1:
        keep = 1 + int(np.argmax(ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))))
        arr = np.asarray(im).copy(); arr[lab != keep] = 0; im = Image.fromarray(arr, "RGBA")
    return im.crop(im.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox())


def stretch_mid(im, w, h, a=0.42, b=0.58):
    """按钮外框必须正好 w×h(和模板组件一致):等比缩到高 h,左右两端不变形,只拉伸 / 压缩中间那段纯底色。"""
    im = im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)
    l, r = int(im.width * a), int(im.width * b)
    mid = max(1, w - l - (im.width - r))
    out = Image.new("RGBA", (w, h))
    out.alpha_composite(im.crop((0, 0, l, h)), (0, 0))
    out.alpha_composite(im.crop((l, 0, r, h)).resize((mid, h), Image.LANCZOS), (l, 0))
    out.alpha_composite(im.crop((r, 0, im.width, h)), (l + mid, 0))
    return out


def load(spec, figma, size):
    if spec.startswith("recolor:"):
        name = spec.split(":", 1)[1]
        return recolor(os.path.join(figma, name), HUE[name]).resize(size, Image.LANCZOS)
    if spec.startswith("pair:"):                   # pair:图:0/1 = 一张图里左右一对按钮,取左 / 右
        path, idx = spec[5:].rsplit(":", 1)
        body = stretch_mid(keep_main(split_pair(key_green(Image.open(path)))[int(idx)]), *PLATE)
        out = Image.new("RGBA", size)               # 画布仍是组件 531×171,看得见的按钮体 434×110 摆在旧按钮体中心
        out.alpha_composite(body, (PLATE_C[0] - PLATE[0] // 2, PLATE_C[1] - PLATE[1] // 2))
        return out
    im = drop_ghosts(key_green(Image.open(spec)))
    return fit(im, *size)                          # 等比缩进组件尺寸,不拉伸


def text(d, xy, s, size, fill="white", stroke=(90, 14, 60), sw=4, anchor="la"):
    f = ImageFont.truetype(FONT, size)
    d.text(xy, s, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)
    return d.textbbox(xy, s, font=f, stroke_width=sw, anchor=anchor)


def dress_fit(plate, coin, label, lead=1.0, old="x168", new="x128", tag="首次6折"):
    """新造型按钮:按底板实际外框排内容。左端留 lead×板高 给装饰,币 / 价格 / 文字一行垂直居中,角标骑在右上边。"""
    im = plate.copy(); d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 60 else 0).getbbox()
    h = y1 - y0; cy = (y0 + y1) // 2; x = x0 + int(h * lead)
    room = x1 - 18 - x
    wid = lambda s, n: d.textbbox((0, 0), s, font=ImageFont.truetype(FONT, n), stroke_width=5)[2]
    k = 1.0                                        # 放不下就整体缩小
    while k > 0.75 and min(60, int(h * 0.42)) * k + 6 + wid(new, int(30 * k)) + 12 + wid(label, int(44 * k)) > room:
        k -= 0.04
    cs = int(min(60, h * 0.42) * k); im.alpha_composite(coin.resize((cs, cs), Image.LANCZOS), (x, cy - cs // 2)); x += cs + 6
    b = text(d, (x, cy - 4), old, int(20 * k), fill=(255, 255, 255, 200), sw=2, anchor="ld")
    d.line((b[0], (b[1] + b[3]) // 2, b[2], (b[1] + b[3]) // 2), fill=(90, 14, 60), width=3)
    b2 = text(d, (x, cy - 2), new, int(30 * k), anchor="lt")
    text(d, (max(b[2], b2[2]) + 12, cy), label, int(44 * k), anchor="lm", sw=5)
    tw, th = 132, 35; tx = x1 - tw - 6; ty = max(0, y0 - th // 2)
    d.rounded_rectangle((tx, ty, tx + tw, ty + th), radius=th // 2, fill=(255, 61, 154), outline="white", width=2)
    text(d, (tx + tw // 2, ty + th // 2), tag, 22, sw=0, anchor="mm")
    return im


def dress(plate, coin, label, old="x168", new="x128", tag="首次6折"):
    im = plate.copy(); d = ImageDraw.Draw(im)
    im.alpha_composite(coin.resize(COIN[2:], Image.LANCZOS), COIN[:2])
    b = text(d, OLD, old, 20, fill=(255, 255, 255, 200), sw=2)
    d.line((b[0], (b[1] + b[3]) // 2, b[2], (b[1] + b[3]) // 2), fill=(90, 14, 60), width=3)
    text(d, NEW, new, 30)
    x, y, w, h = LABEL; text(d, (x, y + h // 2), label, 44, anchor="lm", sw=5)
    x, y, w, h = TAG
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=(255, 61, 154), outline="white", width=2)
    text(d, (x + w // 2, y + h // 2), tag, 22, sw=0, anchor="mm")
    return im


def main():
    p = argparse.ArgumentParser()
    for k in ("dir", "shot", "tag", "logo", "once", "round", "hex"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--figma", default=None); p.add_argument("--lead", type=float, default=1.0)
    a = p.parse_args()
    figma = a.figma or os.path.join(a.dir, "figma")
    coin = Image.open(os.path.join(figma, "raw2.png")).convert("RGBA")
    cut = os.path.join(a.dir, f"{a.tag}_切图"); os.makedirs(cut, exist_ok=True)
    lx, ly, lw, lh = logo_box()
    btn = lambda s, t: (dress_fit(load(s, figma, BTN), coin, t, a.lead) if s.startswith("pair:") else dress(load(s, figma, BTN), coin, t))
    pieces = {
        "logo": glow(fit(drop_ghosts(key_green(Image.open(a.logo))), lw - 30, lh - 20)),
        "hex": load(a.hex, figma, tuple(ZONES["reward_tl"][2:])),
        "btn_once": btn(a.once, "抽取1次"),
        "btn_round": btn(a.round, "抽取1轮"),
    }
    for k, im in pieces.items():
        im.save(os.path.join(cut, f"{k}.png"))
    bg = Image.open(a.shot).convert("RGBA"); assert bg.size == (2436, 1125), bg.size
    bg.alpha_composite(pieces["logo"], (lx + (lw - pieces["logo"].width) // 2, ly + (lh - pieces["logo"].height) // 2))
    for k in ("reward_tl", "reward_bl", "reward_tr", "reward_br"):
        bg.alpha_composite(pieces["hex"], tuple(ZONES[k][:2]))
    for k in ("btn_once", "btn_round"):
        x, y = ZONES[k][:2]; bg.alpha_composite(pieces[k], (x, y))
    out = os.path.join(a.dir, f"{a.tag}_效果图.png")
    bg.convert("RGB").save(out); print(out)


if __name__ == "__main__":
    main()
