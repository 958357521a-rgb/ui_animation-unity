using System;
using System.Collections.Generic;
using UI.Manager;
using UnityEngine;
using UnityEngine.UI;

// =====================================================================================
// S18 赛季通行证 · 奖励图标统一设置(Reward / Task / Shop 三个模块共用)
//
// 规则:
//  1. 先按奖励类型找设计稿里已有的新图标(本视图各页里的图层,第一次用时遍历一次建表);
//  2. 设计稿里没有的(时装、动作、头像框等具体物品)才走服务端图标,加载方式照搬旧代码
//     (通行证奖励轨道 = SeasonPassPanel 图集 + SeasonPassItemInfo.IconName();pgc 物品 = PgcUtils.GetIconSpriteByPgcId(Async);
//      其它货币 = PgcUtils.LoadRewardIcon);
//  3. 不管哪种来源都保持 target 在设计稿里的矩形(不 SetNativeSize、不改 sizeDelta),preserveAspect = true。
//     设计稿图标自带留白、矩形本来就比格子大一圈;服务端图标几乎不留白,直接铺满会溢出格子 →
//     服务端图标画在 target 下的子节点 IconServer 上,四周各缩进 IconServerInset(target 自己的 Image 暂时关掉),
//     换回设计稿图标时再隐藏子节点。自己新建、已按格子算好大小的图标传 inset = false。
//
// 对应表(奖励类型 → 设计稿图层名,按顺序找,先找指定页、再找全部页):
//   金币 RewardCoin(1)                  → 第 2 页「Art/图标/gold.png」
//   徽章 RewardBadge(2)                 → 第 1 页「Art/图标/voucher.png」(蓝色齿轮徽章;S17 每日宝箱 100 的徽章在任务页也用它)
//   钻石 RewardGem(3)                   → 第 1 页「Art/图标/gem.png」(紫色宝石)
//   通行证随机礼包 RewardSeasonPassRandomPack(37) → 第 1 页「Art/图标/gift.svg」(问号礼盒;商店页同名礼盒不是它)
//   活跃度 RewardActive(38)             → 第 2 页「Art/图标/activity.svg」
//   经验 RewardExperience(39) / AbandonedRewardExperience(73) → 第 2 页「Art/at xp-medal」,其次第 0 页「切图/经验徽章」
//   优优币 RewardYouYouCoin(40)         → 第 1 页「Art/图标/coin.png」,其次商店「图标/优优币」
//   通行证币 RewardSeasonPassCoin(90)   → 第 1 页「Art/图标/medal.png」(紫色八角星徽,与商店「图标/通行证币」同款),其次「图标/通行证币」
//   皮肤卡位 RewardSkinSlot(36)         → 第 1 页「Art/图标/slot-group.svg」(解锁立得「形象卡位」)
//   其余类型 / pgc 物品                 → 服务端图标
//
// 怎么验证:
//  - 任务页(第 2~4 页)每行奖励格:活跃度 = 火苗、金币 = 金币堆、经验 = EXP 奖牌,图标都在 100×100 格子范围内,×数量文字在图标上面;
//    「今日活跃度」五个宝箱:金币 / 经验 / 徽章是设计稿图标、大小一致;
//  - 解锁页(第 1 页)两张卡的奖励格:钻石 = 紫宝石、优优币 = 粉色币、徽章 = 蓝齿轮、通行证币 = 紫八角、随机礼包 = 问号礼盒,
//    时装 / 动作是服务端图标且缩在格子里;×数量和名称文字都在图标上层;
//  - 赛季奖励页(第 0 页)等级卡、50 级大奖、商店格子 / 部件 / 奖品预览同理。
// =====================================================================================
namespace Bud.S18SeasonPass
{
    public partial class S18SeasonPassController
    {
        private const string IconPassAtlas = "Assets/Loadable/UI/UIPanel/SeasonPassPanel/SeasonPassPanel.spriteatlas";
        private const string IconServerChildName = "IconServer";
        /// <summary>服务端图标四周各缩进的比例(设计稿图标自带约 1/8 留白)。</summary>
        private const float IconServerInset = 0.125f;

        /// <summary>奖励类型 → 设计稿图层(页序号 -1 = 任意页),按顺序取第一个找到的。</summary>
        private static readonly Dictionary<BUDRewardType, (int page, string name)[]> IconDesignMap = new Dictionary<BUDRewardType, (int, string)[]>
        {
            { BUDRewardType.RewardCoin, new[] { (PageDaily, "Art/图标/gold.png"), (-1, "Art/图标/gold.png") } },
            { BUDRewardType.RewardBadge, new[] { (PageUnlock, "Art/图标/voucher.png"), (-1, "Art/图标/voucher.png") } },
            { BUDRewardType.RewardGem, new[] { (PageUnlock, "Art/图标/gem.png"), (-1, "Art/图标/gem.png") } },
            { BUDRewardType.RewardSeasonPassRandomPack, new[] { (PageUnlock, "Art/图标/gift.svg") } },
            { BUDRewardType.RewardActive, new[] { (PageDaily, "Art/图标/activity.svg"), (-1, "Art/图标/activity.svg") } },
            { BUDRewardType.RewardExperience, new[] { (PageDaily, "Art/at xp-medal"), (PageReward, "切图/经验徽章"), (-1, "Art/at xp-medal") } },
            { BUDRewardType.AbandonedRewardExperience, new[] { (PageDaily, "Art/at xp-medal"), (PageReward, "切图/经验徽章"), (-1, "Art/at xp-medal") } },
            { BUDRewardType.RewardYouYouCoin, new[] { (PageUnlock, "Art/图标/coin.png"), (-1, "图标/优优币") } },
            { BUDRewardType.RewardSeasonPassCoin, new[] { (PageUnlock, "Art/图标/medal.png"), (-1, "图标/通行证币") } },
            { BUDRewardType.RewardSkinSlot, new[] { (PageUnlock, "Art/图标/slot-group.svg") } },
        };

        private Dictionary<BUDRewardType, Sprite> _iconDesign;
        private readonly Dictionary<Image, int> _iconRequest = new Dictionary<Image, int>();
        private int _iconRequestSeq;

        // ================= 对外:各种奖励数据 =================

        /// <summary>通行证奖励轨道 / 解锁页汇总(SeasonPassItemInfo):设计稿图标优先,否则旧版图集 IconName(),pgc 再兜底 pgc 图标。</summary>
        private void IconSet(Image target, SeasonPassItemInfo data, bool inset = true)
        {
            if (target == null) return;
            if (data == null) { IconShow(target, null, false, inset); return; }
            var type = data.BudRewardType;
            if (IconTryDesign(target, type, inset)) return;
            var iconName = data.IconName();
            var sp = string.IsNullOrEmpty(iconName) ? null : XAssetLoaderMgr.Inst.LoadSpriteInAltas(IconPassAtlas, iconName, target.gameObject);
            if (sp == null && type == BUDRewardType.RewardPgcResource)
            {
                var first = data.rewardInfo?.itemList != null && data.rewardInfo.itemList.Count > 0 ? data.rewardInfo.itemList[0] : null;
                var pgc = first?.pgcIdList != null && first.pgcIdList.Count > 0 ? first.pgcIdList[0] : first?.pgcId;
                if (!string.IsNullOrEmpty(pgc)) { IconSetPgc(target, pgc, inset); return; }
            }
            IconShow(target, sp, true, inset);
        }

        /// <summary>任务奖励(本地任务配置 SeasonTaskRewardInfo)。</summary>
        private void IconSet(Image target, SeasonTaskRewardInfo r, bool inset = true)
        {
            if (target == null) return;
            if (r == null) { IconShow(target, null, false, inset); return; }
            if (r.rewardType == BUDRewardType.RewardPgcResource) IconSetPgc(target, r.pgcId, inset);
            else IconSet(target, r.rewardType, inset);
        }

        /// <summary>兑换商店条目(SeasonExchangeConfigItem)。</summary>
        private void IconSet(Image target, SeasonExchangeConfigItem r, bool inset = true)
        {
            if (target == null) return;
            if (r == null) { IconShow(target, null, false, inset); return; }
            if (r.RewardType == BUDRewardType.RewardPgcResource) IconSetPgc(target, r.PgcID.ToString(), inset);
            else IconSet(target, r.RewardType, inset);
        }

        /// <summary>按奖励类型(非 pgc):设计稿图标优先,否则 PgcUtils.LoadRewardIcon。</summary>
        private void IconSet(Image target, BUDRewardType type, bool inset = true)
        {
            if (target == null) return;
            if (IconTryDesign(target, type, inset)) return;
            IconShow(target, PgcUtils.LoadRewardIcon(type, target.gameObject), true, inset);
        }

        /// <summary>具体 pgc 物品(时装 / 动作 / 头像框…):服务端图标,异步加载(同旧版任务行),迟到的回调按请求号丢弃。</summary>
        private void IconSetPgc(Image target, string pgcId, bool inset = true)
        {
            if (target == null) return;
            int req = IconNextRequest(target);
            if (string.IsNullOrEmpty(pgcId)) { IconShow(target, null, true, inset); return; }
            PgcUtils.GetIconSpriteByPgcIdAsync(pgcId, target.gameObject, sp =>
            {
                if (this == null || target == null) return;
                if (!_iconRequest.TryGetValue(target, out var cur) || cur != req) return;
                IconShow(target, sp, true, inset, false);
            });
        }

        /// <summary>套装(bundle)图标:PgcUtils.LoadBundleIcon(同旧版 PaidPackRewardItem / 兑换商店)。</summary>
        private void IconSetBundle(Image target, string bundleId, bool inset = true)
        {
            if (target == null) return;
            var sp = string.IsNullOrEmpty(bundleId) ? null : PgcUtils.LoadBundleIcon(bundleId, target.gameObject);
            IconShow(target, sp, true, inset);
        }

        /// <summary>奖品预览数据(PaidPackRewardData,照搬 PaidPackRewardItem.SetPreviewData):套装用套装图,单品用第一个 pgc 的图标。</summary>
        private void IconSet(Image target, PaidPackRewardData data, bool inset = true)
        {
            if (target == null) return;
            if (data == null) { IconShow(target, null, false, inset); return; }
            if (data.isBundle && !string.IsNullOrEmpty(data.bundleId)) { IconSetBundle(target, data.bundleId, inset); return; }
            var pgc = data.pgcIds != null && data.pgcIds.Count > 0 ? data.pgcIds[0] : null;
            if (string.IsNullOrEmpty(pgc)) { IconShow(target, null, true, inset); return; }
            // 旧版是同步 GetIconSpriteByPgcId
            IconShow(target, PgcUtils.GetIconSpriteByPgcId(pgc, target.gameObject), true, inset);
        }

        /// <summary>
        /// 格子里的文字(数量 / 名称)放到图标上层:文字所在的、与图标同父节点的那一层 SetAsLastSibling。只调层级,不改大小。
        /// </summary>
        private static void IconRaiseTexts(Transform cell, Image icon)
        {
            if (cell == null || icon == null) return;
            var parent = icon.transform.parent;
            if (parent == null) return;
            var raise = new List<Transform>();
            foreach (var t in cell.GetComponentsInChildren<Text>(true))
            {
                var cur = t.transform;
                while (cur != null && cur.parent != parent) cur = cur.parent;
                if (cur == null || cur == icon.transform || raise.Contains(cur)) continue;
                raise.Add(cur);
            }
            foreach (var r in raise) r.SetAsLastSibling();
        }

        // ================= 内部 =================

        private int IconNextRequest(Image target)
        {
            var req = ++_iconRequestSeq;
            _iconRequest[target] = req;
            return req;
        }

        private bool IconTryDesign(Image target, BUDRewardType type, bool inset)
        {
            var sp = IconDesignSprite(type);
            if (sp == null) return false;
            IconShow(target, sp, false, inset);
            return true;
        }

        /// <summary>设计稿里该奖励类型的新图标(没有返回 null)。第一次调用时遍历各页建表(此时各页图标还是设计稿原图)。</summary>
        protected Sprite IconDesignSprite(BUDRewardType type)
        {
            IconEnsureTable();
            return _iconDesign.TryGetValue(type, out var sp) ? sp : null;
        }

        /// <summary>建表:按 IconDesignMap 在各页里找图层,取它当前的 sprite。应在任何模块改图标前调用(Shop / Reward / Task 第一次设图标时自动调用)。</summary>
        private void IconEnsureTable()
        {
            if (_iconDesign != null) return;
            _iconDesign = new Dictionary<BUDRewardType, Sprite>();
            var byName = new Dictionary<string, Image>[11];
            var anyPage = new Dictionary<string, Image>();
            for (int p = 0; p < byName.Length; p++)
            {
                byName[p] = new Dictionary<string, Image>();
                var root = PageRoot(p);
                if (root == null) continue;
                foreach (var img in root.GetComponentsInChildren<Image>(true))
                {
                    if (img.sprite == null || img.name == IconServerChildName) continue;
                    if (!byName[p].ContainsKey(img.name)) byName[p][img.name] = img;
                    if (!anyPage.ContainsKey(img.name)) anyPage[img.name] = img;
                }
            }
            foreach (var kv in IconDesignMap)
                foreach (var (page, name) in kv.Value)
                {
                    Image img = null;
                    if (page >= 0 && page < byName.Length) byName[page].TryGetValue(name, out img);
                    else anyPage.TryGetValue(name, out img);
                    if (img == null || img.sprite == null) continue;
                    _iconDesign[kv.Key] = img.sprite;
                    break;
                }
        }

        /// <summary>
        /// 显示图标:target 的矩形不动、preserveAspect。server = 服务端图标且 inset 时画在缩进的子节点上;
        /// sprite 为空则整个图标不显示。newRequest = 同步设置时作废还没回来的异步请求。
        /// </summary>
        private void IconShow(Image target, Sprite sp, bool server, bool inset, bool newRequest = true)
        {
            if (target == null) return;
            if (newRequest) IconNextRequest(target);
            var child = target.transform.Find(IconServerChildName);
            var childImg = child != null ? child.GetComponent<Image>() : null;
            if (server && inset && sp != null)
            {
                if (childImg == null) childImg = IconMakeServerChild(target);
                target.enabled = false;
                childImg.sprite = sp;
                childImg.preserveAspect = true;
                childImg.color = target.color;
                childImg.enabled = true;
                if (!childImg.gameObject.activeSelf) childImg.gameObject.SetActive(true);
                return;
            }
            if (childImg != null && childImg.gameObject.activeSelf) childImg.gameObject.SetActive(false);
            target.sprite = sp;
            target.preserveAspect = true;
            target.enabled = sp != null;
        }

        private static Image IconMakeServerChild(Image target)
        {
            var go = new GameObject(IconServerChildName, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            go.layer = target.gameObject.layer;
            var rt = (RectTransform)go.transform;
            rt.SetParent(target.transform, false);
            rt.anchorMin = new Vector2(IconServerInset, IconServerInset);
            rt.anchorMax = new Vector2(1 - IconServerInset, 1 - IconServerInset);
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.offsetMin = rt.offsetMax = Vector2.zero;
            rt.SetAsFirstSibling();
            var img = go.GetComponent<Image>();
            img.raycastTarget = false;
            img.preserveAspect = true;
            return img;
        }
    }
}
