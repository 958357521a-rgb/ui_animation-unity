# 资源批处理 · Unity 资产生成:切图 meta、特效 prefab(Arts 源)、Loadable 壳、动画片段 .anim、Animator 控制器 .controller。
# 格式逐字段对齐主工程现有头像框特效(Unity 2022.3.32f1,参考 Assets/Arts/UI/UIWidgets/UserInfoView/HeadCyclePrefabs/HeadTopEffect_36
# 及其 HeadEffect_36/animation.anim / animation.controller,2026-10-13 提取)。改模板前先去主工程对照同类资产,不要凭记忆改字段。
# GUID / fileID 与工作台(BUD_UI_Studio.html 的 stableGuid / makeFidAlloc)同一套算法:按落点路径 / 节点路径派生,再生成逐字节不变。
import math, os, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
M64 = (1 << 64) - 1
IMAGE_SCRIPT = "{fileID: 11500000, guid: fe87c0e1cc204ed48ad3b37840f39efc, type: 3}"   # UGUI Image
HEADER = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"


def fnv64(s, h=0xcbf29ce484222325):
    for c in s.encode("utf-8"):
        h ^= c
        h = (h * 0x100000001b3) & M64
    return h


def stable_guid(path):
    """与工作台 stableGuid 相同:落点路径小写后派生"""
    key = path.lower()
    return format(fnv64("guid:" + key), "016x") + format(fnv64("guid2:" + key, 0x84222325cbf29ce4), "016x")


def fid(key):
    """与工作台 makeFidAlloc 相同的派生方式(不处理冲突:同一 prefab 内的键各不相同)"""
    return str((fnv64("fid:" + key) & ((1 << 62) - 1)) + 1000000000)


def num(v):
    """Unity 风格的数字:整数不带小数点,其余最多 8 位有效数字"""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.8g" % v).rstrip("0").rstrip(".")


def yaml_str(s):
    """中文 / 特殊字符一律双引号(避免主工程踩过的 \\uXXXX 乱码坑)"""
    if all(c.isalnum() and ord(c) < 128 or c in "_-. " for c in s) and s and s[0] != " ":
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------------- meta ----------------
def sprite_meta(guid, border=(0, 0, 0, 0)):
    t = open(os.path.join(HERE, "templates", "sprite.png.meta"), encoding="utf-8").read()
    return (t.replace("{{GUID}}", guid).replace("{{BL}}", num(border[0])).replace("{{BB}}", num(border[1]))
             .replace("{{BR}}", num(border[2])).replace("{{BT}}", num(border[3])))


def prefab_meta(guid):
    return f"fileFormatVersion: 2\nguid: {guid}\nPrefabImporter:\n  externalObjects: {{}}\n  userData: \n  assetBundleName: \n  assetBundleVariant: \n"


def native_meta(guid, main_fid):
    return (f"fileFormatVersion: 2\nguid: {guid}\nNativeFormatImporter:\n  externalObjects: {{}}\n  mainObjectFileID: {main_fid}\n"
            "  userData: \n  assetBundleName: \n  assetBundleVariant: \n")


def folder_meta(guid):
    return f"fileFormatVersion: 2\nguid: {guid}\nfolderAsset: yes\nDefaultImporter:\n  externalObjects: {{}}\n  userData: \n  assetBundleName: \n  assetBundleVariant: \n"


# ---------------- prefab(特效:根节点 + Animator + 若干 Image 层) ----------------
def effect_prefab(name, layers, controller_guid=None, root_size=(100, 100)):
    """layers: [{name, sprite_guid, x, y, w, h}](x/y = 相对根节点中心的 anchoredPosition,Unity 单位)
    返回 (prefab 文本, 根 GameObject fileID, 根 RectTransform fileID)"""
    go, rt, an = fid(name + "|go"), fid(name + "|rt"), fid(name + "|animator")
    kids = [(fid(f"{name}/{l['name']}|go"), fid(f"{name}/{l['name']}|rt"), fid(f"{name}/{l['name']}|cr"), fid(f"{name}/{l['name']}|img"), l) for l in layers]
    comps = f"  - component: {{fileID: {rt}}}\n" + (f"  - component: {{fileID: {an}}}\n" if controller_guid else "")
    out = [HEADER, f"""--- !u!1 &{go}
GameObject:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  serializedVersion: 6
  m_Component:
{comps}  m_Layer: 5
  m_Name: {yaml_str(name)}
  m_TagString: Untagged
  m_Icon: {{fileID: 0}}
  m_NavMeshLayer: 0
  m_StaticEditorFlags: 0
  m_IsActive: 1
--- !u!224 &{rt}
RectTransform:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: {go}}}
  m_LocalRotation: {{x: 0, y: 0, z: 0, w: 1}}
  m_LocalPosition: {{x: 0, y: 0, z: 0}}
  m_LocalScale: {{x: 1, y: 1, z: 1}}
  m_ConstrainProportionsScale: 0
  m_Children:
""" + "".join(f"  - {{fileID: {k[1]}}}\n" for k in kids) + f"""  m_Father: {{fileID: 0}}
  m_LocalEulerAnglesHint: {{x: 0, y: 0, z: 0}}
  m_AnchorMin: {{x: 0.5, y: 0.5}}
  m_AnchorMax: {{x: 0.5, y: 0.5}}
  m_AnchoredPosition: {{x: 0, y: 0}}
  m_SizeDelta: {{x: {num(root_size[0])}, y: {num(root_size[1])}}}
  m_Pivot: {{x: 0.5, y: 0.5}}
"""]
    if controller_guid:
        out.append(f"""--- !u!95 &{an}
Animator:
  serializedVersion: 5
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: {go}}}
  m_Enabled: 1
  m_Avatar: {{fileID: 0}}
  m_Controller: {{fileID: 9100000, guid: {controller_guid}, type: 2}}
  m_CullingMode: 0
  m_UpdateMode: 0
  m_ApplyRootMotion: 0
  m_LinearVelocityBlending: 0
  m_StabilizeFeet: 0
  m_WarningMessage:
  m_HasTransformHierarchy: 1
  m_AllowConstantClipSamplingOptimization: 1
  m_KeepAnimatorStateOnDisable: 0
  m_WriteDefaultValuesOnDisable: 0
""")
    for kgo, krt, kcr, kimg, l in kids:
        out.append(f"""--- !u!1 &{kgo}
GameObject:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  serializedVersion: 6
  m_Component:
  - component: {{fileID: {krt}}}
  - component: {{fileID: {kcr}}}
  - component: {{fileID: {kimg}}}
  m_Layer: 5
  m_Name: {yaml_str(l['name'])}
  m_TagString: Untagged
  m_Icon: {{fileID: 0}}
  m_NavMeshLayer: 0
  m_StaticEditorFlags: 0
  m_IsActive: 1
--- !u!224 &{krt}
RectTransform:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: {kgo}}}
  m_LocalRotation: {{x: 0, y: 0, z: 0, w: 1}}
  m_LocalPosition: {{x: 0, y: 0, z: 0}}
  m_LocalScale: {{x: 1, y: 1, z: 1}}
  m_ConstrainProportionsScale: 0
  m_Children: []
  m_Father: {{fileID: {rt}}}
  m_LocalEulerAnglesHint: {{x: 0, y: 0, z: 0}}
  m_AnchorMin: {{x: 0.5, y: 0.5}}
  m_AnchorMax: {{x: 0.5, y: 0.5}}
  m_AnchoredPosition: {{x: {num(l['x'])}, y: {num(l['y'])}}}
  m_SizeDelta: {{x: {num(l['w'])}, y: {num(l['h'])}}}
  m_Pivot: {{x: 0.5, y: 0.5}}
--- !u!222 &{kcr}
CanvasRenderer:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: {kgo}}}
  m_CullTransparentMesh: 1
--- !u!114 &{kimg}
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: {kgo}}}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {IMAGE_SCRIPT}
  m_Name:
  m_EditorClassIdentifier:
  m_Material: {{fileID: 0}}
  m_Color: {{r: 1, g: 1, b: 1, a: 1}}
  m_RaycastTarget: 0
  m_RaycastPadding: {{x: 0, y: 0, z: 0, w: 0}}
  m_Maskable: 1
  m_OnCullStateChanged:
    m_PersistentCalls:
      m_Calls: []
  m_Sprite: {{fileID: 21300000, guid: {l['sprite_guid']}, type: 3}}
  m_Type: 0
  m_PreserveAspect: 0
  m_FillCenter: 1
  m_FillMethod: 4
  m_FillAmount: 1
  m_FillClockwise: 1
  m_FillOrigin: 0
  m_UseSpriteMesh: 0
  m_PixelsPerUnitMultiplier: 1
""")
    return "".join(out), go, rt


def shell_prefab(name, source_guid, root_go, root_rt, root_size=(100, 100)):
    """Loadable 壳:直接实例化 Arts 源 prefab(与 HeadTopEffect_36 的壳同样的 21 项修改)"""
    mods = [(root_go, "m_Name", yaml_str(name))] + [(root_rt, p, v) for p, v in (
        ("m_Pivot.x", "0.5"), ("m_Pivot.y", "0.5"), ("m_AnchorMax.x", "0.5"), ("m_AnchorMax.y", "0.5"),
        ("m_AnchorMin.x", "0.5"), ("m_AnchorMin.y", "0.5"), ("m_SizeDelta.x", num(root_size[0])), ("m_SizeDelta.y", num(root_size[1])),
        ("m_LocalPosition.x", "0"), ("m_LocalPosition.y", "0"), ("m_LocalPosition.z", "0"),
        ("m_LocalRotation.w", "1"), ("m_LocalRotation.x", "0"), ("m_LocalRotation.y", "0"), ("m_LocalRotation.z", "0"),
        ("m_AnchoredPosition.x", "0"), ("m_AnchoredPosition.y", "0"),
        ("m_LocalEulerAnglesHint.x", "0"), ("m_LocalEulerAnglesHint.y", "0"), ("m_LocalEulerAnglesHint.z", "0"))]
    body = "".join(f"    - target: {{fileID: {t}, guid: {source_guid}, type: 3}}\n      propertyPath: {p}\n      value: {v}\n      objectReference: {{fileID: 0}}\n"
                   for t, p, v in mods)
    return HEADER + f"""--- !u!1001 &{fid(name + '|shell')}
PrefabInstance:
  m_ObjectHideFlags: 0
  serializedVersion: 2
  m_Modification:
    serializedVersion: 3
    m_TransformParent: {{fileID: 0}}
    m_Modifications:
{body}    m_RemovedComponents: []
    m_RemovedGameObjects: []
    m_AddedGameObjects: []
    m_AddedComponents: []
  m_SourcePrefab: {{fileID: 100100000, guid: {source_guid}, type: 3}}
"""


# ---------------- 动效预设 → 动画曲线 ----------------
# 每个预设 = 一个周期波形;clip 长度取所有层周期的最大值,短周期的层在 clip 里重复整数次(循环无缝)。
# 晃动 sway:绕 z 轴来回转 ±amp 度;浮动 float:上下 ±amp;抖动 shake:左右快速 ±amp;呼吸 breathe:缩放 1 ↔ 1+amp;
# 闪烁 blink:透明度 1 ↔ 1-amp;变色 tint:颜色白 ↔ color(Image 颜色是乘在贴图上的,白 = 原色)。
PRESETS = {
    "sway": {"label": "晃动", "amp": 6, "period": 2.0},
    "float": {"label": "浮动", "amp": 6, "period": 2.0},
    "shake": {"label": "抖动", "amp": 4, "period": 0.5},
    "breathe": {"label": "呼吸", "amp": 0.08, "period": 2.0},
    "blink": {"label": "闪烁", "amp": 0.6, "period": 1.0},
    "tint": {"label": "变色", "amp": 1.0, "period": 2.0, "color": "#ffd24a"},
}


def _wave(kind, t, p, d):
    """单位波形及其导数:sin 型(来回)或 cos 型(0→1→0)"""
    w = 2 * math.pi / p
    if kind == "sin":
        return math.sin(w * (t - d)), w * math.cos(w * (t - d))
    return (1 - math.cos(w * (t - d))) / 2, w * math.sin(w * (t - d)) / 2


def _keys(kind, length, p, d, f):
    """在 [0, length] 内每 1/4 周期取一个关键帧(端点必有),值和斜率按解析式算,首尾相等保证循环无缝。f(u, du) → (值, 斜率)"""
    reps = max(1, round(length / p)); p = length / reps
    ts = sorted({0.0, length} | {round((d + k * p / 4) % length, 6) for k in range(reps * 4)})
    return [(t,) + f(*_wave(kind, t, p, d)) for t in ts]


def _float_curve(keys, indent):
    sp = " " * indent
    s = f"{sp}curve:\n{sp}  serializedVersion: 2\n{sp}  m_Curve:\n"
    for t, v, sl in keys:
        s += (f"{sp}  - serializedVersion: 3\n{sp}    time: {num(t)}\n{sp}    value: {num(v)}\n{sp}    inSlope: {num(sl)}\n{sp}    outSlope: {num(sl)}\n"
              f"{sp}    tangentMode: 0\n{sp}    weightedMode: 0\n{sp}    inWeight: 0.33333334\n{sp}    outWeight: 0.33333334\n")
    return s + f"{sp}  m_PreInfinity: 2\n{sp}  m_PostInfinity: 2\n{sp}  m_RotationOrder: 4\n"


def _vec_curve(keys3, indent):
    sp = " " * indent
    s = f"{sp}curve:\n{sp}  serializedVersion: 2\n{sp}  m_Curve:\n"
    for t, v, sl in keys3:
        vv = "{x: %s, y: %s, z: %s}" % tuple(num(x) for x in v)
        ss = "{x: %s, y: %s, z: %s}" % tuple(num(x) for x in sl)
        s += (f"{sp}  - serializedVersion: 3\n{sp}    time: {num(t)}\n{sp}    value: {vv}\n{sp}    inSlope: {ss}\n{sp}    outSlope: {ss}\n"
              f"{sp}    tangentMode: 0\n{sp}    weightedMode: 0\n{sp}    inWeight: {{x: 0.33333334, y: 0.33333334, z: 0.33333334}}\n"
              f"{sp}    outWeight: {{x: 0.33333334, y: 0.33333334, z: 0.33333334}}\n")
    return s + f"{sp}  m_PreInfinity: 2\n{sp}  m_PostInfinity: 2\n{sp}  m_RotationOrder: 4\n"


def _hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def anim_clip(name, motions):
    """motions: [{path(层名), preset, amp, period, delay, color, base_x, base_y}] → .anim 文本(motions 不能为空)"""
    length = max(float(m.get("period") or PRESETS[m["preset"]]["period"]) for m in motions)
    euler, scale, floats, editor, euler_editor, bindings = [], [], [], [], [], []

    def add_float(path, attr, keys, cls, script="{fileID: 0}", custom=0, flags=0):
        block = f"  - serializedVersion: 2\n{_float_curve(keys, 4)}    attribute: {attr}\n    path: {yaml_str(path)}\n    classID: {cls}\n    script: {script}\n    flags: {flags}\n"
        floats.append(block); editor.append(block)
        bindings.append((zlib.crc32(path.encode("utf-8")), zlib.crc32(attr.encode("utf-8")), script, cls, custom))

    for m in motions:
        pr = PRESETS[m["preset"]]
        amp = float(m["amp"] if m.get("amp") is not None else pr["amp"])
        p = float(m.get("period") or pr["period"]); d = float(m.get("delay") or 0) % p
        path = m["path"]
        if m["preset"] == "sway":
            ks = _keys("sin", length, p, d, lambda u, du: (amp * u, amp * du))
            euler.append(f"  - {_vec_curve([(t, (0, 0, v), (0, 0, s)) for t, v, s in ks], 4)[4:]}    path: {yaml_str(path)}\n")
            for ax in "xyz":
                kk = ks if ax == "z" else [(t, 0, 0) for t, _, _ in ks]
                editor.append(f"  - serializedVersion: 2\n{_float_curve(kk, 4)}    attribute: localEulerAnglesRaw.{ax}\n    path: {yaml_str(path)}\n    classID: 224\n    script: {{fileID: 0}}\n    flags: 16\n")
                euler_editor.append(f"  - serializedVersion: 2\n    curve:\n      serializedVersion: 2\n      m_Curve: []\n      m_PreInfinity: 2\n      m_PostInfinity: 2\n      m_RotationOrder: 4\n"
                                    f"    attribute: m_LocalEulerAngles.{ax}\n    path: {yaml_str(path)}\n    classID: 224\n    script: {{fileID: 0}}\n    flags: 0\n")
            bindings.append((zlib.crc32(path.encode("utf-8")), 4, "{fileID: 0}", 4, 4))
        elif m["preset"] == "breathe":
            ks = _keys("cos", length, p, d, lambda u, du: (1 + amp * u, amp * du))
            scale.append(f"  - {_vec_curve([(t, (v, v, 1), (s, s, 0)) for t, v, s in ks], 4)[4:]}    path: {yaml_str(path)}\n")
            for ax in "xyz":
                kk = ks if ax != "z" else [(t, 1, 0) for t, _, _ in ks]
                editor.append(f"  - serializedVersion: 2\n{_float_curve(kk, 4)}    attribute: m_LocalScale.{ax}\n    path: {yaml_str(path)}\n    classID: 224\n    script: {{fileID: 0}}\n    flags: 0\n")
            bindings.append((zlib.crc32(path.encode("utf-8")), 3, "{fileID: 0}", 4, 0))
        elif m["preset"] in ("float", "shake"):
            axis, base = ("y", float(m.get("base_y") or 0)) if m["preset"] == "float" else ("x", float(m.get("base_x") or 0))
            ks = _keys("sin", length, p, d, lambda u, du: (base + amp * u, amp * du))
            add_float(path, f"m_AnchoredPosition.{axis}", ks, 224, custom=28)
        elif m["preset"] == "blink":
            ks = _keys("cos", length, p, d, lambda u, du: (1 - amp * u, -amp * du))
            add_float(path, "m_Color.a", ks, 114, IMAGE_SCRIPT)
        elif m["preset"] == "tint":
            rgb = _hex_rgb(m.get("color") or pr["color"])
            for ch, target in zip("rgb", rgb):
                k = (target - 1) * min(amp, 1)
                ks = _keys("cos", length, p, d, lambda u, du, k=k: (1 + k * u, k * du))
                add_float(path, f"m_Color.{ch}", ks, 114, IMAGE_SCRIPT)
        else:
            raise ValueError("未知动效预设:" + m["preset"])

    lst = lambda xs: ("\n" + "".join(xs)) if xs else " []\n"
    gb = "".join(f"""    - serializedVersion: 2
      path: {p}
      attribute: {a}
      script: {s}
      typeID: {t}
      customType: {c}
      isPPtrCurve: 0
      isIntCurve: 0
      isSerializeReferenceCurve: 0
""" for p, a, s, t, c in bindings)
    return HEADER + f"""--- !u!74 &7400000
AnimationClip:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {yaml_str(name)}
  serializedVersion: 7
  m_Legacy: 0
  m_Compressed: 0
  m_UseHighQualityCurve: 1
  m_RotationCurves: []
  m_CompressedRotationCurves: []
  m_EulerCurves:{lst(euler)}  m_PositionCurves: []
  m_ScaleCurves:{lst(scale)}  m_FloatCurves:{lst(floats)}  m_PPtrCurves: []
  m_SampleRate: 60
  m_WrapMode: 0
  m_Bounds:
    m_Center: {{x: 0, y: 0, z: 0}}
    m_Extent: {{x: 0, y: 0, z: 0}}
  m_ClipBindingConstant:
    genericBindings:
{gb}    pptrCurveMapping: []
  m_AnimationClipSettings:
    serializedVersion: 2
    m_AdditiveReferencePoseClip: {{fileID: 0}}
    m_AdditiveReferencePoseTime: 0
    m_StartTime: 0
    m_StopTime: {num(length)}
    m_OrientationOffsetY: 0
    m_Level: 0
    m_CycleOffset: 0
    m_HasAdditiveReferencePose: 0
    m_LoopTime: 1
    m_LoopBlend: 0
    m_LoopBlendOrientation: 0
    m_LoopBlendPositionY: 0
    m_LoopBlendPositionXZ: 0
    m_KeepOriginalOrientation: 0
    m_KeepOriginalPositionY: 1
    m_KeepOriginalPositionXZ: 0
    m_HeightFromFeet: 0
    m_Mirror: 0
  m_EditorCurves:{lst(editor)}  m_EulerEditorCurves:{lst(euler_editor)}  m_HasGenericRootTransform: 0
  m_HasMotionFloatCurves: 0
  m_Events: []
"""


def anim_controller(name, clip_guid):
    sm, st = fid(name + "|statemachine"), fid(name + "|state")
    return HEADER + f"""--- !u!91 &9100000
AnimatorController:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {yaml_str(name)}
  serializedVersion: 5
  m_AnimatorParameters: []
  m_AnimatorLayers:
  - serializedVersion: 5
    m_Name: Base Layer
    m_StateMachine: {{fileID: {sm}}}
    m_Mask: {{fileID: 0}}
    m_Motions: []
    m_Behaviours: []
    m_BlendingMode: 0
    m_SyncedLayerIndex: -1
    m_DefaultWeight: 0
    m_IKPass: 0
    m_SyncedLayerAffectsTiming: 0
    m_Controller: {{fileID: 9100000}}
--- !u!1102 &{st}
AnimatorState:
  serializedVersion: 6
  m_ObjectHideFlags: 1
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {yaml_str(name)}
  m_Speed: 1
  m_CycleOffset: 0
  m_Transitions: []
  m_StateMachineBehaviours: []
  m_Position: {{x: 50, y: 50, z: 0}}
  m_IKOnFeet: 0
  m_WriteDefaultValues: 1
  m_Mirror: 0
  m_SpeedParameterActive: 0
  m_MirrorParameterActive: 0
  m_CycleOffsetParameterActive: 0
  m_TimeParameterActive: 0
  m_Motion: {{fileID: 7400000, guid: {clip_guid}, type: 2}}
  m_Tag:
  m_SpeedParameter:
  m_MirrorParameter:
  m_CycleOffsetParameter:
  m_TimeParameter:
--- !u!1107 &{sm}
AnimatorStateMachine:
  serializedVersion: 6
  m_ObjectHideFlags: 1
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: Base Layer
  m_ChildStates:
  - serializedVersion: 1
    m_State: {{fileID: {st}}}
    m_Position: {{x: 200, y: 0, z: 0}}
  m_ChildStateMachines: []
  m_AnyStateTransitions: []
  m_EntryTransitions: []
  m_StateMachineTransitions: {{}}
  m_StateMachineBehaviours: []
  m_AnyStatePosition: {{x: 50, y: 20, z: 0}}
  m_EntryPosition: {{x: 50, y: 120, z: 0}}
  m_ExitPosition: {{x: 800, y: 120, z: 0}}
  m_ParentStateMachinePosition: {{x: 800, y: 20, z: 0}}
  m_DefaultState: {{fileID: {st}}}
"""
