"""卡片框出图任务:卡片结构照 S18 原件,AI 只换配色纹样。S18 卡片框 + 角标拼到绿底上当结构底图。
在仓库根目录跑;每期改 D(输出目录)、SHEET(本期角色参考)、base 末尾的主题句和 S 里各方案配色。
生成的 <D>card_jobs.json 交给 gemini-batch-image 批量出图。
"""
import json
from PIL import Image
D = "exports/nano/s18_vsinger_gift/"
L = "dev/season_gift/s18/"
SHEET = "docs/风格卡/S18虚拟歌姬礼包_参考/原画设计稿.jpg"

# 实例 361×460:卡片框 @(8,8)、角标 @(0,0);放大 3 倍放进 3:4 绿底
inst = Image.new("RGBA", (361, 460))
inst.alpha_composite(Image.open(L + "卡片框_raw.png").convert("RGBA").crop((0, 0, 345, 444)), (8, 8))
inst.alpha_composite(Image.open(L + "角标_raw.png").convert("RGBA"), (0, 0))
inst = inst.resize((361 * 3, 460 * 3), Image.LANCZOS)
cv = Image.new("RGBA", (1200, 1600), (0, 255, 0, 255))
cv.alpha_composite(inst, ((1200 - inst.width) // 2, (1600 - inst.height) // 2))
cv.convert("RGB").save(L + "结构底图.png")

base = ("Image 1 is an existing mobile game gift-pack card UI on a pure #00FF00 green background. Redraw THIS EXACT card with a new color scheme and theme motifs. "
 "STRICT: keep the identical outline, size and position of every part — the title bar across the top, the wing ornament position at top-right, the light rectangular icon area in the middle (keep it empty, plain light), "
 "the big empty light body below it, the price button shape and position at the bottom, the small sparkle ornament at the price button's left end, and the oval discount tag overhanging the top-left corner. "
 "Do not move, resize, add or remove parts; only change colors, materials and small decorative motifs (the top-right wing becomes the theme ornament of the same size). "
 "Keep the solid #00FF00 green background around it, same framing. NO text, numbers or letters anywhere. Clean crisp game UI rendering. "
 "Theme (see image 2): sweet-cool chibi virtual idol, pink twin tails, matte black mecha trim with pink neon lines, headphones with pointed horn tips, stars, hearts. ")
S = {
 "A": "Colors: title bar and frame edge matte black #2A2328 with a glowing pink neon line, body near-white with a faint pink tint, icon area pale pink-white; top-right ornament = a small headphone-horn disc with a star; price button magenta #FF3D9A to pink gradient with white gloss; discount tag black with magenta neon rim.",
 "B": "Colors: title bar and frame edge black mecha panel with glowing hot pink #FF3D9A neon edges, body soft light pink, icon area pale pink; top-right ornament = a glowing pink neon star with a horn; price button bright glowing pink with white highlight; discount tag hot pink with black inner rim.",
 "C": "Colors: title bar and frame edge glossy translucent pink PVC with a white glowing rim and holographic sheen, body white with pink-lavender iridescence, icon area pale lavender-white; top-right ornament = a pink holographic star crest; price button pink to coral glossy jelly; discount tag pink star-burst holographic.",
 "D": "Colors: title bar black with tiny devil horns and a heart, frame edge black-and-pink checkerboard trim, body white, icon area pale pink; top-right ornament = a small black heart with devil wing; price button hot pink glossy with white highlight; discount tag black heart-ish oval with pink edge.",
}
jobs = [{"key": f"{k}_card{i}", "prompt": base + v, "refs": [L + "结构底图.png", SHEET], "aspect": "3:4"} for k, v in S.items() for i in (1, 2)]
json.dump(jobs, open(D + "card_jobs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(jobs))
