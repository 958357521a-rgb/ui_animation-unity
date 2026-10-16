using System;
using System.Collections;
using System.Collections.Generic;
using Game.Event;
using Message;
using Newtonsoft.Json;
using UI.Base;
using UI.BaseWidgets;
using UnityEngine;

public class NewSeasonPassPanel : BasePanel<NewSeasonPassPanel>
{
    public CButton btn_Back;

    [Header("左侧Tab")] 
    public GameObject Go_TabView;
    public SeasonPassTabItem tabItemPrefab;
    public Transform tabContent;
    private List<SeasonPassTabItem> _tabItems = new List<SeasonPassTabItem>();
    
    [Header("右侧View")]
    public Transform viewContent;
    private SeasonPassBaseView _seasonPassView;
    private ISeasonPassView _customView;   // 新版赛季视图(S18 起,BUD UI Studio 生成,实现 ISeasonPassView)
    public Action BackAction;

    public override void OnCreate()
    {
        base.OnCreate();
        InitLeftTab();
        InitUIComponent();
        SeasonPassDataManager.Inst.OnSeasonPassDataChangeHandler += OnSeasonPassDataChange;
    }

    public override void OnShow(params object[] args)
    {
        base.OnShow(args);
        if (_seasonPassView != null || _customView != null) return;
        var type = SeasonPassDataManager.Inst.CurrentSeasonPassType;
        var config = SeasonPassDataManager.Inst.GetSeasonPassConfig(type, this.gameObject);
        var viewObj = Loader.Load<GameObject>(config.ViewPrefabPath).Instantiate(viewContent);
        _seasonPassView = viewObj.GetComponent<SeasonPassBaseView>();
        if (_seasonPassView != null)
        {
            _seasonPassView.InitData(config);
            return;
        }
        // 新版赛季视图:根节点脚本实现 ISeasonPassView(返回键、页签在视图里,视图会调 SetTabViewEnable(false) 藏掉外壳自己的)
        _customView = viewObj.GetComponent<ISeasonPassView>();
        _customView?.InitData(config);
    }

    public override void OnWindowBeFocused()
    {
        base.OnWindowBeFocused();
        MessageHelper.Broadcast(MessageName.RefreshSeasonPassTask);
    }

    public override void OnHidden()
    {
        base.OnHidden();
        SeasonPassDataManager.Inst.OnSeasonPassDataChangeHandler -= OnSeasonPassDataChange;
    }

    private void InitUIComponent()
    {
        btn_Back.onClick.AddListener(OnBackClick);
    }
    
    private void OnBackClick() {
        if (this == null) {
            return;
        }
        CloseSelf();
        BackAction?.Invoke();
    }

    #region 左侧Tab栏
    private void InitLeftTab()
    {
        var type = SeasonPassDataManager.Inst.CurrentSeasonPassType;
        var config = SeasonPassDataManager.Inst.GetSeasonPassConfig(type, this.gameObject);
        if (config != null)
        {
            var itemComp = Instantiate(tabItemPrefab, tabContent);
            itemComp.Init(type, config.TabName, OnTabClick);
            itemComp.gameObject.SetActive(true);
            _tabItems.Add(itemComp);
        }
        SeasonPassDataManager.Inst.GetSeasonPassList(type, (b, rsp) => { });
    }

    private void OnTabClick(SeasonPassType type)
    {
        _tabItems.ForEach(x => x.SetSelect(false));
        var curItem = _tabItems.Find(x => x._curSeasonPassType == type);
        curItem?.SetSelect(true);
        _seasonPassView?.gameObject.SetActive(true);
    }

    #endregion

    #region 外部调用方法

    public void SwitchView(SeasonPassType seasonPassType, string viewName)
    {
        _seasonPassView?.SwitchView(viewName);
        _customView?.SwitchView(viewName);
    }

    public void RefreshData(SeasonPassType seasonPassType)
    {
        _seasonPassView?.Reload();
        _customView?.Reload();
    }

    public void SetTabViewEnable(bool isEnable)
    {
        Go_TabView.SetActive(isEnable);
        btn_Back.gameObject.SetActive(isEnable);
    }

    public SeasonPassType GetCurSeasonPassType()
    {
        return SeasonPassDataManager.Inst.CurrentSeasonPassType;
    }
    #endregion

    private void OnSeasonPassDataChange(SeasonPassType type, SeasonPassListRsp rsp)
    {
        var isCanClaim = rsp.seasonLobbyStatus == SeasonLobbyStatus.Claimable;
        var curTabItem = _tabItems.Find(x => x._curSeasonPassType == type);
        curTabItem?.SetRedDot(isCanClaim);
    }
}

/// <summary>
/// 赛季任务 TaskId 的种类后缀。各赛季的 TaskId 都是「赛季前缀 + 种类后缀」，
/// 例如 S16SeasonDaily / S9AiGameSeasonChallenge，因此按后缀就能从 TaskIdList 里定位到具体任务。
/// </summary>
public static class SeasonTaskIdSuffix
{
    public const string Daily = "SeasonDaily";
    public const string WeeklyActive = "SeasonWeeklyActive";
    public const string WeekTask = "SeasonWeekTask";
    public const string Challenge = "SeasonChallenge";
}

public class SeasonPassConfig
{
    public string TabName;
    public string Title;
    public int SeasonPassType;
    public List<string> TaskIdList;

    /// <summary>
    /// 【联调用】SeasonPassDataManager.TestDataSeasonPassType 开启时改用这一组 TaskId，
    /// 填替身赛季（服务端真正有数据的那个赛季）的任务 id。开关关闭或此项为空时忽略。
    /// </summary>
    public List<string> TestTaskIdList;

    public string ViewPrefabPath;
    public string DailyTaskConfigPath;
    public string SeasonTaskConfigPath;
    public string WeeklyTaskConfigPath;

    /// <summary>
    /// 按种类后缀从 TaskIdList 里取出该赛季对应的 TASK_ID。
    /// 各 View 一律走这里拿 TaskId，新赛季只要在 SeasonPassConfig.json 填对 TaskIdList 即可，不用再改代码。
    /// 取不到时返回 TASK_ID.Default（调用方需自行判空，例如 S9 废弃医院就没有 SeasonDaily / SeasonWeeklyActive）。
    /// </summary>
    /// <summary>实际生效的 TaskId 列表：联调开关开启且填了 TestTaskIdList 时用后者，否则用 TaskIdList</summary>
    public List<string> EffectiveTaskIdList =>
        SeasonPassDataManager.IsTestDataSeasonOn && TestTaskIdList != null && TestTaskIdList.Count > 0
            ? TestTaskIdList
            : TaskIdList;

    public TASK_ID GetTaskId(string suffix)
    {
        var taskIdList = EffectiveTaskIdList;
        if (taskIdList == null)
        {
            return TASK_ID.Default;
        }

        foreach (var taskIdName in taskIdList)
        {
            if (string.IsNullOrEmpty(taskIdName) || !taskIdName.EndsWith(suffix, StringComparison.Ordinal))
            {
                continue;
            }

            if (Enum.TryParse<TASK_ID>(taskIdName, out var taskId))
            {
                return taskId;
            }

            Debug.LogError($"SeasonPassConfig: TaskIdList 中的 {taskIdName} 在 TASK_ID 枚举里不存在，请先在 EventCenterDataManager.TASK_ID 中补上");
        }

        return TASK_ID.Default;
    }
}
