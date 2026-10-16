using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Bud.S18SeasonPass
{
    /// <summary>
    /// S18 赛季通行证子视图的业务逻辑(手写,工作台不生成也不覆盖)。
    /// 挂在原通行证外壳 NewSeasonPassPanel(PanelId 290)里:外壳按 SeasonPassConfig.ViewPrefabPath 实例化本视图,
    /// 通过 ISeasonPassView 调 InitData / SwitchView / Reload。数据沿用当前赛季(S17)的服务端接口与配置,不改服务端。
    /// 各模块分文件写(partial):
    ///   S18SeasonPassController.Reward.Logic.cs  赛季奖励页、经验条、购买等级、一键领取
    ///   S18SeasonPassController.Task.Logic.cs    每日 / 每周 / 赛季任务
    ///   S18SeasonPassController.Shop.Logic.cs    兑换商店、解锁通行证、奖励预览
    /// 模块通过下面的 partial 挂钩接入(partial 方法只能实现一次,所以按模块分名):XxxCreate(第一次实例化)、XxxRefresh(InitData / Reload / 回到前台)、XxxAction(按钮事件)、XxxPageShown(切到某页)。
    /// </summary>
    public partial class S18SeasonPassController : ISeasonPassView
    {
        // ---- 页面序号(与生成的 View.pages[] 一致,见 README 页面表)----
        public const int PageReward = 0, PageUnlock = 1, PageDaily = 2, PageWeekly = 3, PageSeasonTask = 4,
            PageShop = 5, PageShopPreview = 6, PageShopPart = 7, PageGacha = 8, PageGachaPart = 9, PageShopSoldOut = 10;

        /// <summary>当前赛季配置(任务 id、任务配置路径等),外壳 InitData 时传入。</summary>
        protected SeasonPassConfig Config { get; private set; }
        private NewSeasonPassPanel _shell;
        private bool _created;

        // ================= ISeasonPassView(外壳调用)=================
        public void InitData(SeasonPassConfig config)
        {
            Config = config;
            _shell = GetComponentInParent<NewSeasonPassPanel>();
            // 新界面自带返回键和「赛季奖励 / 赛季任务」侧栏:藏掉外壳自己的左侧页签和返回键
            if (_shell != null) _shell.SetTabViewEnable(false);
            EnsureCreated();
            RefreshAll();
        }

        /// <summary>外部要求切到某个页签(旧视图名:SeasonRewardView / SeasonTaskView)。</summary>
        public void SwitchView(string viewName)
        {
            if (view == null) return;
            GoHome();   // 先回主页:已经停在每日页时直接 OpenPage 会从同一页切到同一页,结束时把它关掉(空白)
            if (viewName == "SeasonTaskView") view.OpenPage(PageDaily);
        }

        /// <summary>回到主页并通知各模块「切到了主页」(View.ResetToHome 本身不触发 onPageChanged)。</summary>
        private void GoHome()
        {
            view.ResetToHome();
            RewardPageShown(PageReward); TaskPageShown(PageReward); ShopPageShown(PageReward);
        }

        /// <summary>数据变了(购买通行证 / 买等级 / 领奖后外部广播):重新取数刷新各模块。</summary>
        public void Reload() { RefreshAll(); }

        // ================= 生成的 Controller 挂钩 =================
        partial void OnViewCreate()
        {
            view.onPageChanged.AddListener(OnPageChanged);
            EnsureCreated();
        }

        partial void OnViewShow()
        {
            // 生成的 OnEnable 已 ResetToHome(不触发 onPageChanged):补发「切到主页」,让各模块复位当前页记录
            RewardPageShown(PageReward); TaskPageShown(PageReward); ShopPageShown(PageReward);
            if (Config != null) RefreshAll();
        }

        partial void OnViewHide() { }

        partial void OnViewAction(string key, ref bool handled)
        {
            RewardAction(key, ref handled);
            if (!handled) TaskAction(key, ref handled);
            if (!handled) ShopAction(key, ref handled);
        }

        // 主页上的返回:走外壳原来的返回(关闭面板 + 大厅的 BackAction 刷新入口状态)
        partial void OnViewCloseRequested(ref bool handled)
        {
            handled = true;
            if (_shell != null && _shell.btn_Back != null) _shell.btn_Back.onClick.Invoke();
        }

        private void EnsureCreated()
        {
            if (_created || view == null) return;
            _created = true;
            RewardCreate();
            TaskCreate();
            ShopCreate();
        }

        private void RefreshAll()
        {
            if (Config == null) return;
            RewardRefresh();
            TaskRefresh();
            ShopRefresh();
        }

        private void OnPageChanged(string pageObjectName)
        {
            var index = PageIndexOf(pageObjectName);
            if (index < 0) return;
            RewardPageShown(index); TaskPageShown(index); ShopPageShown(index);
        }

        // ---- 各模块实现的挂钩(没实现的模块编译时自动去掉调用)----
        partial void RewardCreate();
        partial void RewardRefresh();
        partial void RewardAction(string key, ref bool handled);
        partial void TaskCreate();
        partial void TaskRefresh();
        partial void TaskAction(string key, ref bool handled);
        partial void ShopCreate();
        partial void ShopRefresh();
        partial void ShopAction(string key, ref bool handled);
        /// <summary>切到某页(OpenPage / SwitchPage / Back 之后),index 见上面的页面序号;各模块只处理自己的页。</summary>
        partial void RewardPageShown(int index);
        partial void TaskPageShown(int index);
        partial void ShopPageShown(int index);

        // ================= 工具:按名字找节点(GameObject 名就是 Figma 图层名,常带「/」,不能用 Transform.Find)=================

        /// <summary>第 index 页的根节点(GameObject 名以「Page_序号_」或「Popup_序号_」开头)。</summary>
        protected Transform PageRoot(int index)
        {
            var prefixA = "Page_" + index + "_";
            var prefixB = "Popup_" + index + "_";
            foreach (Transform child in transform)
                if (child.name.StartsWith(prefixA, StringComparison.Ordinal) || child.name.StartsWith(prefixB, StringComparison.Ordinal)) return child;
            return null;
        }

        private int PageIndexOf(string pageObjectName)
        {
            if (string.IsNullOrEmpty(pageObjectName)) return -1;
            var parts = pageObjectName.Split('_');
            return parts.Length > 1 && int.TryParse(parts[1], out var i) ? i : -1;
        }

        /// <summary>深度优先找第一个名字完全相同的子孙节点(含自己)。</summary>
        protected static Transform FindDeep(Transform root, string name)
        {
            if (root == null) return null;
            if (root.name == name) return root;
            for (int i = 0; i < root.childCount; i++)
            {
                var r = FindDeep(root.GetChild(i), name);
                if (r != null) return r;
            }
            return null;
        }

        /// <summary>按路径逐层找:「内容区|奖励列表 · 可滑动|内容」(用 | 分隔,每段是完整的节点名,只在直接子节点里找)。</summary>
        protected static Transform FindPath(Transform root, string path)
        {
            if (root == null) return null;
            var cur = root;
            foreach (var seg in path.Split('|'))
            {
                Transform next = null;
                for (int i = 0; i < cur.childCount; i++) if (cur.GetChild(i).name == seg) { next = cur.GetChild(i); break; }
                if (next == null) return null;
                cur = next;
            }
            return cur;
        }

        /// <summary>所有名字完全相同的子孙节点(按层级顺序)。</summary>
        protected static List<Transform> FindAllDeep(Transform root, string name, List<Transform> into = null)
        {
            into = into ?? new List<Transform>();
            if (root == null) return into;
            if (root.name == name) into.Add(root);
            for (int i = 0; i < root.childCount; i++) FindAllDeep(root.GetChild(i), name, into);
            return into;
        }

        protected static Text TextAt(Transform root, string name) { var t = FindDeep(root, name); return t ? t.GetComponent<Text>() : null; }
        protected static Image ImageAt(Transform root, string name) { var t = FindDeep(root, name); return t ? t.GetComponent<Image>() : null; }
        protected static void SetText(Text t, string value) { if (t != null) t.text = value ?? ""; }
        protected static void SetActive(Transform t, bool on) { if (t != null && t.gameObject.activeSelf != on) t.gameObject.SetActive(on); }

        /// <summary>
        /// 列表复用:以 template 为模板,在它的父节点下保证有 count 个同级实例(模板自己算第 0 个),多余的隐藏;
        /// 实例按模板的间距(第二个设计实例与模板的位置差 step)依次排开。返回 count 个实例。
        /// 生成的按钮监听(View 里按 key 接好)只在模板上,复制出来的实例要自己接 onClick。
        /// </summary>
        protected static List<Transform> EnsureClones(Transform template, int count, Vector2 step, List<Transform> pool)
        {
            pool = pool ?? new List<Transform>();
            if (template == null) return pool;
            if (pool.Count == 0) pool.Add(template);
            var basePos = ((RectTransform)template).anchoredPosition;
            while (pool.Count < count)
            {
                var go = Instantiate(template.gameObject, template.parent);
                go.name = template.name;
                var b = go.GetComponent<Button>();
                if (b != null) b.onClick.RemoveAllListeners();
                pool.Add(go.transform);
            }
            for (int i = 0; i < pool.Count; i++)
            {
                var on = i < count;
                SetActive(pool[i], on);
                if (on) ((RectTransform)pool[i]).anchoredPosition = basePos + step * i;
            }
            return pool;
        }

        /// <summary>两个设计实例之间的位置差(如 列_12级 → 列_13级),做 EnsureClones 的 step。</summary>
        protected static Vector2 StepBetween(Transform a, Transform b)
        {
            if (a == null || b == null) return Vector2.zero;
            return ((RectTransform)b).anchoredPosition - ((RectTransform)a).anchoredPosition;
        }

        /// <summary>滚动内容按实例数撑开(横向 / 竖向),保证能滑到最后一个。</summary>
        protected static void FitContent(Transform content, Transform last, bool horizontal, float tailPadding = 8f)
        {
            if (content == null || last == null) return;
            var c = (RectTransform)content; var l = (RectTransform)last;
            var corners = new Vector3[4]; l.GetWorldCorners(corners);   // 0 左下 1 左上 2 右上 3 右下
            if (horizontal)
            {
                float need = c.InverseTransformPoint(corners[2]).x - c.rect.xMin + tailPadding, old = c.rect.width;
                if (need <= old) return;
                c.SetSizeWithCurrentAnchors(RectTransform.Axis.Horizontal, need);
                c.anchoredPosition += new Vector2(c.pivot.x * (need - old), 0);   // 左边不动
            }
            else
            {
                float need = c.rect.yMax - c.InverseTransformPoint(corners[0]).y + tailPadding, old = c.rect.height;
                if (need <= old) return;
                c.SetSizeWithCurrentAnchors(RectTransform.Axis.Vertical, need);
                c.anchoredPosition -= new Vector2(0, (1 - c.pivot.y) * (need - old));   // 上边不动
            }
        }

        /// <summary>给按钮接点击(复制出来的实例用);同时去掉旧监听。</summary>
        protected static void BindClick(Transform t, Action onClick)
        {
            if (t == null) return;
            var b = t.GetComponent<Button>();
            if (b == null) return;
            b.onClick.RemoveAllListeners();
            b.onClick.AddListener(() => onClick?.Invoke());
        }
    }
}
