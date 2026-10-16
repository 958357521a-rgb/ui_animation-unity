/// <summary>
/// 通行证外壳 NewSeasonPassPanel 加载的赛季视图接口:旧视图继承 SeasonPassBaseView,
/// 新版(BUD UI Studio 生成的 S18 视图等)实现这个接口即可被外壳加载、切页签、刷新。
/// 放在主工程 Assets/Scripts/UI/UIPanels/SeasonPassPanel/ISeasonPassView.cs。
/// </summary>
public interface ISeasonPassView
{
    void InitData(SeasonPassConfig config);
    /// <summary>viewName:旧视图的页签名 SeasonRewardView / SeasonTaskView。</summary>
    void SwitchView(string viewName);
    void Reload();
}
