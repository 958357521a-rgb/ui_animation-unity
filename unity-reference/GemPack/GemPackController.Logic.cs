// 钻石充值页(充值界面 102「BUD钻充值」页签,RechargeId.GemPack,prefab Assets/Loadable/UI/RechargePanel/Views/GemPackView.prefab)
// 新视觉模块 GemPack 的业务逻辑。手写文件:BUD UI Studio「覆盖到 Unity」不会生成、也不会覆盖它;
// 主工程里没有时,覆盖会从 BUD_UI_Studio/unity-reference/GemPack/ 的这份副本一起写进去(改完主工程里的记得同步回来)。
//
// 原则:只换素材和动效,取数与下单逐行照搬旧 IAPGemPackView / IAPGemItemView,不新增、不修改任何请求,不改支付流程:
//   商品      IAPDataManager.GetGemPackProducts();没有或数量和格子对不上时 GetProductInfo → gemRechargeList(与旧版相同)
//   点格子    官方渠道先开 ConfirmPaymentPanel 选支付方式 → PackPurchaseUtils.StartPurchase(...) → 成功后 CommonRewardPanel 展示钻石;
//            非官方渠道直接 StartPurchase(PaymentType.Default);在换装间 UGC 页签里点时照旧打点 BuyDiamondsClicked
//   累充入口  打开 207 累计充值面板(参数 GetCumulativeRechargeData),有「可领取」档位时亮红点
//   海外包    PACKAGE_TYPE_US 下的默认价格 / 本地化价格逻辑照搬(国内包不走)
// 和旧版的差别(只在显示上):
//   - 格子按服务端顺序一一对应(旧版也是按序号);服务端商品比设计稿格子少时多出的格子隐藏(旧版是显示设计稿占位、点了没反应),
//     多时打错误日志(要让设计补格子)
//   - 价格 / 钻石数文字保留设计稿里的前后缀,只替换数字(设计稿「¥6」→「¥<price>」,「X60」→「X<gemNum>」)
//   - 首充加赠(+20 ~ +620)国内包服务端不下发,旧 prefab 里也是写死的文字:保留设计稿原样
//   - 旧版 Start 里实例化的通用活动背景 ActivityCenterBg 不再加(背景用设计稿切图)
//   - 红点每次切到本页签时按本地缓存数据刷新一次(旧版只在第一次创建时算;不发请求)
//   - 旧版对外的 OnClickProduct 钩子只有 GetMoreGemsPanel 用,而它挂的是自己 prefab 里的 IAPGemPackView,不受影响,这里不提供
using System.Collections.Generic;
using System.Text.RegularExpressions;
using EventTracking;
using UI.UIPanels.FittingRoom;
using UnityEngine;
using UnityEngine.UI;

namespace Bud.GemPack
{
    public partial class GemPackController
    {
        // 工作台模块 GemPack(projects/GemPack.budui.json)里的标识;设计稿改了、重新导入后按 README 事件表核对。
        // 钻石格按界面顺序(服务端商品按同样顺序一一对应):格子按钮 / 价格文字 / 钻石数文字 / 加赠文字。
        // 加赠角标(+20 ~ +620)是切图:国内包服务端不下发加赠,旧 prefab 里也是写死的,所以没做成动态文本(填 null)
        private static readonly (string cell, string price, string gems, string bonus)[] DesignCells =
        {
            ("gemCell1", "gemCell1Price", "gemCell1Gems", null),
            ("gemCell2", "gemCell2Price", "gemCell2Gems", null),
            ("gemCell3", "gemCell3Price", "gemCell3Gems", null),
            ("gemCell4", "gemCell4Price", "gemCell4Gems", null),
            ("gemCell5", "gemCell5Price", "gemCell5Gems", null),
            ("gemCell6", "gemCell6Price", "gemCell6Gems", null),
        };
        // 右侧「充值福利」卡 = 累充入口(打开 207);红点 = 它下面名字含「红点」或 Reddot 的节点(设计稿暂时没有红点,有了再加)
        private const string CumulativeKey = "cumulativeEntry";

        private static readonly Regex Number = new Regex(@"\d[\d,.]*");

        private sealed class Cell
        {
            public string key;
            public Button button;
            public Text price, gems, bonus;
            public string priceTemplate, gemsTemplate;
            public ProductGemInfo product;
        }

        private readonly List<Cell> _cells = new List<Cell>();
        private GameObject _cumReddot;
        private RechargeBenifits _rechargeBenifits;

        // ---------- 第一次实例化(充值界面第一次切到本页签):和旧 IAPGemPackView.Awake 相同 ----------
        partial void OnViewCreate()
        {
            Wire();
#if PACKAGE_TYPE_US
            RefreshDefaultInfo();
#endif
            var datas = IAPDataManager.Inst.GetGemPackProducts();
            _rechargeBenifits = IAPDataManager.Inst.GetCumulativeRechargeData();
            if (datas == null || datas.Count != _cells.Count)
            {
                RefreshDataFromServer();
                return;
            }
            SyncProductInfo(datas);
        }

        partial void OnViewShow()
        {
            ShowReddot();
        }

        partial void OnViewAction(string key, ref bool handled)
        {
            if (key == CumulativeKey) { OnBtnCumlativeClick(); handled = true; return; }
            foreach (var c in _cells)
            {
                if (c.key != key) continue;
                OnClickCell(c);
                handled = true;
                return;
            }
        }

        // 本页是充值界面里的子视图,返回键在外层充值界面上;设计稿里万一有返回类按钮,不处理也不报
        partial void OnViewCloseRequested(ref bool handled) { handled = true; }

        // ---------- 找到设计稿里的格子,记下文字模板 ----------
        private void Wire()
        {
            var missing = new List<string>();
            foreach (var d in DesignCells)
            {
                var btn = View.GetButton(d.cell);
                if (btn == null) { missing.Add(d.cell); continue; }
                var c = new Cell { key = d.cell, button = btn, price = View.GetText(d.price), gems = View.GetText(d.gems), bonus = d.bonus == null ? null : View.GetText(d.bonus) };
                if (c.price == null) missing.Add(d.price);
                if (c.gems == null) missing.Add(d.gems);
                c.priceTemplate = c.price != null ? c.price.text : null;
                c.gemsTemplate = c.gems != null ? c.gems.text : null;
                _cells.Add(c);
            }
            if (missing.Count > 0)
                Debug.LogError($"[GemPackController] 视图里找不到这些标识:{string.Join("、", missing)}。对照工作台 README 事件表改 GemPackController.Logic.cs 顶部的 DesignCells。");

            var cum = View.GetButton(CumulativeKey);
            if (cum != null)
                foreach (var t in cum.GetComponentsInChildren<Transform>(true))
                    if (t != cum.transform && (t.name.Contains("红点") || t.name.ToLowerInvariant().Contains("reddot"))) { _cumReddot = t.gameObject; break; }
        }

        // ---------- 取数(照搬旧版)----------
        private void RefreshDataFromServer()
        {
            IAPDataManager.Inst.GetProductInfo(res =>
            {
                var gems = res.gemRechargeList;
                if (gems != null && this != null)
                {
                    SyncProductInfo(gems);
                }
            });
        }

        private void SyncProductInfo(List<ProductGemInfo> items)
        {
            if (items == null)
            {
                return;
            }
            if (items.Count > _cells.Count)
                Debug.LogError($"[GemPackController] 服务端有 {items.Count} 档钻石商品,设计稿只有 {_cells.Count} 个格子,多出来的档位显示不出来(让设计补格子)");
            for (int i = 0; i < _cells.Count; i++)
            {
                var c = _cells[i];
                c.product = i < items.Count ? items[i] : null;
                c.button.gameObject.SetActive(c.product != null);
                if (c.product != null) SetData(c, c.product);
            }
        }

        // 照搬 IAPGemItemView.SetData:价格、钻石数(海外包用本地化价格)
        private void SetData(Cell c, ProductGemInfo product)
        {
            if (c.price != null) c.price.text = FillNumber(c.priceTemplate, product.price);
            if (c.gems != null) c.gems.text = FillNumber(c.gemsTemplate, product.gemNum.ToString());
#if PACKAGE_TYPE_US
            var priceInfo = IAPDataManager.Inst.GetPriceInfo(product.productId);
            if (priceInfo != null && c.price != null)
            {
                c.price.text = priceInfo.priceLocal;
            }
#endif
        }

#if PACKAGE_TYPE_US
        // 照搬 IAPGemPackView.RefreshDefaultInfo(旧版注释:临时 Hack 做法,折扣,刷新额外 gem)
        private void RefreshDefaultInfo()
        {
            var defaultInfos = IAPDataManager.Inst.GetPriceDefaultInfos();
            if (defaultInfos == null) return;
            for (int i = 0; i < defaultInfos.Count && i < _cells.Count; i++)
            {
                var info = defaultInfos[i];
                var c = _cells[i];
                if (c.price != null) c.price.text = info.price;
                if (c.gems != null) c.gems.text = FillNumber(c.gemsTemplate, info.gems.ToString());
                if (c.bonus != null)
                {
                    c.bonus.gameObject.SetActive(info.bonus > 0);
                    c.bonus.text = "+" + info.bonus;
                }
            }
        }
#endif

        // ---------- 下单(照搬旧版,不改支付流程)----------
        private void OnClickCell(Cell c)
        {
            if (c.product == null)
            {
                return;
            }
            // 照搬 IAPGemItemView.OnClick 的打点
            if (FittingRoomPanel.curTab == MainTabs.Tab.Ugc)
            {
                LoadEvent.ReportPopupStatus("BuyDiamondsClicked", "ClickedBuygems");
            }
            OnClickItem(c.product);
        }

        private void OnClickItem(ProductGemInfo gemInfo)
        {
            if (IAPDataManager.Inst.IsOfficialChannel())
            {
                ConfirmPaymentPanel panel =
                    UIManager.Inst.OpenPanel<ConfirmPaymentPanel>(PanelId.ConfirmPaymentPanel, gemInfo.price);
                panel.SetCallback(paymentType => { BuyGem(gemInfo, paymentType); });
                return;
            }

            BuyGem(gemInfo, ConfirmPaymentPanel.PaymentType.Default);
        }

        private void BuyGem(ProductGemInfo gemInfo, ConfirmPaymentPanel.PaymentType paymentType)
        {
            var productId = gemInfo.productId;
            if (string.IsNullOrEmpty(productId))
            {
                LoggerUtils.LogError($"[IAP] Not get productId {gemInfo}");
                return;
            }

            string productName = gemInfo.gemNum + "钻";
            var channelProductInfo = gemInfo.toU8Info();
            PackPurchaseUtils.Inst.StartPurchase(channelProductInfo, paymentType, productName, OnBuyGemSuccess);
        }

        private void OnBuyGemSuccess(string orderId, ProductGemInfo productGemInfo)
        {
            ShowReward(productGemInfo);
        }

        private void ShowReward(ProductGemInfo productInfo)
        {
            if (productInfo == null)
            {
                return;
            }

            var coinNum = productInfo.gemNum;
            if (coinNum <= 0)
            {
                return;
            }

            var panel = UIManager.Inst.OpenPanel<CommonRewardPanel>(PanelId.CommonRewardPanel);
            panel.ShowRewards(new List<TaskRewardData>()
            {
                new TaskRewardData()
                {
                    num = coinNum,
                    rewardType = (int)BUDRewardType.RewardGem,
                }
            });
        }

        // ---------- 累充入口(照搬旧版)----------
        private void OnBtnCumlativeClick()
        {
            _rechargeBenifits = IAPDataManager.Inst.GetCumulativeRechargeData();
            UIManager.Inst.OpenPanel(PanelId.CumulativeRechargePanel, _rechargeBenifits);
        }

        private void ShowReddot()
        {
            if (_cumReddot == null)
                return;
            _rechargeBenifits = IAPDataManager.Inst.GetCumulativeRechargeData();
            bool on = false;
            if (_rechargeBenifits != null && _rechargeBenifits.rechargeLevelList != null)
                foreach (var levelData in _rechargeBenifits.rechargeLevelList)
                    if (levelData.rewardStatus == (int)ClaimStatus.Unlocked) { on = true; break; }
            _cumReddot.SetActive(on);
        }

        private static string FillNumber(string template, string value) =>
            string.IsNullOrEmpty(template) || !Number.IsMatch(template) ? value : Number.Replace(template, value, 1);
    }
}
