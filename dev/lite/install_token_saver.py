# 一键装「提前自动压缩 + 压缩前存进度」到本机 Claude 的用户设置(~/.claude/settings.json),只影响这台电脑。
#   python dev/lite/install_token_saver.py [--window 200000]    安装 / 改压缩线(10 万~100 万 tokens,默认 20 万)
#   python dev/lite/install_token_saver.py --uninstall          卸载(压缩恢复成默认,约 97 万)
#   python dev/lite/install_token_saver.py --status             看现在装了什么
# 做的事:① 写 autoCompactWindow(Claude Code 正式设置:上下文到这个数就自动压缩,默认要到约 97 万才压);
#         ② 加两个钩子跑 dev/lite/token_guard.py:快到压缩线时让 Claude 先把进度写进进度卡,压缩后先读进度卡接着做。
# 改之前先把 settings.json 备份成 settings.json.bak-<时间>;重复运行不会重复添加。
# 为什么不放进仓库的 .claude/settings.json:那样每个打开这个项目的人都会被改,原作者自己不想要提前压缩。
import argparse, datetime, json, os, shutil, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "token_guard.py")
MARK = "token_guard.py"


def settings_path(a):
    return a.settings or os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def strip(hooks):
    """去掉以前装过的 token_guard 钩子(重复安装 / 卸载用)"""
    for ev in list(hooks):
        groups = []
        for g in hooks[ev]:
            hs = [h for h in g.get("hooks", []) if MARK not in h.get("command", "")]
            if hs:
                groups.append(dict(g, hooks=hs))
        if groups:
            hooks[ev] = groups
        else:
            del hooks[ev]
    return hooks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=200000)
    ap.add_argument("--uninstall", action="store_true"); ap.add_argument("--status", action="store_true")
    ap.add_argument("--settings", help="settings.json 路径(测试用)")
    a = ap.parse_args()
    p = settings_path(a)
    s = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    if a.status:
        mine = [h["command"] for g in sum(s.get("hooks", {}).values(), []) for h in g.get("hooks", []) if MARK in h.get("command", "")]
        print(f"设置文件:{p}\n  autoCompactWindow = {s.get('autoCompactWindow', '(没设,默认约 97 万)')}\n  守卫钩子:{len(mine)} 个")
        if os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW"):
            print("  注意:系统环境变量 CLAUDE_CODE_AUTO_COMPACT_WINDOW 已设置,它优先于 autoCompactWindow")
        return
    if not a.uninstall and not 100000 <= a.window <= 1000000:
        sys.exit("✗ --window 要在 100000~1000000 之间(Claude Code 的限制)")
    if os.path.exists(p):
        bak = p + ".bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy(p, bak); print("已备份原设置:" + bak)
    hooks = strip(s.get("hooks", {}))
    if a.uninstall:
        s.pop("autoCompactWindow", None)
        print("已卸载:自动压缩恢复默认(约 97 万),守卫钩子已去掉")
    else:
        py = sys.executable[:-5] + ".exe" if sys.executable.lower().endswith("pythonw.exe") else sys.executable
        cmd = lambda mode: f'"{py}" "{GUARD}" {mode}'
        hooks.setdefault("UserPromptSubmit", []).append({"hooks": [{"type": "command", "command": cmd("prompt"), "timeout": 10}]})
        hooks.setdefault("SessionStart", []).append({"matcher": "compact", "hooks": [{"type": "command", "command": cmd("compact"), "timeout": 10}]})
        s["autoCompactWindow"] = a.window
        print(f"已安装:上下文到约 {a.window // 10000} 万 tokens 自动压缩;到 {int(a.window * 0.8) // 10000} 万时 Claude 先把进度写进进度卡,压缩后自动读回来")
        if os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW"):
            print("注意:系统环境变量 CLAUDE_CODE_AUTO_COMPACT_WINDOW 已设置,它会盖过这里的设置,要去掉它才生效")
        print("新开的会话生效;在 Claude 里输入 /status 可以确认")
    if hooks:
        s["hooks"] = hooks
    else:
        s.pop("hooks", None)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
