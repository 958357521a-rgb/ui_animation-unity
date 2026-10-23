# 上下文守卫(配合「提前自动压缩」用;由 dev/lite/install_token_saver.py 装进本机用户设置,不放进仓库的项目设置)
#   python token_guard.py prompt    UserPromptSubmit:上下文到自动压缩线的 80% 时(每次压缩前提醒一次),让 Claude 先把进度写进进度卡
#   python token_guard.py compact   SessionStart(compact):刚自动压缩过,让 Claude 先读进度卡接着做
# 自动压缩线读 ~/.claude/settings.json 的 autoCompactWindow(安装脚本写的,默认 20 万)。
# 出任何错都静默退出(exit 0、不输出):钩子坏了不能挡住发消息。输出只用 ASCII(中文转成 \uXXXX),不赌控制台编码。
import json, os, sys, time

HOME = os.path.expanduser("~")
SETTINGS = os.path.join(HOME, ".claude", "settings.json")
STATE = os.path.join(HOME, ".claude", "hooks", "state", "token-guard.json")
WARN = 0.8


def card(inp):
    """进度卡位置:在工作台项目里写 exports/lite/进度卡.md(exports/ 不进仓库),别的项目写 .claude/进度卡.md"""
    cwd = inp.get("cwd") or os.getcwd()
    return "exports/lite/进度卡.md" if os.path.exists(os.path.join(cwd, "BUD_UI_Studio.html")) else ".claude/进度卡.md"


def window():
    try:
        return int(json.load(open(SETTINGS, encoding="utf-8")).get("autoCompactWindow") or 200000)
    except Exception:
        return 200000


def tokens_of(transcript):
    """从会话记录末尾找最近一条主对话回复的 usage,算当前上下文大小;先碰到压缩边界就返回 0(压缩后重新计)"""
    with open(transcript, "rb") as f:
        f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 8 * 1024 * 1024))
        lines = f.read().decode("utf-8", "replace").split("\n")
    for l in reversed(lines):
        if '"compact_boundary"' in l:
            return 0
        if '"usage"' not in l or '"assistant"' not in l:
            continue
        try:
            j = json.loads(l)
        except ValueError:
            continue
        m = j.get("message") or {}; u = m.get("usage") or {}
        if j.get("type") != "assistant" or j.get("isSidechain") or m.get("model") == "<synthetic>" or not u:
            continue
        return sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
    return 0


def emit(note, context, event):
    print(json.dumps({"systemMessage": note, "hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}, ensure_ascii=True))


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    now = time.time()
    s = {k: v for k, v in s.items() if now - v.get("at", 0) < 30 * 86400}
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w", encoding="utf-8"))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    raw = sys.stdin.read()
    inp = json.loads(raw) if raw.strip() else {}
    sid = inp.get("session_id"); CARD = card(inp)
    if mode == "compact":
        s = load_state(); s.pop(sid, None); save_state(s)
        emit("上下文刚自动压缩过:Claude 会先读进度卡接着做。",
             f"【上下文刚自动压缩过(自动提醒)】前面的对话已压成摘要。先读 {CARD}(有的话),对照摘要确认做到哪、用的风格卡和文件路径、下一步,再继续处理用户的消息;不要让用户重发截图或参考图。", "SessionStart")
        return
    if not sid or not inp.get("transcript_path") or not os.path.exists(inp["transcript_path"]):
        return
    t = tokens_of(inp["transcript_path"]); w = window()
    s = load_state()
    if t < w * WARN:
        return
    if s.get(sid, {}).get("warned"):
        return
    s[sid] = {"warned": True, "at": time.time()}; save_state(s)
    emit(f"上下文约 {round(t / 10000)} 万 tokens,快到自动压缩线(约 {round(w / 10000)} 万):Claude 会先把进度存好,压缩后自动接着做。",
         f"【快到自动压缩(自动提醒)】上下文约 {round(t / 10000)} 万 tokens,约 {round(w / 10000)} 万会自动压缩,压缩后前面的细节只剩摘要。"
         f"照常处理用户这条消息,同时把进度写进 {CARD}(≤15 行:做到哪、用的风格卡、关键文件路径、用户定下的修改要求、下一步),已有就更新。"
         "不用提醒用户开新会话,压缩后会自动读进度卡接着做。", "UserPromptSubmit")


try:
    main()
except Exception:
    pass
sys.exit(0)
