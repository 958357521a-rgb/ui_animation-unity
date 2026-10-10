using System;
using System.Collections;
using System.Collections.Generic;
using Message;
using Newtonsoft.Json;
using UI.Base;
using UI.BaseWidgets;
using UnityEngine;
using UnityEngine.UI;

public class CumulativeRechargePanel : BasePanel<CumulativeRechargePanel>
{
    [Header("UI相关")]
    public Text Txt_ChargeCount;
    public Text Txt_ChargeCountHide;
    public CButton Btn_Close;
    public CButton Btn_ShowChargeCount;
    public CButton Btn_HideChargeCount;
    public CButton Btn_GoCharge;
    public CButton Btn_Tips;
    public CButton Btn_CloseTips;
    public GameObject Go_Tips;

    [Header("滑动条相关")] 
    public Transform ChargeItemContent;
    public CumulativeRechargeItem ItemPrefab;
    public Image Img_ChargeProgress;
    
    private RechargeBenifits _rechargeBenifits;
    private const int _boarder = 216;
    private const float _progressLen = 5052.0f;
    private const float _preItemLen = 217.5f;
    private List<CumulativeRechargeItem> _curItems = new List<CumulativeRechargeItem>();

    // ===== 新版视图(RechargeRewards)切换 =====
    // 回退开关：false 即完整恢复旧版展示，旧字段/旧逻辑全部保留未动
    public static bool UseNewView = true;
    private const string NewViewPrefabPath = "Assets/Loadable/UI/RechargePanel/RechargeRewardsView/Prefabs/RechargeRewards.prefab";
    private RechargeRewardsServerAdapter _newViewAdapter;

    public override void OnCreate()
    {
        base.OnCreate();
        MessageHelper.AddListener(MessageName.RefreshCumData, RefreshData);
    }

    protected override void OnDestroy()
    {
        base.OnDestroy();
        MessageHelper.RemoveListener(MessageName.RefreshCumData, RefreshData);
    }

    public override void OnShow(params object[] args)
    {
        base.OnShow(args);

        if (UseNewView && ShowNewView())
            return;

        InitUI();

        if (args != null && args.Length > 0)
        {
            _rechargeBenifits = (RechargeBenifits)args[0];
        }
        GetDataByHttp();
    }

    /// <summary>
    /// 实例化新版视图并隐藏旧版视觉。返回 false 表示加载失败，回落旧版流程。
    /// 新视图数据由 RechargeRewardsServerAdapter 自行拉取/领取，与旧字段互不依赖。
    /// </summary>
    private bool ShowNewView()
    {
        if (_newViewAdapter == null)
        {
            var prefab = Loader.Load<GameObject>(NewViewPrefabPath, gameObject);
            if (prefab == null)
            {
                LoggerUtils.LogError($"[CumulativeRechargePanel] 新版视图加载失败，回落旧版: {NewViewPrefabPath}");
                return false;
            }
            var go = Instantiate(prefab, transform);
            // 源 prefab 根节点曾存出过 localScale=0 的状态，这里强制归一，避免整个视图不可见
            go.transform.localScale = Vector3.one;
            // 外部工程交付的 prefab 层级是 Default(0)，UI 相机只渲染 UI 层：整树强制跟随本面板的层
            SetLayerRecursively(go.transform, gameObject.layer);
            var rt = go.transform as RectTransform;
            if (rt != null)
            {
                rt.anchorMin = Vector2.zero;
                rt.anchorMax = Vector2.one;
                rt.offsetMin = Vector2.zero;
                rt.offsetMax = Vector2.zero;
            }
            // 隐藏旧版视觉(字段引用保留，UseNewView=false 可完整回退)
            for (int i = 0; i < transform.childCount; i++)
            {
                var child = transform.GetChild(i);
                if (child != go.transform) child.gameObject.SetActive(false);
            }
            _newViewAdapter = go.GetComponent<RechargeRewardsServerAdapter>();
            if (_newViewAdapter == null) _newViewAdapter = go.AddComponent<RechargeRewardsServerAdapter>();
            _newViewAdapter.SetCloseHandler(CloseSelf);
        }
        _newViewAdapter.gameObject.SetActive(true);
        _newViewAdapter.RequestServerData();
        return true;
    }

    private static void SetLayerRecursively(Transform root, int layer)
    {
        root.gameObject.layer = layer;
        for (int i = 0; i < root.childCount; i++)
            SetLayerRecursively(root.GetChild(i), layer);
    }

    private void GetDataByHttp()
    {
        IAPDataManager.Inst.GetProductInfo(res =>
        {
            _rechargeBenifits = res.rechargeBenefits;
            if (_rechargeBenifits == null)
            {
                LoggerUtils.LogError("CumulativeRechargePanel _rechargeBenifits is NUll");
                CloseSelf();
                return;
            }

            InitByData();
        });
    }

    private void InitByData()
    {
        // // 测试数据：补充8888挡位
        // if (this._rechargeBenifits.rechargeLevelList != null &&
        //     !this._rechargeBenifits.rechargeLevelList.Exists(d => d.rechargeNum == 8888))
        // {
        //     this._rechargeBenifits.rechargeLevelList.Add(new RechargeLevelData
        //     {
        //         id = 12,
        //         rechargeNum = 8888,
        //         rewardType = 5,
        //         itemName = "8888元累充奖励",
        //         pgcId = 0,
        //         isOptionalReward = 1,
        //         rewardStatus = 2,
        //         optionalPgcList = new List<int> { 190000027, 190000028 },
        //     });
        // }

        // // 测试数据：模拟已累充到8888
        // this._rechargeBenifits.totalRecharged = 8888;

        this.Txt_ChargeCount.text = this._rechargeBenifits.totalRecharged.ToString();
        for (int i = 0; i < this._rechargeBenifits.rechargeLevelList.Count; i++)
        {
            var data = this._rechargeBenifits.rechargeLevelList[i];
            var itemObj = GameObject.Instantiate(ItemPrefab, ChargeItemContent);
            var itemComp = itemObj.GetComponent<CumulativeRechargeItem>();
            itemObj.gameObject.SetActive(true);
            itemComp.InitData(data);
            itemComp.SetIcon(i);
            _curItems.Add(itemComp);
        }
        
        InitProgress(_rechargeBenifits.totalRecharged);
    }

    private void RefreshData()
    {
        AccountDataManager.Inst.BalanceInfo.Refresh();
        // 新版视图自行管理刷新(领取后 CompleteClaim 内部已更新)，跳过旧版 item 重建
        if (UseNewView && _newViewAdapter != null) return;
        IAPDataManager.Inst.GetProductInfo(res =>
        {
           LoggerUtils.Log(JsonConvert.SerializeObject(this._rechargeBenifits.rechargeLevelList));
            _rechargeBenifits = res.rechargeBenefits;
            if (_rechargeBenifits != null)
            {
                for (int i = 0; i < this._rechargeBenifits.rechargeLevelList.Count; i++)
                {
                    var data = this._rechargeBenifits.rechargeLevelList[i];
                    _curItems[i]?.InitData(data);
                }
            }
        });
    }

    private int[] nodes = { 0, 6, 30, 68, 98, 188, 348, 648, 1288, 1888, 3688 , 5688 , 8888 , 8889}; // 节点数组

    /// <summary>
    /// 更新进度条显示
    /// </summary>
    /// <param name="currency">当前值</param>
    public void InitProgress(int cy)
    {
        int currency = cy;
        if (nodes == null || nodes.Length < 2)
        {
            Debug.LogError("节点数组至少需要两个值");
            return;
        }

        // 如果 currency 小于第一个节点
        if (currency <= nodes[0])
        {
            Img_ChargeProgress.fillAmount = 0f;
            return;
        }

        if (currency >= 8888)
        {
            currency = nodes[nodes.Length - 1];
        }

        // 如果 currency 大于等于最后一个节点
        if (currency >= nodes[nodes.Length - 1])
        {
            Img_ChargeProgress.fillAmount = 1f;
            return;
        }

        // 找到 currency 所属的段
        for (int i = 1; i < nodes.Length; i++)
        {
            if (currency <= nodes[i])
            {
                // 当前段的起点和终点
                int start = nodes[i - 1];
                int end = nodes[i];

                // 当前段占总进度条的比例
                float startFill = (float)(i - 1) / (nodes.Length - 1);
                float endFill = (float)i / (nodes.Length - 1);

                // 计算 currency 在当前段的相对进度
                float segmentProgress = (float)(currency - start) / (end - start);

                // 计算总进度条的 fillAmount
                Img_ChargeProgress.fillAmount = Mathf.Lerp(startFill, endFill, segmentProgress);
                return;
            }
        }
    }
    
    private void InitUI()
    {
        Txt_ChargeCount.gameObject.SetActive(false);
        Txt_ChargeCountHide.gameObject.SetActive(true);
        Btn_ShowChargeCount.gameObject.SetActive(true);
        Btn_HideChargeCount.gameObject.SetActive(false);
        
        Btn_Close.onClick.AddListener(CloseSelf);
        Btn_ShowChargeCount.onClick.AddListener(() => { SetChargeCountEnable(true);});
        Btn_HideChargeCount.onClick.AddListener(() => { SetChargeCountEnable(false);});
        Btn_GoCharge.onClick.AddListener(OnBtnGoChargeClick);
        
        Btn_Tips.onClick.AddListener(() => { SetTipsEnable(true);});
        Btn_CloseTips.onClick.AddListener(() => { SetTipsEnable(false);});
    }

    private void SetChargeCountEnable(bool enable)
    {
        Btn_ShowChargeCount.gameObject.SetActive(!enable);
        Btn_HideChargeCount.gameObject.SetActive(enable);
        
        Txt_ChargeCount.gameObject.SetActive(enable);
        Txt_ChargeCountHide.gameObject.SetActive(!enable);
    }

    private void SetTipsEnable(bool enable)
    {
        Go_Tips.SetActive(enable);
    }

    private void OnBtnGoChargeClick()
    {
        CloseSelf();
    }
    
}
