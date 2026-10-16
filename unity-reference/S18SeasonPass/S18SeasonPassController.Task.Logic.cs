using System;
using System.Collections.Generic;
using System.Linq;
using Game.Event;
using Message;
using Network;
using Network.Http;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UI.Manager;
using UnityEngine;
using UnityEngine.UI;

namespace Bud.S18SeasonPass
{
    /// <summary>
    /// 每日 / 每周 / 赛季任务三页(页序号 2 / 3 / 4)。数据与交互照搬旧通行证:
    ///   任务列表   SeasonPassBaseView.RequestTaskInfo(HttpUrlDefine.TaskList + GetTaskListReq{idList = Config.EffectiveTaskIdList})
    ///   每日任务   DailyTaskView(任务 eventId 1~11、今日活跃度宝箱 12~16、本周活跃度宝箱 17/18;领取一律用 *SeasonDaily 的 taskId,同旧版)
    ///   每周任务   WeeklyTaskView(第 w 周任务 eventId = 6(w-1)+1..5,周奖励 = 6w;currentWeek 之后的周不开放)
    ///   赛季任务   SeasonTaskSubView(*SeasonChallenge 全部 event)
    ///   领取       EventCenterDataManager.CliamReward(taskId, eventId, 1, 0) → CommonRewardPanel(奖励取本地任务配置,每周任务未购买通行证只弹第一个奖励)
    ///   一键领取   赛季页 = 旧 SeasonTaskView.ClaimAllRewards:CliamReward(Challenge, 1, 2, 0)(奖励取回包 rewardList);每日 / 每周页 = 本页可领 event 逐个 CliamReward(taskId, eventId, 1, 0),合并弹一次领奖(TaskClaimSequential)
    ///   前往       EventCenterDataManager.SkipToTask(eventSkipType)
    ///   领完       AccountDataManager.BalanceInfo.Refresh + 广播 RefreshSeasonPass / RefreshSeasonPassTask(本模块监听后者重新拉任务)
    ///
    /// 验证步骤(进游戏打开赛季通行证 PanelId 290):
    ///  1. 点侧栏「赛季任务」→ 每日任务页:任务行数 = S17 DailyTaskConfig 的任务数(超出可上下滑到底),每行图标 / ×数量 / 任务名 / 进度数字 / 进度条与服务端一致;
    ///     未完成显示「前往」(没有跳转的显示「进行中」点了无反应),已完成显示「领取」,领过显示「已领取」。
    ///  2. 点「领取」→ 弹通用领奖面板,关掉后该行变「已领取」;点「前往」→ 跳到对应玩法界面(社区地图 / 换装间 / 扭蛋…)。
    ///  3. 底部今日活跃度:数字 = 今日活跃度,20~100 五个宝箱显示配置里的数量和门槛;可领的宝箱带红点,点击领取并弹领奖;领过显示对勾。
    ///     左侧本周活跃度数字 + 300 / 600 宝箱:未达成显示锁,可领时点击领取。
    ///  4. 每周任务页:五个周页签显示「第N周  完成数/5」;点未开放的周弹「任务未开放，请下周再来」并退回原来的页签;
    ///     切周后列表换成该周 5 个任务,第二个奖励在未买豪华通行证时带锁;底部「第N周累计完成5个每周任务」进度、状态(进行中 / 可领取 / 已领取),可领时点状态框领取。
    ///  5. 赛季任务页:顶部「每日在线时长上限为120分钟（今日已在线X分钟）」X = 服务端 todaySyncTime;列表同上。
    ///  6. 各页「一键领取」:有可领任务时可点,领完弹领奖面板、列表刷新;没有可领时按钮置灰。
    ///  7. 侧栏「赛季任务」页签上的红点(各页的 Art/at note-dot):三类任务里有任何可领奖励时显示,全部领完后消失。
    ///  8. 切到别的应用再回来(外壳 OnWindowBeFocused 广播 RefreshSeasonPassTask)列表自动刷新。
    /// </summary>
    public partial class S18SeasonPassController
    {
        private sealed class TaskPageUi
        {
            public Transform template, content;
            public Vector2 step;
            public readonly List<Transform> pool = new List<Transform>();
            public Sprite fullBar, emptyBar;
            public Button claimAll;
        }

        private static readonly List<int> TaskDailyEventIds = new List<int> { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 };
        private static readonly List<int> TaskDailyChestIds = new List<int> { 12, 13, 14, 15, 16 };
        private static readonly List<int> TaskWeeklyActiveIds = new List<int> { 17, 18 };
        private const int TaskWeekTaskCount = 5, TaskWeekRewardId = 6;

        private readonly Dictionary<int, TaskPageUi> _taskPages = new Dictionary<int, TaskPageUi>();
        private readonly Dictionary<int, SeasonTaskEventInfo> _taskDailyInfos = new Dictionary<int, SeasonTaskEventInfo>();
        private readonly Dictionary<int, SeasonTaskEventInfo> _taskWeeklyInfos = new Dictionary<int, SeasonTaskEventInfo>();
        private readonly Dictionary<int, SeasonTaskEventInfo> _taskSeasonInfos = new Dictionary<int, SeasonTaskEventInfo>();
        private TaskListRsp _taskRsp;
        private SeasonPassListRsp _taskPassRsp;
        private int _taskWeek = 1, _taskUnlockedWeek = 1;
        private bool _taskConfigLoaded, _taskListening;
        private Message.MessageHandler _taskRefreshHandler;
        private Font _taskFont;

        private string TaskDailyId => Config != null ? Config.GetTaskId(SeasonTaskIdSuffix.Daily).ToString() : "";
        private string TaskWeeklyActiveId => Config != null ? Config.GetTaskId(SeasonTaskIdSuffix.WeeklyActive).ToString() : "";
        private string TaskWeekId => Config != null ? Config.GetTaskId(SeasonTaskIdSuffix.WeekTask).ToString() : "";
        private string TaskSeasonId => Config != null ? Config.GetTaskId(SeasonTaskIdSuffix.Challenge).ToString() : "";

        // ================= 挂钩 =================
        partial void TaskCreate()
        {
            TaskPrepareRows(PageDaily);
            TaskPrepareRows(PageWeekly);
            TaskPrepareRows(PageSeasonTask);
            TaskPrepareChests();
            TaskPrepareWeekly();
            if (!_taskListening)
            {
                _taskListening = true;
                _taskRefreshHandler = () =>
                {
                    if (this == null) { MessageHelper.RemoveListener(MessageName.RefreshSeasonPassTask, _taskRefreshHandler); return; }
                    TaskRequest();
                };
                MessageHelper.AddListener(MessageName.RefreshSeasonPassTask, _taskRefreshHandler);
            }
        }

        partial void TaskRefresh()
        {
            // 不在这里复位一键领取锁:逐个领取过程中每领一个都可能触发刷新,复位会让后面的领取和领奖弹窗作废(锁靠换页 / 10 秒超时兜底)
            TaskLoadConfigs();
            _taskPassRsp = SeasonPassDataManager.Inst.GetSeasonPassList(SeasonPassDataManager.Inst.CurrentSeasonPassType) ?? _taskPassRsp;
            SeasonPassDataManager.Inst.GetSeasonPassList(SeasonPassDataManager.Inst.CurrentSeasonPassType, (ok, rsp) =>
            {
                if (this == null || !ok || rsp == null) return;
                _taskPassRsp = rsp;
                TaskApplyAll();
            });
            TaskRequest();
        }

        partial void TaskAction(string key, ref bool handled)
        {
            switch (key)
            {
                case "pageClaim3": handled = true; TaskClaimSequential(PageDaily); return;
                case "pageClaim6": handled = true; TaskClaimSequential(PageWeekly); return;
                case "pageClaim9": handled = true; TaskClaimAll(TaskSeasonId); return;
                case "pageAction19": handled = true; TaskClickChest(TaskWeeklyActiveId, 17); return;
                case "pageAction20": handled = true; TaskClickChest(TaskWeeklyActiveId, 18); return;
                case "pageAction27": handled = true; TaskClickChest(TaskDailyId, 12); return;
                case "pageAction28": handled = true; TaskClickChest(TaskDailyId, 13); return;
                case "pageAction29": handled = true; TaskClickChest(TaskDailyId, 14); return;
                case "pageAction30": handled = true; TaskClickChest(TaskDailyId, 15); return;
                case "pageAction31": handled = true; TaskClickChest(TaskDailyId, 16); return;
                case "pageAction36": case "pageAction37": case "pageAction38": case "pageAction39": case "pageAction40":
                    handled = true; TaskSelectWeek(int.Parse(key.Substring("pageAction".Length)) - 35); return;
                // 当前页的页签(View 不切页),无需处理
                case "pageAction22": case "pageAction34": case "pageAction46": handled = true; return;
            }
        }

        partial void TaskPageShown(int index)
        {
            TaskResetClaimLock();   // 任意换页都复位一键领取锁(CliamReward 回包为空时不回调)
            if (index != PageDaily && index != PageWeekly && index != PageSeasonTask) return;
            if (_taskRsp == null) TaskRequest();
            else TaskApplyPage(index);
        }

        // ================= 取数 =================
        private void TaskLoadConfigs()
        {
            if (_taskConfigLoaded || Config == null) return;
            _taskConfigLoaded = true;
            try
            {
                var daily = Loader.Load<TextAsset>(Config.DailyTaskConfigPath, gameObject);
                if (daily != null)
                    foreach (var e in JsonConvert.DeserializeObject<List<SeasonTaskEventInfo>>(daily.text)) _taskDailyInfos[e.eventId] = e;
                var season = Loader.Load<TextAsset>(Config.SeasonTaskConfigPath, gameObject);
                if (season != null)
                    foreach (var e in JsonConvert.DeserializeObject<List<SeasonTaskEventInfo>>(season.text)) _taskSeasonInfos[e.eventId] = e;
                var weekly = Loader.Load<TextAsset>(Config.WeeklyTaskConfigPath, gameObject);
                if (weekly != null)
                {
                    var jo = JObject.Parse(weekly.text);
                    if (!jo.TryGetValue(TaskWeekId, out var tok) && jo.Count == 1) tok = jo.Properties().First().Value;   // 同旧版:联调替身赛季时取唯一那组
                    if (tok != null)
                        foreach (var e in tok.ToObject<List<SeasonTaskEventInfo>>()) _taskWeeklyInfos[e.eventId] = e;
                }
            }
            catch (Exception ex) { Debug.LogError("[S18SeasonPass] 任务配置读取失败:" + ex.Message); }
        }

        private void TaskRequest()
        {
            if (this == null || Config == null) return;
            var req = new GetTaskListReq { idList = Config.EffectiveTaskIdList };
            NetworkManager.Inst.SendHttpRequest(HttpUrlDefine.TaskList, HttpMethod.POST, JsonConvert.SerializeObject(req), content =>
            {
                if (this == null) return;
                var rsp = JsonConvert.DeserializeObject<TaskListRsp>(content);
                if (rsp == null || rsp.list == null) return;
                _taskRsp = rsp;
                TaskApplyAll();
            }, error => { });
        }

        private TaskInfoData TaskData(string taskId) => _taskRsp?.list?.Find(x => x.taskId == taskId);

        private static bool TaskHasClaimable(TaskInfoData d, Func<TaskItemData, bool> filter = null) =>
            d?.eventList != null && d.eventList.Exists(e => e != null && e.eventStatus == (int)ClaimStatus.Unlocked && (filter == null || filter(e)));

        private void TaskApplyAll()
        {
            if (_taskRsp == null) return;
            TaskApplyPage(PageDaily);
            TaskApplyPage(PageWeekly);
            TaskApplyPage(PageSeasonTask);
            // 侧栏「赛季任务」页签红点:同旧版 SeasonPassBaseView,任何任务有可领就亮
            var any = _taskRsp.list.Exists(t => TaskHasClaimable(t));
            foreach (var p in new[] { PageReward, PageDaily, PageWeekly, PageSeasonTask })
            {
                var root = PageRoot(p);
                if (root == null) continue;
                for (int i = 0; i < root.childCount; i++)
                    if (root.GetChild(i).name == "Art/at note-dot") SetActive(root.GetChild(i), any);
            }
        }

        private void TaskApplyPage(int page)
        {
            if (_taskRsp == null) return;
            if (page == PageDaily) TaskApplyDaily();
            else if (page == PageWeekly) TaskApplyWeekly();
            else if (page == PageSeasonTask) TaskApplySeason();
        }

        // ================= 行模板准备 =================
        private void TaskPrepareRows(int page)
        {
            var root = PageRoot(page);
            var list = FindDeep(root, "任务列表 · 可滑动");
            var content = list != null ? FindPath(list, "内容") ?? FindDeep(list, "内容") : null;
            if (content == null) return;
            var rows = new List<Transform>();
            for (int i = 0; i < content.childCount; i++) if (content.GetChild(i).name == "at task-row") rows.Add(content.GetChild(i));
            if (rows.Count == 0) return;
            var ui = new TaskPageUi { template = rows[0], content = content, step = rows.Count > 1 ? StepBetween(rows[0], rows[1]) : new Vector2(0, -136) };
            var clip = FindPath(rows[0], "内容裁切") ?? rows[0];
            var claim = FindDeep(rows[0], "操作/领取");

            // 三种按钮都收进模板(设计稿每行只有一种)
            foreach (var btnName in new[] { "操作/领取", "操作/前往", "操作/已领取" })
            {
                if (FindDeep(rows[0], btnName) != null) continue;
                Transform src = null;
                for (int r = 1; r < rows.Count && src == null; r++) src = FindDeep(rows[r], btnName);
                if (src != null) { src.SetParent(clip, false); continue; }
                // 本页没有这种按钮(每周页没有「已领取」):从别的任务页拷一个
                foreach (var other in new[] { PageDaily, PageSeasonTask, PageWeekly })
                {
                    var o = other == page ? null : FindDeep(PageRoot(other), btnName);
                    if (o == null) continue;
                    var go = Instantiate(o.gameObject, clip, false);
                    go.name = btnName;
                    if (claim != null) ((RectTransform)go.transform).anchoredPosition = ((RectTransform)claim).anchoredPosition;
                    break;
                }
            }

            // 进度条:底用空条(进度 0/x 那行的图),上面叠一层满条做 Filled
            var bar = ImageAt(rows[0], "at row-progress");
            if (bar != null)
            {
                ui.fullBar = bar.sprite;
                foreach (var r in rows)
                {
                    var t = TaskRowProgressText(r);
                    if (t != null && t.text.StartsWith("0/", StringComparison.Ordinal)) { var b = ImageAt(r, "at row-progress"); if (b != null) ui.emptyBar = b.sprite; break; }
                }
                TaskMakeFill(bar, ui.fullBar, ui.emptyBar);
            }

            // 奖励数量在设计稿里是图片:关掉图片,叠一个 Text
            var progressText = TaskRowProgressText(rows[0]);
            if (progressText != null) _taskFont = _taskFont ?? progressText.font;
            foreach (var cell in FindAllDeep(rows[0], "奖励格")) TaskEnsureQtyText(cell);

            for (int r = 1; r < rows.Count; r++) SetActive(rows[r], false);
            ui.pool.Add(rows[0]);
            ui.claimAll = FindDeep(root, "操作/一键领取")?.GetComponent<Button>();
            _taskPages[page] = ui;
        }

        private static Image TaskMakeFill(Image bar, Sprite full, Sprite empty)
        {
            if (bar == null) return null;
            var exist = bar.transform.Find("TaskFill");
            if (exist != null) return exist.GetComponent<Image>();
            if (empty != null) bar.sprite = empty;
            var go = new GameObject("TaskFill", typeof(RectTransform), typeof(Image));
            go.layer = bar.gameObject.layer;
            var rt = (RectTransform)go.transform;
            rt.SetParent(bar.transform, false);
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.offsetMin = rt.offsetMax = Vector2.zero;
            var img = go.GetComponent<Image>();
            img.sprite = full; img.raycastTarget = false;
            img.type = Image.Type.Filled; img.fillMethod = Image.FillMethod.Horizontal; img.fillOrigin = 0; img.fillAmount = 0;
            return img;
        }

        private static void TaskSetFill(Image bar, float v)
        {
            if (bar == null) return;
            var f = bar.transform.Find("TaskFill");
            var img = f != null ? f.GetComponent<Image>() : null;
            if (img != null) img.fillAmount = Mathf.Clamp01(v);
        }

        private Text TaskEnsureQtyText(Transform cell)
        {
            Transform qty = null;
            for (int i = 0; i < cell.childCount; i++) if (cell.GetChild(i).name.StartsWith("文案/×", StringComparison.Ordinal)) { qty = cell.GetChild(i); break; }
            if (qty == null) return null;
            var existing = qty.Find("TaskQty");
            if (existing != null) return existing.GetComponent<Text>();
            var img = qty.GetComponent<Image>();
            if (img != null) img.enabled = false;
            var go = new GameObject("TaskQty", typeof(RectTransform), typeof(Text));
            go.layer = qty.gameObject.layer;
            var rt = (RectTransform)go.transform;
            rt.SetParent(qty, false);
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one;
            rt.offsetMin = new Vector2(-60, -6); rt.offsetMax = new Vector2(2, 6);
            var t = go.GetComponent<Text>();
            if (_taskFont == null) { var any = GetComponentInChildren<Text>(true); if (any != null) _taskFont = any.font; }   // 兜底:取页面上任一 Text 的字体
            t.font = _taskFont; t.fontSize = 20; t.alignment = TextAnchor.MiddleRight;
            t.horizontalOverflow = HorizontalWrapMode.Overflow; t.verticalOverflow = VerticalWrapMode.Overflow;
            t.color = new Color32(0x7a, 0x67, 0x9a, 0xff); t.raycastTarget = false;
            return t;
        }

        private static Text TaskRowProgressText(Transform row)
        {
            var clip = FindPath(row, "内容裁切") ?? row;
            var box = FindPath(clip, "text");
            return box != null ? box.GetComponentInChildren<Text>(true) : null;
        }

        private static Text TaskRowNameText(Transform row)
        {
            var clip = FindPath(row, "内容裁切") ?? row;
            var box = FindPath(clip, "text left");
            return box != null ? box.GetComponentInChildren<Text>(true) : null;
        }

        private static Image TaskCellIcon(Transform cell)
        {
            for (int i = 0; i < cell.childCount; i++)
            {
                var c = cell.GetChild(i);
                if (c.name.StartsWith("底/", StringComparison.Ordinal) || c.name.StartsWith("文案/", StringComparison.Ordinal) || c.name.Contains("status_locked")) continue;
                var img = c.GetComponent<Image>();
                if (img != null) return img;
            }
            return null;
        }

        // ================= 填行 =================
        /// <summary>按 items 填 page 的任务列表;locked2nd = 第二个奖励带锁(每周任务未买豪华通行证)。</summary>
        private void TaskFillList(int page, string taskId, List<TaskItemData> items, Dictionary<int, SeasonTaskEventInfo> infos, bool locked2nd)
        {
            if (!_taskPages.TryGetValue(page, out var ui)) return;
            EnsureClones(ui.template, items.Count, ui.step, ui.pool);
            for (int i = 0; i < items.Count; i++)
            {
                infos.TryGetValue(items[i].eventId, out var info);
                TaskFillRow(ui.pool[i], taskId, items[i], info, infos, locked2nd);
            }
            if (items.Count > 0) FitContent(ui.content, ui.pool[items.Count - 1], false);
        }

        private void TaskFillRow(Transform row, string taskId, TaskItemData data, SeasonTaskEventInfo info, Dictionary<int, SeasonTaskEventInfo> infos, bool locked2nd)
        {
            var rewards = info?.rewardList ?? new List<SeasonTaskRewardInfo>();
            var cells = FindAllDeep(row, "奖励格");
            for (int c = 0; c < cells.Count; c++)
            {
                var on = c < rewards.Count;
                SetActive(cells[c], on);
                if (!on) continue;
                var r = rewards[c];
                var icon = TaskCellIcon(cells[c]);
                var qty = TaskEnsureQtyText(cells[c]);
                // 图标统一走 IconSet:设计稿新图标优先(活跃度 / 金币 / 经验…),时装等才用服务端图标;保持设计稿矩形
                if (icon != null) { IconSet(icon, r); IconRaiseTexts(cells[c], icon); }
                SetText(qty, r.rewardType == BUDRewardType.RewardPgcResource ? r.rewardName : "×" + r.rewardAmount);
                for (int k = 0; k < cells[c].childCount; k++)
                    if (cells[c].GetChild(k).name.Contains("status_locked")) SetActive(cells[c].GetChild(k), c == 1 && locked2nd);
            }

            var name = info != null ? info.eventName : data.eventName;
            var target = info != null ? info.targetAmount : data.targetAmount;
            var nameText = TaskRowNameText(row);
            if (nameText != null) nameText.SetLocalText(name ?? "");
            var status = (ClaimStatus)data.eventStatus;
            SetText(TaskRowProgressText(row), target >= 1 ? $"{Mathf.Min(data.finishAmount, target)}/{target}" : "");
            float fill = target >= 1 ? (float)data.finishAmount / target : 0f;
            if (status == ClaimStatus.Unlocked || status == ClaimStatus.Claimed) fill = 1f;
            TaskSetFill(ImageAt(row, "at row-progress"), fill);

            var claim = FindDeep(row, "操作/领取");
            var go = FindDeep(row, "操作/前往");
            var done = FindDeep(row, "操作/已领取");
            SetActive(claim, status == ClaimStatus.Unlocked);
            SetActive(done, status == ClaimStatus.Claimed);
            SetActive(go, status == ClaimStatus.Lock);
            var eventId = data.eventId;
            BindClick(claim, () => TaskClaimOne(taskId, eventId, infos));
            BindClick(done, null);
            var skip = info != null ? info.eventSkipType : EventCenterSkipType.ErrType;
            if (go != null)
            {
                var goText = go.GetComponentInChildren<Text>(true);
                if (goText != null) goText.SetLocalText(skip != EventCenterSkipType.ErrType ? "前往" : "进行中");
                BindClick(go, () => { if (skip != EventCenterSkipType.ErrType) EventCenterDataManager.Inst.SkipToTask(skip); });
            }
        }

        private void TaskSetClaimAll(int page, bool can)
        {
            if (_taskPages.TryGetValue(page, out var ui) && ui.claimAll != null) ui.claimAll.interactable = can && !_taskClaiming;
        }

        // ================= 每日任务 =================
        private readonly List<Transform> _taskChests = new List<Transform>();

        private void TaskPrepareChests()
        {
            var root = PageRoot(PageDaily);
            if (root == null) return;
            foreach (var n in new[] { "20", "40", "60", "80", "100" })
            {
                var b = FindDeep(root, "操作/今日活跃度" + n + "奖励");
                if (b != null) _taskChests.Add(b);
            }
            Transform claimedMark = null, dot = null;
            foreach (var c in _taskChests) { claimedMark = claimedMark ?? FindPath(c, "状态/已领取"); dot = dot ?? FindPath(c, "Art/at note-dot"); }
            foreach (var c in _taskChests)
            {
                if (claimedMark != null && FindPath(c, "状态/已领取") == null) Instantiate(claimedMark.gameObject, c, false).name = "状态/已领取";
                if (dot != null && FindPath(c, "Art/at note-dot") == null) Instantiate(dot.gameObject, c, false).name = "Art/at note-dot";
            }
        }

        private void TaskApplyDaily()
        {
            var root = PageRoot(PageDaily);
            var daily = TaskData(TaskDailyId);
            var items = daily?.eventList?.Where(e => e != null && TaskDailyEventIds.Contains(e.eventId)).ToList() ?? new List<TaskItemData>();
            TaskFillList(PageDaily, TaskDailyId, items, _taskDailyInfos, false);
            TaskSetClaimAll(PageDaily, TaskHasClaimable(daily, e => TaskDailyEventIds.Contains(e.eventId) || TaskDailyChestIds.Contains(e.eventId)) || TaskHasClaimable(TaskData(TaskWeeklyActiveId), e => TaskWeeklyActiveIds.Contains(e.eventId)));

            // 今日活跃度宝箱(eventId 12~16;12 的 finishAmount = 今日活跃度)
            for (int i = 0; i < _taskChests.Count && i < TaskDailyChestIds.Count; i++)
            {
                var chest = _taskChests[i];
                var id = TaskDailyChestIds[i];
                var d = daily?.eventList?.Find(e => e != null && e.eventId == id);
                _taskDailyInfos.TryGetValue(id, out var info);
                if (info != null)
                {
                    SetText(TextAt(chest, "数值"), info.spendNum.ToString());
                    var qty = FindDeep(chest, "text")?.GetComponentInChildren<Text>(true);
                    if (qty != null && info.rewardList != null && info.rewardList.Count > 0) qty.text = "×" + info.rewardList[0].rewardAmount;
                    TaskSetSiblingIcon(chest, info);
                }
                var st = d != null ? (ClaimStatus)d.eventStatus : ClaimStatus.Lock;
                SetActive(FindPath(chest, "状态/已领取"), st == ClaimStatus.Claimed);
                SetActive(FindPath(chest, "Art/at note-dot"), st == ClaimStatus.Unlocked);
                if (id == 12 && d != null)
                {
                    var crop = FindDeep(root, "文案/今日活跃度")?.parent?.parent;
                    var box = crop != null ? FindPath(crop, "text left") : null;
                    if (box != null) SetText(box.GetComponentInChildren<Text>(true), d.finishAmount.ToString());
                }
            }

            // 本周活跃度宝箱(*SeasonWeeklyActive 的 17 / 18;17 的 finishAmount = 本周活跃度)
            var weeklyActive = TaskData(TaskWeeklyActiveId);
            var ribbon = FindDeep(root, "at ribbon");
            var area = ribbon != null ? ribbon.parent : null;
            var locks = new List<Transform>();
            if (area != null) for (int i = 0; i < area.childCount; i++) if (area.GetChild(i).name == "Art/图标/status_locked.png") locks.Add(area.GetChild(i));
            var states = new List<Transform>();
            if (area != null) for (int i = 0; i < area.childCount; i++) if (area.GetChild(i).name == "at state") states.Add(area.GetChild(i));
            for (int i = 0; i < TaskWeeklyActiveIds.Count; i++)
            {
                var id = TaskWeeklyActiveIds[i];
                var d = weeklyActive?.eventList?.Find(e => e != null && e.eventId == id);
                if (_taskDailyInfos.TryGetValue(id, out var info) && i < states.Count)
                    SetText(states[i].GetComponentInChildren<Text>(true), info.spendNum.ToString());
                var st = d != null ? (ClaimStatus)d.eventStatus : ClaimStatus.Lock;
                if (i < locks.Count) SetActive(locks[i], st == ClaimStatus.Lock);
                if (id == 17 && d != null && ribbon != null) SetText(TextAt(ribbon, "文案/50"), d.finishAmount.ToString());
            }
        }

        /// <summary>宝箱按钮前面紧挨着的兄弟节点是它的奖励图标(设计稿结构),换成配置里的奖励图标。</summary>
        private void TaskSetSiblingIcon(Transform chest, SeasonTaskEventInfo info)
        {
            if (info.rewardList == null || info.rewardList.Count == 0 || chest.parent == null) return;
            var idx = chest.GetSiblingIndex() - 1;
            if (idx < 0) return;
            var sib = chest.parent.GetChild(idx);
            if (!sib.name.StartsWith("Art/", StringComparison.Ordinal)) return;
            var img = sib.GetComponent<Image>();
            if (img == null) return;
            // 统一走 IconSet:设计稿新图标优先、保持设计稿矩形(五个宝箱图标大小一致);宝箱按钮(含 ×数量文字)本来就在图标后面,压在图标上层
            IconSet(img, info.rewardList[0]);
        }

        private void TaskClickChest(string taskId, int eventId)
        {
            var d = TaskData(taskId)?.eventList?.Find(e => e != null && e.eventId == eventId);
            if (d == null || d.eventStatus != (int)ClaimStatus.Unlocked) return;
            // 旧版 DailyTaskView 的今日 / 本周活跃度宝箱都用 *SeasonDaily 的 taskId 领取,照搬
            TaskClaimOne(TaskDailyId, eventId, _taskDailyInfos);
        }

        // ================= 每周任务 =================
        private readonly List<Transform> _taskWeekTabs = new List<Transform>();

        private void TaskPrepareWeekly()
        {
            var root = PageRoot(PageWeekly);
            var tabs = FindDeep(root, "周页签 · 可滑动");
            var content = tabs != null ? FindPath(tabs, "内容") ?? FindDeep(tabs, "内容") : null;
            if (content != null)
                for (int i = 0; i < content.childCount; i++)
                    if (content.GetChild(i).name.StartsWith("操作/第", StringComparison.Ordinal)) _taskWeekTabs.Add(content.GetChild(i));
            // 周奖励的进度条同样做成 Filled;状态框可点击领取
            var shellText = view != null ? view.GetText("pageTotal5") : null;
            var crop = shellText != null ? shellText.transform.parent?.parent : null;
            if (crop != null && _taskPages.TryGetValue(PageWeekly, out var ui))
            {
                TaskMakeFill(ImageAt(crop, "at row-progress"), ui.fullBar, ui.emptyBar);
                var state = FindPath(crop, "Art/at state");
                if (state != null && state.GetComponent<Button>() == null) state.gameObject.AddComponent<Button>();
            }
        }

        private void TaskSelectWeek(int week)
        {
            if (week > _taskUnlockedWeek)
            {
                TipPanel.ShowToast("任务未开放，请下周再来");
                var prev = _taskWeek - 1;
                if (prev >= 0 && prev < _taskWeekTabs.Count) _taskWeekTabs[prev].GetComponent<Button>()?.onClick.Invoke();   // 退回原来的页签
                return;
            }
            _taskWeek = week;
            TaskApplyWeekly();
        }

        private static readonly string[] TaskWeekNames = { "一", "二", "三", "四", "五", "六", "七", "八" };

        private void TaskApplyWeekly()
        {
            var root = PageRoot(PageWeekly);
            if (_taskPassRsp != null) _taskUnlockedWeek = Math.Max(1, Math.Min(8, _taskPassRsp.currentWeek));
            var data = TaskData(TaskWeekId);
            var list = data?.eventList ?? new List<TaskItemData>();
            for (int w = 1; w <= _taskWeekTabs.Count; w++)
            {
                var tab = _taskWeekTabs[w - 1];
                var reward = list.Find(e => e != null && e.eventId == TaskWeekRewardId * w);
                var done = reward != null ? reward.finishAmount : 0;
                foreach (var t in tab.GetComponentsInChildren<Text>(true)) t.text = $"第{TaskWeekNames[w - 1]}周  {done}/{TaskWeekTaskCount}";
                var cg = tab.GetComponent<CanvasGroup>() ?? tab.gameObject.AddComponent<CanvasGroup>();
                cg.alpha = w <= _taskUnlockedWeek ? 1f : 0.5f;   // 未开放的周变暗(点了提示,见 TaskSelectWeek)
            }

            var week = _taskWeek;
            var items = list.Where(e => e != null && (e.eventId - 1) / (TaskWeekTaskCount + 1) == week - 1
                                        && (e.eventId - 1) % (TaskWeekTaskCount + 1) + 1 <= TaskWeekTaskCount).ToList();
            TaskFillList(PageWeekly, TaskWeekId, items, _taskWeeklyInfos, !(_taskPassRsp != null && _taskPassRsp.paidType == 1));
            TaskSetClaimAll(PageWeekly, TaskHasClaimable(data));

            // 底部周奖励
            var total = view != null ? view.GetText("pageTotal5") : null;
            var crop = total != null ? total.transform.parent?.parent : null;
            var wr = list.Find(e => e != null && e.eventId == TaskWeekRewardId * week);
            _taskWeeklyInfos.TryGetValue(TaskWeekRewardId * week, out var wInfo);
            if (total != null) total.text = wInfo != null && !string.IsNullOrEmpty(wInfo.eventName) ? wInfo.eventName : $"第{TaskWeekNames[week - 1]}周累计完成{TaskWeekTaskCount}个每周任务";
            if (crop == null) return;
            var target = wInfo != null && wInfo.targetAmount > 0 ? wInfo.targetAmount : TaskWeekTaskCount;
            var finish = wr != null ? wr.finishAmount : 0;
            SetText(TextAt(crop, "文案/2/5"), $"{Mathf.Min(finish, target)}/{target}");
            if (wInfo?.rewardList != null && wInfo.rewardList.Count > 0) SetText(TextAt(crop, "文案/80"), wInfo.rewardList[0].rewardAmount.ToString());
            TaskSetFill(ImageAt(crop, "at row-progress"), (float)finish / target);
            var st = wr != null ? (ClaimStatus)wr.eventStatus : ClaimStatus.Lock;
            var stText = TextAt(crop, "文案/进行中");
            if (stText != null) stText.SetLocalText(st == ClaimStatus.Claimed ? "已领取" : st == ClaimStatus.Unlocked ? "可领取" : "进行中");
            var rewardId = TaskWeekRewardId * week;
            BindClick(FindPath(crop, "Art/at state"), () =>
            {
                var cur = TaskData(TaskWeekId)?.eventList?.Find(e => e != null && e.eventId == rewardId);
                if (cur != null && cur.eventStatus == (int)ClaimStatus.Unlocked) TaskClaimOne(TaskWeekId, rewardId, _taskWeeklyInfos);
            });
        }

        // ================= 赛季任务 =================
        private void TaskApplySeason()
        {
            var root = PageRoot(PageSeasonTask);
            var data = TaskData(TaskSeasonId);
            TaskFillList(PageSeasonTask, TaskSeasonId, data?.eventList?.Where(e => e != null).ToList() ?? new List<TaskItemData>(), _taskSeasonInfos, false);
            TaskSetClaimAll(PageSeasonTask, TaskHasClaimable(data));
            if (_taskPassRsp != null && root != null)
            {
                var t = TaskFindTextByPrefix(root, "文案/每日在线时长上限");
                if (t != null) t.SetLocalText("每日在线时长上限为120分钟（今日已在线{0}分钟）", _taskPassRsp.todaySyncTime);
            }
        }

        private static Text TaskFindTextByPrefix(Transform root, string prefix)
        {
            foreach (var t in root.GetComponentsInChildren<Text>(true))
                if (t.name.StartsWith(prefix, StringComparison.Ordinal)) return t;
            return null;
        }

        // ================= 领取 =================
        private void TaskClaimOne(string taskId, int eventId, Dictionary<int, SeasonTaskEventInfo> infos)
        {
            if (string.IsNullOrEmpty(taskId) || taskId == TASK_ID.Default.ToString()) return;
            if (_taskClaiming) return;
            EventCenterDataManager.Inst.CliamReward(taskId, eventId, 1, 0, rsp =>
            {
                if (this == null) return;
                var list = new List<CommonRewardItemData>();
                TaskAddConfigRewards(list, taskId, eventId, infos);
                if (list.Count > 0) TaskShowRewards(list);
                TaskAfterClaim();
            });
        }

        /// <summary>奖励取本地任务配置(同旧版单个领取);每周任务未购买通行证只取第一个奖励(同旧版 WeeklyTaskView)。</summary>
        private void TaskAddConfigRewards(List<CommonRewardItemData> list, string taskId, int eventId, Dictionary<int, SeasonTaskEventInfo> infos)
        {
            if (!infos.TryGetValue(eventId, out var info) || info.rewardList == null) return;
            var isWeekly = taskId == TaskWeekId;
            var paid = SeasonPassDataManager.Inst.GetSeasonPassIsPaid((SeasonPassType)Config.SeasonPassType);
            for (int i = 0; i < info.rewardList.Count; i++)
            {
                if (isWeekly && !paid && i > 0) continue;
                var r = info.rewardList[i];
                list.Add(new CommonRewardItemData { rewardType = (int)r.rewardType, RewardAmount = r.rewardAmount, rewardName = r.rewardName, pgcId = r.pgcId });
            }
        }

        private bool _taskClaiming;

        /// <summary>
        /// 每日 / 每周页的一键领取:对本页所有可领的 event 按顺序逐个调已验证的单个领取 CliamReward(taskId, eventId, 1, 0),
        /// 全部回调后合并奖励弹一次领奖、统一刷新一次。每日页 = 每日任务 1~11 + 今日活跃度宝箱 12~16 + 本周活跃度宝箱 17/18
        /// (宝箱照旧版用 *SeasonDaily 的 taskId 领);每周页 = 每周任务里所有周的可领 event(含周奖励)。
        /// 单个失败:旧版失败无提示,这里同样不弹,跳过继续领下一个。过程中按钮置灰防重复点击。
        /// </summary>
        private void TaskClaimSequential(int page)
        {
            if (_taskClaiming && Time.unscaledTime - _taskClaimStart > 10f) TaskResetClaimLock();   // 兜底:超时没回
            if (_taskClaiming || Config == null) return;
            var queue = new List<KeyValuePair<string, int>>();   // taskId, eventId
            Dictionary<int, SeasonTaskEventInfo> infos;
            if (page == PageDaily)
            {
                infos = _taskDailyInfos;
                foreach (var e in TaskData(TaskDailyId)?.eventList ?? new List<TaskItemData>())
                    if (e != null && e.eventStatus == (int)ClaimStatus.Unlocked && (TaskDailyEventIds.Contains(e.eventId) || TaskDailyChestIds.Contains(e.eventId)))
                        queue.Add(new KeyValuePair<string, int>(TaskDailyId, e.eventId));
                foreach (var e in TaskData(TaskWeeklyActiveId)?.eventList ?? new List<TaskItemData>())
                    if (e != null && e.eventStatus == (int)ClaimStatus.Unlocked && TaskWeeklyActiveIds.Contains(e.eventId))
                        queue.Add(new KeyValuePair<string, int>(TaskDailyId, e.eventId));
            }
            else
            {
                infos = _taskWeeklyInfos;
                foreach (var e in TaskData(TaskWeekId)?.eventList ?? new List<TaskItemData>())
                    if (e != null && e.eventStatus == (int)ClaimStatus.Unlocked)
                        queue.Add(new KeyValuePair<string, int>(TaskWeekId, e.eventId));
            }
            if (queue.Count == 0 || queue[0].Key == TASK_ID.Default.ToString()) return;

            // 主工程 CliamReward:回包内容为空时 succ / fail 都不回调,所以锁要有兜底(换页 / 刷新复位 + 10 秒超时);token 让复位后迟到的回调失效
            _taskClaiming = true;
            _taskClaimStart = Time.unscaledTime;
            int token = ++_taskClaimToken;
            TaskSetClaimAll(page, false);
            if (gameObject.activeInHierarchy) StartCoroutine(TaskClaimTimeout(token));
            var rewards = new List<CommonRewardItemData>();
            int index = 0;
            Action next = null;
            next = () =>
            {
                if (this == null || token != _taskClaimToken) return;
                if (index >= queue.Count)
                {
                    _taskClaiming = false;
                    if (rewards.Count > 0) TaskShowRewards(rewards);
                    TaskAfterClaim();   // 统一刷新一次(重拉任务后按钮可点状态随数据恢复)
                    return;
                }
                var item = queue[index++];
                EventCenterDataManager.Inst.CliamReward(item.Key, item.Value, 1, 0,
                    rsp => { if (this == null || token != _taskClaimToken) return; TaskAddConfigRewards(rewards, item.Key, item.Value, infos); next(); },
                    () => { if (this == null || token != _taskClaimToken) return; Debug.LogWarning($"[S18SeasonPass] 一键领取 {item.Key}/{item.Value} 失败,跳过"); next(); });
            };
            next();
        }

        private int _taskClaimToken;
        private float _taskClaimStart;

        private System.Collections.IEnumerator TaskClaimTimeout(int token)
        {
            yield return new WaitForSecondsRealtime(10f);
            if (this == null || token != _taskClaimToken || !_taskClaiming) yield break;
            Debug.LogWarning("[S18SeasonPass] 一键领取超时,复位");
            TaskResetClaimLock();
            TaskAfterClaim();
        }

        /// <summary>复位一键领取锁(并让进行中的回调失效)。</summary>
        private void TaskResetClaimLock()
        {
            _taskClaimToken++;
            _taskClaiming = false;
        }

        private void TaskShowRewards(List<CommonRewardItemData> list)
        {
            var panel = UIManager.Inst.OpenPanel<CommonRewardPanel>(PanelId.CommonRewardPanel);
            if (panel != null) panel.ShowRewards(list);
        }

        private void TaskClaimAll(string taskId)
        {
            if (string.IsNullOrEmpty(taskId) || taskId == TASK_ID.Default.ToString()) return;
            if (!TaskHasClaimable(TaskData(taskId))) return;
            EventCenterDataManager.Inst.CliamReward(taskId, 1, 2, 0, rsp =>
            {
                if (this == null) return;
                var list = new List<CommonRewardItemData>();
                if (rsp != null && rsp.rewardList != null)
                    foreach (var r in rsp.rewardList)
                        list.Add(new CommonRewardItemData
                        {
                            rewardType = r.rewardType,
                            RewardAmount = r.amount,
                            rewardName = PgcUtils.GetRewardName((BUDRewardType)r.rewardType),
                            pgcId = r.pgcIdList != null && r.pgcIdList.Count > 0 ? r.pgcIdList[0] : "",
                        });
                if (list.Count > 0) TaskShowRewards(list);
                TaskAfterClaim();   // 回包没奖励也要刷新列表和红点
            });
        }

        private void TaskAfterClaim()
        {
            AccountDataManager.Inst.BalanceInfo.Refresh();
            MessageHelper.Broadcast(MessageName.RefreshSeasonPass);
            MessageHelper.Broadcast(MessageName.RefreshSeasonPassTask);   // 本模块监听它重新拉任务列表
        }
    }
}
