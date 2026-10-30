"""赛季礼包小样拼图:按 docs/赛季礼包规范.md 第 3 节坐标拼整页(区域锁死,AI 只出素材)。
用法: python compose.py <素材目录> <方案字母> <卡片编号> <输出.png>
素材目录里要有 <方案>_bg.png、<方案>_card<n>.png、icons.png;通用页签用本目录 通用页签.png。
S18 原件在 s18/(卡片框 / 角标 / 信息行 / 解锁条,从 Figma 组件板 746:587 导出);信息行、解锁条由脚本给原件换色,不用 AI 出。
每期改:TAB_NAME / CARD_TITLE / UNLOCK / CHAR 四行,以及 SCHEME 里各方案的颜色。
"""
import sys, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../.."))
W, H = 2436, 1125
TAB_NAME = "甜心歌姬礼包"
CARD_TITLE = "甜心歌姬礼 Ⅵ"
UNLOCK = "拥有伙伴·甜心歌姬后解锁"
CHAR = os.path.join(ROOT, "docs/风格卡/S18虚拟歌姬礼包_参考/角色模型.webp")
FB = "C:/Windows/Fonts/SourceHanSansCN-Heavy.otf"
FM = "C:/Windows/Fonts/SourceHanSansCN-Bold.otf"
font = lambda p, s: ImageFont.truetype(p, s)

CARD_X = [442, 820, 1198, 1576]; CARD_Y = [97, 553]; CW, CH = 361, 460


def key_green(im):
    im = im.convert("RGBA"); px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            d = g - max(r, b)
            if d > 30:
                al = max(0, 255 - (d - 30) * 4)
                g2 = max(r, b)  # 去绿边
                px[x, y] = (r, g2, b, min(a, al))
    return im


def bbox_crop(im):
    bb = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    return im.crop(bb) if bb else im


def sidebar():
    """通用页签 Figma 渲染(灰底)→ 还原成半透明层,换选中页签名。"""
    src = Image.open(os.path.join(HERE, "通用页签.png")).convert("RGB")
    grey = src.getpixel((900, 300))[0]
    # 选中页签文字区先补掉(用上下行插值)
    x0, x1, y0, y1 = 56, 150, 70, 96
    px = src.load()
    for x in range(x0, x1):
        a, b = px[x, y0 - 1], px[x, y1]
        for y in range(y0, y1):
            t = (y - y0 + 1) / (y1 - y0 + 1)
            px[x, y] = tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))
    out = Image.new("RGBA", src.size); op = out.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b = px[x, y]
            sat = max(r, g, b) - min(r, g, b)
            v = (r + g + b) / 3
            if sat > 18:
                op[x, y] = (r, g, b, 255)
            elif v <= grey:
                op[x, y] = (0, 0, 0, int(255 * (1 - v / grey)))
            else:
                op[x, y] = (255, 255, 255, int(255 * (v - grey) / (255 - grey)))
    s = W / src.width
    out = out.resize((W, round(src.height * s)), Image.LANCZOS)
    d = ImageDraw.Draw(out)
    f = font(FB, 34)
    cx, cy = (x0 + x1) / 2 * s, (y0 + y1) / 2 * s
    d.text((cx, cy), TAB_NAME, font=f, fill=(42, 36, 64), anchor="mm")
    return out


def lum(im, box):
    c = im.crop(box).convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def icons(path):
    sheet = key_green(Image.open(path))
    cw, ch = sheet.width / 4, sheet.height / 2
    res = []
    for r in range(2):
        for c in range(4):
            cell = bbox_crop(sheet.crop((int(c * cw), int(r * ch), int((c + 1) * cw), int((r + 1) * ch))))
            cell.thumbnail((228 - 16, 172 - 16), Image.LANCZOS)
            box = Image.new("RGBA", (228, 172)); box.alpha_composite(cell, ((228 - cell.width) // 2, (172 - cell.height) // 2))
            res.append(box)
    return res


S18 = os.path.join(HERE, "s18")
# 每个方案:标题色、价格色、信息行/解锁条色相偏移(S18 紫 → 粉 ≈ +0.27)、解锁条底板明度倍数
SCHEME = {
    "A": dict(title=(255, 255, 255), price=(255, 255, 255), hue=0.27, dark=0.95),
    "B": dict(title=(255, 255, 255), price=(255, 255, 255), hue=0.27, dark=0.45),
    "C": dict(title=(150, 60, 120), price=(255, 255, 255), hue=0.27, dark=1.0),
    "D": dict(title=(255, 255, 255), price=(255, 255, 255), hue=0.27, dark=0.5),
}


def recolor(im, dh, dv=1.0):
    """只改颜色:色相偏移 + 明度倍数,透明度不动。"""
    im = im.convert("RGBA"); a = im.getchannel("A")
    h, s, v = im.convert("RGB").convert("HSV").split()
    h = h.point(lambda x: int(x + dh * 255) % 256)
    if dv != 1.0:
        v = v.point(lambda x: int(x * dv))
    out = Image.merge("HSV", (h, s, v)).convert("RGBA"); out.putalpha(a)
    return out


def unlock_bar(sc):
    bar = recolor(Image.open(os.path.join(S18, "解锁_raw1.png")), sc["hue"], sc["dark"])
    src = Image.open(os.path.join(S18, "解锁条.png")).convert("RGBA")
    # 锁和两侧细线:从 S18 原件取白色像素原样搬过来(结构不动)
    px = src.load(); bp = bar.load()
    for y in range(0, 31):
        for x in range(337):
            r, g, b, al = px[x, y]
            w = min(r, g, b)
            if w > 200 and al > 120:
                t = (w - 200) / 55
                o = bp[x, y]
                bp[x, y] = tuple(int(o[k] * (1 - t) + 255 * t) for k in range(3)) + (max(o[3], al),)
    d = ImageDraw.Draw(bar)
    d.text((168, 43), UNLOCK, font=font(FB, 19), fill=(255, 255, 255), anchor="mm")
    return bar


def info_row(sc):
    """S18 信息行(Figma 导出带灰底,按原样重建):淡紫渐变底条向右渐隐 + 计时图标 + 两段文字,只换色。"""
    row = Image.new("RGBA", (280, 28)); d = ImageDraw.Draw(row)
    for x in range(280):
        d.line([(x, 0), (x, 27)], fill=(183, 176, 233, int(255 * (1 - (x / 280) ** 2))))
    row.alpha_composite(Image.open(os.path.join(S18, "信息行_raw.png")).convert("RGBA"), (6, 5))
    f = font(FM, 17)
    d.text((29, 14), "剩余：1小时", font=f, fill=(255, 255, 255), anchor="lm")
    d.text((277, 14), "限购1/1", font=f, fill=(115, 99, 181), anchor="rm")
    return recolor(row, sc["hue"])


def card(base, icon, state, sc):
    c = Image.new("RGBA", (CW, CH)); c.alpha_composite(base, (0, 0))
    c.alpha_composite(icon, (68, 116))
    d = ImageDraw.Draw(c)
    d.text((115 + 88, 32 + 17), CARD_TITLE, font=font(FB, 28), fill=sc["title"], anchor="mm")
    c.alpha_composite(info_row(sc), (29, 313))
    d.text((8 + 327 / 2, 363 + 51 / 2), "¥ 98", font=font(FB, 42), fill=sc["price"], anchor="mm",
           stroke_width=2, stroke_fill=(150, 30, 90))
    d.text((60, 36), "8.8折", font=font(FB, 26), fill=(255, 255, 255), anchor="mm",
           stroke_width=3, stroke_fill=(60, 20, 50))
    if state == "sold":
        a = c.getchannel("A")
        g = ImageOps.grayscale(c.convert("RGB")).point(lambda v: int(v * 0.7))
        c = Image.merge("RGBA", (g, g, g, a))
        st = Image.new("RGBA", (149, 119)); sd = ImageDraw.Draw(st)
        sd.ellipse((10, 4, 139, 115), fill=(70, 200, 140, 235), outline=(255, 255, 255), width=4)
        sd.text((74, 60), "已售罄", font=font(FB, 30), fill=(255, 255, 255), anchor="mm")
        c.alpha_composite(st.rotate(15, resample=Image.BICUBIC), (103, 116))
    if state == "lock":
        c.alpha_composite(unlock_bar(sc), (12, 210))
    return c

def topbar(page):
    d = ImageDraw.Draw(page)
    for x, w, icon, num in ((1790, 299, (190, 90, 255), "48541"), (2119, 263, (255, 205, 70), "0")):
        d.rounded_rectangle((x + 20, 34, x + w - 10, 100), 33, fill=(30, 20, 35, 200))
        d.text((x + w / 2 + 10, 67), num, font=font(FB, 34), fill=(255, 255, 255), anchor="mm")
        d.ellipse((x + w - 60, 44, x + w - 16, 90), fill=(255, 80, 160))
        d.text((x + w - 38, 66), "+", font=font(FB, 34), fill=(255, 255, 255), anchor="mm")
    d.polygon([(1810, 66), (1840, 36), (1870, 66), (1840, 100)], fill=(190, 90, 255))
    d.ellipse((2099, 28, 2174, 102), fill=(255, 205, 70), outline=(255, 255, 255), width=3)


def main(src, scheme, n, out):
    sc = SCHEME[scheme]
    bg = Image.open(os.path.join(src, f"{scheme}_bg.png")).convert("RGBA")
    page = ImageOps.fit(bg, (W, H), Image.LANCZOS)
    ch = Image.open(CHAR).convert("RGBA").resize((1174, 1174), Image.LANCZOS)
    page.paste(ch, (1502, -18), ch)
    # 卡片实例内容范围 = 角标 (0,0) 到 卡片框右下 (353,452)
    base = bbox_crop(key_green(Image.open(os.path.join(src, f"{scheme}_card{n}.png")))).resize((353, 452), Image.LANCZOS)
    ic = icons(os.path.join(src, "icons.png"))
    states = ["sold", "tag", "tag", "tag", "tag", "tag", "lock", "lock"]
    for i, st in enumerate(states):
        page.alpha_composite(card(base, ic[i], st, sc), (CARD_X[i % 4], CARD_Y[i // 4]))
    page.alpha_composite(sidebar(), (0, 0))
    topbar(page)
    page.convert("RGB").save(out)
    print(out)


if __name__ == "__main__":
    main(*sys.argv[1:5])