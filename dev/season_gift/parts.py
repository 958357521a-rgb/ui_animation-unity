"""定稿后切配套件(1x + @2x,透明底,不带文字),尺寸照 docs/赛季礼包规范.md 第 2 节。
用法: python parts.py <方案字母> <选定的整卡.png> <无角标卡片框.png> <弹窗卡片.png> <输出目录>
- 整卡 = card_jobs 出的卡片(绿底,带角标);角标从这里按 S18 角标外形抠出来
- 无角标卡片框 / 弹窗卡片 = AI 在整卡上去掉角标 / 去掉价格按钮的版本(绿底)
- 已售罄卡片框:价格按钮换灰;置灰遮罩:卡片本体完整剪影,和卡片框同画布(345×444),在母件里和卡片框同位置
- 信息行底 / 解锁条底:只切底,不带图标(11-02 用户:图标和底分开)。计时图标、锁、两侧细线、印章、物品图标、货币条是通用件,
  在 Figma 里直接用 S18 组件实例 / 原图层,不重切。信息行底在 Figma 里是渐变矩形,这里另存一张 PNG 备用。
可选第 6 个参数 = 背景图:另存 背景.png(2436×1125)和 立绘.png(带柔光,裁到内容,文件名里不带坐标,坐标打印出来)
"""
import sys, os
from PIL import Image, ImageOps, ImageFilter
from compose import key_green, bbox_crop, recolor, place_char, SCHEME, S18, W, H, CHAR_H, CHAR_CX, CHAR_FOOT

SIZES = {"卡片框": (345, 444), "折扣角标": (124, 77), "置灰遮罩": (345, 444), "已售罄卡片框": (345, 444), "弹窗卡片": (329, 424),
         "信息行底": (280, 28), "解锁条底": (337, 59)}


def crisp_cut(path):
    """绿底 AI 图 → 边缘干净的卡片本体(11-02 用户:边缘模糊不干净,要像 S18 那样边缘清晰、投影另算)。
    在原图分辨率上硬抠:绿色占比稍高就全透明(霓虹光晕和 AI 画在绿底上的投影一起去掉),去绿溢色,
    贴边残留的暗青色也去掉,小开运算去毛刺;RGB 轻度锐化。抗锯齿交给之后缩到 2x / 1x 的 LANCZOS。"""
    # 11-02 用户:扭蛋切图质量合格 → 照 dev/gacha_bg/ui_compose.key_green:按绿色占比线性出 alpha(原图自带的抗锯齿和光晕
    # 半透明都保留,不阈值、不模糊、不锐化),去绿边;只多一步:贴边的暗青色(AI 画在绿底上的投影)按青色程度渐变去掉
    import numpy as np
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    alpha = 1 - np.clip((g - np.maximum(r, b) - 25) / 110, 0, 1)
    # 半透明边上的颜色 = 本体色和绿底的混合:按 alpha 把绿底减回去(不减会留一圈黄绿边),再去绿溢色
    bgc = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3)]), axis=0)
    k = np.maximum(alpha, 0.05)[..., None]
    r, g, b = np.moveaxis(np.clip((a - (1 - k) * bgc) / k, 0, 255), -1, 0)
    g = np.minimum(g, np.maximum(r, b) + 4)
    edge = np.asarray(Image.fromarray(((alpha < 0.5) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))) > 0
    cyan = np.clip((np.minimum(g, b) - r - 4) / 20, 0, 1) * np.clip((190 - np.maximum(np.maximum(r, g), b)) / 60, 0, 1)
    alpha = np.where(edge, alpha * (1 - cyan), alpha)
    out = Image.fromarray(np.dstack([r, g, b, alpha * 255]).clip(0, 255).astype(np.uint8), "RGBA")
    return out.crop(out.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox())


def with_shadow(body, size):
    """本体放进组件画布(下方留投影位),在本体下面垫一层合成投影:本体边缘保持清晰,投影只在下沿露出来。"""
    w, h = size; W = body.width
    s = W / (w - 4)  # 左右各留 2px(1x)
    cw, ch = round(w * s), round(h * s)
    bh = ch - round(10 * s)  # 下方留 10px(1x)给投影
    b = body.resize((cw - round(4 * s), bh), Image.LANCZOS)
    canvas = Image.new("RGBA", (cw, ch)); x0 = round(2 * s)
    al = b.getchannel("A")
    sh = Image.new("RGBA", b.size, (60, 16, 52, 0)); sh.putalpha(al.point(lambda v: v * 110 // 255))
    pad = Image.new("RGBA", (cw, ch)); pad.alpha_composite(sh, (x0, round(5 * s)))
    pad = pad.filter(ImageFilter.GaussianBlur(3 * s))
    canvas.alpha_composite(pad); canvas.alpha_composite(b, (x0, 0))
    return canvas, (x0, 0, b.width, b.height)


def grey_button(frame):
    """价格按钮(卡片框下部)去色压暗:按饱和度渐变混合,按钮本体全灰,抗锯齿边和粉色光晕按比例变灰,
    浅色卡身几乎不动 —— 不用膨胀遮罩(会在卡身上压出一圈灰晕)。"""
    W, H = frame.size; y0 = int(H * 0.76)
    out = frame.copy(); px = out.load()
    for y in range(y0, H):
        for x in range(W):
            r, g, b, a = px[x, y]
            if not a: continue
            sat = max(r, g, b) - min(r, g, b)
            f = min(1.0, max(0.0, (sat - 12) / 40))
            if not f: continue
            v = (0.299 * r + 0.587 * g + 0.114 * b) * (1 - 0.38 * min(1.0, max(0.0, (sat - 60) / 60)))  # 浅色光晕只去色不压暗
            px[x, y] = (int(r + (v - r) * f), int(g + (v - g) * f), int(b + (v + 6 - b) * f), a)
    return out


def mask_of(canvas, box):
    """置灰遮罩 = 卡片本体的完整剪影(连同耳机等外沿装饰),和卡片框同画布同位置,叠上去严丝合缝。"""
    x0, y0, w, h = box
    a = canvas.getchannel("A").crop((x0, y0, x0 + w, y0 + h))
    m = Image.new("RGBA", canvas.size, (30, 26, 36, 0))
    al = Image.new("L", canvas.size); al.paste(a.point(lambda v: v * 140 // 255), (x0, y0)); m.putalpha(al)
    return m


def main(scheme, card, frame, popup, out, bg=None):
    sc = SCHEME[scheme]; os.makedirs(out, exist_ok=True)
    hi = {}  # 2x 源
    body = crisp_cut(frame)
    hi["卡片框"], box = with_shadow(body, SIZES["卡片框"])
    hi["已售罄卡片框"], _ = with_shadow(grey_button(body), SIZES["已售罄卡片框"])
    hi["置灰遮罩"] = mask_of(hi["卡片框"], box)
    hi["弹窗卡片"], _ = with_shadow(crisp_cut(popup), SIZES["弹窗卡片"])
    # 角标:整卡实例(353×452 内容范围,角标在 (0,0) 124×77)按 S18 角标 alpha 抠
    inst = bbox_crop(key_green(Image.open(card)))
    s = inst.width / 353
    tag = inst.crop((0, 0, round(124 * s), round(77 * s)))
    shape = Image.open(os.path.join(S18, "角标_raw.png")).convert("RGBA").getchannel("A").resize(tag.size, Image.LANCZOS)
    tag.putalpha(shape)
    hi["折扣角标"] = tag
    for name, im in hi.items():
        w, h = SIZES[name]
        im.resize((w, h), Image.LANCZOS).save(os.path.join(out, name + ".png"))
        im.resize((w * 2, h * 2), Image.LANCZOS).save(os.path.join(out, name + "@2x.png"))
    sc_row = Image.new("RGBA", (280, 28))
    for x in range(280):
        for y in range(28):
            sc_row.putpixel((x, y), (183, 176, 233, int(255 * (1 - (x / 280) ** 2))))
    for name, im in (("信息行底", recolor(sc_row, sc["hue"])),
                     ("解锁条底", recolor(Image.open(os.path.join(S18, "解锁_raw1.png")), sc["hue"], sc["dark"]))):
        im.save(os.path.join(out, name + ".png"))
        im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(os.path.join(out, name + "@2x.png"))
    # Figma 里信息行底是渐变矩形:打印 S18 渐变 / 「限购」文字色换色后的值
    for nm, c in (("渐变起", (183, 176, 233)), ("渐变中", (213, 184, 239)), ("渐变尾", (255, 232, 232)), ("限购字", (111, 87, 216))):
        print(nm, recolor(Image.new("RGBA", (1, 1), c + (255,)), sc["hue"]).getpixel((0, 0))[:3])
    if bg:
        page = ImageOps.fit(Image.open(bg).convert("RGBA"), (W, H), Image.LANCZOS)
        page.convert("RGB").save(os.path.join(out, "背景.png"))
        layer = place_char(page, CHAR_H, CHAR_CX, CHAR_FOOT)
        bb = layer.getchannel("A").getbbox()
        layer.crop(bb).save(os.path.join(out, "立绘.png"))
        print("立绘", bb)
    print(out)


if __name__ == "__main__":
    main(*sys.argv[1:7])
