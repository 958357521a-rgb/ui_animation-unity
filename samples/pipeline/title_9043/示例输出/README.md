# 示例 · 称号_9043

标准:称号 · 模式:新增 · 生成于 2026-10-13 23:57:54

## 包里有什么

- 图标(整张称号图):`Assets/Loadable/UI/UIWidgets/Title/Icon/Title_9043.png`
- 称号 prefab:`Assets/Loadable/UI/UIWidgets/Title/Prefab/Title_9043/2D.prefab`(界面)、`3D.prefab`(场景头顶),5 层、3 个动效

## 还要手动加的配置(Assets/Loadable/UI/UIWidgets/Title/TitleConfig.json)

交付包不会改已有的配置文件(避免覆盖别人同时加的条目),把下面的条目加进数组末尾:

```json
{
  "Id": 9043,
  "Name": "山河知音客称号(示例)",
  "PgcId": "190109043",
  "Size": {
    "x": 0.5,
    "y": 0.5,
    "z": 0.5
  },
  "SpriteName": "Title_9043",
  "Desc": "通过「山河有声」扭蛋解锁<color=#FF835D>山河知音客称号</color>",
  "Icon": "Assets/Loadable/UI/UIWidgets/Title/Icon/Title_9043.png",
  "Prefab": "Assets/Loadable/UI/UIWidgets/Title/Prefab/Title_9043/2D.prefab",
  "GamePrefab": "Assets/Loadable/UI/UIWidgets/Title/Prefab/Title_9043/3D.prefab",
  "PreviewPath": "Assets/Loadable/UI/UIWidgets/Title/Prefab/Title_9043/2D.prefab"
}
```

## 导入后

- Title/Icon 文件夹被 UserTitleView 图集打包:Unity 打开后图集会重新打包,.spriteatlas 的变化一起提交。
- PgcId 按 39 号以后的号段 1901000NN 推的,和服务端 / 策划确认一下。
- 主工程的扫光(Mask + 加色材质)这里不生成,需要的话在 Unity 里加。
