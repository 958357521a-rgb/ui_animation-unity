// 赛季累充福利页(热销界面「赛季累充福利」页签,RechargeId 91/93/99/101 共用的页签 prefab SeasonCumulativeView.prefab)
// 新视觉模块 AmountRechargeLibrary 的业务逻辑。手写文件:BUD UI Studio「覆盖到 Unity」不会生成、也不会覆盖它;
// 主工程里没有时,覆盖会从 BUD_UI_Studio/unity-reference/AmountRechargeLibrary/ 的这份副本一起写进去(改完主工程里的记得同步回来)。
//
// 原则:只换素材和动效,取数与领取逐行照搬旧 SeasonCumulativeView / SeasonCumulativeItem,不新增、不修改任何请求:
//   档位表    按当前赛季读 Assets/Loadable/UI/RechargePanel/CumulativeRechargePanel/Prefabs/SeasonData_sXX.json(List<RewardItem>)
//   取数      POST HttpUrlDefine.ActivityList(idList = 当前赛季累充 ActivityId)→ 累充金额 currencyAmount + 档位状态 eventList
//             (档位按序号一一对应:设计稿第 i 张卡 = json 第 i 档 = eventList[i])
//   领取      「可领取」的卡点一下 → POST HttpUrlDefine.ClaimActivityReward{activityId,eventId} → 刷新档位状态 → CommonRewardPanel 展示奖励
//            → ReddotManagerUtils.RefreshRedDot / VipDataManager.UpdateVipStatus / BalanceInfo.Refresh,并 AccountDataManager.RefreshUserInfo
//   预览      「未达成」的卡(hasPreview == 1)点一下 → 按赛季打开 CurrencyTipsPanel / PreviewManager / ProfileTitlePreviewPanel / ProfileThemePreviewPanel(逐赛季照搬)
//   前往充值  热销界面切到钻石页(RechargePanel.OnTabClick(RechargeId.GemPack))
//   金额显隐  设计稿里「金额=隐藏 / 金额=显示」两个状态层,点击互切由 View 自己处理;这里只保证第一次显示时是隐藏态(旧版默认隐藏)
//   红点      打开本页就标记当前赛季已看(SeasonCumulativeSystem.SetRed),和旧版 Start 里一致
// 和旧版的差别(只在显示上,见各处 TODO):
//   - 宿主 RechargePanel.CreateRechargeView 用 view.TryGetComponent<SeasonCumulativeView>(…)(RechargePanel.cs:576),根节点上没有这个组件时
//     只是不调用 Initialize,不会空引用;旧版靠它记下页签 RechargeId,但 GetCurActivityId 在「页签 id 对不上当前赛季」时本来就退回按赛季通行证选,
//     所以这里直接按 SeasonPassDataManager.CurrentSeasonPassType 选,结果相同
//   - 卡片上的图标 / 已领取标记 / 锁 / 进度条是设计稿的切图,View 没有暴露它们,不随状态切换(只切 status 文字);见 TODO
//   - 旧版只在 UNITY_EDITOR / DEVELOPMENT_BUILD 下编译的本地测试开关(SeasonCumulativeView.TestSkipClaimRequest)不再提供
using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using EventTracking;
using Network;
using Network.Http;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UI.Manager;
using UI.UIPanels.RechargePanel;
using UnityEngine;
using UnityEngine.UI;

namespace Bud.AmountRechargeLibrary
{
    public partial class AmountRechargeLibraryController
    {
        // 工作台模块 AmountRechargeLibrary 里的标识;设计稿改了、重新导入后按 README 事件表核对。
        // 7 张卡按界面顺序(= SeasonData_s17.json 的 7 档 = 服务端 eventList 的 7 项):整卡按钮 / 状态文字 / 奖励名文字 / 金额文字 / 奖励数量文字。
        // 奖励数量文字(×6 / ×12 / ×30 …)的标识是按设计稿里的文字生成的,设计稿改了数字这里的标识也会变;
        // 第 1 档(VIP 体验卡 ×1)和第 7 档(主页皮肤 ×1)设计稿没有数量文字,填 null。
        private static readonly (string card, string status, string name, string amount, string count)[] DesignCards =
        {
            ("cardItem",  "cardItemStatus",  "cardItemRewardName",  "cardItemAmount",  null),
            ("cardItem2", "cardItem2Status", "cardItem2RewardName", "cardItem2Amount", "cardItem26"),
            ("cardItem3", "cardItem3Status", "cardItem3RewardName", "cardItem3Amount", "cardItem312"),
            ("cardItem4", "cardItem4Status", "cardItem4RewardName", "cardItem4Amount", "cardItem430"),
            ("cardItem5", "cardItem5Status", "cardItem5RewardName", "cardItem5Amount", "cardItem530"),
            ("cardItem6", "cardItem6Status", "cardItem6RewardName", "cardItem6Amount", "cardItem660"),
            ("cardItem7", "cardItem7Status", "cardItem7RewardName", "cardItem7Amount", null),
        };
        private const string GoChargeKey = "buttonPrimary";      // 前往充值
        private const string TotalAmountKey = "totalAmount";     // 累计充值金额
        // 金额显隐:点「金额=隐藏」层 → 显示「金额=显示」层,反之亦然;切换由 View 完成,这里只处理初始状态
        private const string AmountHiddenLayerKey = "amountRechargeLibrarySwap";
        private const string AmountShownLayerKey = "amountRechargeLibraryRestore";

        // status 文字:设计稿只给了一份文字,这里按状态换;TODO 设计稿的实际文案定了以后改这三个常量(Lock 为 null 时保留设计稿原文)
        private const string StatusClaimed = "已领取";
        private const string StatusUnlocked = "可领取";
        private const string StatusLock = null;

        private static readonly Regex Number = new Regex(@"\d[\d,.]*");

        private sealed class Card
        {
            public string key;
            public Button button;
            public Text status, rewardName, amount, count;
            public string amountTemplate, countTemplate, statusTemplate;
            public RewardItem reward;            // SeasonData_sXX.json 里这一档
            public ActivityEventInfo evt;        // 服务端这一档的状态
        }

        private readonly List<Card> _cards = new List<Card>();
        private List<RewardItem> _rewardItems = new List<RewardItem>();
        private ActivityInfo _activityInfo;
        private bool _isSending;
        private string _totalTemplate;
        private Text _totalText;
        private string _spriteAtlasPath = RechargePanel.CumulativeRechargePanelAtlas;

        // ---------- 第一次实例化(充值界面第一次切到本页签):相当于旧 SeasonCumulativeView.Start ----------
        partial void OnViewCreate()
        {
            Wire();
            LoadRewardTable();
            ShowRewardTable();
            ResetAmountToHidden();
            GetDataByHttp();

            // 打开累充页也算看过,按当前赛季标记(换赛季是新 key,红点会重新出现一次)
            SeasonCumulativeSystem.Inst.SetRed();
        }

        partial void OnViewAction(string key, ref bool handled)
        {
            if (key == GoChargeKey) { OnBtnGoChargeClick(); handled = true; return; }
            if (key == AmountHiddenLayerKey || key == AmountShownLayerKey) { handled = true; return; }   // 显隐由 View 自己切
            foreach (var c in _cards)
            {
                if (c.key != key) continue;
                OnClickCard(c);
                handled = true;
                return;
            }
        }

        // 本页是热销界面里的子视图,返回键在外层面板上;旧版的 Btn_Close 监听也是注释掉的(不关面板)
        partial void OnViewCloseRequested(ref bool handled) { handled = true; }

        // ---------- 找到设计稿里的卡片,记下文字模板 ----------
        private void Wire()
        {
            var missing = new List<string>();
            foreach (var d in DesignCards)
            {
                var btn = View.GetButton(d.card);
                if (btn == null) { missing.Add(d.card); continue; }
                var c = new Card
                {
                    key = d.card,
                    button = btn,
                    status = View.GetText(d.status),
                    rewardName = View.GetText(d.name),
                    amount = View.GetText(d.amount),
                    count = d.count == null ? null : View.GetText(d.count),
                };
                if (c.status == null) missing.Add(d.status);
                if (c.rewardName == null) missing.Add(d.name);
                if (c.amount == null) missing.Add(d.amount);
                if (d.count != null && c.count == null) missing.Add(d.count);
                if (c.rewardName != null) _nameMax[c.rewardName] = c.rewardName.fontSize;   // 记下设计稿字号(最大字号)
                c.statusTemplate = c.status != null ? c.status.text : null;
                c.amountTemplate = c.amount != null ? c.amount.text : null;
                c.countTemplate = c.count != null ? c.count.text : null;
                _cards.Add(c);
            }
            _totalText = View.GetText(TotalAmountKey);
            if (_totalText == null) missing.Add(TotalAmountKey);
            _totalTemplate = _totalText != null ? _totalText.text : null;
            if (View.GetButton(GoChargeKey) == null) missing.Add(GoChargeKey);
            if (missing.Count > 0)
                Debug.LogError($"[AmountRechargeLibraryController] 视图里找不到这些标识:{string.Join("、", missing)}。对照工作台 README 事件表改 AmountRechargeLibraryController.Logic.cs 顶部的 DesignCards。");
        }

        // 奖励名(服务端下发的 title,如「优优币*12+巫灵夜游会头像框」)比设计稿的占位文字长:按文字框宽度自动缩小字号,
        // 最大 = 设计稿字号,最小 = 75%;MiddleCenter(prefab 里奖励名也是这个对齐,框中心 = 正常字号时的字位置,缩小后仍居中)。
        // 先找「单行放得下」的最大字号;缩到最小仍放不下就在最小字号折成两行(纵向 Overflow,两行约 48px,仍在底下黄色色带 54px 里)
        private void FitRewardName(Text t)
        {
            if (t == null) return;
            int max = _nameMax.TryGetValue(t, out var m) ? m : t.fontSize;
            int min = Mathf.Max(2, Mathf.RoundToInt(max * 0.75f));
            t.resizeTextForBestFit = false;
            t.alignment = TextAnchor.MiddleCenter;
            t.horizontalOverflow = HorizontalWrapMode.Wrap;
            t.verticalOverflow = VerticalWrapMode.Overflow;
            float width = t.rectTransform.rect.width;
            int size = max;
            t.fontSize = size;
            while (size > min && t.preferredWidth > width) t.fontSize = --size;
        }
        private readonly Dictionary<Text, int> _nameMax = new Dictionary<Text, int>();

        // ---------- 赛季 / 档位表(照搬旧版 GetCurActivityId / GenerateContent 的取表部分)----------
        private static ActivityId GetCurActivityId()
        {
            var currentSeason = SeasonPassDataManager.Inst.CurrentSeasonPassType;
            return currentSeason switch
            {
                SeasonPassType.S14SeasonPass => ActivityId.S14SeasonRecharge,
                SeasonPassType.S15SeasonPass => ActivityId.S15SeasonRecharge,
                SeasonPassType.S16SeasonPass => ActivityId.S16SeasonRecharge,
                SeasonPassType.S17SeasonPass => ActivityId.S17SeasonRecharge,
                _ => ActivityId.S16SeasonRecharge,
            };
        }

        private void LoadRewardTable()
        {
            string jsonPath = GetCurActivityId() switch
            {
                ActivityId.S14SeasonRecharge => "Assets/Loadable/UI/RechargePanel/CumulativeRechargePanel/Prefabs/SeasonData_s14.json",
                ActivityId.S15SeasonRecharge => "Assets/Loadable/UI/RechargePanel/CumulativeRechargePanel/Prefabs/SeasonData_s15.json",
                ActivityId.S16SeasonRecharge => "Assets/Loadable/UI/RechargePanel/CumulativeRechargePanel/Prefabs/SeasonData_s16.json",
                ActivityId.S17SeasonRecharge => "Assets/Loadable/UI/RechargePanel/CumulativeRechargePanel/Prefabs/SeasonData_s17.json",
                _ => "Assets/Loadable/UI/RechargePanel/CumulativeRechargePanel/Prefabs/SeasonData_s17.json",
            };
            var asset = Loader.Load<TextAsset>(jsonPath, gameObject);
            _rewardItems = asset != null ? JsonConvert.DeserializeObject<List<RewardItem>>(asset.text) : null;
            if (_rewardItems == null) _rewardItems = new List<RewardItem>();
            // 设计稿固定 7 张卡:档位表多了显示不出来(让设计补卡),少了的卡隐藏
            if (_rewardItems.Count > _cards.Count)
                Debug.LogError($"[AmountRechargeLibraryController] 当前赛季有 {_rewardItems.Count} 档奖励,设计稿只有 {_cards.Count} 张卡,多出来的档位显示不出来(让设计补卡)");
            for (int i = 0; i < _cards.Count; i++)
                _cards[i].reward = i < _rewardItems.Count ? _rewardItems[i] : null;
        }

        // 照搬 SeasonCumulativeItem.OnInitCreate 的文字部分:奖励名 = title,金额 = progress + 「元」,数量 = 「x」+ rewardNum1
        // 金额 / 数量文字保留设计稿里的前后缀,只替换数字(设计稿「6元」→「<progress>元」,「×12」→「×<rewardNum1>」)
        private void ShowRewardTable()
        {
            foreach (var c in _cards)
            {
                c.button.gameObject.SetActive(c.reward != null);
                if (c.reward == null) continue;
                if (c.rewardName != null) { c.rewardName.text = c.reward.title; FitRewardName(c.rewardName); }
                if (c.amount != null) c.amount.text = FillNumber(c.amountTemplate, c.reward.progress.ToString());
                // TODO 第 1、7 档设计稿没有数量文字;其它档设计稿的数量文字要和 json 的 rewardNum1 对得上(S17:6/12/30/30/60)
                if (c.count != null) c.count.text = FillNumber(c.countTemplate, c.reward.rewardNum1.ToString());
                // TODO 奖励图标(旧版按 rewardIcon1/rewardIcon2 从图集加载)、双奖励布局、「有预览」角标、已领取 / 锁 / 可领取高亮、进度条
                // 在设计稿里都是写死的切图,View 没有暴露它们的 Image,不随赛季 / 状态变化。当前只对得上 S17 的 7 档;
                // 要随状态切换需让设计把这几层做成「状态=xxx」的互切图层(像金额显隐那样),再在 View 里暴露出来。
                SetStatus(c, ClaimStatus.Lock);
            }
        }

        // 旧版默认金额是隐藏的(Txt_ChargeCountHide 显示、Btn_ShowChargeCount 显示):保证第一次显示是「金额=隐藏」层
        private void ResetAmountToHidden()
        {
            var hidden = View.GetButton(AmountHiddenLayerKey);
            var shown = View.GetButton(AmountShownLayerKey);
            if (hidden == null || shown == null) return;
            hidden.gameObject.SetActive(true);
            shown.gameObject.SetActive(false);
        }

        // ---------- 取数(照搬旧 SeasonCumulativeView.GetDataByHttp / OnGetActivityListSuccess / InitListUI)----------
        private void GetDataByHttp()
        {
            ActivityCenterInfoReq req = new ActivityCenterInfoReq();
            req.idList = new List<string>
            {
                GetCurActivityId().ToString()
            };
            NetworkManager.Inst.SendHttpRequest(HttpUrlDefine.ActivityList, HttpMethod.POST,
                JsonConvert.SerializeObject(req), (content) =>
                {
                    ActivityResponse activityResponse = JsonConvert.DeserializeObject<ActivityResponse>(content);
                    if (this != null && activityResponse.list != null)
                    {
                        OnGetActivityListSuccess(activityResponse.list);
                    }
                },
                (error) =>
                {
                });
        }

        private void OnGetActivityListSuccess(List<ActivityInfo> activityList)
        {
            // 旧版在这里先 Load 一次 SeasonCumulativeView.json 判空(只判空,内容不用),保持一致
            var textAsset = Loader.Load<TextAsset>("Assets/Loadable/UI/RechargePanel/CumulativeRechargePanel/Prefabs/SeasonCumulativeView.json", gameObject);
            if (textAsset == null)
            {
                return;
            }

            var activityInfo = activityList.Find(x => x.activityId == GetCurActivityId().ToString());
            if (activityInfo == null)
            {
                return;
            }

            _activityInfo = activityInfo;
            ShowTotalAmount(_activityInfo.currencyAmount);

            Dictionary<string, object> superProperties = AnalyticsManager.Inst.GetSuperProperties();
            superProperties["season_charge_amount"] = _activityInfo.currencyAmount;
            AnalyticsManager.Inst.SetSuperProperties(superProperties);  //上报赛季累充公共属性

            // TODO 旧版这里还会按累充金额刷进度条(InitProgress);设计稿没有可填充的进度条 Image,暂无对应
            InitListUI(_activityInfo.eventList);
        }

        private void ShowTotalAmount(int amount)
        {
            if (_totalText != null) _totalText.text = FillNumber(_totalTemplate, amount.ToString());
        }

        private void InitListUI(List<ActivityEventInfo> eventDatas)
        {
            if (eventDatas == null || eventDatas.Count == 0)
            {
                return;
            }
            if (eventDatas.Count != _cards.Count)
                Debug.LogError($"[AmountRechargeLibraryController] 服务端有 {eventDatas.Count} 档,设计稿有 {_cards.Count} 张卡,按序号一一对应,多出 / 缺少的档位对不上");
            for (int i = 0; i < _cards.Count; i++)
            {
                var c = _cards[i];
                c.evt = i < eventDatas.Count ? eventDatas[i] : null;
                if (c.evt != null) SetStatus(c, (ClaimStatus)c.evt.eventStatus);
            }
        }

        // 旧版 RefreshClaimStatus 的显示部分:这里只切 status 文字(其余状态层见 ShowRewardTable 的 TODO)
        private void SetStatus(Card c, ClaimStatus status)
        {
            if (c.status == null) return;
            switch (status)
            {
                case ClaimStatus.Claimed: c.status.text = StatusClaimed; break;
                case ClaimStatus.Unlocked: c.status.text = StatusUnlocked; break;
                default: c.status.text = StatusLock ?? c.statusTemplate; break;
            }
        }

        // ---------- 点卡:可领取 → 领取;未达成 → 预览;已领取 → 无(旧版 Btn_Claim / Btn_Preview 在不同状态下互斥显示)----------
        private void OnClickCard(Card c)
        {
            if (c.reward == null || c.evt == null) return;   // 服务端数据还没回来
            switch ((ClaimStatus)c.evt.eventStatus)
            {
                case ClaimStatus.Unlocked:
                    ClaimRewardItem(c.evt, c.reward);
                    break;
                case ClaimStatus.Claimed:
                    break;
                default:
                    if (c.reward.hasPreview == 1) RewarPreview(c.reward.rewardId);
                    break;
            }
        }

        // ---------- 领取(照搬旧 SeasonCumulativeView.ClaimRewardItem / OnClaimRewardItemSuccess / ShowRewards)----------
        private void ClaimRewardItem(ActivityEventInfo eventInfo, RewardItem rewardItem)
        {
            if ((ClaimStatus)eventInfo.eventStatus == ClaimStatus.Claimed)
            {
                return;
            }

            if ((ClaimStatus)eventInfo.eventStatus == ClaimStatus.Lock)
            {
                return;
            }

            if (_isSending)
            {
                return;
            }

            if (_activityInfo == null)
            {
                return;
            }

            _isSending = true;

            JObject jObject = new JObject()
            {
                ["activityId"] = _activityInfo.activityId,
                ["eventId"] = eventInfo.eventId
            };
            NetworkManager.Inst.SendHttpRequest(HttpUrlDefine.ClaimActivityReward,
                HttpMethod.POST,
                JsonConvert.SerializeObject(jObject),
                (content) =>
                {
                    ActivityEventClaimResponse activityEventClaimResponse =
                        JsonConvert.DeserializeObject<ActivityEventClaimResponse>(content);
                    _isSending = false;
                    OnClaimRewardItemSuccess(activityEventClaimResponse, rewardItem);
                    AccountDataManager.Inst.RefreshUserInfo(); //刷新UserInfo
                },
                (error) =>
                { _isSending = false; });
        }

        private void OnClaimRewardItemSuccess(ActivityEventClaimResponse response, RewardItem rewardItem)
        {
            if (this == null || gameObject == null)
            {
                return;
            }

            var eventInfo = _activityInfo.eventList.Find(x => x.eventId == response.eventInfo.eventId);
            if (eventInfo == null)
            {
                return;
            }

            eventInfo.eventStatus = response.eventInfo.eventStatus;
            RefreshRewardItems();

            ShowRewards(rewardItem);
            ReddotManagerUtils.Inst.RefreshRedDot();
            VipDataManager.Inst.UpdateVipStatus();
            AccountDataManager.Inst.BalanceInfo.Refresh();
        }

        // 照搬旧 RefreshRewardItems:eventList 里的状态变了,逐档刷新显示
        private void RefreshRewardItems()
        {
            if (_activityInfo.eventList == null)
                return;

            if (_cards.Count != _activityInfo.eventList.Count)
            {
                LoggerUtils.LogError("[SunnyDoll] Refresh Event ItemView fail");
                return;
            }

            for (int i = 0; i < _activityInfo.eventList.Count; i++)
            {
                _cards[i].evt = _activityInfo.eventList[i];
                SetStatus(_cards[i], (ClaimStatus)_activityInfo.eventList[i].eventStatus);
            }
        }

        private void ShowRewards(RewardItem rewardItem)
        {
            var panel = UIManager.Inst.OpenPanel<CommonRewardPanel>(PanelId.CommonRewardPanel);
            List<CommonRewardItemData> rewardItemDatas = new List<CommonRewardItemData>();
            if (string.IsNullOrEmpty(rewardItem.rewardIcon2))
            {
                rewardItemDatas.Add(new CommonRewardItemData()
                {
                    IconSp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(_spriteAtlasPath, rewardItem.rewardIcon1,
                        gameObject),
                    RewardAmount = rewardItem.rewardNum1,
                    rewardName = rewardItem.rewardName1,
                    rewardType = rewardItem.rewardType,
                    pgcId = GetRewardPgcId(rewardItem, 0)
                });
            }
            else
            {
                rewardItemDatas.Add(new CommonRewardItemData()
                {
                    IconSp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(_spriteAtlasPath, rewardItem.rewardIcon1,
                        gameObject),
                    RewardAmount = rewardItem.rewardNum1,
                    rewardName = rewardItem.rewardName1,
                    rewardType = rewardItem.rewardType1,
                    pgcId = GetRewardPgcId(rewardItem, 0)
                });
                rewardItemDatas.Add(new CommonRewardItemData()
                {
                    IconSp = XAssetLoaderMgr.Inst.LoadSpriteInAltas(_spriteAtlasPath, rewardItem.rewardIcon2,
                        gameObject),
                    RewardAmount = rewardItem.rewardNum2,
                    rewardName = rewardItem.rewardName2,
                    rewardType = rewardItem.rewardType2,
                    pgcId = GetRewardPgcId(rewardItem, 1)
                });
            }
            panel.ShowRewards(rewardItemDatas);
        }

        // 取某个奖励位的 pgcId:SeasonData_sXX.json 里 pgcIds 按奖励位下标对齐,只有一个奖励时也可以直接写 pgcId 字段(照搬旧版)
        private static string GetRewardPgcId(RewardItem rewardItem, int index)
        {
            if (rewardItem.pgcIds != null && index < rewardItem.pgcIds.Count)
            {
                return rewardItem.pgcIds[index];
            }

            return index == 0 ? rewardItem.pgcId : string.Empty;
        }

        // ---------- 预览(逐赛季照搬旧 SeasonCumulativeItem.RewarPreview)----------
        private void RewarPreview(string id)
        {
            switch (SeasonPassDataManager.Inst.CurrentSeasonPassType)
            {
                case SeasonPassType.S14SeasonPass:
                    PreviewS14(id);
                    break;
                case SeasonPassType.S15SeasonPass:
                    PreviewS15(id);
                    break;
                case SeasonPassType.S16SeasonPass:
                    PreviewS16(id);
                    break;
                case SeasonPassType.S17SeasonPass:
                    PreviewS17(id);
                    break;
            }
        }

        private static void PreviewVipTrial(bool withText)
        {
            var panel = UIManager.Inst.OpenPanel<CurrencyTipsPanel>(PanelId.CurrencyTipsPanel);
            if (withText)
                panel.UpdateUI(PgcUtils.LoadRewardIcon(BUDRewardType.RewardVipFreeTrail, panel.gameObject), "VIP体验卡1天", null, "特殊权益，领取后VIP月卡有效期增加1天");
            else
                panel.UpdateUI(PgcUtils.LoadRewardIcon(BUDRewardType.RewardVipFreeTrail, panel.gameObject), null, BUDRewardType.RewardVipFreeTrail);
        }

        private static void PreviewYouYouCoin()
        {
            PreviewManager.Inst.ShowPreview(new RewardPreviewInfo(BUDRewardType.RewardYouYouCoin, CurrencyType.YouYouCoin, "", "", ""));
        }

        private static void PreviewAvatarFrame(int headCycleId)
        {
            HeadCycleData headData = UserUIWidgetManager.Inst.GetHeadCycleDataById(headCycleId);
            if (headData != null)
            {
                PreviewManager.Inst.ShowAvatarFramePreview(headData.Id);
            }
        }

        private static void PreviewChatBubble(int chatBubbleId)
        {
            GameChatBubbleData chatData = UserUIWidgetManager.Inst.GetChatDataByID(chatBubbleId);
            if (chatData != null)
            {
                var info = new RewardPreviewInfo(BUDRewardType.RewardChatBubbles, CurrencyType.None, chatData.PgcId, chatData.Name, "");
                info.SetTitleAndDes(chatData.Name, chatData.Desc);
                PreviewManager.Inst.ShowPreview(info);
            }
        }

        private static void PreviewS14(string id)
        {
            switch (id)
            {
                case "1": PreviewVipTrial(false); break;
                case "2": PreviewYouYouCoin(); break;
                case "3": PreviewAvatarFrame(49); break;
                case "4": PreviewYouYouCoin(); break;
                case "5": PreviewChatBubble(29); break;
                case "6": UIManager.Inst.OpenPanel<ProfileTitlePreviewPanel>(PanelId.ProfileTitlePreviewPanel, 29); break;
                case "7":
                    // 旧版按页签 id 是否 S14SeasonRecharge 选 S14 / S15 主页皮肤;子视图拿不到页签 id,S14 赛季里就是 S14 的皮肤
                    UIManager.Inst.OpenPanel<ProfileThemePreviewPanel>(PanelId.ProfileThemePreviewPanel, ProfileTheme.S14Season);
                    break;
            }
        }

        private static void PreviewS15(string id)
        {
            switch (id)
            {
                case "1": PreviewVipTrial(false); break;
                case "2": PreviewYouYouCoin(); break;
                case "3": PreviewAvatarFrame(49); break;
                case "4": PreviewYouYouCoin(); break;
                case "5": PreviewChatBubble(29); break;
                case "6": UIManager.Inst.OpenPanel<ProfileTitlePreviewPanel>(PanelId.ProfileTitlePreviewPanel, 29); break;
                case "7": UIManager.Inst.OpenPanel<ProfileThemePreviewPanel>(PanelId.ProfileThemePreviewPanel, ProfileTheme.S15Season); break;
            }
        }

        private static void PreviewS16(string id)
        {
            switch (id)
            {
                case "1": PreviewVipTrial(true); break;
                case "2": PreviewYouYouCoin(); break;
                case "3": PreviewManager.Inst.ShowPreview(new RewardPreviewInfo(BUDRewardType.RewardPgcResource, CurrencyType.None, "40100612", "舞剑", "")); break;
                case "4": PreviewYouYouCoin(); break;
                case "5": PreviewChatBubble(36); break;
                case "6": UIManager.Inst.OpenPanel<ProfileTitlePreviewPanel>(PanelId.ProfileTitlePreviewPanel, 38); break;
                case "7": UIManager.Inst.OpenPanel<ProfileThemePreviewPanel>(PanelId.ProfileThemePreviewPanel, ProfileTheme.S16Season); break;
            }
        }

        private static void PreviewS17(string id)
        {
            // 七档奖励见 SeasonData_s17.json,点预览展示的是该档里的非货币奖励(纯优优币档就展示优优币)
            switch (id)
            {
                case "1": PreviewVipTrial(true); break;
                case "2": PreviewYouYouCoin(); break;
                case "3": PreviewAvatarFrame(59); break;                 // 优优币*12 + 巫灵夜游会头像框(HeadCycleConfig.json Id=59)
                case "4": PreviewYouYouCoin(); break;
                case "5": PreviewChatBubble(38); break;                  // 优优币*30 + 巫灵夜游会聊天气泡(ChatBubbleConfig.json Id=38)
                case "6": UIManager.Inst.OpenPanel<ProfileTitlePreviewPanel>(PanelId.ProfileTitlePreviewPanel, 42); break;   // 优优币*60 + 称号(TitleConfig.json Id=42)
                case "7": UIManager.Inst.OpenPanel<ProfileThemePreviewPanel>(PanelId.ProfileThemePreviewPanel, ProfileTheme.S17Season); break;   // 旧版注释:Theme_42 美术资源未进前点这里会加载失败
            }
        }

        // ---------- 前往充值(照搬旧 OnBtnGoChargeClick)----------
        private void OnBtnGoChargeClick()
        {
            if (UIManager.Inst.TryFindPanel<RechargePanel>(PanelId.RechargePanel, out var panel))
            {
                panel.OnTabClick(RechargeId.GemPack);
            }
        }

        private static string FillNumber(string template, string value) =>
            string.IsNullOrEmpty(template) || !Number.IsMatch(template) ? value : Number.Replace(template, value, 1);
    }
}
