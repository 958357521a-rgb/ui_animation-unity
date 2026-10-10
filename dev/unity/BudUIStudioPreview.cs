// BUD UI Studio 验收工具(源文件在工作台 dev/unity/,不长期放在主工程里):
// 由 dev/unity_preview.py 临时拷进 <Unity 工程>/Assets/BudUIStudioTemp/Editor/,用 batchmode 跑完后连目录一起删掉。
// 做两件事:逐页渲染 prefab 截图(弹窗叠在打开它的页面上)+ 调用主工程的「UI导入体检」(有的话),结果写进 -budOut 目录的 report.md。
// 参数:-budPrefab Assets/....prefab  -budOut 输出目录  -budPopupParents "6:0,7:4"(弹窗页序号:底下那页的序号)
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

public static class BudUIStudioPreview
{
    const int W = 2436, H = 1125;   // 与主工程 CanvasScaler 一致

    static string Arg(string name, string fallback)
    {
        var args = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback;
    }

    public static void Run()
    {
        string prefabPath = Arg("-budPrefab", "");
        string outDir = Arg("-budOut", Path.GetFullPath("Temp/BudUIStudioPreview"));
        var popupParent = new Dictionary<int, int>();
        foreach (var pair in Arg("-budPopupParents", "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries))
        {
            var kv = pair.Split(':');
            if (kv.Length == 2 && int.TryParse(kv[0], out var k) && int.TryParse(kv[1], out var v)) popupParent[k] = v;
        }
        Directory.CreateDirectory(outDir);
        var rep = new StringBuilder();
        int code = 0;
        try
        {
            rep.AppendLine("# Unity 验收报告").AppendLine().AppendLine($"- prefab:{prefabPath}").AppendLine($"- Unity {Application.unityVersion}").AppendLine();
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null) throw new Exception("找不到 prefab:" + prefabPath);
            HealthCheck(prefab, rep);
            Render(prefab, outDir, popupParent, rep);
        }
        catch (Exception e)
        {
            rep.AppendLine("EXCEPTION: " + e);
            code = 1;
        }
        File.WriteAllText(Path.Combine(outDir, "report.md"), rep.ToString(), new UTF8Encoding(false));
        Debug.Log("[BudUIStudioPreview] done → " + outDir);
        EditorApplication.Exit(code);
    }

    // 主工程的 UIImportHealthChecker 是 EditorWindow,扫描方法是私有的:反射调用,拿它的 Markdown 报告
    static void HealthCheck(GameObject prefab, StringBuilder rep)
    {
        rep.AppendLine("## UI导入体检").AppendLine();
        var t = AppDomain.CurrentDomain.GetAssemblies().SelectMany(a => { try { return a.GetTypes(); } catch { return new Type[0]; } })
            .FirstOrDefault(x => x.Name == "UIImportHealthChecker");
        if (t == null) { rep.AppendLine("这个工程里没有 UIImportHealthChecker,跳过").AppendLine(); return; }
        var w = ScriptableObject.CreateInstance(t);
        const BindingFlags F = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        t.GetField("_target", F).SetValue(w, prefab);
        t.GetMethod("Scan", F).Invoke(w, null);
        rep.AppendLine((string)t.GetMethod("BuildMarkdownReport", F).Invoke(w, null)).AppendLine();
        UnityEngine.Object.DestroyImmediate(w);
    }

    static void Render(GameObject prefab, string outDir, Dictionary<int, int> popupParent, StringBuilder rep)
    {
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        var rt = new RenderTexture(W, H, 24, RenderTextureFormat.ARGB32);
        var cam = new GameObject("PreviewCam").AddComponent<Camera>();
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = new Color(1f, 0f, 1f, 1f);   // 洋红底:截图里透出洋红说明没铺满
        cam.orthographic = true;
        cam.targetTexture = rt;
        var canvasGo = new GameObject("PreviewCanvas", typeof(RectTransform));
        var canvas = canvasGo.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceCamera;
        canvas.worldCamera = cam;
        canvas.planeDistance = 10;
        var scaler = canvasGo.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(W, H);
        scaler.matchWidthOrHeight = 1f;

        var root = (GameObject)PrefabUtility.InstantiatePrefab(prefab, canvasGo.transform);
        var all = root.GetComponentsInChildren<Transform>(true);
        rep.AppendLine("## 渲染").AppendLine();
        rep.AppendLine($"- 根节点:{root.name},缺失脚本 {all.Sum(x => GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(x.gameObject))} 个,Layer≠5 的节点 {all.Count(x => x.gameObject.layer != 5)} 个");

        GameObject[] pages = null;
        foreach (var mb in root.GetComponents<MonoBehaviour>())
        {
            if (mb == null) continue;
            var sp = new SerializedObject(mb).FindProperty("pages");
            if (sp == null || !sp.isArray) continue;
            pages = new GameObject[sp.arraySize];
            for (int i = 0; i < sp.arraySize; i++) pages[i] = sp.GetArrayElementAtIndex(i).objectReferenceValue as GameObject;
            rep.AppendLine($"- 视图脚本:{mb.GetType().FullName},pages[] = {sp.arraySize}");
        }
        if (pages == null) pages = new[] { root };   // 不是工作台生成的多页视图:整张截一次
        rep.AppendLine();

        var tex = new Texture2D(W, H, TextureFormat.RGB24, false);
        for (int i = 0; i < pages.Length; i++)
        {
            var pg = pages[i];
            if (pg == null) { rep.AppendLine($"### {i} (空引用)"); continue; }
            if (pg != root) foreach (var p in pages) if (p != null) p.SetActive(false);
            var show = new List<GameObject>();
            if (popupParent.TryGetValue(i, out var parent) && parent >= 0 && parent < pages.Length && pages[parent] != null) show.Add(pages[parent]);
            show.Add(pg);
            foreach (var p in show)
            {
                p.SetActive(true);
                var cg = p.GetComponent<CanvasGroup>();
                if (cg != null) cg.alpha = 1f;
            }
            Canvas.ForceUpdateCanvases();
            cam.Render();
            RenderTexture.active = rt;
            tex.ReadPixels(new Rect(0, 0, W, H), 0, 0);
            tex.Apply();
            RenderTexture.active = null;
            string file = $"{i:00}_{Safe(pg.name)}.png";
            File.WriteAllBytes(Path.Combine(outDir, file), tex.EncodeToPNG());

            int magenta = 0;
            var px = tex.GetPixels32();
            for (int k = 0; k < px.Length; k += 7) if (px[k].r > 250 && px[k].g < 5 && px[k].b > 250) magenta++;
            rep.AppendLine($"### {i} {pg.name}" + (show.Count > 1 ? $"(叠在 {show[0].name} 上)" : ""));
            rep.AppendLine($"- 截图:{file},露底(洋红)采样占比 {magenta * 700f / px.Length:0.0}%");
            Diagnose(pg, rep);
            rep.AppendLine();
        }
    }

    static void Diagnose(GameObject pg, StringBuilder rep)
    {
        var imgs = pg.GetComponentsInChildren<Image>(true);
        var noSprite = imgs.Where(x => x.sprite == null && x.color.a > 0.01f).Select(x => x.name).ToList();
        var texts = pg.GetComponentsInChildren<Text>(true);
        var noFont = texts.Count(x => x.font == null);
        var fonts = texts.Where(x => x.font != null).GroupBy(x => x.font.name).Select(g => $"{g.Key}×{g.Count()}");
        rep.AppendLine($"- Image {imgs.Length} 个(无贴图且不透明 {noSprite.Count}{(noSprite.Count > 0 ? ":" + string.Join("、", noSprite.Take(8)) : "")});Text {texts.Length} 个,字体:{string.Join(",", fonts)}{(noFont > 0 ? ",缺字体 " + noFont : "")}");
        var over = new List<string>();
        foreach (var t in texts)
        {
            if (!t.gameObject.activeInHierarchy || string.IsNullOrEmpty(t.text) || t.font == null) continue;
            var r = t.rectTransform.rect;
            float pw = t.preferredWidth, ph = t.preferredHeight;
            if ((t.horizontalOverflow == HorizontalWrapMode.Overflow && pw > r.width + 2) || ph > r.height + 2)
                over.Add($"「{Trim(t.text)}」({t.name}) 框 {r.width:0}×{r.height:0},需要 {pw:0}×{ph:0}");
        }
        if (over.Count > 0)
        {
            rep.AppendLine($"- 文字超框 {over.Count} 处:");
            foreach (var o in over.Take(15)) rep.AppendLine("  - " + o);
        }
    }

    static string Trim(string s) { s = s.Replace("\n", "⏎"); return s.Length > 20 ? s.Substring(0, 20) + "…" : s; }

    static string Safe(string s)
    {
        foreach (var c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
        return s.Replace(' ', '_').Replace('·', '_');
    }
}
