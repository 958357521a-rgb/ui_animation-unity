using System.Collections.Generic;
using System.Linq;
using System.Text;
using TMPro;
using UnityEditor;
using UnityEditor.U2D;
using UnityEngine;
using UnityEngine.U2D;
using UnityEngine.UI;

/// <summary>
/// UI 导入体检:扫描(外部工程交付的)UI prefab,按主工程硬性规范逐项检查。
/// 与 Docs/UI预制体替换规范.md §3 对齐总清单一一对应,均为试点真实踩坑:
///   [错误] 丢失脚本引用 / 节点 Layer≠UI / 节点缩放为 0 / 字体缺失或不在白名单
///   [警告] sprite 未进入任何 SpriteAtlas / 使用 TMP(项目 UI 规范为 Text)/ 根节点未激活 / 自定义材质
/// 入口:Project 窗口选中 prefab 或文件夹 → 右键 Assets/BUD工具/UI导入体检;支持"复制Markdown报告"贴进 MR。
/// </summary>
public class UIImportHealthChecker : EditorWindow
{
    private const string FontWhitelistRoot = "Assets/Arts/Font/";

    private enum Severity { Error, Warning, Info }

    private class Issue
    {
        public Severity severity;
        public string prefabPath;
        public string message;
        public Object context; // ping 用
    }

    private readonly List<Issue> _issues = new List<Issue>();
    private readonly List<string> _scannedPrefabs = new List<string>();
    private Vector2 _scroll;
    private Object _target;
    private int _errorCount, _warningCount;

    // 图集覆盖缓存(一次扫描构建一次)
    private List<string> _atlasFolders;
    private HashSet<string> _atlasSpriteGuids;

    [MenuItem("Assets/BUD工具/UI导入体检", false, 20)]
    private static void CheckSelection()
    {
        var window = GetWindow<UIImportHealthChecker>("UI导入体检");
        window._target = Selection.activeObject;
        window.Scan();
        window.Show();
    }

    [MenuItem("Assets/BUD工具/UI导入体检", true)]
    private static bool CheckSelectionValidate() => Selection.activeObject != null;

    [MenuItem("BUD工具/UI导入体检窗口")]
    private static void OpenWindow() => GetWindow<UIImportHealthChecker>("UI导入体检").Show();

    private void OnGUI()
    {
        EditorGUILayout.BeginHorizontal(EditorStyles.toolbar);
        _target = EditorGUILayout.ObjectField(_target, typeof(Object), false, GUILayout.MinWidth(220));
        if (GUILayout.Button("扫描", EditorStyles.toolbarButton, GUILayout.Width(60))) Scan();
        if (GUILayout.Button("复制Markdown报告", EditorStyles.toolbarButton, GUILayout.Width(130)))
        {
            EditorGUIUtility.systemCopyBuffer = BuildMarkdownReport();
            ShowNotification(new GUIContent("报告已复制到剪贴板"));
        }
        GUILayout.FlexibleSpace();
        EditorGUILayout.EndHorizontal();

        if (_scannedPrefabs.Count > 0)
        {
            var color = _errorCount > 0 ? "red" : (_warningCount > 0 ? "orange" : "green");
            var verdict = _errorCount > 0 ? "不通过" : (_warningCount > 0 ? "通过(有警告)" : "通过");
            EditorGUILayout.LabelField(
                $"扫描 {_scannedPrefabs.Count} 个 prefab:{_errorCount} 错误 / {_warningCount} 警告 → <color={color}><b>{verdict}</b></color>",
                new GUIStyle(EditorStyles.label) { richText = true });
        }
        else
        {
            EditorGUILayout.HelpBox("在 Project 窗口选中交付的 prefab 或整个文件夹,点击\"扫描\"。", MessageType.Info);
        }

        _scroll = EditorGUILayout.BeginScrollView(_scroll);
        string curPrefab = null;
        foreach (var issue in _issues)
        {
            if (issue.prefabPath != curPrefab)
            {
                curPrefab = issue.prefabPath;
                EditorGUILayout.Space(4);
                EditorGUILayout.LabelField(curPrefab, EditorStyles.boldLabel);
            }
            EditorGUILayout.BeginHorizontal();
            var icon = issue.severity == Severity.Error ? "console.erroricon.sml"
                : issue.severity == Severity.Warning ? "console.warnicon.sml" : "console.infoicon.sml";
            GUILayout.Label(EditorGUIUtility.IconContent(icon), GUILayout.Width(20), GUILayout.Height(18));
            EditorGUILayout.LabelField(issue.message, EditorStyles.wordWrappedLabel);
            if (issue.context != null && GUILayout.Button("定位", GUILayout.Width(44)))
                EditorGUIUtility.PingObject(issue.context);
            EditorGUILayout.EndHorizontal();
        }
        EditorGUILayout.EndScrollView();
    }

    private void Scan()
    {
        _issues.Clear();
        _scannedPrefabs.Clear();
        _errorCount = _warningCount = 0;
        BuildAtlasCache();

        foreach (var path in CollectPrefabPaths())
        {
            _scannedPrefabs.Add(path);
            CheckPrefab(path);
        }

        _errorCount = _issues.Count(i => i.severity == Severity.Error);
        _warningCount = _issues.Count(i => i.severity == Severity.Warning);
        Debug.Log($"[UI导入体检] 扫描 {_scannedPrefabs.Count} 个 prefab:{_errorCount} 错误 / {_warningCount} 警告");
        Repaint();
    }

    private IEnumerable<string> CollectPrefabPaths()
    {
        var result = new List<string>();
        var targets = Selection.objects != null && Selection.objects.Length > 0 && _target == Selection.activeObject
            ? Selection.objects
            : new[] { _target };
        foreach (var obj in targets)
        {
            if (obj == null) continue;
            var path = AssetDatabase.GetAssetPath(obj);
            if (string.IsNullOrEmpty(path)) continue;
            if (AssetDatabase.IsValidFolder(path))
                result.AddRange(AssetDatabase.FindAssets("t:Prefab", new[] { path })
                    .Select(AssetDatabase.GUIDToAssetPath));
            else if (path.EndsWith(".prefab"))
                result.Add(path);
        }
        return result.Distinct().OrderBy(p => p);
    }

    private void BuildAtlasCache()
    {
        _atlasFolders = new List<string>();
        _atlasSpriteGuids = new HashSet<string>();
        foreach (var guid in AssetDatabase.FindAssets("t:SpriteAtlas"))
        {
            var atlasPath = AssetDatabase.GUIDToAssetPath(guid);
            var atlas = AssetDatabase.LoadAssetAtPath<SpriteAtlas>(atlasPath);
            if (atlas == null) continue;
            foreach (var packable in atlas.GetPackables())
            {
                if (packable == null) continue;
                var p = AssetDatabase.GetAssetPath(packable);
                if (string.IsNullOrEmpty(p)) continue;
                if (AssetDatabase.IsValidFolder(p)) _atlasFolders.Add(p + "/");
                else _atlasSpriteGuids.Add(AssetDatabase.AssetPathToGUID(p));
            }
        }
    }

    private bool IsSpriteInAtlas(string spritePath)
    {
        if (_atlasSpriteGuids.Contains(AssetDatabase.AssetPathToGUID(spritePath))) return true;
        for (int i = 0; i < _atlasFolders.Count; i++)
            if (spritePath.StartsWith(_atlasFolders[i])) return true;
        return false;
    }

    private void CheckPrefab(string path)
    {
        var root = AssetDatabase.LoadAssetAtPath<GameObject>(path);
        if (root == null)
        {
            Add(Severity.Error, path, "prefab 加载失败(文件损坏或 YAML 非法)", null);
            return;
        }

        int uiLayer = LayerMask.NameToLayer("UI");
        var wrongLayer = new List<string>();
        var zeroScale = new List<string>();
        int tmpCount = 0, rawImageCount = 0;

        // 根节点状态
        if (!root.activeSelf)
            Add(Severity.Warning, path, "根节点 Active 为关闭状态,接入后需要代码显式激活", root);
        if (!NearlyOne(root.transform.localScale))
            Add(Severity.Error, path, $"根节点 localScale = {root.transform.localScale},必须为 (1,1,1) —— 试点事故:整界面不可见", root);

        foreach (var t in root.GetComponentsInChildren<Transform>(true))
        {
            var go = t.gameObject;
            var nodePath = NodePath(t, root.transform);

            // 丢失脚本
            int missing = GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(go);
            if (missing > 0)
                Add(Severity.Error, path, $"节点 [{nodePath}] 有 {missing} 个丢失脚本(Missing Script)", go);

            // Layer
            if (go.layer != uiLayer) wrongLayer.Add(nodePath);

            // 缩放为 0(根节点已单独报,这里报子节点)
            if (t != root.transform && HasZeroAxis(t.localScale)) zeroScale.Add($"{nodePath} = {t.localScale}");

            // 字体
            var text = go.GetComponent<Text>();
            if (text != null)
            {
                if (text.font == null)
                    Add(Severity.Error, path, $"节点 [{nodePath}] 的 Text 字体为空(引用丢失)", go);
                else
                {
                    var fontPath = AssetDatabase.GetAssetPath(text.font);
                    bool builtin = fontPath.Contains("unity default resources") || fontPath.StartsWith("Library/");
                    if (builtin || !fontPath.StartsWith(FontWhitelistRoot))
                        Add(Severity.Error, path,
                            $"节点 [{nodePath}] 字体 [{text.font.name}] 不在白名单({FontWhitelistRoot}) → 需替换为项目字体",
                            go);
                }
            }
            if (go.GetComponent<TMP_Text>() != null) tmpCount++;

            // 散图未入图集
            var image = go.GetComponent<Image>();
            if (image != null && image.sprite != null)
            {
                var sp = AssetDatabase.GetAssetPath(image.sprite);
                bool skip = string.IsNullOrEmpty(sp) || sp.Contains("unity_builtin_extra") ||
                            sp.Contains("unity default resources") || sp.StartsWith("Packages/");
                if (!skip && !IsSpriteInAtlas(sp))
                    Add(Severity.Warning, path, $"节点 [{nodePath}] 的 sprite 未进入任何 SpriteAtlas:{sp}", image.sprite);
            }
            if (go.GetComponent<RawImage>() != null) rawImageCount++;

            // 自定义材质(默认 UI 材质之外的需真机验证 shader)
            var graphic = go.GetComponent<Graphic>();
            if (graphic != null && graphic.material != null &&
                graphic.material != Graphic.defaultGraphicMaterial &&
                graphic.material.shader != null)
                Add(Severity.Warning, path,
                    $"节点 [{nodePath}] 使用自定义材质 [{graphic.material.name}](shader: {graphic.material.shader.name}),需 URP 真机验证",
                    graphic.material);
        }

        if (wrongLayer.Count > 0)
            Add(Severity.Error, path,
                $"{wrongLayer.Count} 个节点 Layer≠UI(试点事故:UI 相机按层剔除,零报错零像素)。示例:{string.Join("、", wrongLayer.Take(5))}{(wrongLayer.Count > 5 ? " …" : "")}",
                root);
        if (zeroScale.Count > 0)
            Add(Severity.Error, path, $"{zeroScale.Count} 个子节点缩放含 0:{string.Join("、", zeroScale.Take(3))}", root);
        if (tmpCount > 0)
            Add(Severity.Warning, path, $"使用了 {tmpCount} 个 TMP 文本组件(项目 UI 规范为 UGUI Text),请确认", root);
        if (rawImageCount > 0)
            Add(Severity.Info, path, $"含 {rawImageCount} 个 RawImage(不走图集,请确认为 RenderTexture/大图专用)", root);
    }

    private static bool NearlyOne(Vector3 v) =>
        Mathf.Abs(v.x - 1) < 0.001f && Mathf.Abs(v.y - 1) < 0.001f && Mathf.Abs(v.z - 1) < 0.001f;

    private static bool HasZeroAxis(Vector3 v) =>
        Mathf.Abs(v.x) < 0.0001f || Mathf.Abs(v.y) < 0.0001f || Mathf.Abs(v.z) < 0.0001f;

    private static string NodePath(Transform t, Transform root)
    {
        if (t == root) return t.name;
        var sb = new StringBuilder(t.name);
        var cur = t.parent;
        while (cur != null && cur != root)
        {
            sb.Insert(0, cur.name + "/");
            cur = cur.parent;
        }
        return sb.ToString();
    }

    private void Add(Severity severity, string prefabPath, string message, Object context)
    {
        _issues.Add(new Issue { severity = severity, prefabPath = prefabPath, message = message, context = context });
    }

    private string BuildMarkdownReport()
    {
        var sb = new StringBuilder();
        sb.AppendLine("# UI 导入体检报告");
        sb.AppendLine();
        sb.AppendLine($"- 扫描 prefab:{_scannedPrefabs.Count} 个");
        sb.AppendLine($"- 结果:**{_errorCount} 错误 / {_warningCount} 警告** → {(_errorCount > 0 ? "❌ 不通过,请按下表修正后重新交付" : "✅ 通过")}");
        sb.AppendLine();
        sb.AppendLine("| 级别 | Prefab | 问题 |");
        sb.AppendLine("| --- | --- | --- |");
        foreach (var i in _issues)
        {
            var tag = i.severity == Severity.Error ? "🔴错误" : i.severity == Severity.Warning ? "🟡警告" : "ℹ️提示";
            sb.AppendLine($"| {tag} | {System.IO.Path.GetFileName(i.prefabPath)} | {i.message.Replace("|", "\\|")} |");
        }
        return sb.ToString();
    }
}
