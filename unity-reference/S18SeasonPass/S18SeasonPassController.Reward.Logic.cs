using System;
using System.Collections.Generic;
using System.Linq;
using Message;
using UI.Manager;
using UnityEngine;
using UnityEngine.UI;

// =====================================================================================
// S18 赛季通行证 · 赛季奖励页(第 0 页)+ 各页经验条 + 购买等级 + 一键领取 + 侧栏「赛季奖励」红点
// 数据与交互照搬旧版 SeasonRewardView / SeasonPassFreeItem / SeasonPassPaidItem / SeasonPassBaseView(S17 接口,不改服务端)。
//
// 怎么验证(进游戏打开通行证面板 PanelId 290):
//  1. 第 0 页「赛季奖励」:等级卡数量 = 服务端奖励等级数(列_12级 为模板复制),每张卡显示真实等级、普通 / 高级奖励图标与数量;
//     当前等级那张卡用黄色底(设计稿 12 级卡底),其它卡用 13 级卡底;打开时列表自动滚到当前等级附近,能一直滑到最后一级。
//  2. 卡片状态:未达标(灰字)/ 可领取(橙色状态底 + 白字「可领取」+ 呼吸动画)/ 已领取(绿字);没买高级通行证时高级奖励上显示锁。
//  3. 点「可领取」的卡 → 领取该级奖励(先普通后高级,每点一次领一项),弹 CommonRewardPanel 领奖窗,随后卡片变「已领取」、经验条与红点刷新;
//     点未达标的卡 → 时装类奖励打开奖励预览,其它弹 Toast「完成任务以解锁此奖励！」;没买通行证点高级奖励已到级的卡 → Toast「购买高级通行证即可解锁高级奖励」。
//  4. 「一键领取」:有可领取时可点 → 一次领完并弹领奖窗;没有可领取时按钮置灰。
//  5. 经验条(第 0 / 2 / 3 / 4 页顶部):「当前经验/升级所需经验」「N级」与旧版一致,进度填充按比例变化、左边不动(第 2~4 页设计稿没有填充层,运行时在进度槽里补一条)。
//  6. 「购买等级」(四页都有)→ 弹出旧版 SkipSeasonConfirmPanel(50 钻买 1 级),买完外壳 RefreshData → Reload,等级与经验条刷新。
//  7. 「套装预览」→ 旧版 PaidPackRewardPanel 高级奖励预览;「预览50级大奖」→ 最后一级可领取时领取,否则同样打开奖励预览;右上角规则按钮 → GashaponRulePanel 旧规则。
//  8. 侧栏「赛季奖励」页签(第 0 / 2 / 3 / 4 页)右上角红点:有任何可领取奖励时显示,领完消失。
// =====================================================================================
namespace Bud.S18SeasonPass
{
    public partial class S18SeasonPassController
    {
        private const string RewardAtlasPath = "Assets/Loadable/UI/UIPanel/SeasonPassPanel/SeasonPassPanel.spriteatlas";
        private const string RewardRulePath = "Assets/Loadable/UI/UIPanel/SeasonPassPanel/SeasonPassRule.json";
        private static readonly Color RewardClaimableBgColor = new Color(1f, 0.55f, 0.2f, 1f);

        private SeasonPassListRsp _rewardRsp;
        private bool _rewardCreatedNodes;
        private bool _rewardScrollPending = true;

        // 第 0 页节点
        private Transform _rewardContent, _rewardTemplate, _rewardFinalCol;
        private ScrollRect _rewardScroll;
        private Vector2 _rewardStep;
        private readonly List<Transform> _rewardCards = new List<Transform>();
        private Sprite _rewardBgCurrent, _rewardBgNormal, _rewardStatusBgClaimed, _rewardStatusBgLocked;
        private Color _rewardTextClaimed = new Color(0.416f, 0.725f, 0.494f, 1f), _rewardTextLocked = new Color(0.275f, 0.212f, 0.486f, 0.6f);
        private Button _rewardClaimAllBtn;

        // 经验条(第 0/2/3/4 页)
        private class RewardXpBar { public Text exp, level; public RectTransform fill; public float fullWidth; }
        private readonly List<RewardXpBar> _rewardXpBars = new List<RewardXpBar>();
        private readonly List<GameObject> _rewardRedDots = new List<GameObject>();

        // ================= 挂钩 =================
        partial void RewardCreate()
        {
            RewardCacheNodes();
            MessageHelper.AddListener(MessageName.RefreshSeasonPass, RewardOnRefreshMessage);
            SeasonPassDataManager.Inst.OnSeasonPassDataChangeHandler += RewardOnDataChange;
        }

        partial void RewardRefresh()
        {
            var cached = SeasonPassDataManager.Inst.GetSeasonPassList(SeasonPassDataManager.Inst.CurrentSeasonPassType);
            if (cached != null) RewardApply(cached);
            RewardRequest();
        }

        partial void RewardPageShown(int index)
        {
            if (index == PageReward) { _rewardScrollPending = true; RewardScrollToCurrent(); }
        }

        partial void RewardAction(string key, ref bool handled)
        {
            switch (key)
            {
                case "claim": handled = true; RewardOnClaimAll(); break;
                case "action5": case "pageAction21": case "pageAction32": case "pageAction43":
                    handled = true; RewardShowBuyLevel(key); break;
                case "action3": handled = true; RewardShowPreview(true); break;
                case "action4": handled = true; RewardOnFinalClick(); break;
                case "rulesLink":
                    handled = true;
                    UIManager.Inst.OpenPanel<GashaponRulePanel>(PanelId.GashaponRulePanel, RewardRulePath);
                    break;
                case "reward": handled = true; break;   // 已在赛季奖励页
                default:
                    // 卡片按钮在 RewardApply 里已直接 BindClick(去掉了 View 的 cardNN 监听),这里只吞掉残留事件
                    if (key.StartsWith("card", StringComparison.Ordinal) && key.Length <= 6) handled = true;
                    break;
            }
        }

        // ================= 消息 / 取数 =================
        private void RewardOnRefreshMessage()
        {
            if (this == null) { MessageHelper.RemoveListener(MessageName.RefreshSeasonPass, RewardOnRefreshMessage); return; }
            RewardRequest();
        }

        private void RewardOnDataChange(SeasonPassType type, SeasonPassListRsp rsp)
        {
            if (this == null) { SeasonPassDataManager.Inst.OnSeasonPassDataChangeHandler -= RewardOnDataChange; return; }
            if (type != SeasonPassDataManager.Inst.CurrentSeasonPassType || rsp == null) return;
            RewardApply(rsp);
        }

        private void RewardRequest()
        {
            SeasonPassDataManager.Inst.GetSeasonPassList(SeasonPassDataManager.Inst.CurrentSeasonPassType, (ok, rsp) =>
            {
                if (this == null || !ok || rsp == null) return;
                RewardApply(rsp);   // OnSeasonPassDataChangeHandler 已刷新过一次,这里保险再刷(幂等)
                // 旧 SeasonPassBaseView.RequestSeasonPassData:预购结算弹窗 + 广播数据更新
                if (SeasonPassDataManager.Inst.ConsumePrePaidRewardPopup(SeasonPassDataManager.Inst.CurrentSeasonPassType)) RewardShowPrePaidPopup();
                MessageHelper.Broadcast(MessageName.SeasonPassDataUpdate);
            });
        }

        // ================= 节点缓存 =================
        private void RewardCacheNodes()
        {
            if (_rewardCreatedNodes) return;
            _rewardCreatedNodes = true;
            var p0 = PageRoot(PageReward);
            if (p0 != null)
            {
                var list = FindPath(p0, "内容区|奖励列表 · 可滑动");
                _rewardScroll = list ? list.GetComponent<ScrollRect>() : null;
                _rewardContent = FindPath(list, "内容");
                _rewardTemplate = FindPath(_rewardContent, "列_12级");
                var c13 = FindPath(_rewardContent, "列_13级");
                _rewardStep = StepBetween(_rewardTemplate, c13);
                if (_rewardStep == Vector2.zero) _rewardStep = new Vector2(241, 0);
                _rewardBgCurrent = RewardSprite(_rewardTemplate, "切图/列_12级");
                _rewardBgNormal = RewardSprite(c13, "切图/列_13级") ?? _rewardBgCurrent;
                _rewardStatusBgClaimed = RewardSprite(_rewardTemplate, "切图/状态底_12级");
                _rewardStatusBgLocked = RewardSprite(c13, "切图/状态底_13级") ?? _rewardStatusBgClaimed;
                var t12 = TextAt(_rewardTemplate, "文案/已领取"); if (t12) _rewardTextClaimed = t12.color;
                var t13 = TextAt(c13, "文案/未达标"); if (t13) _rewardTextLocked = t13.color;
                // 设计稿的 13~15 级卡只做样式来源,运行时全部由模板复制
                foreach (var n in new[] { "列_13级", "列_14级", "列_15级" }) SetActive(FindPath(_rewardContent, n), false);
                _rewardFinalCol = FindPath(p0, "内容区|操作/预览50级大奖");
                var claimT = FindPath(p0, "内容区|操作/一键领取");
                _rewardClaimAllBtn = claimT ? claimT.GetComponent<Button>() : null;

                var fill = FindPath(p0, "内容区|切图/进度填充");
                var groove = FindPath(p0, "内容区|切图/进度槽");
                _rewardXpBars.Add(new RewardXpBar
                {
                    exp = TextAt(FindPath(p0, "内容区"), "文案/50/100经验"),
                    level = FindPath(p0, "内容区|文案/12级") ? FindPath(p0, "内容区|文案/12级").GetComponent<Text>() : null,
                    fill = fill as RectTransform,
                    fullWidth = groove ? ((RectTransform)groove).rect.width : (fill ? ((RectTransform)fill).rect.width : 0),
                });
                RewardAddRedDot(p0);

                // 第 2~4 页经验条:设计稿只有进度槽,运行时按第 0 页的填充切图补一条填充
                var fillImg = fill ? fill.GetComponent<Image>() : null;
                foreach (var pi in new[] { PageDaily, PageWeekly, PageSeasonTask })
                {
                    var page = PageRoot(pi);
                    if (page == null) continue;
                    RewardAddRedDot(page);
                    var bar = FindDeep(page, "at xpbar");
                    if (bar == null) continue;
                    var slot = FindPath(bar, "Art/进度槽") as RectTransform;
                    _rewardXpBars.Add(new RewardXpBar
                    {
                        exp = TextAt(bar, "文案/0/100经验"),
                        level = TextAt(bar, "文案/0级"),
                        fill = RewardMakeFill(slot, fillImg),
                        fullWidth = slot ? slot.rect.width : 0,
                    });
                }
            }
        }

        private static Sprite RewardSprite(Transform root, string path)
        {
            var t = FindPath(root, path);
            var img = t ? t.GetComponent<Image>() : null;
            return img ? img.sprite : null;
        }

        private static RectTransform RewardMakeFill(RectTransform slot, Image src)
        {
            if (slot == null || src == null) return null;
            var go = new GameObject("Reward/进度填充", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            go.layer = slot.gameObject.layer;
            var rt = (RectTransform)go.transform;
            rt.SetParent(slot, false);
            rt.anchorMin = new Vector2(0, 0); rt.anchorMax = new Vector2(0, 1); rt.pivot = new Vector2(0, 0.5f);
            rt.anchoredPosition = Vector2.zero; rt.sizeDelta = new Vector2(0, 0);
            var img = go.GetComponent<Image>();
            img.sprite = src.sprite; img.type = src.type; img.color = src.color; img.raycastTarget = false;
            img.fillMethod = src.fillMethod; img.fillOrigin = src.fillOrigin;
            return rt;
        }

        /// <summary>侧栏「赛季奖励」页签右上角的红点:复制设计稿红点切图(Art/at note-dot,那个是任务红点,不动它),挂在赛季奖励页签按钮下。</summary>
        private void RewardAddRedDot(Transform page)
        {
            var tab = FindPath(page, "操作/查看赛季奖励母版");
            var src = FindPath(page, "Art/at note-dot");
            var srcImg = src ? src.GetComponent<Image>() : null;
            if (tab == null || srcImg == null) return;
            var go = new GameObject("Reward/赛季奖励红点", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            go.layer = tab.gameObject.layer;
            var rt = (RectTransform)go.transform;
            rt.SetParent(tab, false);
            rt.anchorMin = rt.anchorMax = rt.pivot = new Vector2(0.5f, 0.5f);
            // 设计稿:红点相对「赛季任务」页签左上 (205,-25),79×79;页签 304×118 → 相对页签中心 (92.5, 44.5)
            rt.sizeDelta = ((RectTransform)src).rect.size;
            rt.anchoredPosition = new Vector2(92.5f, 44.5f);
            var img = go.GetComponent<Image>();
            img.sprite = srcImg.sprite; img.color = srcImg.color; img.raycastTarget = false; img.preserveAspect = srcImg.preserveAspect;
            go.SetActive(false);
            _rewardRedDots.Add(go);
        }

        // ================= 刷新 =================
        private void RewardApply(SeasonPassListRsp rsp)
        {
            if (rsp == null || view == null) return;
            _rewardRsp = rsp;
            RewardCacheNodes();
            var free = rsp.rewardList ?? new List<SeasonPassItemInfo>();
            var paid = rsp.paidRewardList ?? new List<SeasonPassItemInfo>();
            bool isPaid = rsp.isPaid == 1;
            int tier = rsp.progressInfo != null ? rsp.progressInfo.currentTier : SeasonPassDataManager.Inst.GetCurDay(free);
            int count = Math.Max(free.Count, paid.Count);

            // ---- 等级卡 ----
            if (_rewardTemplate != null && count > 0)
            {
                int before = _rewardCards.Count;
                EnsureClones(_rewardTemplate, count, _rewardStep, _rewardCards);
                for (int i = Math.Max(1, before); i < _rewardCards.Count; i++) RewardStripMotion(_rewardCards[i]);
                for (int i = 0; i < count; i++)
                {
                    var card = _rewardCards[i];
                    int idx = i;
                    BindClick(card, () => RewardOnCardClick(idx));
                    RewardFillCard(card, i + 1, i < free.Count ? free[i] : null, i < paid.Count ? paid[i] : null, isPaid, i + 1 == tier);
                }
                FitContent(_rewardContent, _rewardCards[count - 1], true, Mathf.Max(8f, _rewardStep.x * 0.5f));
            }

            // ---- 50 级大奖列(最后一级)----
            if (_rewardFinalCol != null && count > 0)
            {
                var f = count - 1 < free.Count ? free[count - 1] : null;
                var pd = count - 1 < paid.Count ? paid[count - 1] : null;
                SetText(TextAt(_rewardFinalCol, "文案/50级"), count + "级");
                RewardSetIcon(_rewardFinalCol, "切图/图标_50级普通", f);
                RewardSetIcon(_rewardFinalCol, "切图/图标_50级高级", pd);
                SetText(TextAt(_rewardFinalCol, "文案/X10"), RewardAmountText(f));
                SetText(TextAt(_rewardFinalCol, "文案/傩面飞渡"), RewardAmountText(pd));
                SetActive(FindPath(_rewardFinalCol, "切图/锁_50级"), pd != null && !isPaid);
                RewardSetStatus(FindPath(_rewardFinalCol, "切图/状态底_50级"), TextAt(_rewardFinalCol, "文案/未达标"), f, pd, isPaid);
            }

            // ---- 经验条 ----
            if (rsp.progressInfo != null)
            {
                var pi = rsp.progressInfo;
                string expStr = pi.start + "/" + LocalizationManager.Inst.GetLocalizedText("{0}经验", pi.end);
                float ratio = pi.end > 0 ? Mathf.Clamp01((float)pi.start / pi.end) : 0f;
                if (SeasonPassDataManager.Inst.FinishAllProgress(free)) ratio = 1f;
                foreach (var bar in _rewardXpBars)
                {
                    SetText(bar.exp, expStr);
                    if (bar.level != null) bar.level.SetLocalText("{0}级", pi.currentTier);
                    RewardSetFill(bar, ratio);
                }
            }

            // ---- 一键领取 / 红点 ----
            bool canClaim = free.Exists(x => x.BudRewardStatus == BudRewardStatus.Unlocked) || paid.Exists(x => x.BudRewardStatus == BudRewardStatus.Unlocked);
            if (_rewardClaimAllBtn != null) _rewardClaimAllBtn.interactable = canClaim;
            foreach (var dot in _rewardRedDots) if (dot != null && dot.activeSelf != canClaim) dot.SetActive(canClaim);

            RewardScrollToCurrent();
        }

        /// <summary>复制出来的卡片去掉进场动效组件(复制时模板可能正在 PopIn,会把中间缩放当成静止缩放),复位缩放。</summary>
        private static void RewardStripMotion(Transform card)
        {
            foreach (var m in card.GetComponents<S18SeasonPassMotion>()) DestroyImmediate(m);
            card.localScale = Vector3.one;
            card.localRotation = Quaternion.identity;
            var g = card.GetComponent<CanvasGroup>(); if (g != null) g.alpha = 1;
        }

        private void RewardFillCard(Transform card, int level, SeasonPassItemInfo free, SeasonPassItemInfo paid, bool isPaid, bool isCurrent)
        {
            var bg = FindPath(card, "切图/列_12级");
            var bgImg = bg ? bg.GetComponent<Image>() : null;
            if (bgImg != null) { var s = isCurrent ? _rewardBgCurrent : _rewardBgNormal; if (s != null) bgImg.sprite = s; }
            SetText(TextAt(card, "文案/12级"), level + "级");

            // 两个「文案/X10」:上面的是普通奖励数量,下面的是高级奖励数量
            var amounts = FindAllDeep(card, "文案/X10");
            amounts.Sort((a, b) => ((RectTransform)b).anchoredPosition.y.CompareTo(((RectTransform)a).anchoredPosition.y));
            var freeAmt = amounts.Count > 0 ? amounts[0].GetComponent<Text>() : null;
            var paidAmt = amounts.Count > 1 ? amounts[1].GetComponent<Text>() : null;

            RewardSetIcon(card, "切图/图标_12级普通", free);
            SetText(freeAmt, RewardAmountText(free));
            if (freeAmt) SetActive(freeAmt.transform, free != null);
            RewardSetIcon(card, "切图/图标_12级高级", paid);
            SetText(paidAmt, RewardAmountText(paid));
            if (paidAmt) SetActive(paidAmt.transform, paid != null);
            SetActive(FindPath(card, "切图/锁_13级"), paid != null && !isPaid);

            RewardSetStatus(FindPath(card, "切图/状态底_12级"), TextAt(card, "文案/已领取"), free, paid, isPaid);
        }

        /// <summary>奖励图标:统一走 IconSet(设计稿新图标优先,其次旧版图集;保持设计稿矩形),数量文字放到图标上层。</summary>
        private void RewardSetIcon(Transform root, string path, SeasonPassItemInfo data)
        {
            var t = FindPath(root, path);
            if (t == null) return;
            SetActive(t, data != null);
            if (data == null) return;
            var img = t.GetComponent<Image>();
            if (img == null) return;
            IconSet(img, data);
            IconRaiseTexts(root, img);
        }

        private static string RewardAmountText(SeasonPassItemInfo data)
        {
            if (data == null) return "";
            var amount = data.RewardAmount();
            return "X" + Math.Max(1, amount);
        }

        private enum RewardCardState { Locked, Claimable, Claimed }

        private static RewardCardState RewardStateOf(SeasonPassItemInfo free, SeasonPassItemInfo paid, bool isPaid)
        {
            bool fu = free != null && free.BudRewardStatus == BudRewardStatus.Unlocked;
            bool pu = paid != null && paid.BudRewardStatus == BudRewardStatus.Unlocked;
            if (fu || pu) return RewardCardState.Claimable;
            bool fc = free == null || free.BudRewardStatus == BudRewardStatus.Claimed;
            bool pc = paid == null || paid.BudRewardStatus == BudRewardStatus.Claimed || (!isPaid && paid.BudRewardStatus == BudRewardStatus.Lock);
            if (fc && pc && (free != null || paid != null)) return RewardCardState.Claimed;
            return RewardCardState.Locked;
        }

        private void RewardSetStatus(Transform statusBg, Text statusText, SeasonPassItemInfo free, SeasonPassItemInfo paid, bool isPaid)
        {
            var state = RewardStateOf(free, paid, isPaid);
            var bgImg = statusBg ? statusBg.GetComponent<Image>() : null;
            if (bgImg != null)
            {
                bgImg.sprite = state == RewardCardState.Claimed ? (_rewardStatusBgClaimed ?? bgImg.sprite) : (_rewardStatusBgLocked ?? bgImg.sprite);
                bgImg.color = state == RewardCardState.Claimable ? RewardClaimableBgColor : Color.white;
            }
            if (statusText != null)
            {
                statusText.text = state == RewardCardState.Claimable ? "可领取" : state == RewardCardState.Claimed ? "已领取" : "未达标";
                statusText.color = state == RewardCardState.Claimable ? Color.white : state == RewardCardState.Claimed ? _rewardTextClaimed : _rewardTextLocked;
            }
            // 可领取:状态底和文字呼吸(旧版是 animator「LoginGiftPanel_prompt」,新稿没有对应动画,用生成的 Breathe 动效代替)
            RewardSetBreathe(statusBg, state == RewardCardState.Claimable);
            RewardSetBreathe(statusText ? statusText.transform : null, state == RewardCardState.Claimable);
        }

        private static void RewardSetBreathe(Transform t, bool on)
        {
            if (t == null) return;
            S18SeasonPassMotion m = null;
            foreach (var c in t.GetComponents<S18SeasonPassMotion>()) if (c.preset == S18SeasonPassMotion.Preset.Breathe) m = c;
            if (on)
            {
                if (m == null)
                {
                    t.localScale = Vector3.one;
                    m = t.gameObject.AddComponent<S18SeasonPassMotion>();
                    m.enabled = false;
                    m.preset = S18SeasonPassMotion.Preset.Breathe;
                }
                if (!m.enabled) m.enabled = true;
            }
            else if (m != null && m.enabled) m.enabled = false;   // OnDisable 复位缩放
        }

        private static void RewardSetFill(RewardXpBar bar, float ratio)
        {
            var rt = bar.fill;
            if (rt == null || bar.fullWidth <= 0) return;
            var img = rt.GetComponent<Image>();
            bool filled = img != null && img.type == Image.Type.Filled;
            float w = filled ? bar.fullWidth : bar.fullWidth * ratio;
            SetActive(rt, ratio > 0.001f);
            // 改宽度时左边不动(锚点在左右同一处时有效;第 2~4 页补的填充锚在左边,pivot.x=0)
            float old = rt.rect.width;
            rt.SetSizeWithCurrentAnchors(RectTransform.Axis.Horizontal, w);
            if (Mathf.Approximately(rt.anchorMin.x, rt.anchorMax.x)) rt.anchoredPosition += new Vector2(rt.pivot.x * (w - old), 0);
            if (filled) img.fillAmount = ratio;
        }

        /// <summary>滚到当前等级附近(当前等级卡放在可视区左起第二格);旧版按已领取数 / 总数设 horizontalNormalizedPosition。</summary>
        private void RewardScrollToCurrent()
        {
            if (!_rewardScrollPending || _rewardScroll == null || _rewardContent == null || _rewardRsp == null || _rewardCards.Count == 0) return;
            if (!_rewardScroll.gameObject.activeInHierarchy) return;
            _rewardScrollPending = false;
            Canvas.ForceUpdateCanvases();
            var content = (RectTransform)_rewardContent;
            var viewport = _rewardScroll.viewport != null ? _rewardScroll.viewport : (RectTransform)_rewardScroll.transform;
            float max = content.rect.width - viewport.rect.width;
            if (max <= 0) { _rewardScroll.horizontalNormalizedPosition = 0; return; }
            int tier = _rewardRsp.progressInfo != null ? _rewardRsp.progressInfo.currentTier : 1;
            int idx = Mathf.Clamp(tier - 1, 0, _rewardCards.Count - 1);
            float target = Mathf.Abs(_rewardStep.x) * Mathf.Max(0, idx - 1);
            _rewardScroll.StopMovement();
            _rewardScroll.horizontalNormalizedPosition = Mathf.Clamp01(target / max);
        }

        // ================= 点击 =================
        private void RewardOnCardClick(int index)
        {
            var rsp = _rewardRsp;
            if (rsp == null) return;
            var free = rsp.rewardList != null && index < rsp.rewardList.Count ? rsp.rewardList[index] : null;
            var paid = rsp.paidRewardList != null && index < rsp.paidRewardList.Count ? rsp.paidRewardList[index] : null;
            if (free != null && free.BudRewardStatus == BudRewardStatus.Unlocked) { RewardClaimOne(free, false); return; }
            if (paid != null && paid.BudRewardStatus == BudRewardStatus.Unlocked) { RewardClaimOne(paid, true); return; }
            if (free != null && free.BudRewardStatus == BudRewardStatus.Lock)
            {
                // 旧 OnClickFreeItem
                if (RewardIsPgcCloth(free)) RewardShowPreview(false);
                else TipPanel.ShowToast("完成任务以解锁此奖励！");
                return;
            }
            if (paid != null && paid.BudRewardStatus == BudRewardStatus.Lock)
            {
                // 旧 OnClickPaidItem
                if (RewardIsPgcCloth(paid)) RewardShowPreview(true);
                else if (paid.BudRewardType == BUDRewardType.RewardSeasonPassRandomPack) RewardShowRandomPackPreview();
                else if (SeasonPassDataManager.Inst.GetSeasonPassIsPaid(SeasonPassDataManager.Inst.CurrentSeasonPassType)) TipPanel.ShowToast("完成任务以解锁此奖励！");
                else TipPanel.ShowToast("购买高级通行证即可解锁高级奖励");
            }
        }

        private void RewardOnFinalClick()
        {
            var rsp = _rewardRsp;
            int count = rsp == null ? 0 : Math.Max(rsp.rewardList?.Count ?? 0, rsp.paidRewardList?.Count ?? 0);
            if (count > 0)
            {
                var free = rsp.rewardList != null && count - 1 < rsp.rewardList.Count ? rsp.rewardList[count - 1] : null;
                var paid = rsp.paidRewardList != null && count - 1 < rsp.paidRewardList.Count ? rsp.paidRewardList[count - 1] : null;
                if (free != null && free.BudRewardStatus == BudRewardStatus.Unlocked) { RewardClaimOne(free, false); return; }
                if (paid != null && paid.BudRewardStatus == BudRewardStatus.Unlocked) { RewardClaimOne(paid, true); return; }
            }
            RewardShowPreview(true);
        }

        private static bool RewardIsPgcCloth(SeasonPassItemInfo data)
        {
            try { return data != null && data.IsPgcCloth(); } catch (Exception) { return false; }
        }

        private void RewardClaimOne(SeasonPassItemInfo data, bool isPaid)
        {
            SeasonPassDataManager.Inst.Claim(SeasonPassDataManager.Inst.CurrentSeasonPassType, data, (ok, rsp) =>
            {
                if (!ok || this == null || rsp == null) return;
                if (data.BudRewardType != BUDRewardType.RewardPgcResource) AccountDataManager.Inst.BalanceInfo.Refresh();
                data.rewardStatus = (int)BudRewardStatus.Claimed;   // 旧 SyncRewardState:先本地置已领取,随后广播重新取数
                if (_rewardRsp != null) RewardApply(_rewardRsp);
                RewardOnClaimedSuccess(rsp);
            });
        }

        private void RewardOnClaimAll()
        {
            var rsp = _rewardRsp;
            bool can = rsp != null && ((rsp.rewardList?.Exists(x => x.BudRewardStatus == BudRewardStatus.Unlocked) ?? false) || (rsp.paidRewardList?.Exists(x => x.BudRewardStatus == BudRewardStatus.Unlocked) ?? false));
            if (!can) return;
            SeasonPassDataManager.Inst.ClaimAll(SeasonPassDataManager.Inst.CurrentSeasonPassType, (ok, claimRsp) =>
            {
                if (ok && this != null && claimRsp != null) RewardOnClaimedSuccess(claimRsp);
            });
        }

        /// <summary>照搬旧 SeasonRewardView.OnClaimedSuccess:弹 CommonRewardPanel,没买通行证时展示「买了能拿」的高级奖励,刷新余额并广播 RefreshSeasonPass。</summary>
        private void RewardOnClaimedSuccess(SeasonPassClaimRsp rsp)
        {
            var panel = UIManager.Inst.OpenPanel<CommonRewardPanel>(PanelId.CommonRewardPanel);
            var rewardList = new List<CommonRewardItemData>();
            bool bo14 = false, bo15 = false;
            if (rsp.rewardList != null)
                foreach (var rewardInfo in rsp.rewardList)
                {
                    if (rewardInfo.pgcId == "10400508" || rewardInfo.pgcId == "11300369") { bo14 = true; continue; }
                    if (rewardInfo.pgcId == "10400513" || rewardInfo.pgcId == "12100153" || rewardInfo.pgcId == "11400090") { bo15 = true; continue; }
                    var item = new CommonRewardItemData();
                    item.rewardType = rewardInfo.rewardType;
                    item.RewardAmount = rewardInfo.amount;
                    item.pgcId = rewardInfo.pgcId;
                    item.rewardName = rewardInfo.rewardType == (int)BUDRewardType.RewardPgcResource ? "" : PgcUtils.GetRewardName((BUDRewardType)rewardInfo.rewardType);
                    item.isConverted = rewardInfo.isReplaced == 1;
                    rewardList.Add(item);
                }
            RewardInsertSuits(rewardList, bo14, bo15);
            if (panel != null)
            {
                panel.ShowRewards(rewardList);
                var type = SeasonPassDataManager.Inst.CurrentSeasonPassType;
                if (SeasonPassDataManager.Inst.GetSeasonPassIsPaid(type)) panel.ShowReplaceTex(rsp.replaceRewardList);
                else
                {
                    var datas = SeasonPassDataManager.Inst.GetSeasonPassList(type);
                    if (datas != null && datas.paidRewardList != null && datas.progressInfo != null)
                    {
                        var unlockedPaid = datas.paidRewardList.Take(datas.progressInfo.currentTier).ToList();
                        if (unlockedPaid.Count > 0) panel.ShowSeasonPassRewards(RewardConvertToItemData(unlockedPaid), true);
                        else panel.ShowReplaceTex(rsp.replaceRewardList);
                    }
                }
            }
            _rewardScrollPending = true;
            AccountDataManager.Inst.BalanceInfo.Refresh();
            MessageHelper.Broadcast(MessageName.RefreshSeasonPass);   // 本模块与外部都靠它重新取数
        }

        private void RewardInsertSuits(List<CommonRewardItemData> list, bool bo14, bool bo15)
        {
            if (bo14) list.Insert(0, new CommonRewardItemData { rewardName = "焦糖布丁喵套装", IconSp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(RewardAtlasPath, "icon_ma", gameObject) });
            if (bo15) list.Insert(0, new CommonRewardItemData { rewardName = "天使小羊套装", IconSp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(RewardAtlasPath, "icon_ma1", gameObject) });
        }

        /// <summary>照搬旧 ConvertToRewardItemData。</summary>
        private List<CommonRewardItemData> RewardConvertToItemData(List<SeasonPassItemInfo> unlockedPaidRewards)
        {
            var result = new List<CommonRewardItemData>();
            bool bo14 = false, bo15 = false;
            foreach (var reward in unlockedPaidRewards)
            {
                if (reward.rewardInfo == null || reward.rewardInfo.itemList == null) continue;
                foreach (var item in reward.rewardInfo.itemList)
                {
                    var d = new CommonRewardItemData();
                    d.rewardType = item.rewardType;
                    d.RewardAmount = item.amount;
                    d.pgcId = item.pgcIdList != null && item.pgcIdList.Count > 0 ? item.pgcIdList.First() : "";
                    if (item.rewardType == (int)BUDRewardType.RewardPgcResource)
                    {
                        if (d.pgcId == "10400508" || d.pgcId == "11300369") { bo14 = true; continue; }
                        if (d.pgcId == "10400513" || d.pgcId == "12100153" || d.pgcId == "11400090") { bo15 = true; continue; }
                        if (d.pgcId == "11300350") { d.bundleId = "87"; d.rewardType = (int)BUDRewardType.RewardPgcBundle; }
                        if (d.pgcId == "10100054") { d.bundleId = "81"; d.rewardType = (int)BUDRewardType.RewardPgcBundle; }
                        if (d.pgcId == "10400497") { d.bundleId = "199"; d.rewardType = (int)BUDRewardType.RewardPgcBundle; }
                    }
                    d.rewardName = item.rewardType == (int)BUDRewardType.RewardPgcResource ? "" : PgcUtils.GetRewardName((BUDRewardType)item.rewardType);
                    d.isConverted = item.isReplaced == 1;
                    result.Add(d);
                }
            }
            RewardInsertSuits(result, bo14, bo15);
            return result;
        }

        /// <summary>旧 SeasonPassBaseView.ShowSeasonReward:预购通行证的结算弹窗。</summary>
        private void RewardShowPrePaidPopup()
        {
            const string atlas = "Assets/Arts/UI/UIPanel/RechargePanel/SeasonPrePack/SeasonPrePackAtlas.spriteatlas";
            var list = new List<CommonRewardItemData>
            {
                new CommonRewardItemData { IconSp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(atlas, "season", gameObject), RewardAmount = 1, rewardName = "高级通行证" }
            };
            var panel = UIManager.Inst.OpenPanel<CommonRewardPanel>(PanelId.CommonRewardPanel);
            if (panel != null) panel.ShowRewards(list);
        }

        /// <summary>旧 ShowSkipConfirmPanel:SkipSeasonConfirmPanel(50 钻买 1 级),弹窗信息框放在点击的「购买等级」按钮处。</summary>
        private void RewardShowBuyLevel(string key)
        {
            var panel = UIManager.Inst.OpenPanel<SkipSeasonConfirmPanel>(PanelId.SkipSeasonConfirmPanel);
            var btn = view != null ? view.GetButton(key) : null;
            if (panel != null && btn != null) panel.AdjustPosition(btn.transform.position);
        }

        /// <summary>旧 ShowRewardPreview:PaidPackRewardPanel 奖励预览(旧版的 Texture2DBg 背景图是旧 prefab 上的序列化字段,新视图没有,不调 SetStyle)。</summary>
        private void RewardShowPreview(bool isPaid)
        {
            var panel = UIManager.Inst.OpenPanel<PaidPackRewardPanel>(PanelId.PaidPackRewardPanel);
            if (panel == null) return;
            panel.bundleBgColorStr = "#FFFFFF";
            panel.bundleContentBgColorStr = "#FF9B9B";
            panel.SetEventPreview(SeasonPassDataManager.Inst.GetSeasonPassRewardDatas(SeasonPassDataManager.Inst.CurrentSeasonPassType, isPaid), "", null);
        }

        private void RewardShowRandomPackPreview()
        {
            var sp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(RewardAtlasPath, "icon_36_min", gameObject);
            var panel = UIManager.Inst.OpenPanel<CurrencyTipsPanel>(PanelId.CurrencyTipsPanel);
            if (panel != null) panel.UpdateUI(sp, "通行证随机礼包", null, "打开后有机会获得以下奖励之一：30个通行证币；10个通行证币；10个徽章；200个金币");
        }
    }
}
