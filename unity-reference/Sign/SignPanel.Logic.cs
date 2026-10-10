// 累计充值福利(PanelId 207,新视觉 Sign)的业务逻辑。手写文件:BUD UI Studio「覆盖到 Unity」不会生成、也不会覆盖它。
// ⚠ 别跟着模块目录一起删(删了界面只剩设计稿占位数据);BUD_UI_Studio/unity-reference/Sign/ 里有一份副本。
//
// 原则:新界面只替换素材和动效,服务端数据与领取流程一律沿用旧 CumulativeRechargePanel / CumulativeRechargeItem 的调用,
// 不新增、不修改任何服务端请求:
//   数据      IAPDataManager.GetProductInfo → rechargeBenefits(totalRecharged + rechargeLevelList);收到 RefreshCumData 时重拉
//   普通档    POST ClaimRechargeBenifits {rewardId, pgcId} → CommonRewardPanel 展示 → 广播 RefreshCumData(与旧 CumulativeRechargeItem 相同)
//   自选档    isOptionalReward == 1 打开旧的 OptionalClaimRewardPanel(208),其余打开 OfficalClaimRewardPanel(209),走旧流程
//   前往充值  关掉本面板;充值界面没开着(从别的入口进来)就顺手打开充值界面(钻石页)
//
// 设计稿主页只有 8 张卡(6/30/68/98/188/648/1288/3688 元)。卡片按「金额」对上服务端档位;
// 服务端有、设计稿没有的档位,复制一张卡补上(图标用旧图集 Cumulative_Icon_<序号>,和旧面板一样),保证每一档都能看到、能领;
// 设计稿有、服务端没有的档位隐藏并打错误日志。
using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using Game.Store;
using Message;
using Network;
using Network.Http;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UI.BaseWidgets;
using UI.Manager;
using UnityEngine;
using UnityEngine.UI;

namespace Bud.Sign
{
    public partial class SignPanel
    {
        // 设计稿里的卡片:卡片按钮标识 / 动态文本前缀 / 详情页上「领取 / 兑换 / 前往充值」按钮的标识(没有详情页为 null)
        private static readonly (string card, string text, string detailCta)[] DesignCards =
        {
            ("cardHair", "cardHair", "hairDetailCta"),
            ("cardDress", "cardDress", null),
            ("cardShoe", "cardShoe", "shoeDetailCta"),
            ("cardCoin", "cardCoin", null),
            ("cardBench", "cardBench", null),
            ("cardAction", "cardAction", "choiceActionCta"),
            ("cardEffect", "cardEffect", "choiceEffectCta"),
            ("cardWing", "cardWing", "wingCta"),
        };

        private const int StatusLock = 1, StatusUnlocked = 2, StatusClaimed = 3;   // 与旧代码用的 ClaimStatus 一致
        private static readonly Regex Number = new Regex(@"\d+(?:\.\d+)?");

        private class Card
        {
            public RectTransform rt;
            public Text status, rewardName, amount;
            public Image statusSurface, icon;
            public Button button, detailCta;
            public Text detailCtaLabel;
            public string detailCtaUnlockedText;
            public int designAmount;      // 设计稿上的金额(补出来的卡为 0)
            public float designLeftOffset; // 设计稿里卡片中心离 Content 左边缘的距离
            public RechargeLevelData data;
            public int serverIndex;
            public bool cloned;
        }

        private struct StatusStyle { public Sprite sprite; public Color color; public string text; }

        private readonly List<Card> _designCards = new List<Card>();
        private readonly List<Card> _clones = new List<Card>();
        private readonly List<Card> _shown = new List<Card>();   // 当前显示的卡,按金额从小到大
        private readonly Dictionary<int, StatusStyle> _styles = new Dictionary<int, StatusStyle>();
        private RectTransform _content, _rail, _filled;
        private ScrollRect _scroll;
        private float _contentWidth0, _firstOffset, _spacing, _rightPad;
        private CanvasGroup _contentGroup;
        private bool _resetScroll;
        private string _amountTemplate = "0 元", _totalTemplate, _nextTemplate;
        private Card _cloneTemplate;
        private RechargeBenifits _data;
        private bool _wired, _closing;

        partial void OnPanelCreate()
        {
            MessageHelper.AddListener(MessageName.RefreshCumData, RefreshData);
        }

        protected override void OnDestroy()
        {
            base.OnDestroy();
            MessageHelper.RemoveListener(MessageName.RefreshCumData, RefreshData);
        }

        partial void OnPanelShow(object[] args)
        {
            _closing = false;
            if (!_wired) Wire();
            _resetScroll = true;                                     // 数据到了排好版再定位到最左边
            if (_data == null && _contentGroup != null) _contentGroup.alpha = 0f;   // 第一次打开:数据到之前不显示设计稿的占位卡片
            if (args != null && args.Length > 0 && args[0] is RechargeBenifits passed) Apply(passed);   // 和旧面板一样,先用调用方传进来的数据
            FetchData();
        }

        // 返回键和「前往充值」可能先后都请求关闭:只关一次
        public override void CloseSelf()
        {
            if (_closing) return;
            _closing = true;
            base.CloseSelf();
        }

        partial void OnViewAction(string key, ref bool handled)
        {
            if (key == "cta") { GoRecharge(); handled = true; return; }   // 主页「前往充值」
            foreach (var c in _designCards)
            {
                if (c.button == null || key != KeyOf(c)) continue;
                handled = true;
                if (c.detailCta == null) OnCardClick(c);   // 有详情页的卡由视图负责翻页
                return;
            }
            // 视图自己处理的(翻页、弹窗、数字遮罩等),不需要业务逻辑
            if (key == "rulesLink" || key == "toggleSummaryAmountVisibility" || key == "confirmConfirm") handled = true;
        }

        private string KeyOf(Card c)
        {
            foreach (var d in DesignCards) if (View.GetButton(d.card) == c.button) return d.card;
            return null;
        }

        // 前往充值:充值界面已经开着(从充值界面进来的)就关掉自己回去;否则关掉自己再打开充值界面(钻石页)
        private void GoRecharge()
        {
            bool rechargeOpen = UIManager.Inst.TryFindPanel(PanelId.RechargePanel, out var recharge) && recharge != null && recharge.gameObject.activeInHierarchy;
            CloseSelf();
            if (!rechargeOpen) UIManager.Inst.OpenPanel<RechargePanel>(PanelId.RechargePanel, global::UI.UIPanels.RechargePanel.RechargeId.GemPack);
        }

        // ---------- 第一次打开:找到设计稿里的卡片、记下排版和状态样式 ----------
        private void Wire()
        {
            _wired = true;
            foreach (var d in DesignCards)
            {
                var btn = View.GetButton(d.card);
                if (btn == null) { Debug.LogError($"[SignPanel] 视图里没有卡片按钮 {d.card}(设计稿改过?),这张卡不会显示服务端数据"); continue; }
                var c = new Card
                {
                    rt = (RectTransform)btn.transform, button = btn,
                    status = View.GetText(d.text + "Status"), rewardName = View.GetText(d.text + "RewardName"), amount = View.GetText(d.text + "Amount"),
                };
                c.statusSurface = FindImage(c.rt, "status-surface");
                c.icon = FindIcon(c.rt);
                if (c.amount != null && int.TryParse(Number.Match(c.amount.text).Value, out var amt)) c.designAmount = amt;
                if (d.detailCta != null)
                {
                    c.detailCta = View.GetButton(d.detailCta);
                    if (c.detailCta != null)
                    {
                        // 换掉视图生成的接线(它会不等服务端结果就弹「领取成功 / 确认兑换」),改为走旧的领取流程
                        c.detailCta.onClick.RemoveAllListeners();
                        var card = c;
                        c.detailCta.onClick.AddListener(() => OnClaimOrGo(card));
                        c.detailCtaLabel = c.detailCta.GetComponentInChildren<Text>(true);
                        c.detailCtaUnlockedText = c.detailCtaLabel != null ? c.detailCtaLabel.text : "领取奖励";
                    }
                }
                if (c.amount != null && _amountTemplate == "0 元") _amountTemplate = c.amount.text;
                // 设计稿里各状态的状态条底图和文字颜色,作为样式模板
                if (c.status != null)
                {
                    int st = c.status.text.Contains("可领取") ? StatusUnlocked : c.status.text.Contains("已领取") ? StatusClaimed : StatusLock;
                    if (!_styles.ContainsKey(st)) _styles[st] = new StatusStyle { sprite = c.statusSurface != null ? c.statusSurface.sprite : null, color = c.status.color, text = c.status.text };
                }
                if (c.detailCta == null && _cloneTemplate == null) _cloneTemplate = c;
                _designCards.Add(c);
            }
            if (!_styles.ContainsKey(StatusClaimed) && _styles.TryGetValue(StatusLock, out var lockStyle)) _styles[StatusClaimed] = new StatusStyle { sprite = lockStyle.sprite, color = lockStyle.color, text = "✓ 已领取" };
            if (_cloneTemplate == null && _designCards.Count > 0) _cloneTemplate = _designCards[0];

            if (_designCards.Count > 0)
            {
                _content = (RectTransform)_designCards[0].rt.parent;
                _scroll = _content.GetComponentInParent<ScrollRect>(true);
                _contentGroup = _content.GetComponent<CanvasGroup>() ?? _content.gameObject.AddComponent<CanvasGroup>();
                _contentWidth0 = _content.rect.width;
                foreach (var c in _designCards) c.designLeftOffset = LeftOffset(c.rt, _contentWidth0);
                var sorted = new List<Card>(_designCards);
                sorted.Sort((a, b) => a.designLeftOffset.CompareTo(b.designLeftOffset));
                _firstOffset = sorted[0].designLeftOffset;
                _rightPad = _contentWidth0 - sorted[sorted.Count - 1].designLeftOffset;
                _spacing = sorted.Count > 1 ? sorted[1].designLeftOffset - sorted[0].designLeftOffset : _cloneTemplate.rt.rect.width + 32f;
            }
            var total = View.GetText("labelTotalAmount");
            var next = View.GetText("nextTier");
            _totalTemplate = total != null ? total.text : null;
            _nextTemplate = next != null ? next.text : null;
            foreach (var r in View.GetComponentsInChildren<RectTransform>(true))
            {
                if (r.name == "progress/rail") _rail = r;
                else if (r.name == "progress/filled") _filled = r;
            }
        }

        // ---------- 服务端数据(与旧面板相同的接口) ----------
        private void FetchData()
        {
            IAPDataManager.Inst.GetProductInfo(res =>
            {
                if (this == null || !gameObject.activeInHierarchy) return;
                if (res == null || res.rechargeBenefits == null)
                {
                    LoggerUtils.LogError("SignPanel rechargeBenefits is NUll");
                    CloseSelf();
                    return;
                }
                Apply(res.rechargeBenefits);
            });
        }

        private void RefreshData()
        {
            AccountDataManager.Inst.BalanceInfo.Refresh();
            if (this == null || !gameObject.activeInHierarchy) return;
            IAPDataManager.Inst.GetProductInfo(res =>
            {
                if (this == null || !gameObject.activeInHierarchy) return;
                if (res != null && res.rechargeBenefits != null) Apply(res.rechargeBenefits);
            });
        }

        private void Apply(RechargeBenifits data)
        {
            if (data == null || data.rechargeLevelList == null) return;
            _data = data;
            foreach (var c in _designCards) c.data = null;
            _shown.Clear();
            int cloneUsed = 0;
            for (int i = 0; i < data.rechargeLevelList.Count; i++)
            {
                var level = data.rechargeLevelList[i];
                var card = _designCards.Find(c => c.data == null && c.designAmount == level.rechargeNum);
                if (card == null)
                {
                    card = GetClone(cloneUsed++);
                    if (card == null) continue;
                    LoadOldIcon(card, i, level);
                }
                card.data = level;
                card.serverIndex = i;
                _shown.Add(card);
            }
            foreach (var c in _designCards)
            {
                c.rt.gameObject.SetActive(c.data != null);
                if (c.data == null) LoggerUtils.LogError($"[SignPanel] 设计稿上的 {c.designAmount} 元档服务端没有,已隐藏这张卡");
            }
            for (int k = cloneUsed; k < _clones.Count; k++) _clones[k].rt.gameObject.SetActive(false);
            _shown.Sort((a, b) => a.data.rechargeNum.CompareTo(b.data.rechargeNum));
            Layout();
            foreach (var c in _shown) Fill(c);

            // 累计金额、距下一档(经视图写入,保持「金额可见性」遮罩状态)
            var texts = new Dictionary<string, string>();
            if (_totalTemplate != null) texts["labelTotalAmount"] = FillNumber(_totalTemplate, data.totalRecharged.ToString());
            if (_nextTemplate != null)
            {
                var next = _shown.Find(c => c.data.rechargeNum > data.totalRecharged);
                texts["nextTier"] = next != null ? FillNumber(_nextTemplate, (next.data.rechargeNum - data.totalRecharged).ToString()) : "已解锁全部档位";
            }
            View.ApplyServerState(texts);
            UpdateProgress();
        }

        private void Fill(Card c)
        {
            var d = c.data;
            c.rt.gameObject.SetActive(true);
            if (c.rewardName != null) c.rewardName.text = d.itemName;
            if (c.amount != null) c.amount.text = FillNumber(_amountTemplate, d.rechargeNum.ToString());
            int st = d.rewardStatus == StatusUnlocked || d.rewardStatus == StatusClaimed ? d.rewardStatus : StatusLock;
            if (_styles.TryGetValue(st, out var style))
            {
                if (c.statusSurface != null && style.sprite != null) c.statusSurface.sprite = style.sprite;
                if (c.status != null) { c.status.color = style.color; c.status.text = d.rewardStatus == 4 ? "已过期" : style.text; }
            }
            if (c.detailCtaLabel != null) c.detailCtaLabel.text = st == StatusUnlocked ? c.detailCtaUnlockedText : st == StatusClaimed ? "已领取" : "前往充值";
        }

        // ---------- 卡片排版:按金额从小到大等距排,Content 跟着变宽 ----------
        // 只用锚点坐标算(anchoredPosition + 锚点 + Content 宽度),不读 localPosition:父节点刚改尺寸时子节点的 localPosition 要到下一帧才更新
        private void Layout()
        {
            if (_content == null || _shown.Count == 0) return;
            float width = _firstOffset + (_shown.Count - 1) * _spacing + _rightPad;
            _content.SetSizeWithCurrentAnchors(RectTransform.Axis.Horizontal, width);
            for (int i = 0; i < _shown.Count; i++)
            {
                var rt = _shown[i].rt;
                var p = rt.anchoredPosition;
                p.x = _firstOffset + i * _spacing - rt.anchorMin.x * width - (0.5f - rt.pivot.x) * rt.rect.width;
                rt.anchoredPosition = p;
            }
            if (_scroll != null && _resetScroll)
            {
                _resetScroll = false;
                Canvas.ForceUpdateCanvases();
                _scroll.StopMovement();
                _scroll.horizontalNormalizedPosition = 0f;   // 打开时停在最左边,不留回弹动画(否则会左右闪)
            }
            if (_contentGroup != null && _contentGroup.alpha < 1f) StartCoroutine(FadeInContent());
        }

        // 数据到了以后卡片区淡入(0.2 秒),不要一下子冒出来
        private System.Collections.IEnumerator FadeInContent()
        {
            for (float t = _contentGroup.alpha * 0.2f; t < 0.2f; t += Time.unscaledDeltaTime)
            {
                _contentGroup.alpha = t / 0.2f;
                yield return null;
            }
            _contentGroup.alpha = 1f;
        }

        // 卡片中心离 Content 左边缘的距离(卡片是点锚点)
        private static float LeftOffset(RectTransform rt, float contentWidth) => rt.anchorMin.x * contentWidth + rt.anchoredPosition.x + (0.5f - rt.pivot.x) * rt.rect.width;

        // ---------- 进度条:填充到当前累计金额在卡片之间对应的位置(跟着滚动走) ----------
        protected override void Update()
        {
            base.Update();
            if (_data != null) UpdateProgress();
        }

        private void UpdateProgress()
        {
            if (_rail == null || _filled == null || _shown.Count == 0) return;
            var parent = _rail.parent;
            float railLeft = _rail.localPosition.x + _rail.rect.xMin, railWidth = _rail.rect.width;
            int total = _data.totalRecharged;
            float x;
            if (total <= 0) x = railLeft;
            else if (total >= _shown[_shown.Count - 1].data.rechargeNum) x = railLeft + railWidth;
            else
            {
                float prevX = railLeft, prevAmt = 0;
                x = railLeft;
                foreach (var c in _shown)
                {
                    float cx = parent.InverseTransformPoint(c.rt.TransformPoint(new Vector3(c.rt.rect.center.x, 0, 0))).x;
                    if (total < c.data.rechargeNum) { x = Mathf.Lerp(prevX, cx, (total - prevAmt) / (c.data.rechargeNum - prevAmt)); break; }
                    prevX = cx; prevAmt = c.data.rechargeNum;
                }
            }
            float w = Mathf.Clamp(x - railLeft, 0f, railWidth);
            // 左边缘按当前 x 缩放算:进场「生长」动效用 x 缩放 + 位置补偿,这里不能和它抢
            float left = _filled.localPosition.x + _filled.rect.xMin * _filled.localScale.x;
            if (Mathf.Abs(_filled.rect.width - w) < 0.5f && Mathf.Abs(left - railLeft) < 0.5f) return;
            _filled.SetSizeWithCurrentAnchors(RectTransform.Axis.Horizontal, w);
            left = _filled.localPosition.x + _filled.rect.xMin * _filled.localScale.x;
            var fp = _filled.anchoredPosition; fp.x += railLeft - left; _filled.anchoredPosition = fp;
        }

        // ---------- 点击:与旧 CumulativeRechargeItem 相同的分支 ----------
        private void OnCardClick(Card c)
        {
            var d = c.data;
            if (d == null) return;
            if (d.rewardStatus == StatusUnlocked) ClaimOrChoose(d);
            else if (d.rewardStatus == StatusLock) OpenPreview(d);   // 旧的 Btn_Preview
        }

        private void OnClaimOrGo(Card c)
        {
            var d = c.data;
            if (d == null) return;
            if (d.rewardStatus == StatusUnlocked) ClaimOrChoose(d);
            else if (d.rewardStatus == StatusLock) GoRecharge();   // 未达标:前往充值
        }

        private void ClaimOrChoose(RechargeLevelData d)
        {
            if (d.isOptionalReward == 0) ClaimSingleItem(d);
            else OpenPreview(d);
        }

        private void OpenPreview(RechargeLevelData d)
        {
            if (d.isOptionalReward == 1)
            {
                var panel = UIManager.Inst.OpenPanel<OptionalClaimRewardPanel>(PanelId.OptionalClaimRewardPanel);
                if (panel != null) panel.SetPreviewData(d);
            }
            else
            {
                var panel = UIManager.Inst.OpenPanel<OfficalClaimRewardPanel>(PanelId.OfficalClaimRewardPanel);
                if (panel != null) panel.SetPreviewData(d);
            }
        }

        // 与旧 CumulativeRechargeItem.ClaimSingleItem 逐行一致
        private void ClaimSingleItem(RechargeLevelData d)
        {
            JObject jb = new JObject
            {
                ["rewardId"] = d.id,
                ["pgcId"] = d.pgcId
            };
            var rewardType = (BUDRewardType)d.rewardType;
            Sprite sp = rewardType == BUDRewardType.RewardPgcResource
                ? PgcUtils.GetIconSpriteByPgcId(d.pgcId.ToString(), gameObject)
                : PgcUtils.LoadRewardIcon(rewardType, gameObject);

            NetworkManager.Inst.SendHttpRequest(HttpUrlDefine.ClaimRechargeBenifits,
                HttpMethod.POST,
                JsonConvert.SerializeObject(jb),
                onReceive: arg0 =>
                {
                    var itemData = new CommonRewardItemData
                    {
                        IconSp = sp,
                        RewardAmount = rewardType == BUDRewardType.RewardPinkCoin ? 200 : 1,
                        rewardName = d.itemName
                    };
                    var panel = UIManager.Inst.OpenPanel<CommonRewardPanel>(PanelId.CommonRewardPanel);
                    panel.ShowRewards(new List<CommonRewardItemData> { itemData });
                    MessageHelper.Broadcast(MessageName.RefreshCumData);
                }, onFail: arg0 => { });
        }

        // ---------- 设计稿没有的档位:复制一张卡 ----------
        private Card GetClone(int i)
        {
            if (i < _clones.Count) return _clones[i];
            if (_cloneTemplate == null) return null;
            var t = _cloneTemplate;
            var go = Instantiate(t.rt.gameObject, t.rt.parent, false);
            go.name = "RewardCard/extra" + i;
            var c = new Card { rt = (RectTransform)go.transform, cloned = true, detailCtaUnlockedText = "" };
            c.status = Same<Text>(t.rt, c.rt, t.status);
            c.rewardName = Same<Text>(t.rt, c.rt, t.rewardName);
            c.amount = Same<Text>(t.rt, c.rt, t.amount);
            c.statusSurface = Same<Image>(t.rt, c.rt, t.statusSurface);
            c.icon = Same<Image>(t.rt, c.rt, t.icon);
            c.button = go.GetComponent<Button>();
            if (c.button != null)
            {
                c.button.onClick.RemoveAllListeners();
                c.button.onClick.AddListener(() => OnCardClick(c));
            }
            _clones.Add(c);
            return c;
        }

        private void LoadOldIcon(Card c, int serverIndex, RechargeLevelData d)
        {
            if (c.icon == null) return;
            // 和旧面板一样:先取旧图集里的 Cumulative_Icon_<序号>,没有再按奖励类型取图标
            var sp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(RechargePanel.CumulativeRechargePanelAtlas, "Cumulative_Icon_" + serverIndex, c.rt.gameObject);
            if (sp == null)
            {
                var type = (BUDRewardType)d.rewardType;
                sp = type == BUDRewardType.RewardPgcResource ? PgcUtils.GetIconSpriteByPgcId(d.pgcId.ToString(), c.rt.gameObject) : PgcUtils.LoadRewardIcon(type, c.rt.gameObject);
            }
            if (sp != null) { c.icon.sprite = sp; c.icon.preserveAspect = true; }
        }

        // ---------- 小工具 ----------
        private static string FillNumber(string template, string value) =>
            string.IsNullOrEmpty(template) || !Number.IsMatch(template) ? value : Number.Replace(template, value, 1);

        private static Image FindImage(Transform root, string name)
        {
            foreach (var img in root.GetComponentsInChildren<Image>(true)) if (img.name == name) return img;
            return null;
        }

        private static Image FindIcon(Transform root)
        {
            foreach (var img in root.GetComponentsInChildren<Image>(true))
                if (img.transform != root && (img.name.Contains("Icon") || img.name.Contains("RewardArt"))) return img;
            return null;
        }

        // 模板卡里某个组件在复制卡上的对应组件(按层级序号找,名字里带 "/" 也没关系)
        private static T Same<T>(Transform templateRoot, Transform cloneRoot, Component inTemplate) where T : Component
        {
            if (inTemplate == null) return null;
            var path = new List<int>();
            for (var t = inTemplate.transform; t != templateRoot && t != null; t = t.parent) path.Insert(0, t.GetSiblingIndex());
            var cur = cloneRoot;
            foreach (var i in path) { if (i >= cur.childCount) return null; cur = cur.GetChild(i); }
            return cur.GetComponent<T>();
        }
    }
}
