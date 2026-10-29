"""扭蛋背景验收:叠 UI 遮罩出预览图 + 量各区明暗 / 杂乱度 / 配色比例。

用法:
  python dev/gacha_bg/gacha_check.py 背景图 [--ref 模板背景] [--out 目录]

  不给 --ref 时用 docs/扭蛋背景规范_参考/圣羽降临_干净背景.png 当基准。
  输出 <out>/<名字>_遮罩.png(UI 区半透明盖上 + 标注)和 <名字>_报告.md,终端只打印报告。
  ✗ = 必须改;! = 建议看一眼。
"""
import argparse, json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAYOUT = json.load(open(os.path.join(os.path.dirname(__file__), "layout.json"), encoding="utf-8"))
DEFAULT_REF = os.path.join(ROOT, "docs", "扭蛋背景规范_参考", "圣羽降临_干净背景.png")
W, H = LAYOUT["canvas"]
T = LAYOUT["targets"]
COLORS = {"ui": (40, 40, 40), "title": (255, 200, 0), "focus": (255, 60, 60),
          "reward": (60, 160, 255), "button": (60, 220, 120)}


def load(path):
    im = Image.open(path).convert("RGB")
    if im.size != (W, H):
        print(f"! 尺寸 {im.size[0]}×{im.size[1]},不是 {W}×{H},已等比铺满并居中裁切后再量")
        k = max(W / im.size[0], H / im.size[1])
        im = im.resize((round(im.size[0] * k), round(im.size[1] * k)), Image.LANCZOS)
        x, y = (im.size[0] - W) // 2, (im.size[1] - H) // 2
        im = im.crop((x, y, x + W, y + H))
    return im


def box(r):
    x, y, w, h = r
    return (x, y, x + w, y + h)


def zone_stats(im, r):
    """平均明度(0-100)和杂乱度(高频细节的平均强度,越大越花)。"""
    crop = im.crop(box(r)).convert("L")
    lum = ImageStat.Stat(crop).mean[0] / 2.55
    edges = crop.filter(ImageFilter.FIND_EDGES)
    busy = ImageStat.Stat(edges).mean[0]
    return lum, busy


def palette(im):
    """全图按明度分暗 / 中 / 亮三段,按饱和度和色相分主色 / 对比色占比。"""
    small = im.resize((244, 113)).convert("HSV")
    px = list(small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata())
    n = len(px)
    dark = sum(1 for h, s, v in px if v < 100) / n
    light = sum(1 for h, s, v in px if v > 200) / n
    sat = [(h, s, v) for h, s, v in px if s > 70 and v > 60]
    hist = [0] * 12
    for h, s, v in sat:
        hist[h * 12 // 256] += 1
    main = max(range(12), key=lambda i: hist[i])
    near = {main, (main - 1) % 12, (main + 1) % 12}
    main_share = sum(hist[i] for i in near) / n
    accent_share = sum(hist[i] for i in range(12) if i not in near) / n
    return {"dark": dark, "mid": 1 - dark - light, "light": light,
            "main_hue": main * 30, "main": main_share, "accent": accent_share, "sat": len(sat) / n}


def overlay(im, out_path):
    ov = im.copy().convert("RGBA")
    layer = Image.new("RGBA", ov.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    try:
        font = ImageFont.truetype("msyh.ttc", 26)
    except OSError:
        font = ImageFont.load_default()
    for z in LAYOUT["zones"]:
        c = COLORS[z["kind"]]
        alpha = 150 if z["kind"] == "ui" else 70
        d.rectangle(box(z["rect"]), fill=c + (alpha,), outline=c + (255,), width=3)
        d.text((z["rect"][0] + 6, z["rect"][1] + 4), z["name"], fill=(255, 255, 255, 255), font=font)
    s = LAYOUT["structure"]
    d.line([(0, s["horizon_y"]), (W, s["horizon_y"])], fill=(255, 255, 255, 160), width=2)
    ex, ey, ew, eh = s["stage_ellipse"]
    d.ellipse((ex, ey, ex + ew, ey + eh), outline=(255, 255, 255, 160), width=3)
    for k in ("frame_left", "frame_right", "character_slot"):
        d.rectangle(box(s[k]), outline=(255, 120, 255, 220), width=4)
    Image.alpha_composite(ov, layer).convert("RGB").save(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--ref", default=DEFAULT_REF)
    ap.add_argument("--out", default=os.path.join(ROOT, "exports", "gacha_bg"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    name = os.path.splitext(os.path.basename(a.image))[0]
    im, ref = load(a.image), load(a.ref)

    lines = [f"# 扭蛋背景验收:{name}", "", "| 区域 | 明度 | 基准 | 杂乱度 | 基准 | 结论 |", "|---|---|---|---|---|---|"]
    bad = 0
    for z in LAYOUT["zones"]:
        if z["kind"] not in ("focus", "reward", "button", "title"):
            continue
        lum, busy = zone_stats(im, z["rect"])
        rl, rb = zone_stats(ref, z["rect"])
        verdict = "✓"
        lo, hi = T["focus_lum"]
        if busy > rb * T["busy_ratio_fail"] and busy > 8:
            verdict = "✗ 背后太花,会和 UI / 模型抢"
        elif z["kind"] == "focus" and not lo <= lum <= hi:
            verdict = "✗ 模型背后明度不在 %d–%d,模型会糊进去或背景发脏" % (lo, hi)
        elif busy > rb * T["busy_ratio_warn"]:
            verdict = "! 比模板花"
        if verdict.startswith("✗"):
            bad += 1
        lines.append(f"| {z['name']} | {lum:.0f} | {rl:.0f} | {busy:.1f} | {rb:.1f} | {verdict} |")

    p, rp = palette(im), palette(ref)
    main_of_sat = p["main"] / p["sat"] if p["sat"] else 1
    lines += ["", "| 配色 | 本图 | 模板 | 目标 |", "|---|---|---|---|",
              f"| 亮部(V>200) | {p['light']:.0%} | {rp['light']:.0%} | ≥{T['light_min']:.0%} |",
              f"| 中间调 | {p['mid']:.0%} | {rp['mid']:.0%} | — |",
              f"| 暗部(V<100) | {p['dark']:.0%} | {rp['dark']:.0%} | ≤{T['dark_max']:.0%}(只做框景道具里的小块压重) |",
              f"| 饱和色总量 | {p['sat']:.0%} | {rp['sat']:.0%} | ≤{T['sat_max']:.0%} |",
              f"| 主色相 ±30° | {p['main']:.0%}(色相 {p['main_hue']}°) | {rp['main']:.0%}(色相 {rp['main_hue']}°) | 占饱和色 ≥{T['main_hue_share_of_sat_min']:.0%} |",
              f"| 对比色 | {p['accent']:.0%} | {rp['accent']:.0%} | {T['accent_min']:.0%}–{T['accent_max']:.0%} |"]
    checks = [
        (p["light"] < T["light_min"], "✗", "亮部不够:整体要像模板一样是高调浅色,UI 和模型才读得清"),
        (p["dark"] > T["dark_max"], "✗", "暗部太多:深色只留给框景道具里的小块结构"),
        (p["sat"] > T["sat_max"], "✗", "饱和色太多:画面会被一个颜色淹没(初版的问题),主色只上在道具、灯带、舞台边"),
        (main_of_sat < T["main_hue_share_of_sat_min"], "!", "饱和色不集中在主色相,看起来杂"),
        (p["accent"] < T["accent_min"], "!", "几乎只有一个色相:按风格卡加少量对比色(灯光、点缀)"),
        (p["accent"] > T["accent_max"], "!", "对比色过多,主色不够统一"),
    ]
    for hit, mark, msg in checks:
        if hit:
            lines.append(f"- {mark} {msg}")
            bad += mark == "✗"

    ov_path = os.path.join(a.out, f"{name}_遮罩.png")
    overlay(im, ov_path)
    lines += ["", f"遮罩预览:{ov_path}", "", "✗ 共 %d 项" % bad if bad else "全部通过(仍需人看遮罩预览确认构图)"]
    report = "\n".join(lines)
    open(os.path.join(a.out, f"{name}_报告.md"), "w", encoding="utf-8").write(report)
    print(report)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
