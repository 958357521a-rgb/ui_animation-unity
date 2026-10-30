"""主页皮肤 / 装扮切图交付前自动验收。

用法:
  python dev/lite/skin_check.py <切图文件夹> [--ref <完成稿文件夹>] [--color-ref 配色参考图] [--layout 板序]
  python dev/lite/skin_check.py --measure <完成稿文件夹>      只量完成稿,打印各区指标(定阈值用)

切图文件夹 = 01_主页背景 / 02_个人信息底板 / … 这种分区,每区有 1x/2x × 原位/紧边 PNG + 图层坐标与动效.json + 1x/2x_A级静态.png。
--ref 默认是异星俱乐部 V8 完成稿(用户给的交付标准)。清晰度、边缘、投影这些和完成稿同一分区的数值比;
配色只和 --color-ref(风格卡参考图)比,因为每套皮肤主题色不同。
输出:终端摘要 + 切图文件夹下 _验收报告.md、_验收合成.jpg(背景 + 底板按位置规范摆好 + 导航,用来人眼看)。
有「不合格」时返回码 1。阈值的来历见 docs/主页皮肤验收清单.md。
"""
import os, sys, json, glob, argparse
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

REF_DEFAULT = r'E:\主页皮肤\output\S18_异星俱乐部_动效与切图_V8\动效切图交付\主页皮肤切图规则'
# 分区尺寸(docs/主页皮肤组成规范.md;装扮按 xisi 输出尺寸,切图画布可以比输出大,只查游戏图标)
SIZES = {'主页背景': (2436, 1125), '个人信息底板': (902, 864), '窄底板': (347, 862), '中底板': (686, 864),
         '宽底板': (1260, 862), '连续底部导航': (2436, 108)}
ICON_SIZES = {'头像框': (256, 256), '名字底': (447, 130), '气泡框': (195, 133), '称号': (304, 72)}
BOARDS = ('个人信息底板', '窄底板', '中底板', '宽底板')
LAYOUT_X0, LAYOUT_Y, GAP, NAV_Y = 880, 78, 50, 1017   # 第一张底板看得见的左边缘 / 上沿 / 间距 / 导航 y
DECO_ROLES = ('ornament', 'deco')
MOTION_OK = ('static', 'swing', 'float', 'drift')
SCRAP_WARN, SCRAP_FAIL = 0.015, 0.05      # 部件和底框同色同位的占比(10-30 虚拟歌姬:v2 飘带 31.5% / 格子旗 6.9% ✗;v3 独立件 ≤5%,粉星压粉框会到 2~5%)
RAGGED_WARN, RAGGED_FAIL = 0.12, 0.25     # 部件轮廓细刺 / 毛边(v2 挂带 0.39 ✗;v3 全部 <0.12)


def load(p):
    return np.asarray(Image.open(p).convert('RGBA')).astype(np.float32) / 255


def kind_of(name):
    for k in list(SIZES) + list(ICON_SIZES):
        if k in name: return k
    return None


def lum(a): return a[..., :3] @ np.array([.299, .587, .114], np.float32)


def hsv(a):
    rgb = a[..., :3]; mx = rgb.max(-1); mn = rgb.min(-1)
    s = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
    return mx, s


# ---------- 单图指标 ----------
def sharpness(a):
    """不透明区域的细节量:亮度减去高斯模糊后的平均绝对差(×1000)。糊图 / 放大图明显偏低。"""
    L = lum(a); m = a[..., 3] > 0.95
    m = ndimage.binary_erosion(m, iterations=3)
    if m.sum() < 500: return None
    B = ndimage.gaussian_filter(L, 1.5)
    return float(np.abs(L - B)[m].mean() * 1000)


def edge_softness(a):
    """半透明过渡像素数 / 轮廓长度 ≈ 边缘过渡宽度(px)。硬切 ≈0.5 以下,正常抗锯齿 1 左右,糊边 >2。"""
    al = a[..., 3]; solid = al > 0.5
    rim = solid & ~ndimage.binary_erosion(solid, border_value=1)   # 画布边不算轮廓
    n = rim.sum()
    if n < 50: return None
    near = ndimage.binary_dilation(solid, iterations=4)            # 只看贴着轮廓的,投影不算
    semi = (al > 0.04) & (al < 0.96) & near & (lum(a) > 0.3)
    return float(semi.sum() / n)


def straight_cuts(a, minlen=12):
    """水平 / 竖直方向一步从 >0.6 掉到 <0.05 的连续硬边,长度 ≥minlen 的条数(不算画布边)。部件被框硬切的特征。"""
    al = a[..., 3]; H, W = al.shape; runs = []
    for axis in (0, 1):
        A = al if axis == 0 else al.T
        hi, lo = A[:-1] > 0.6, A[1:] < 0.05          # 往下 / 往右掉
        hi2, lo2 = A[1:] > 0.6, A[:-1] < 0.05        # 往上 / 往左掉
        # 缩小出来的切边有 1 像素过渡,隔一格掉下去也算(10-30 v2 的飘带直切口一步判不出)
        s1, s2 = (A[:-2] > 0.6) & (A[2:] < 0.05), (A[2:] > 0.6) & (A[:-2] < 0.05)
        s1 = np.vstack([s1, np.zeros_like(s1[:1])]) & ~(hi & lo); s2 = np.vstack([s2, np.zeros_like(s2[:1])]) & ~(hi2 & lo2)
        for M in (hi & lo, hi2 & lo2, s1, s2):
            M = M.copy(); M[:, :1] = False; M[:, -1:] = False
            lab, n = ndimage.label(M, structure=[[0, 0, 0], [1, 1, 1], [0, 0, 0]])
            if not n: continue
            ln = ndimage.sum_labels(M, lab, range(1, n + 1))
            runs += [int(x) for x in ln if x >= minlen]
    return len(runs), (max(runs) if runs else 0)


def frame_scrap(part, base):
    """部件带走底框碎片(10-30 用户:音响带着框条、星星下面挂着框描边):部件实心处和底框同位置颜色几乎一样、
    连成 ≥30px(2x)的块 —— 那是从效果图里连底框一起抠下来的。返回占部件面积比例。"""
    m = (part[..., 3] > 0.9) & (base[..., 3] > 0.9) & (np.abs(part[..., :3] - base[..., :3]).max(-1) < 0.07)
    m = ndimage.binary_opening(m)
    lab, n = ndimage.label(m)
    if n: m = np.isin(lab, 1 + np.where(ndimage.sum_labels(m, lab, range(1, n + 1)) >= 30)[0])
    return float(m.sum() / max((part[..., 3] > 0.5).sum(), 1))


def ragged(a):
    """边缘发毛:部件轮廓上宽 ≤4px(2x)的细刺 / 毛边像素,占轮廓长度的比例(干净的独立小件描边粗、轮廓顺,接近 0)。"""
    m = a[..., 3] > 0.5
    rim = (m & ~ndimage.binary_erosion(m)).sum()
    if rim < 50: return 0.0
    spur = m & ~ndimage.binary_opening(m, iterations=2)
    return float(spur.sum() / rim)


def fragments(a):
    """独立的小碎块:alpha>0.1 的连通块里,面积 < 最大块 2% 且 < 400px 的个数。"""
    m = a[..., 3] > 0.1
    lab, n = ndimage.label(m)
    if n <= 1: return 0
    ar = ndimage.sum_labels(m, lab, range(1, n + 1))
    big = ar.max()
    return int(((ar < big * 0.02) & (ar < 400) & (ar >= 4)).sum())


def green_spill(a):
    al = a[..., 3]; semi = (al > 0.05) & (al < 0.9)
    if semi.sum() < 50: return 0.0
    g = a[..., 1] - np.maximum(a[..., 0], a[..., 2])
    solid = al >= 0.9   # 本身就是绿色的元素(异星信号光)不算:只看半透明边比实心部分多出来的绿
    base = float((g[solid] > 0.12).mean()) if solid.sum() > 50 else 0.0
    return max(0.0, float((g[semi] > 0.12).mean()) - base)


def shadow(a):
    """底板投影:实体外偏暗像素的 alpha 总和 / 轮廓长度(投影量),和投影伸出去最远多少像素。
    10-26 用户要求所有底板加投影后通过的机甲 R3:投影量 ≈1.9、伸出 ≈33px(画布每边外扩 40 放投影)。"""
    al = a[..., 3]; solid = al > 0.9
    rim = solid & ~ndimage.binary_erosion(solid, border_value=1)
    out = ~solid & (al > 0.01) & (lum(a) < 0.5)
    if rim.sum() < 50 or not out.any(): return 0.0, 0
    dt = ndimage.distance_transform_edt(~solid)
    return float(al[out].sum() / rim.sum()), int(dt[out].max())


def visible_size(a):
    ys, xs = np.where(a[..., 3] > 0.9)
    return (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)) if len(xs) else (0, 0)


def color_stats(a):
    m = a[..., 3] > 0.5
    if m.sum() < 100: return None
    v, s = hsv(a)
    v, s = v[m], s[m]
    return {'V': float(v.mean()), 'S': float(s.mean()), '暗(V<.35)': float((v < .35).mean()), '近白': float(((v > .9) & (s < .1)).mean())}


def composite(layers, W, H):
    out = np.zeros((H, W, 4), np.float32)
    for it in layers:
        im, (x, y) = it[:2]; scr = len(it) > 2 and it[2] == 'screen'
        h, w = im.shape[:2]
        x0, y0 = max(x, 0), max(y, 0); x1, y1 = min(x + w, W), min(y + h, H)
        if x1 <= x0 or y1 <= y0: continue
        src = im[y0 - y:y1 - y, x0 - x:x1 - x]; dst = out[y0:y1, x0:x1]
        sa = src[..., 3:]; da = dst[..., 3:]
        if scr:   # 滤色动效层只提亮,不改 alpha
            out[y0:y1, x0:x1, :3] = 1 - (1 - dst[..., :3]) * (1 - src[..., :3] * sa); continue
        oa = sa + da * (1 - sa)
        oc = (src[..., :3] * sa + dst[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
        out[y0:y1, x0:x1] = np.dstack([oc, oa])
    return out


SPLIT_MIN = 0.35   # 10-29 量:通过的完成稿 S 级歌姬 0.39 / 中秋 0.45 / 机甲 0.48 / 异星 0.84;被指割裂的 A 级录音棚小样 0.29


def split_ratio(a):
    """背景左右是否割裂:导航以上,右侧底板区(x≥1100)和左侧主题区(x<880)的局部细节(亮度梯度均值)之比。
    连续场景的右侧只是更静,比值不会太低;右侧是平涂空板时接近 0。"""
    L = lum(a[:1017])
    g = np.abs(np.diff(L, axis=1))[:-1] + np.abs(np.diff(L, axis=0))[:, :-1]
    left, right = g[:, :880].mean(), g[:, 1100:].mean()
    return float(right / max(left, 1e-6))


def split_file(p):
    a = load(p)
    if a.shape[1] != 2436: a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((2436, 1125)), np.float32) / 255
    return split_ratio(a)


# ---------- 一个分区 ----------
def measure_section(d):
    r = {'name': os.path.basename(d), 'kind': kind_of(os.path.basename(d)), 'fail': [], 'warn': [], 'm': {}}
    jp = os.path.join(d, '图层坐标与动效.json')
    st1, st2 = os.path.join(d, '1x_A级静态.png'), os.path.join(d, '2x_A级静态.png')
    for p in (jp, st1, st2):
        if not os.path.exists(p): r['fail'].append('缺文件 ' + os.path.basename(p))
    for sub in ('1x_原位PNG', '1x_紧边PNG', '2x_原位PNG', '2x_紧边PNG'):
        if not os.path.isdir(os.path.join(d, sub)): r['fail'].append('缺文件夹 ' + sub)
    if r['fail']: return r
    J = json.load(open(jp, encoding='utf-8'))
    W, H = J['width'], J['height']
    S1 = load(st1); S2 = Image.open(st2)
    r['size'] = (W, H)
    if S1.shape[1] != W or S1.shape[0] != H: r['fail'].append(f'1x 静态图 {S1.shape[1]}x{S1.shape[0]} ≠ json {W}x{H}')
    if S2.size != (2 * W, 2 * H): r['fail'].append(f'2x 静态图 {S2.size[0]}x{S2.size[1]} ≠ 1x 的 2 倍')
    k = r['kind']
    if k in BOARDS:   # 底板画布可以外扩放投影,看得见的板子本身要等于规范尺寸
        vw, vh = visible_size(S1); sw, sh = SIZES[k]; r['m']['板子尺寸'] = f'{vw}x{vh}'
        e = max(abs(vw - sw), abs(vh - sh))
        if e > 24: r['fail'].append(f'看得见的底板 {vw}x{vh},规范 {sw}x{sh}')
        elif e > 6: r['warn'].append(f'看得见的底板 {vw}x{vh},规范 {sw}x{sh}(差 {e}px,内容区会对不齐)')
    elif k in SIZES and (W, H) != SIZES[k]: r['fail'].append(f'画布 {W}x{H} ≠ 规范 {SIZES[k][0]}x{SIZES[k][1]}')
    if k in ICON_SIZES:
        ic = glob.glob(os.path.join(d, '游戏图标_*.png'))
        if not ic: r['warn'].append(f'没有游戏图标 {ICON_SIZES[k][0]}x{ICON_SIZES[k][1]}')
        elif Image.open(ic[0]).size != ICON_SIZES[k]: r['fail'].append(f'游戏图标尺寸 {Image.open(ic[0]).size} ≠ {ICON_SIZES[k]}')

    # 图层:1x 一份、2x 一份(json 里先 1x 后 2x,同名)
    L = J['layers']; half = [l for l in L if l.get('scale', 1) == 1] or L[:len(L) // 2]
    two = [l for l in L if l.get('scale', 1) == 2] or L[len(L) // 2:]
    by2 = {l['name']: l for l in two}
    lay1 = []
    for l in half:
        p = os.path.join(d, l['trimmed']) if l.get('trimmed') else None
        if not p or not os.path.exists(p): r['fail'].append('图层文件不存在 ' + str(l.get('trimmed'))); continue
        im = load(p); l2 = by2.get(l['name'])
        if l2 is None: r['fail'].append(f'「{l["name"]}」没有 2x'); continue
        # 2x 紧边尺寸应 ≈ 2×1x(1x 是缩出来的,允许外扩几像素)
        sz2 = Image.open(os.path.join(d, l2['trimmed'].replace('1x_', '2x_'))).size if os.path.exists(os.path.join(d, l2['trimmed'].replace('1x_', '2x_'))) else tuple(l2['size'])
        if abs(sz2[0] - 2 * im.shape[1]) > 16 or abs(sz2[1] - 2 * im.shape[0]) > 16:
            r['warn'].append(f'「{l["name"]}」2x 尺寸 {sz2} 和 1x×2 差太多')
        # 用 2x 坐标 /2 摆(10-27 踩过:1x 紧边外扩会错位)
        im2 = load(os.path.join(d, l2['trimmed'].replace('1x_', '2x_'))) if os.path.exists(os.path.join(d, l2['trimmed'].replace('1x_', '2x_'))) else None
        lay1.append((l, im, l2, im2))
        if l.get('role') in DECO_ROLES:
            n, mx = straight_cuts(im2 if im2 is not None else im, 24 if im2 is not None else 12)
            moving = (l.get('motion') or {}).get('type', 'static') != 'static'   # 不动的层(如称号字)叠在原位,直边看不出来,只提醒
            if n >= 3 and moving: r['fail'].append(f'部件「{l["name"]}」有 {n} 条硬切直边(最长 {mx}px),像被框裁过')
            elif n: r['warn'].append(f'部件「{l["name"]}」有 {n} 条硬切直边(最长 {mx}px),确认是不是本来就是直的')
            fr = fragments(im)
            if fr: r['warn'].append(f'部件「{l["name"]}」带 {fr} 个游离小碎块(别的部件 / 环的残片?)')
        gs = green_spill(im)
        if gs > 0.05: r['fail'].append(f'「{l["name"]}」半透明边 {gs:.0%} 偏绿(抠绿残留)')
        # S 级动效:同一个 4 秒循环,只摆动 / 浮动 / 漂移,没有闪烁、缩放呼吸(homeskin skill「动效」)
        mt = (l.get('motion') or {}).get('type', 'static')
        if mt not in MOTION_OK: r['fail'].append(f'「{l["name"]}」动效 {mt} 不允许(只用 swing 摆动 / float 浮动 / drift 漂移,没有闪烁、缩放呼吸)')
        elif mt != 'static' and (l['motion'].get('loop') or l['motion'].get('duration')) != 4:
            r['fail'].append(f'「{l["name"]}」动效周期 {l["motion"].get("loop") or l["motion"].get("duration")}s,所有物件统一 4 秒循环')

    # 头部 / 主体:2x 坐标判断接缝
    hd = [x for x in lay1 if '头部' in x[0]['name']]; bd = [x for x in lay1 if '主体' in x[0]['name']]
    if hd and bd:
        hb = hd[0][2]['position'][1] + hd[0][2]['size'][1]; bt = bd[0][2]['position'][1]
        ov = (hb - bt) / 2
        r['m']['头身接缝'] = ov
        if ov > 1: r['warn'].append(f'头部下沿压进主体 {ov:.0f}px(2x 坐标/2),确认是有意叠压')
        if ov < -1: r['fail'].append(f'头部和主体之间漏缝 {-ov:.0f}px')

    # 图层按 2x 坐标合成 = 静态图?(拆层后有没有丢东西 / 多残留)
    if lay1 and all(x[3] is not None for x in lay1):
        S2a = np.asarray(S2.convert('RGBA')).astype(np.float32) / 255
        bad = 1.0
        for glow in (False, True):   # 静态图里含不含滤色动效层,两种都试
            ls = [(x[3], tuple(x[2]['position']), x[0].get('blend')) for x in lay1 if glow or x[0].get('blend', 'normal') == 'normal']
            comp = composite(ls, 2 * W, 2 * H)
            dif = np.abs(comp[..., 3] - S2a[..., 3]) + np.abs(comp[..., :3] * comp[..., 3:] - S2a[..., :3] * S2a[..., 3:]).mean(-1)
            bad = min(bad, float((dif > 0.15).mean()))
        r['m']['合成差异'] = bad
        # 2x 是不是只是 1x 放大:缩到 1x 再放回 2x,丢掉的细节越少越像假 2x
        L2 = lum(S2a); msk = S2a[..., 3] > 0.95
        sm = Image.fromarray((L2 * 255).astype(np.uint8)).resize((W, H), Image.BOX).resize((2 * W, 2 * H), Image.BICUBIC)
        if msk.sum() > 1000: r['m']['2x细节'] = float(np.abs(L2 - np.asarray(sm, np.float32) / 255)[msk].mean() * 1000)
        if bad > 0.01: r['fail'].append(f'各图层合起来和 A 级静态图有 {bad:.1%} 像素对不上(拆层丢了东西或多了残留)')
        elif bad > 0.002: r['warn'].append(f'各图层合起来和静态图有 {bad:.2%} 像素不同')
        # 装扮拆层:叠回 = 效果图(10-30「拆完之后拼回去和效果图不能不一样」),逐像素差 >8/255 的不许有
        ef = os.path.join(d, '2x_效果图.png')
        if os.path.exists(ef):
            Ea = np.asarray(Image.open(ef).convert('RGBA')).astype(np.float32) / 255
            comp = composite([(x[3], tuple(x[2]['position']), x[0].get('blend')) for x in lay1], 2 * W, 2 * H)
            dif = np.abs(np.dstack([comp[..., :3] * comp[..., 3:], comp[..., 3:]]) - np.dstack([Ea[..., :3] * Ea[..., 3:], Ea[..., 3:]])).max(-1)
            nb = int((dif > 8 / 255).sum()); r['m']['叠回效果图最大差'] = float(dif.max() * 255)
            if nb > 20: r['fail'].append(f'各图层叠回和 2x 效果图有 {nb} 像素差 >8/255(最大 {dif.max() * 255:.0f}/255),拆完拼不回效果图')
            elif nb: r['warn'].append(f'各图层叠回和 2x 效果图有 {nb} 像素差 >8/255')
            # 动起来露洞(10-30「不能出现崩坏」):部件摆 / 浮到最大处,原来被它盖住的地方如果是底框围住的透明洞就露馅
            As = [composite([(x[3], tuple(x[2]['position']), x[0].get('blend'))], 2 * W, 2 * H)[..., 3] for x in lay1]
            for k, x in enumerate(lay1):
                mo = x[0].get('motion') or {}
                if mo.get('type', 'static') == 'static': continue
                O = np.maximum.reduce([a for i, a in enumerate(As) if i != k]) > 0.5
                enc = ndimage.binary_fill_holes(ndimage.binary_closing(O, iterations=6)) & ~O
                lab, n = ndimage.label(enc); sz = ndimage.sum(enc, lab, range(1, n + 1))
                enc = np.isin(lab, 1 + np.where(sz < enc.size * 0.01)[0])   # 大洞本来就空(头像框中间的头像位)
                worst = 0
                for s in (1, -0.15):   # 最大处和前摇
                    if mo['type'] == 'swing' and mo.get('pivot'):
                        mv = np.asarray(Image.fromarray(As[k]).rotate(mo.get('angle', 0) * s, resample=Image.BILINEAR, center=tuple(v * 2 for v in mo['pivot'])))
                    elif mo.get('offset'):
                        dx, dy = [int(round(v * 2 * s)) for v in mo['offset']]; mv = np.roll(np.roll(As[k], dy, 0), dx, 1)
                    else: continue
                    worst = max(worst, int(((As[k] > 0.9) & (mv < 0.5) & enc).sum()))
                if worst > 100: r['fail'].append(f'部件「{x[0]["name"]}」动到最大处露出底下 {worst} 像素透明洞(2x),底框没补全')
                elif worst > 20: r['warn'].append(f'部件「{x[0]["name"]}」动到最大处露出 {worst} 像素透明洞(2x)')
            # 部件要是干净独立的小件(10-30 用户:像 S17 中秋那样,不带底框碎片、边缘不发毛,动起来才不穿帮)
            bi = [i for i, x in enumerate(lay1) if x[0].get('role') == 'base']
            if bi:
                Bc = composite([(lay1[bi[0]][3], tuple(lay1[bi[0]][2]['position']), 'normal')], 2 * W, 2 * H)
                for x in lay1:
                    if (x[0].get('motion') or {}).get('type', 'static') == 'static': continue
                    Pc = composite([(x[3], tuple(x[2]['position']), 'normal')], 2 * W, 2 * H)
                    sc, rg = frame_scrap(Pc, Bc), ragged(x[3])
                    r['m'].setdefault('部件底框碎片', {})[x[0]['name']] = round(sc, 4)
                    r['m'].setdefault('部件毛边', {})[x[0]['name']] = round(rg, 3)
                    if sc > SCRAP_FAIL: r['fail'].append(f'部件「{x[0]["name"]}」有 {sc:.1%} 是和底框一模一样的像素(带走了底框碎片),动起来会穿帮')
                    elif sc > SCRAP_WARN: r['warn'].append(f'部件「{x[0]["name"]}」有 {sc:.1%} 和底框同色同位,确认不是底框碎片')
                    if rg > RAGGED_FAIL: r['fail'].append(f'部件「{x[0]["name"]}」轮廓毛边 / 细刺 {rg:.2f}(干净独立件 ≤{RAGGED_WARN}),像从整图里硬抠')
                    elif rg > RAGGED_WARN: r['warn'].append(f'部件「{x[0]["name"]}」轮廓毛边 / 细刺 {rg:.2f},确认边缘干净')

    # 静态图整体指标
    r['m']['清晰度'] = sharpness(S1)
    r['m']['边缘过渡'] = edge_softness(S1) if S1[..., 3].min() < 0.5 else None
    if k in BOARDS:
        amt, reach = shadow(S1); r['m']['投影量'] = amt; r['m']['投影伸出'] = reach
        if amt < 0.8 or reach < 15:
            r['fail'].append(f'底板投影太弱:投影量 {amt:.1f}、伸出 {reach}px(机甲 R3 通过版 ≈1.9 / 33px;10-26「所有信息底板都得加上投影」)')
    if k == '主页背景':
        lr = split_ratio(S1); r['m']['右左细节比'] = lr
        if lr < SPLIT_MIN:
            r['warn'].append(f'右侧(底板区)细节只有左侧的 {lr:.0%},可能左右割裂、右边是平涂空板(10-29:背景要整屏连续)')
    r['m']['配色'] = color_stats(S1)
    r['static'] = S1
    return r


def sections(root):
    return sorted(d for d in glob.glob(os.path.join(root, '*')) if os.path.isdir(d) and os.path.exists(os.path.join(d, '图层坐标与动效.json')))


def compare(r, ref):
    """和完成稿同类分区比。"""
    if not ref: return
    m, q = r['m'], ref['m']
    if m.get('清晰度') and q.get('清晰度'):
        # 清晰度和画面内容有关(平涂多的本来就低),两项都低于完成稿一半才算不合格
        k = m['清晰度'] / q['清晰度']; k2 = (m.get('2x细节') or 0) / (q.get('2x细节') or 1)
        if k < 0.5 and k2 < 0.6: r['fail'].append(f'清晰度只有完成稿的 {k:.0%}、2x 细节 {k2:.0%}(糊 / 2x 是放大出来的)')
        elif k < 0.6 or k2 < 0.6: r['warn'].append(f'清晰度是完成稿的 {k:.0%}、2x 细节 {k2:.0%},看一眼是不是偏糊')
    if m.get('边缘过渡') is not None and q.get('边缘过渡') is not None:
        if m['边缘过渡'] > max(2.0, q['边缘过渡'] * 2): r['warn'].append(f'外轮廓过渡 {m["边缘过渡"]:.1f}px,完成稿 {q["边缘过渡"]:.1f}px(边发虚)')
        if m['边缘过渡'] < 0.3: r['warn'].append(f'外轮廓几乎没有抗锯齿({m["边缘过渡"]:.2f}),边会有锯齿')


def color_check(rs, ref_img, out):
    if not ref_img: return
    a = load(ref_img); a[..., 3] = 1; c = color_stats(a)
    out.append(f'\n## 配色(对照 {os.path.basename(ref_img)}:V {c["V"]:.2f} / S {c["S"]:.2f} / 暗 {c["暗(V<.35)"]:.0%} / 近白 {c["近白"]:.0%})')
    for r in rs:
        m = r['m'].get('配色')
        if not m: continue
        dv, ds = m['V'] - c['V'], m['S'] - c['S']
        tag = '不合格' if abs(dv) > 0.12 or abs(ds) > 0.12 else ('注意' if abs(dv) > 0.06 or abs(ds) > 0.06 else '合格')
        out.append(f'- {r["name"]}:V {m["V"]:.2f}({dv:+.2f}) S {m["S"]:.2f}({ds:+.2f}) 暗 {m["暗(V<.35)"]:.0%} 近白 {m["近白"]:.0%} → {tag}')
        if tag == '不合格': r['fail'].append(f'明度 / 饱和度和配色参考差 {dv:+.2f} / {ds:+.2f}')
        elif tag == '注意': r['warn'].append(f'明度 / 饱和度和配色参考差 {dv:+.2f} / {ds:+.2f}')


def screen(rs, path, order):
    """背景 + 底板(第一张看得见的左边缘 880、上沿 78、间距 50)+ 导航,出 1x 合成图给人看;底板压到哪些装饰在这张图上一眼能看出来。"""
    by = {r['kind']: r for r in rs if 'static' in r}
    if '主页背景' not in by: return None
    out = by['主页背景']['static'].copy(); out[..., 3] = 1
    x = None; items = []
    for k in order:
        if k not in by: continue
        im = by[k]['static']; cols = np.where(by[k]['static'][..., 3].max(0) > 0.5)[0]
        vis0 = int(cols[0]) if len(cols) else 0; vis1 = int(cols[-1]) if len(cols) else im.shape[1]
        rows = np.where(im[..., 3].max(1) > 0.5)[0]; top = int(rows[0]) if len(rows) else 0
        px = (LAYOUT_X0 if x is None else x) - vis0
        items.append((im, (px, LAYOUT_Y - top))); x = px + vis1 + 1 + GAP
    if '连续底部导航' in by: items.append((by['连续底部导航']['static'], (0, NAV_Y)))
    c = composite([(out, (0, 0))] + items, out.shape[1], out.shape[0])
    Image.fromarray((c[..., :3] * 255 + .5).astype(np.uint8)).save(path, quality=88)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder', nargs='?'); ap.add_argument('--ref', default=REF_DEFAULT)
    ap.add_argument('--color-ref'); ap.add_argument('--measure')
    ap.add_argument('--layout', default='个人信息底板,窄底板,中底板,宽底板')
    a = ap.parse_args()
    if a.measure:
        for d in sections(a.measure):
            r = measure_section(d)
            print(r['name'], r.get('size'), {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r['m'].items() if k != '配色'},
                  {k: round(v, 2) for k, v in (r['m'].get('配色') or {}).items()}, r['fail'] + r['warn'])
        return 0
    refs = {}
    if a.ref and os.path.isdir(a.ref):
        for d in sections(a.ref):
            rr = measure_section(d); refs[rr['kind']] = rr
    rs = [measure_section(d) for d in sections(a.folder)]
    for r in rs: compare(r, refs.get(r['kind']))
    out = [f'# 验收报告 · {a.folder}', f'对照完成稿:{a.ref}', '']
    color_check(rs, a.color_ref, out)
    sp = screen(rs, os.path.join(a.folder, '_验收合成.jpg'), a.layout.split(','))
    out.insert(2, '合成图:' + (sp or '(没有主页背景分区,不出)') + '  ← 必须人眼看:装饰有没有被底板盖住、底板位置、整体配色')
    nf = 0
    for r in rs:
        ref = refs.get(r['kind']); m = r['m']
        tag = '不合格' if r['fail'] else ('注意' if r['warn'] else '合格'); nf += bool(r['fail'])
        def f(k):
            v, q = m.get(k), (ref or {'m': {}})['m'].get(k)
            if v is None: return None
            return f'{k} {v:.2f}' + (f'(完成稿 {q:.2f})' if isinstance(q, float) else '') if isinstance(v, float) else f'{k} {v}'
        nums = ' · '.join(x for x in map(f, ('板子尺寸', '清晰度', '2x细节', '边缘过渡', '投影量', '投影伸出', '合成差异', '叠回效果图最大差', '头身接缝')) if x)
        out.append(f'\n## {r["name"]} — {tag}\n{nums}')
        out += ['- ✗ ' + x for x in r['fail']] + ['- △ ' + x for x in r['warn']]
    txt = '\n'.join(out)
    open(os.path.join(a.folder, '_验收报告.md'), 'w', encoding='utf-8').write(txt)
    print(txt)
    return 1 if nf else 0


if __name__ == '__main__':
    sys.exit(main())
