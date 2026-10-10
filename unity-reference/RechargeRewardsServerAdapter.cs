using System;
using System.Collections.Generic;
using Bud.RechargeRewards;
using Message;
using Network;
using Network.Http;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

/// <summary>
/// 充值福利新版视图(RechargeRewardsView，纯展示)与现有业务的适配层。
/// 职责：
///   1. 服务端 RechargeBenifits(IAPDataManager.GetProductInfo) -> view.ApplyServerState
///   2. 视图领取回调 -> /pay/claimRechargeBenefits -> view.CompleteClaim + 广播 RefreshCumData
///   3. 前往充值/返回 -> 交给宿主面板处理(与旧版 CumulativeRechargePanel.Btn_GoCharge 一致：关闭自身回充值页)
/// 挂在 RechargeRewards.prefab 根节点。当前没有接入任何 PanelId 入口，不影响线上旧面板；
/// 正式切换时由宿主(BasePanel 外壳)调用 SetCloseHandler + RequestServerData。
/// Catalog 档位(rewards)必须与服务端 rechargeLevelList 按金额升序一一对应，
/// 数量不一致时拒绝绑定并报错，防止错档展示。
/// </summary>
[RequireComponent(typeof(RechargeRewardsView))]
public class RechargeRewardsServerAdapter : MonoBehaviour
{
    [SerializeField] private RechargeRewardsView view;

    private readonly Dictionary<string, RechargeLevelData> _levelByRewardId = new Dictionary<string, RechargeLevelData>();
    private Action _requestClose;
    private bool _wired;

    /// <summary>宿主面板注入"关闭/返回充值页"的行为。</summary>
    public void SetCloseHandler(Action requestClose) => _requestClose = requestClose;

    private void Awake()
    {
        if (view == null) view = GetComponent<RechargeRewardsView>();
        view.Initialize();
        if (_wired) return;
        _wired = true;
        view.onClaimRequested.AddListener(OnClaimRequested);
        view.onRechargeRequested.AddListener(OnGoRecharge);
        view.onBackRequested.AddListener(OnBack);
        view.onRechargeStatusRequested.AddListener(RequestServerData);
    }

    private void OnDestroy()
    {
        if (!_wired || view == null) return;
        view.onClaimRequested.RemoveListener(OnClaimRequested);
        view.onRechargeRequested.RemoveListener(OnGoRecharge);
        view.onBackRequested.RemoveListener(OnBack);
        view.onRechargeStatusRequested.RemoveListener(RequestServerData);
    }

    /// <summary>主动向服务端拉一次数据并刷新视图(宿主 OnShow 时调用)。</summary>
    public void RequestServerData()
    {
        IAPDataManager.Inst.GetProductInfo(res =>
        {
            if (this == null) return;
            if (res?.rechargeBenefits == null)
            {
                LoggerUtils.LogError("[RechargeRewardsAdapter] rechargeBenefits is null");
                return;
            }
            Bind(res.rechargeBenefits);
        });
    }

    /// <summary>把服务端数据映射进视图。可由宿主直接传入已请求好的数据。</summary>
    public void Bind(RechargeBenifits data)
    {
        if (data?.rechargeLevelList == null || view.catalog == null)
        {
            LoggerUtils.LogError("[RechargeRewardsAdapter] 数据或 Catalog 为空，无法绑定");
            return;
        }

        var levels = new List<RechargeLevelData>(data.rechargeLevelList);
        levels.Sort((a, b) => a.rechargeNum.CompareTo(b.rechargeNum));

        // 按"档位金额(元)"对齐 Catalog 与服务端，两侧数量可以不同：
        // 配不上的逐档报错点名，联调期据此把 Catalog 档位补齐成与服务端一致。
        var rewards = view.catalog.rewards;
        if (rewards.Length != levels.Count)
            LoggerUtils.LogError($"[RechargeRewardsAdapter] Catalog 档位数 {rewards.Length} 与服务端 {levels.Count} 不一致，按金额对齐兜底");

        _levelByRewardId.Clear();
        var claimedIds = new List<string>();
        foreach (var reward in rewards)
        {
            var level = levels.Find(l => l.rechargeNum == reward.thresholdYuan);
            if (level == null)
            {
                LoggerUtils.LogError($"[RechargeRewardsAdapter] Catalog 档位 {reward.thresholdYuan} 元({reward.id})在服务端不存在，该档无法领取");
                continue;
            }
            _levelByRewardId[reward.id] = level;
            if (level.rewardStatus == (int)ClaimStatus.Claimed)
                claimedIds.Add(reward.id);
        }
        foreach (var level in levels)
        {
            if (Array.Exists(rewards, r => r.thresholdYuan == level.rechargeNum)) continue;
            LoggerUtils.LogError($"[RechargeRewardsAdapter] 服务端档位 {level.rechargeNum} 元(id={level.id}, {level.itemName})未配进 Catalog，不会显示");
        }

        // 服务端金额单位为元，视图统一用分
        view.ApplyServerState((long)data.totalRecharged * 100, claimedIds);
    }

    private void OnClaimRequested(string rewardId, int choiceIndex)
    {
        if (!_levelByRewardId.TryGetValue(rewardId, out var level))
        {
            view.CompleteClaim(rewardId, choiceIndex, false, "奖励配置缺失");
            return;
        }

        // 五选一档位取所选项的 pgcId，普通档位用配置 pgcId(与旧版 CumulativeRechargeItem.ClaimSingleItem 同参)
        int pgcId = level.pgcId;
        if (level.isOptionalReward == 1 && level.optionalPgcList != null &&
            choiceIndex >= 0 && choiceIndex < level.optionalPgcList.Count)
            pgcId = level.optionalPgcList[choiceIndex];

        var body = new JObject { ["rewardId"] = level.id, ["pgcId"] = pgcId };
        NetworkManager.Inst.SendHttpRequest(HttpUrlDefine.ClaimRechargeBenifits, HttpMethod.POST,
            JsonConvert.SerializeObject(body),
            onReceive: _ =>
            {
                if (this == null) return;
                view.CompleteClaim(rewardId, choiceIndex, true);
                MessageHelper.Broadcast(MessageName.RefreshCumData);
            },
            onFail: _ =>
            {
                if (this == null) return;
                view.CompleteClaim(rewardId, choiceIndex, false, "领取失败，请稍后重试");
            });
    }

    // 新视图自带的"钻石商城"页与现有 RechargePanel 功能重复，不启用：
    // 与旧版 Btn_GoCharge 行为保持一致 —— 交给宿主关闭本面板、回到充值页。
    private void OnGoRecharge() => _requestClose?.Invoke();

    private void OnBack() => _requestClose?.Invoke();
}
