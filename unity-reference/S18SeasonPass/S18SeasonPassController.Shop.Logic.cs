using System;
using System.Collections.Generic;
using System.Linq;
using Message;
using UI.Manager;
using UnityEngine;
using UnityEngine.UI;

namespace Bud.S18SeasonPass
{
    /// <summary>
    /// 兑换商店(第 5 / 6 / 7 / 10 页)、解锁通行证(第 1 页)、奖品预览 —— 照搬旧版
    /// SeasonPassExchangePanel / SeasonPassGiftPanel / SeasonPurchaseView / SeasonRewardView.ShowRewardPreview,不改服务端。
    ///
    /// 验证步骤(进游戏打开通行证面板 290):
    /// 1. 主页点「兑换」→ 第 5 页:商品格数量 = SeasonPassExchangeSystem.rewardList(S17 为 19 个,4 列可上下滑),
    ///    图标 / 名称 / 价格 / 「限购次数：已兑/上限」为真实数据;第一个(骑士小喵礼包)默认选中(选中框);右上通行证币 / 钻石为真实余额。
    /// 2. 礼包类商品:右侧人物图换成套装图标,下方「套装部件」是礼包内全部物品(图标 + X 数量);
    ///    未买通行证 → 左按钮「高级版通行证解锁」(点了打开第 1 页),等级 < 25 → 右按钮「通行证等级25级解锁」(点了打开 SeasonPassUpPanel);
    ///    两个都满足 → 两按钮隐藏,出现「兑换 价格」按钮 → 打开 SeasonPassGiftPanel(数量 / 通行证币不足 → SeasonPassCoinPanel / 兑换)。
    ///    兑换次数已满 → 出现灰色「兑换已达上限」按钮(第 10 页样式),点了提示。兑换成功后 ReqProductInfo 回包刷新限购次数。
    /// 3. 货币类商品(金币 / 徽章 / 能量币 / 幸运币 / 优优币):切到第 6 页,右侧大图 / 名称 / 介绍 / 数量 / 价格换成该商品;兑换同上。
    /// 4. 点部件格 → 第 7 页,气泡显示部件名称并对准该格,选中框移到该格;再点同一格回第 5 页。
    /// 5. 加号:通行证币 → SeasonPassCoinPanel(钻石兑换),钻石 → 充值钻石页;问号 → 兑换商店规则(GashaponRulePanel)。
    /// 6. 主页「购买通行证」→ 第 1 页:两张卡奖励格 = 付费轨道全部奖励汇总(paidRewardList),价格 300 / 600(已买高级则豪华为差价 300);
    ///    已买的显示「已解锁」;点击 → 钻石不足弹 GetMoreGemsPanel,否则 IAPDataManager.PaySeasonPassByGem,成功弹奖励、重新取数并回主页。
    /// 7. 主页 / 第 1 页的「奖品预览」→ 打开旧面板 PaidPackRewardPanel(3D 试穿),不再进第 8 页(第 8 / 9 页奖品格是整张拍平的图,无法填数据)。
    /// </summary>
    public partial class S18SeasonPassController
    {
        private static readonly int[] ShopPages = { PageShop, PageShopPreview, PageShopPart, PageShopSoldOut };
        private const int ShopGiftLevel = 25;   // 旧版 SeasonPassExchangePanel.UpdateLock:currentTier >= 25
        private const string ShopPassAtlas = "Assets/Loadable/UI/UIPanel/SeasonPassPanel/SeasonPassPanel.spriteatlas";

        private int _shopSel;                 // 选中商品(rewardList 序号)
        private int _shopPart = -1;           // 选中部件(礼包 RewardList 序号)
        private int _shopCurPage = -1;
        private bool _shopPaySending;
        private readonly Dictionary<int, List<Transform>> _shopCells = new Dictionary<int, List<Transform>>();
        private readonly Dictionary<int, List<Transform>> _shopParts = new Dictionary<int, List<Transform>>();
        private readonly Dictionary<Transform, Text> _shopOverlay = new Dictionary<Transform, Text>();
        private readonly Dictionary<int, Transform> _shopBuyBtn = new Dictionary<int, Transform>();
        private readonly Dictionary<int, Transform> _shopGrayBtn = new Dictionary<int, Transform>();
        private Sprite _shopGreenSp, _shopPrimarySp;

        private List<SeasonExchangeConfig> ShopItems => SeasonPassExchangeSystem.Inst.rewardList;
        private SeasonExchangeConfig ShopSelected => ShopItems != null && _shopSel >= 0 && _shopSel < ShopItems.Count ? ShopItems[_shopSel] : null;

        // ================= 挂钩 =================
        partial void ShopCreate()
        {
            MessageHelper.AddListener(MessageName.SeasonExchangeGiftUpdate, ShopOnExchangeUpdate);
            MessageHelper.AddListener(MessageName.SeasonPassDataUpdate, ShopOnExchangeUpdate);

            // 底部按钮:把第 6 页的「兑换」、第 10 页的「兑换已达上限」复制到各商店页(礼包页本来没有)
            var buySrc = FindDeep(PageRoot(PageShopPreview), "操作/兑换");
            var graySrc = FindDeep(PageRoot(PageShopSoldOut), "操作/兑换已达上限");
            foreach (var p in ShopPages)
            {
                var root = PageRoot(p);
                if (root == null) continue;
                var buy = FindDeep(root, "操作/兑换");
                if (buy == null && buySrc != null) buy = ShopCloneInto(buySrc, root);
                var gray = FindDeep(root, "操作/兑换已达上限");
                if (gray == null && graySrc != null) gray = ShopCloneInto(graySrc, root);
                if (buy != null) { _shopBuyBtn[p] = buy; BindClick(buy, ShopOnBuy); }
                if (gray != null) { _shopGrayBtn[p] = gray; BindClick(gray, () => TipPanel.ShowToast("已达兑换上限")); }
                BindClick(FindDeep(root, "操作/高级版通行证解锁"), ShopOnPassBtn);
                BindClick(FindDeep(root, "操作/✓ 通行证等级12级解锁"), ShopOnLevelBtn);
                if (_shopGreenSp == null) { var g = ImageAt(root, "Art/按钮底图/green.png"); if (g != null) _shopGreenSp = g.sprite; }
                if (_shopPrimarySp == null) { var g = ImageAt(root, "Art/按钮底图/primary.png"); if (g != null) _shopPrimarySp = g.sprite; }
            }

            // 奖品预览:旧版是 PaidPackRewardPanel(3D 试穿);第 8 页奖品格是拍平的整图,改为打开旧面板(换掉 View 的 OpenPage(8))
            BindClick(view.GetButton("action2")?.transform, ShopOpenRewardPreview);
            BindClick(view.GetButton("pageAction")?.transform, ShopOpenRewardPreview);
        }

        partial void ShopRefresh()
        {
            SeasonPassExchangeSystem.Inst.ReqProductInfo();   // 回包广播 SeasonExchangeGiftUpdate → ShopOnExchangeUpdate
            ShopFillAll();
            ShopFillUnlock();
        }

        partial void ShopPageShown(int index)
        {
            if (index == PageReward) { _shopCurPage = -1; return; }   // 回到主页:复位,再进商店重置选中项并重新 ReqProductInfo
            var prev = _shopCurPage;
            _shopCurPage = index;
            if (index == PageUnlock) { ShopFillUnlock(); return; }
            if (Array.IndexOf(ShopPages, index) < 0) return;
            // 从商店外进来:和旧版 Def() 一样默认选第一个
            if (Array.IndexOf(ShopPages, prev) < 0) { _shopSel = 0; _shopPart = -1; SeasonPassExchangeSystem.Inst.ReqProductInfo(); }
            ShopFillAll();
        }

        partial void ShopAction(string key, ref bool handled)
        {
            switch (key)
            {
                case "pageAction68": case "bAction11": case "cAction20": case "pageAction106":   // 通行证币 +
                    UIManager.Inst.OpenPanel<SeasonPassCoinPanel>(PanelId.SeasonPassCoinPanel)?.SetData(CurrencyType.SeasonPassCoin, CurrencyType.Gem);
                    handled = true; break;
                case "pageAction69": case "bAction12": case "cAction21": case "pageAction107":   // 钻石 +(同 AccountWidget)
                    RechargePanel.OpenTo(UI.UIPanels.RechargePanel.RechargeId.GemPack);
                    handled = true; break;
                case "pageRulesLink": case "bRulesLink": case "cRulesLink": case "pageRulesLink2":
                    UIManager.Inst.OpenPanel<GashaponRulePanel>(PanelId.GashaponRulePanel, "Assets/Loadable/UI/UIPanel/SeasonPassExchange/SeasonPassExchangeRule.json");
                    handled = true; break;
                case "pageAction108": TipPanel.ShowToast("已达兑换上限"); handled = true; break;
                case "pageAction9": ShopSendPay(false); handled = true; break;    // 300 解锁高级
                case "pageAction18": ShopSendPay(true); handled = true; break;    // 600 解锁豪华
            }
        }

        private void ShopOnExchangeUpdate()
        {
            if (this == null)   // 视图已销毁:退订(MessageHelper.Broadcast 遍历的是快照,回调里退订安全)
            {
                MessageHelper.RemoveListener(MessageName.SeasonExchangeGiftUpdate, ShopOnExchangeUpdate);
                MessageHelper.RemoveListener(MessageName.SeasonPassDataUpdate, ShopOnExchangeUpdate);
                return;
            }
            ShopFillAll();
        }

        // ================= 兑换商店 =================
        private void ShopFillAll()
        {
            if (view == null || ShopItems == null) return;
            if (_shopSel >= ShopItems.Count) _shopSel = 0;
            foreach (var p in ShopPages) ShopFillPage(p);
        }

        private void ShopFillPage(int page)
        {
            var root = PageRoot(page);
            if (root == null) return;
            var items = ShopItems;

            // 商品格:4 列网格
            var content = FindPath(root, "商品列表 · 可滑动|内容");
            var cells = ShopEnsureGrid(page, content, items.Count);
            for (int i = 0; i < cells.Count && i < items.Count; i++)
            {
                var idx = i;
                ShopFillCell(cells[i], items[i], i == _shopSel);
                BindClick(cells[i], () => ShopSelect(idx));
            }
            if (cells.Count > 0 && items.Count > 0) FitContent(content, cells[Math.Min(items.Count, cells.Count) - 1], false);

            // 货币栏(设计稿数字是图片,盖一层文字)
            var balance = AccountDataManager.Inst.BalanceInfo;
            ShopSetImageText(FindPath(root, "货币栏/通行证币|文案/2000"), balance.GetAccountCount(CurrencyType.SeasonPassCoin).ToString());
            ShopSetImageText(FindPath(root, "货币栏/钻石|文案/21542"), balance.GetAccountCount(CurrencyType.Gem).ToString());

            var info = ShopSelected;
            if (info == null) return;
            bool reached = SeasonPassExchangeSystem.Inst.GetTime(info.ExchangeId) >= info.Count;
            if (page == PageShopPreview) ShopFillPreview(root, info, reached);
            else ShopFillGift(page, root, info, reached);
        }

        /// <summary>商品格池:设计稿里的格子先统一外观(常态 = 普通格,选中态 = 第一格的选中框),不够时复制。</summary>
        private List<Transform> ShopEnsureGrid(int page, Transform content, int count)
        {
            if (!_shopCells.TryGetValue(page, out var pool))
            {
                pool = new List<Transform>();
                if (content != null)
                    for (int i = 0; i < content.childCount; i++)
                        if (content.GetChild(i).name.StartsWith("操作/预览", StringComparison.Ordinal)) pool.Add(content.GetChild(i));
                if (pool.Count >= 2)
                {
                    var normal = FindPath(pool[1], "常态");
                    var selected = FindPath(pool[0], "选中态");
                    for (int i = 0; i < pool.Count; i++)
                    {
                        if (i != 1 && normal != null) ShopReplaceChild(pool[i], "常态", normal);
                        if (i != 0 && selected != null) ShopReplaceChild(pool[i], "选中态", selected);
                    }
                }
                _shopCells[page] = pool;
            }
            if (pool.Count == 0) return pool;
            var c0 = (RectTransform)pool[0];
            var dx = pool.Count > 1 ? StepBetween(pool[0], pool[1]) : new Vector2(c0.rect.width + 28, 0);
            var dy = pool.Count > 4 ? StepBetween(pool[0], pool[4]) : new Vector2(0, -(c0.rect.height + 16));
            var basePos = c0.anchoredPosition;
            while (pool.Count < count)
            {
                var go = Instantiate(pool[Math.Min(1, pool.Count - 1)].gameObject, content);
                go.name = pool[0].name;
                pool.Add(go.transform);
            }
            for (int i = 0; i < pool.Count; i++)
            {
                SetActive(pool[i], i < count);
                if (i < count) ((RectTransform)pool[i]).anchoredPosition = basePos + dx * (i % 4) + new Vector2(0, dy.y) * (i / 4);
            }
            return pool;
        }

        private void ShopFillCell(Transform cell, SeasonExchangeConfig info, bool selected)
        {
            var normal = FindPath(cell, "常态");
            var sel = FindPath(cell, "选中态");
            SetActive(normal, !selected);
            SetActive(sel, selected);
            foreach (var layer in new[] { normal, sel })
            {
                if (layer == null) continue;
                SetText(ShopTextByPrefix(layer, "文案/商品名"), ShopItemName(info));
                SetText(ShopTextByPrefix(layer, "文案/限购次数"), $"限购次数：{SeasonPassExchangeSystem.Inst.GetTime(info.ExchangeId)}/{info.Count}");
                var band = FindDeep(layer, "at price-band");
                if (band != null) SetText(band.GetComponentInChildren<Text>(true), info.Price.ToString());
                var icon = ShopImageByPrefix(layer, "Art/图标/");
                if (icon != null)
                {
                    icon.sprite = ShopItemIcon(info, icon.gameObject);
                    icon.preserveAspect = true;
                    icon.enabled = icon.sprite != null;
                }
                var gift = ImageAt(layer, "Art/图标/gift.svg");   // 设计稿礼包格多一层礼盒图
                if (gift != null) gift.enabled = false;
            }
        }

        private void ShopSelect(int index)
        {
            if (ShopItems == null || index < 0 || index >= ShopItems.Count) return;
            _shopSel = index;
            _shopPart = -1;
            var info = ShopItems[index];
            var target = info.Gift ? PageShop : PageShopPreview;
            ShopFillAll();
            if (_shopCurPage != target) view.SwitchPage(target);
        }

        /// <summary>第 6 页:货币类商品预览。</summary>
        private void ShopFillPreview(Transform root, SeasonExchangeConfig info, bool reached)
        {
            var first = info.RewardList?.FirstOrDefault();
            if (first == null) return;
            var big =ImageAt(root, "预览/物品大图");
            if (big != null) { big.sprite = ShopRewardIcon(first, big.gameObject); big.preserveAspect = true; }
            var name = info.Gift ? info.Name : PgcUtils.GetRewardName(first.RewardType);
            SetText(TextAt(root, "文案/物品名称"), name);
            SetText(TextAt(root, "文案/物品介绍"), $"兑换获得{name}×{first.Count}，本赛季限兑 {info.Count} 次。");
            ShopSetImageText(FindDeep(root, "文案/预览数量"), "×" + first.Count);
            ShopSetBottom(PageShopPreview, info, reached, true, true);
        }

        /// <summary>第 5 / 7 / 10 页:礼包(套装 + 动作)预览、部件栏、解锁条件。</summary>
        private void ShopFillGift(int page, Transform root, SeasonExchangeConfig info, bool reached)
        {
            var character = ImageAt(root, "Art/图标/character.png");
            if (character != null && info.Gift)
            {
                character.sprite = PgcUtils.LoadBundleIcon(info.BundleID, character.gameObject);
                character.preserveAspect = true;
            }

            // 部件栏 = 礼包 RewardList(旧版 RewardGroup 展示的同一份列表)
            var content = FindPath(root, "at parts-tray|部件列表 · 可滑动|内容");
            if (!_shopParts.TryGetValue(page, out var pool))
            {
                pool = new List<Transform>();
                if (content != null)
                    for (int i = 0; i < content.childCount; i++)
                        if (content.GetChild(i).name.StartsWith("操作/预览部件", StringComparison.Ordinal)) pool.Add(content.GetChild(i));
                _shopParts[page] = pool;
            }
            var rewards = info.RewardList;
            if (pool.Count > 0)
            {
                var step = pool.Count > 1 ? StepBetween(pool[0], pool[1]) : new Vector2(162, 0);
                EnsureClones(pool[0], rewards.Count, step, pool);
                for (int i = 0; i < rewards.Count && i < pool.Count; i++)
                {
                    var r = rewards[i];
                    var icon = ShopImageByPrefix(pool[i], "Art/图标/");
                    if (icon != null) { icon.sprite = ShopRewardIcon(r, icon.gameObject); icon.preserveAspect = true; }
                    SetText(ShopTextByPrefix(pool[i], "文案/数量"), "X" + r.Count);
                    var idx = i;
                    BindClick(pool[i], () => ShopSelectPart(idx));
                }
                FitContent(content, pool[Math.Max(0, Math.Min(rewards.Count, pool.Count) - 1)], true);
            }

            // 部件选中(第 7 页):选中框对准部件格,气泡尖角对准部件格
            if (page == PageShopPart && _shopPart >= 0 && _shopPart < rewards.Count && _shopPart < pool.Count)
            {
                var cell = (RectTransform)pool[_shopPart];
                var frame = FindDeep(root, "部件选中框");
                if (frame != null) { frame.SetAsLastSibling(); ShopAlignX(frame, frame, cell, true); }
                var bubble = FindDeep(root, "部件介绍气泡");
                if (bubble != null) ShopAlignX(bubble, FindDeep(bubble, "尖角"), cell, false);
                var r = rewards[_shopPart];
                SetText(TextAt(root, "文案/部件名称"), ShopRewardName(r));
                var nameText = TextAt(root, "文案/部件名称");
                if (nameText != null) nameText.horizontalOverflow = HorizontalWrapMode.Overflow;
                if (r.RewardType != BUDRewardType.RewardPgcResource) SetText(TextAt(root, "文案/部件介绍"), $"礼包附赠，数量 ×{r.Count}");
                else if (_shopPart == 0) SetText(TextAt(root, "文案/部件介绍"), "礼包内的动作，兑换后可在动作栏使用。");
                else SetText(TextAt(root, "文案/部件介绍"), "套装部件之一，集齐后可激活完整套装外观。");
            }

            ShopSetBottom(page, info, reached, false, page != PageShopSoldOut);
        }

        private void ShopSelectPart(int index)
        {
            if (_shopCurPage == PageShopPart && index == _shopPart) { _shopPart = -1; view.SwitchPage(PageShop); return; }
            _shopPart = index;
            if (_shopCurPage != PageShopPart) view.SwitchPage(PageShopPart);   // ShopPageShown → ShopFillAll
            else ShopFillAll();
        }

        /// <summary>底部按钮:礼包要先满足「已购通行证 + 等级」两个条件(旧版 UpdateLock),否则显示条件按钮;满足后显示兑换 / 已达上限。</summary>
        private void ShopSetBottom(int page, SeasonExchangeConfig info, bool reached, bool isPreviewPage, bool hasCondButtons)
        {
            var root = PageRoot(page);
            bool passOk = true, levelOk = true;
            if (info.Gift)
            {
                var data = SeasonPassDataManager.Inst.GetCurSeasonData();
                passOk = data != null && data.isPaid == 1;
                levelOk = data != null && data.progressInfo != null && data.progressInfo.currentTier >= ShopGiftLevel;
            }
            bool showCond = info.Gift && !(passOk && levelOk);
            var passBtn = FindDeep(root, "操作/高级版通行证解锁");
            var levelBtn = FindDeep(root, "操作/✓ 通行证等级12级解锁");
            SetActive(passBtn, showCond);
            SetActive(levelBtn, showCond);
            if (showCond)
            {
                ShopCondButton(passBtn, passOk, passOk ? "✓ 高级版通行证已解锁" : "高级版通行证解锁");
                ShopCondButton(levelBtn, levelOk, (levelOk ? "✓ " : "") + $"通行证等级{ShopGiftLevel}级解锁");
            }
            _shopBuyBtn.TryGetValue(page, out var buy);
            _shopGrayBtn.TryGetValue(page, out var gray);
            SetActive(buy, !showCond && !reached);
            SetActive(gray, !showCond && reached);
            if (buy != null) SetText(TextAt(buy, "文案/价格"), info.Price.ToString());
        }

        private void ShopCondButton(Transform btn, bool ok, string text)
        {
            if (btn == null) return;
            var label = btn.GetComponentsInChildren<Text>(true).FirstOrDefault();
            SetText(label, text);
            SetActive(FindDeep(btn, "Art/图标/status_locked.png"), !ok);
            var bg = ImageAt(btn, "Art/按钮底图/green.png") ?? ImageAt(btn, "Art/按钮底图/primary.png");
            var sp = ok ? _shopGreenSp : _shopPrimarySp;
            if (bg != null && sp != null) bg.sprite = sp;
        }

        private void ShopOnBuy()
        {
            var info = ShopSelected;
            if (info == null) return;
            if (SeasonPassExchangeSystem.Inst.GetTime(info.ExchangeId) >= info.Count) { TipPanel.ShowToast("已达兑换上限"); return; }
            UIManager.Inst.OpenPanel(PanelId.SeasonPassGiftPanel, info);   // 旧版 OnBuyBtnClick:数量选择、通行证币不足 → SeasonPassCoinPanel、ReqStore
        }

        private void ShopOnPassBtn()
        {
            if (SeasonPassDataManager.Inst.GetSeasonPassIsPaid(SeasonPassDataManager.Inst.CurrentSeasonPassType)) return;
            view.OpenPage(PageUnlock);   // 旧版打开 SeasonPurchaseView;新界面的解锁页就是第 1 页
        }

        private void ShopOnLevelBtn()
        {
            var data = SeasonPassDataManager.Inst.GetCurSeasonData();
            if (data != null && data.progressInfo != null && data.progressInfo.currentTier >= ShopGiftLevel) return;
            UIManager.Inst.OpenPanel(PanelId.SeasonPassUpPanel);
        }

        // ================= 奖品预览(旧面板)=================
        private void ShopOpenRewardPreview()
        {
            var panel = UIManager.Inst.OpenPanel<PaidPackRewardPanel>(PanelId.PaidPackRewardPanel);
            if (panel == null) return;
            panel.bundleBgColorStr = "#FFFFFF";
            panel.bundleContentBgColorStr = "#FF9B9B";
            // 旧版还调 SetStyle(Texture2DBg):那张图在 Assets/Arts(不可按路径加载),这里沿用面板默认背景
            panel.SetPreviewData(SeasonPassDataManager.Inst.GetSeasonPassRewardDatas(SeasonPassDataManager.Inst.CurrentSeasonPassType, true));
        }

        // ================= 解锁通行证(第 1 页)=================
        private readonly Dictionary<string, List<Transform>> _shopUnlockCells = new Dictionary<string, List<Transform>>();

        private void ShopFillUnlock()
        {
            var root = PageRoot(PageUnlock);
            var dm = SeasonPassDataManager.Inst;
            var data = dm.GetCurSeasonData();
            if (root == null || data == null) return;
            bool paid = data.isPaid == 1, luxury = paid && data.paidType == 1;

            // 奖励汇总:付费轨道全部奖励,按奖励类型 / pgcId 合并数量
            var keys = new List<string>();
            var sum = new Dictionary<string, int>();
            var sample = new Dictionary<string, SeasonPassItemInfo>();
            if (data.paidRewardList != null)
                foreach (var it in data.paidRewardList)
                {
                    var first = it?.rewardInfo?.itemList?.FirstOrDefault();
                    if (first == null) continue;
                    var key = first.BudRewardType == BUDRewardType.RewardPgcResource ? "pgc:" + (first.pgcIdList?.FirstOrDefault() ?? first.pgcId) : "t:" + first.rewardType;
                    if (!sum.ContainsKey(key)) { keys.Add(key); sum[key] = 0; sample[key] = it; }
                    sum[key] += Math.Max(1, first.amount);
                }

            ShopFillPassCard(FindDeep(root, "at pass-card"), "premium", keys, sum, sample, 8);
            ShopFillPassCard(FindDeep(root, "at pass-card luxury"), "luxury", keys, sum, sample, 7);   // 豪华卡最后一格「额外经验」保留

            var premiumGem = dm.PremiumSeasonPassGem;
            var luxuryGem = paid ? dm.LuxurySeasonPassGem - dm.PremiumSeasonPassGem : dm.LuxurySeasonPassGem;
            ShopPayButton(FindDeep(root, "操作/300 解锁高级"), paid ? "已解锁" : $"{premiumGem} 解锁高级", !paid);
            ShopPayButton(FindDeep(root, "操作/600 解锁豪华"), luxury ? "已解锁" : $"{luxuryGem} 解锁豪华", !luxury);
        }

        private void ShopFillPassCard(Transform card, string id, List<string> keys, Dictionary<string, int> sum, Dictionary<string, SeasonPassItemInfo> sample, int maxCells)
        {
            var clip = FindDeep(card, "内容裁切");
            if (clip == null) return;
            if (!_shopUnlockCells.TryGetValue(id, out var pool))
            {
                pool = new List<Transform>();
                for (int i = 0; i < clip.childCount; i++)
                {
                    var c = clip.GetChild(i);
                    if (c.name.StartsWith("操作/预览", StringComparison.Ordinal) && c.name != "操作/预览额外经验") pool.Add(c);
                }
                _shopUnlockCells[id] = pool;
            }
            if (pool.Count == 0) return;
            var dx = pool.Count > 1 ? StepBetween(pool[0], pool[1]) : new Vector2(163, 0);
            var dy = pool.Count > 4 ? StepBetween(pool[0], pool[4]) : new Vector2(0, -183);
            var basePos = ((RectTransform)pool[0]).anchoredPosition;
            int count = Math.Min(keys.Count, maxCells);
            var tpl = pool[0];   // 第一格(紫钻)结构完整:图标 + 数量 + 名称
            for (int i = 0; i < pool.Count; i++) SetActive(pool[i], false);
            var cells = new List<Transform>();
            for (int i = 0; i < count; i++)
            {
                Transform cell;
                if (i == 0) cell = tpl;
                else
                {
                    var cloneName = tpl.name + "#" + i;
                    cell = FindPath(clip, cloneName);
                    if (cell == null) { cell = Instantiate(tpl.gameObject, clip).transform; cell.name = cloneName; }
                }
                SetActive(cell, true);
                ((RectTransform)cell).anchoredPosition = basePos + dx * (i % 4) + new Vector2(0, dy.y) * (i / 4);
                var key = keys[i];
                var info = sample[key];
                var reward = info.rewardInfo.itemList.First();
                var icon = ShopImageByPrefix(cell, "Art/图标/");
                if (icon != null)
                {
                    var iconName = info.IconName();
                    icon.sprite = string.IsNullOrEmpty(iconName) ? null : XAssetLoaderMgr.Inst.LoadSpriteInAltas(ShopPassAtlas, iconName, icon.gameObject);
                    icon.preserveAspect = true;
                    icon.enabled = icon.sprite != null;
                }
                var texts = cell.GetComponentsInChildren<Text>(true);
                if (texts.Length > 0) SetText(texts[0], "×" + sum[key]);
                if (texts.Length > 1)
                {
                    string name;
                    if (reward.BudRewardType == BUDRewardType.RewardPgcResource)
                    {
                        var pgc = reward.pgcIdList?.FirstOrDefault() ?? reward.pgcId;
                        name = SeasonPassDataManager.Inst.GetPgcName(pgc);
                        if (string.IsNullOrEmpty(name)) name = SeasonPassDataManager.Inst.GetSeasonPassRewardAvatarName(pgc);
                    }
                    else name = PgcUtils.GetRewardName(reward.BudRewardType);
                    SetText(texts[1], name);
                }
                var btn = cell.GetComponent<Button>();
                if (btn != null) btn.onClick.RemoveAllListeners();   // 奖励格只展示
                cells.Add(cell);
            }
            // 多余的复制格隐藏
            for (int i = 0; i < clip.childCount; i++)
            {
                var c = clip.GetChild(i);
                if (c.name.StartsWith(tpl.name + "#", StringComparison.Ordinal) && !cells.Contains(c)) SetActive(c, false);
            }
        }

        private static void ShopPayButton(Transform btn, string text, bool canBuy)
        {
            if (btn == null) return;
            SetText(btn.GetComponentsInChildren<Text>(true).FirstOrDefault(), text);
            SetActive(FindDeep(btn, "Art/图标/currency-diamond.png"), canBuy);
            var b = btn.GetComponent<Button>();
            if (b != null) b.interactable = canBuy;
        }

        /// <summary>照搬旧版 SeasonPurchaseView.SendPayRequest / ShowReward。</summary>
        private void ShopSendPay(bool isLuxury)
        {
            var dm = SeasonPassDataManager.Inst;
            var type = dm.CurrentSeasonPassType;
            bool isPaid = dm.GetSeasonPassIsPaid(type);
            if (!isLuxury && isPaid) return;
            if (isLuxury && isPaid && dm.GetSeasonPassPaidType(type) == 1) return;
            int gem = isLuxury ? dm.LuxurySeasonPassGem : dm.PremiumSeasonPassGem;
            if (isLuxury && isPaid) gem = dm.LuxurySeasonPassGem - dm.PremiumSeasonPassGem;
            var gemNum = AccountDataManager.Inst.BalanceInfo.GetAccountCount(CurrencyType.Gem);
            if (gemNum < gem) { UIManager.Inst.OpenPanel<GetMoreGemsPanel>(PanelId.GetMoreGemsPanel, gem - gemNum); return; }
            if (_shopPaySending) return;
            _shopPaySending = true;
            IAPDataManager.Inst.PaySeasonPassByGem(dm.GetSeasonPassName(SeasonPassDataManager.ToNetSeasonPassType(type)), isLuxury,
                resultHandler: result =>
                {
                    if (this == null) return;
                    _shopPaySending = false;
                    if (!result) { TipPanel.ShowToast("哎呀！出错了。请重试！"); return; }
                    ShopShowPayReward(isLuxury, isPaid);
                    dm.GetSeasonPassList(type, (ok, rsp) => { if (this == null) return; Reload(); });
                    view.ResetToHome();
                    _shopCurPage = -1;   // 回主页后复位,再进商店重置选中项
                });
        }

        private void ShopShowPayReward(bool isLuxury, bool isPaid)
        {
            MessageHelper.Broadcast(MessageName.RefreshSeasonPass);
            var rewardSp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(ShopPassAtlas, isLuxury ? "luxury_logo" : "logo", gameObject);
            if (rewardSp == null) return;
            var panel = UIManager.Inst.OpenPanel<CommonRewardPanel>(PanelId.CommonRewardPanel);
            var list = new List<CommonRewardItemData>
            {
                new CommonRewardItemData { IconSp = rewardSp, RewardAmount = 1, rewardName = isLuxury ? "豪华通行证" : "高级通行证" },
            };
            if (!isLuxury)
                list.Add(new CommonRewardItemData { IconSp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(SpriteAtlasType.Common, "SlotIcon", panel.gameObject), RewardAmount = 1, rewardName = "皮肤形象位" });
            else
                list.AddRange(SeasonPassDataManager.Inst.OnPaidSeasonPassAndGetRewardData(SeasonPassDataManager.Inst.CurrentSeasonPassType, isPaid, gameObject));
            panel.ShowRewards(list, IsResize: true);
        }

        // ================= 小工具 =================
        private static string ShopItemName(SeasonExchangeConfig info)
        {
            if (info.Gift) return info.Name;
            var first = info.RewardList?.FirstOrDefault();
            return first == null ? info.Name : $"{info.Name}×{first.Count}";
        }

        private static Sprite ShopItemIcon(SeasonExchangeConfig info, GameObject owner)
        {
            if (info.Gift) return PgcUtils.LoadBundleIcon(info.BundleID, owner);
            var first = info.RewardList?.FirstOrDefault();
            return first == null ? null : PgcUtils.LoadRewardIcon(first.RewardType, owner);
        }

        private static Sprite ShopRewardIcon(SeasonExchangeConfigItem r, GameObject owner)
        {
            return r.RewardType == BUDRewardType.RewardPgcResource ? PgcUtils.GetIconSpriteByPgcId(r.PgcID.ToString(), owner) : PgcUtils.LoadRewardIcon(r.RewardType, owner);
        }

        private static string ShopRewardName(SeasonExchangeConfigItem r)
        {
            if (r.RewardType != BUDRewardType.RewardPgcResource) return PgcUtils.GetRewardName(r.RewardType);
            var id = r.PgcID.ToString();
            var name = SeasonPassDataManager.Inst.GetPgcName(id);
            return string.IsNullOrEmpty(name) ? PgcUtils.GetEmoteName(id) : name;
        }

        private static Text ShopTextByPrefix(Transform root, string prefix)
        {
            foreach (var t in root.GetComponentsInChildren<Text>(true))
                if (t.name.StartsWith(prefix, StringComparison.Ordinal)) return t;
            return null;
        }

        private static Image ShopImageByPrefix(Transform root, string prefix)
        {
            foreach (var t in root.GetComponentsInChildren<Image>(true))
                if (t.name.StartsWith(prefix, StringComparison.Ordinal)) return t;
            return null;
        }

        private static Transform ShopCloneInto(Transform src, Transform parent)
        {
            var go = Instantiate(src.gameObject, parent, false);
            go.name = src.name;
            go.SetActive(false);
            return go.transform;
        }

        /// <summary>把 cell 下名为 childName 的子节点换成 source 的副本(保持层级顺序)。</summary>
        private static void ShopReplaceChild(Transform cell, string childName, Transform source)
        {
            var old = FindPath(cell, childName);
            int sibling = old != null ? old.GetSiblingIndex() : cell.childCount;
            var go = Instantiate(source.gameObject, cell, false);
            go.name = childName;
            go.transform.SetSiblingIndex(sibling);
            if (old != null) { old.gameObject.SetActive(false); old.name = childName + "(旧)"; Destroy(old.gameObject); }
        }

        /// <summary>设计稿里数字是图片的地方(货币栏、预览数量):隐藏图片,叠一个同位置的 Text(从页面已有文字复制,字体合规)。</summary>
        private void ShopSetImageText(Transform imageNode, string value)
        {
            if (imageNode == null) return;
            if (!_shopOverlay.TryGetValue(imageNode, out var text) || text == null)
            {
                var src = TextAt(PageRoot(PageShopPreview), "文案/价格");
                if (src == null) return;
                var go = Instantiate(src.gameObject, imageNode.parent, false);
                go.name = imageNode.name + "(数字)";
                foreach (var mb in go.GetComponents<MonoBehaviour>()) if (!(mb is Text)) Destroy(mb);
                var rt = (RectTransform)go.transform; var ir = (RectTransform)imageNode;
                rt.anchorMin = ir.anchorMin; rt.anchorMax = ir.anchorMax; rt.pivot = ir.pivot;
                rt.anchoredPosition = ir.anchoredPosition; rt.sizeDelta = ir.sizeDelta;
                rt.SetSiblingIndex(imageNode.GetSiblingIndex() + 1);
                text = go.GetComponent<Text>();
                text.alignment = TextAnchor.MiddleCenter;
                text.horizontalOverflow = HorizontalWrapMode.Overflow;
                text.fontSize = Mathf.Max(16, Mathf.RoundToInt(ir.rect.height * 0.95f));
                text.raycastTarget = false;
                var img = imageNode.GetComponent<Image>();
                if (img != null) img.enabled = false;
                _shopOverlay[imageNode] = text;
            }
            SetActive(text.transform, true);
            text.text = value;
        }

        /// <summary>水平移动 target,使 anchor 的中心与 cell 中心对齐(anchor 为 target 或其子节点)。</summary>
        private static void ShopAlignX(Transform target, Transform anchor, RectTransform cell, bool alsoY)
        {
            if (target == null || anchor == null || cell == null) return;
            var a = ShopCenterWorld((RectTransform)anchor);
            var c = ShopCenterWorld(cell);
            var d = c - a;
            target.position += alsoY ? d : new Vector3(d.x, 0, 0);
        }

        private static Vector3 ShopCenterWorld(RectTransform rt)
        {
            var corners = new Vector3[4];
            rt.GetWorldCorners(corners);
            return (corners[0] + corners[2]) * 0.5f;
        }
    }
}
