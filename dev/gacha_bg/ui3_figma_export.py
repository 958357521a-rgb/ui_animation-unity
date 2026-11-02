"""扭蛋 UI 件导出 2x 切图给 Figma 用(放进模板画板里替换图层):
按钮只出底板(不带字,字 / 币 / 角标用 Figma 组件里的),画布 1062×342,按钮体 868×220 放在 ui3_compose.PLATE_C 位置;
奖励底 458×464;logo 2x 并打印它在 2436×1125 画面里的 1x 位置。

python dev/gacha_bg/ui3_figma_export.py --out 目录 --logo X.png --once pair:X.png:0 --round pair:X.png:1 --hex X.png
"""
import argparse, os, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ui_compose import ZONES, key_green, drop_ghosts, logo_box, fit, glow
from ui3_compose import BTN, PLATE, PLATE_C, keep_main, split_pair, stretch_mid, erase_badge


def plate2x(spec):
    path, idx = spec[5:].rsplit(":", 1)
    body = erase_badge(stretch_mid(keep_main(split_pair(key_green(Image.open(path)))[int(idx)]), PLATE[0] * 2, PLATE[1] * 2))
    out = Image.new("RGBA", (BTN[0] * 2, BTN[1] * 2))
    out.alpha_composite(body, (PLATE_C[0] * 2 - body.width // 2, PLATE_C[1] * 2 - body.height // 2))
    return out


def main():
    p = argparse.ArgumentParser()
    for k in ("out", "logo", "once", "round", "hex"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args(); os.makedirs(a.out, exist_ok=True)
    lx, ly, lw, lh = logo_box()
    logo = glow(fit(drop_ghosts(key_green(Image.open(a.logo))), (lw - 30) * 2, (lh - 20) * 2))
    w, h = logo.width / 2, logo.height / 2
    print("logo 1x 位置", round(lx + (lw - w) / 2), round(ly + (lh - h) / 2), round(w), round(h))
    hw, hh = ZONES["reward_tl"][2:]
    pieces = {"logo": logo, "hex": fit(drop_ghosts(key_green(Image.open(a.hex))), hw * 2, hh * 2),
              "plate_once": plate2x(a.once), "plate_round": plate2x(a.round)}
    for k, im in pieces.items():
        f = os.path.join(a.out, f"{k}@2x.png"); im.save(f); print(f, im.size)


if __name__ == "__main__":
    main()
