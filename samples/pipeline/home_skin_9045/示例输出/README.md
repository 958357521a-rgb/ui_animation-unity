# 示例 · 主页皮肤_9045

标准:主页皮肤 · 模式:新增 · 生成于 2026-10-13 23:57:54

## 包里有什么

- 背景(全屏):`Assets/Arts/UI/Themes/Theme_9045/bg.png`
- 底栏:`Assets/Arts/UI/Themes/Theme_9045/Image_Bottom0.png`
- 底栏上层:`Assets/Arts/UI/Themes/Theme_9045/Image_Bottom1.png`
- 卡片1 主体:`Assets/Arts/UI/Themes/Theme_9045/Frame01_Bottom.png`
- 卡片1 头部:`Assets/Arts/UI/Themes/Theme_9045/Frame01_Top.png`
- 卡片2 主体:`Assets/Arts/UI/Themes/Theme_9045/Frame02_Bottom.png`
- 卡片2 头部:`Assets/Arts/UI/Themes/Theme_9045/Frame02_Top.png`
- 卡片3 主体:`Assets/Arts/UI/Themes/Theme_9045/Frame03_Bottom.png`
- 卡片3 头部:`Assets/Arts/UI/Themes/Theme_9045/Frame03_Top.png`
- 卡片4 主体:`Assets/Arts/UI/Themes/Theme_9045/Frame04_Bottom.png`
- 卡片4 头部:`Assets/Arts/UI/Themes/Theme_9045/Frame04_Top.png`
- 卡片5 主体:`Assets/Arts/UI/Themes/Theme_9045/Frame05_Bottom.png`
- 卡片5 头部:`Assets/Arts/UI/Themes/Theme_9045/Frame05_Top.png`
- 合成效果图(预览用):`Assets/Arts/UI/Themes/Theme_9045/Image_UP.png`
- 缩略图:`Assets/Arts/UI/UIPanel/ProfileTheme/Textures/theme_icon_9045.png`
- 主页皮肤:`Assets/Arts/UI/Themes/Theme_9045/ThemeBg.prefab`(装饰 12 个、动效 6 个)、Bg1~5,壳在 `Assets/Loadable/UI/Themes/Theme_9045/`,预览 `Assets/Loadable/UI/Themes/Theme_9045/ThemeBg9045/ThemeBg9045.prefab`

## 还要手动加的配置(Assets/Loadable/UI/UIPanel/ProfileTheme/ProfileThemeConfig.json)

交付包不会改已有的配置文件(避免覆盖别人同时加的条目)。ProfileThemeConfig.json 的结构是 {"configs": [...]},把下面的条目加进 configs 数组末尾:

```json
{
  "themeId": 9045,
  "pgcId": "150109045",
  "themeName": "桂月栖兔主页皮肤(示例)",
  "previewTitle": "<color=#6E3D9E>通过中秋礼包解锁</color><color=#F461A2>桂月栖兔主页皮肤</color>",
  "title": "桂月栖兔主页皮肤(示例)",
  "colorInfo": {
    "titleBgColor": "#F0836C00",
    "profileCardColor": "#F0836C00",
    "mainBgColor": "#FFF7CB",
    "cardSubColor": "#FFF8DC",
    "placeHolderColor": "#CCB47C",
    "textColor": "#000000",
    "textBorderColor": "#FFFFFF",
    "gridColor": "#FFEAB8",
    "priceColor": "#FFCFDD",
    "titleInfoColor": "#FFCFDD",
    "info_bg1": "Assets/Loadable/UI/Themes/Theme_9045/Bg1.prefab",
    "info_bg2": "Assets/Loadable/UI/Themes/Theme_9045/Bg2.prefab",
    "info_bg3": "Assets/Loadable/UI/Themes/Theme_9045/Bg3.prefab",
    "info_bg4": "Assets/Loadable/UI/Themes/Theme_9045/Bg4.prefab",
    "info_bg5": "Assets/Loadable/UI/Themes/Theme_9045/Bg5.prefab"
  },
  "localPath": "Assets/Loadable/UI/Themes/Theme_9045/ThemeBg9045/ThemeBg9045.prefab"
}
```

## 导入后

- 缩略图进 ProfileTheme 图集(Textures 文件夹):Unity 打开后图集会重新打包,.spriteatlas 的变化一起提交。
- 背景 / 合成效果图 2436 宽,超过 2048 上限,构建时会被缩小(主工程现有皮肤也是这样)。
- 可选:在 ProfileThemeConfig.cs 的枚举 ProfileTheme 里加一项(只做注释用)。pgcId 按 1501000NN 推的,和服务端 / 策划确认一下。
