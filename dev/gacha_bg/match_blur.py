"""AI 细化后背景墙的虚化(景深)没了时，照原图补回来:原图里清楚的区域(物件、舞台)保持，虚的区域(背景墙、光束)重新虚化。
python dev/gacha_bg/match_blur.py --src 原图(用户调过的版本).png --img 细化版_2436.png --out 输出.png [--sigma 4.5] [--thr 3]
两张图须构图一致(细化版先按原比例压回去，见 SKILL.md);另存一张 _虚化遮罩.png(白 = 会被虚化)方便检查。
"""
import argparse, os
import numpy as np
from PIL import Image
from scipy import ndimage


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True); p.add_argument("--img", required=True); p.add_argument("--out", required=True)
    p.add_argument("--sigma", type=float, default=4.5); p.add_argument("--thr", type=float, default=3.0)
    a = p.parse_args()
    im = Image.open(a.img).convert("RGB"); W, H = im.size
    o = np.asarray(Image.open(a.src).convert("L").resize((W, H), Image.LANCZOS), float)
    # 原图里细节多的地方 = 清楚的物件;闭合、填洞后去掉小碎块
    sharp = ndimage.uniform_filter(np.abs(o - ndimage.gaussian_filter(o, 3)), 9) > a.thr
    sharp = ndimage.binary_fill_holes(ndimage.binary_closing(ndimage.binary_opening(sharp, iterations=2), iterations=10))
    lab, n = ndimage.label(sharp)
    keep = np.isin(lab, 1 + np.where(ndimage.sum(sharp, lab, range(1, n + 1)) > 250)[0])
    bg = ndimage.gaussian_filter((~ndimage.binary_dilation(keep, iterations=6)).astype(float), 5)
    Image.fromarray((bg * 255).astype(np.uint8)).save(os.path.join(os.path.dirname(a.out), "_虚化遮罩.png"))
    # 只用背景像素做模糊(归一化),物件颜色不会晕进背景
    x = np.asarray(im, float); w = ndimage.gaussian_filter(bg, a.sigma) + 1e-4
    bl = np.stack([ndimage.gaussian_filter(x[..., c] * bg, a.sigma) / w for c in range(3)], -1)
    out = x * (1 - bg[..., None]) + bl * bg[..., None]
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out); print(a.out)


if __name__ == "__main__":
    main()
