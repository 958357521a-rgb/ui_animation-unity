# Unity 实机验收:在 Unity 里逐页渲染 prefab 截图 + 跑主工程的「UI导入体检」,结果放 exports/unity_preview/
# 工具代码只存在工作台(dev/unity/BudUIStudioPreview.cs):运行时临时拷进 <Unity 工程>/Assets/BudUIStudioTemp/,
# 跑完(成功、失败、中断都一样)连目录和 .meta 一起删掉,主工程里不留任何工具脚本。
# 用法:python dev/unity_preview.py --unity E:\BUDGCB\BUD_CHINA --prefab Assets/.../X.prefab [--project projects/X.budui.json] [--out 目录] [--unity-exe Unity.exe 路径]
#   --project:用工程文件算出每个弹窗由哪一页打开,截图时把弹窗叠在那一页上(不给就叠在主页上)
# 限制:Unity 编辑器开着这个工程时没法用命令行模式(工程被锁),先关编辑器。
import argparse, json, os, re, shutil, subprocess, sys, time

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "unity", "BudUIStudioPreview.cs")
TEMP_DIR = "BudUIStudioTemp"   # 主工程 Assets/ 下的临时目录名,只放这一个工具脚本


def editor_locked(root):
    lf = os.path.join(root, "Temp", "UnityLockfile")
    if not os.path.exists(lf):
        return False
    try:   # 编辑器开着时锁文件被独占,打不开
        with open(lf, "a"):
            return False
    except OSError:
        return True


def unity_exe(root, given):
    if given:
        return given
    ver = re.search(r"m_EditorVersion: (\S+)", open(os.path.join(root, "ProjectSettings", "ProjectVersion.txt"), encoding="utf-8").read()).group(1)
    exe = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Unity", "Hub", "Editor", ver, "Editor", "Unity.exe")
    if not os.path.isfile(exe):
        sys.exit(f"找不到 Unity {ver}:{exe}(用 --unity-exe 指定)")
    return exe


def popup_parents(project_file):
    """弹窗页序号 → 打开它的那一页的序号(View 的 pages[] 与工程 pages 同序)"""
    if not project_file:
        return ""
    proj = json.load(open(project_file, encoding="utf-8"))
    proj = proj.get("proj", proj)
    pages = proj.get("pages") or []
    index = {p["id"]: i for i, p in enumerate(pages)}
    parent = {}

    def walk(nodes, i):
        for n in nodes or []:
            t = n.get("clickTargetPage")
            if n.get("clickAction") == "openPopup" and t in index and index[t] not in parent:
                parent[index[t]] = i
            walk(n.get("children"), i)

    for i, p in enumerate(pages):
        walk(p.get("nodes"), i)
    # 弹窗里打开的弹窗(确认兑换 → 兑换成功):运行时同一时间只显示一个弹窗,底下是最初那一页
    for k in parent:
        seen = {k}
        while parent[k] in parent and parent[k] not in seen:
            seen.add(parent[k])
            parent[k] = parent[parent[k]]
    return ",".join(f"{k}:{v}" for k, v in sorted(parent.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unity", required=True)
    ap.add_argument("--prefab", required=True)
    ap.add_argument("--project")
    ap.add_argument("--out", default=os.path.join(ROOT, "exports", "unity_preview"))
    ap.add_argument("--unity-exe")
    a = ap.parse_args()
    root = os.path.abspath(a.unity)
    if not os.path.isfile(os.path.join(root, "ProjectSettings", "ProjectVersion.txt")):
        sys.exit("不是 Unity 工程目录:" + root)
    if editor_locked(root):
        sys.exit("Unity 编辑器正开着这个工程(工程被锁),命令行模式跑不了:先关掉编辑器再运行。")
    if not os.path.isfile(os.path.join(root, a.prefab)):
        sys.exit("工程里没有这个 prefab:" + a.prefab)
    exe = unity_exe(root, a.unity_exe)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    tmp = os.path.join(root, "Assets", TEMP_DIR)
    if os.path.exists(tmp):
        sys.exit(f"{tmp} 已存在(上次没清理干净?),确认里面只有本工具的文件后删掉再运行。")
    log = os.path.join(out, "unity.log")
    t0 = time.time()
    try:
        os.makedirs(os.path.join(tmp, "Editor"))
        shutil.copy2(TOOL, os.path.join(tmp, "Editor", os.path.basename(TOOL)))
        cmd = [exe, "-batchmode", "-projectPath", root, "-executeMethod", "BudUIStudioPreview.Run",
               "-budPrefab", a.prefab.replace("\\", "/"), "-budOut", out, "-budPopupParents", popup_parents(a.project), "-logFile", log]
        print("Unity 运行中(编译 + 渲染,一般一两分钟)…", flush=True)
        code = subprocess.run(cmd).returncode
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.exists(tmp + ".meta"):
            os.remove(tmp + ".meta")
        print("已清理主工程里的临时工具目录:" + ("干净" if not os.path.exists(tmp) and not os.path.exists(tmp + ".meta") else "⚠ 没删干净,请手动删除 " + tmp), flush=True)
    print(f"Unity 退出码 {code},用时 {int(time.time() - t0)} 秒;日志 {log}")
    rp = os.path.join(out, "report.md")
    if os.path.isfile(rp) and os.path.getmtime(rp) >= t0:
        print("报告:" + rp)
    else:
        print("没有生成报告,看 Unity 日志里的报错(搜 error / Exception)")
        code = code or 1
    sys.exit(code)


if __name__ == "__main__":
    main()
