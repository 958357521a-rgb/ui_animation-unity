"""定稿后切配套件(1x + @2x,透明底,不带文字),尺寸照 docs/赛季礼包规范.md 第 2 节。
用法: python parts.py <方案字母> <选定的整卡.png> <无角标卡片框.png> <弹窗卡片.png> <输出目录>
- 整卡 = card_jobs 出的卡片(绿底,带角标);角标从这里按 S18 角标外形抠出来
- 无角标卡片框 / 弹窗卡片 = AI 在整卡上去掉角标 / 去掉价格按钮的版本(绿底)
- 已售罄卡片框:价格按钮换灰;置灰遮罩:卡片框外形的深灰剪影;信息行 / 解锁条:S18 原件换色(同 compose.py)
"""
import sys, os
from PIL import Image, ImageOps
from compose import key_green, bbox_crop, info_row, unlock_bar, SCHEME, S18

SIZES = {"卡片框": (345, 444), "折扣角标": (124, 77), "置灰遮罩": (341, 440), "已售罄卡片框": (345, 444), "弹窗卡片": (329, 424),
         "信息行": (280, 28), "解锁条": (337, 59)}


def grey_button(frame):
    """价格按钮(卡片框下部的高饱和区)去色压暗,其余不动。"""
    out = frame.copy(); px = out.load()
    y0 = int(frame.height * 0.78)
    for y in range(y0, frame.height):
        for x in range(frame.width):
            r, g, b, a = px[x, y]
            if a and max(r, g, b) - min(r, g, b) > 50:
                v = int((0.299 * r + 0.587 * g + 0.114 * b) * 0.8)
                px[x, y] = (v, v, v + 6, a)
    return out


def mask_of(frame):
    a = frame.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    m = Image.new("RGBA", frame.size, (34, 30, 38, 0)); m.putalpha(a.point(lambda v: v * 150 // 255))
    return m


def main(scheme, card, frame, popup, out):
    sc = SCHEME[scheme]; os.makedirs(out, exist_ok=True)
    hi = {}  # 2x 源
    fr = bbox_crop(key_green(Image.open(frame)))
    hi["卡片框"] = fr
    hi["已售罄卡片框"] = grey_button(fr)
    hi["置灰遮罩"] = mask_of(fr)
    hi["弹窗卡片"] = bbox_crop(key_green(Image.open(popup)))
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
    for name, im in (("信息行", info_row(sc, False)), ("解锁条", unlock_bar(sc, False))):
        im.save(os.path.join(out, name + ".png"))
        im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(os.path.join(out, name + "@2x.png"))
    print(out)


if __name__ == "__main__":
    main(*sys.argv[1:6])
