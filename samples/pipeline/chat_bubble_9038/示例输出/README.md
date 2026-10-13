# 示例 · 聊天气泡_9038

标准:聊天气泡框 · 模式:新增 · 生成于 2026-10-13 23:57:51

## 包里有什么

- 气泡底图(九宫格):`Assets/Arts/UI/UIWidgets/UserInfoView/Textures/CreatorBubbles/HallChatBubble_9038.png`
- 气泡底图(九宫格):`Assets/Loadable/UI/UIWidgets/CreatorBubbles/GameChatBubble_9038.png`
- 图标:`Assets/Arts/UI/UIWidgets/UserInfoView/Textures/CreatorBubbles/ChatBubbleIcon_9038.png`
- 更换面板预览(九宫格):`Assets/Arts/UI/UIWidgets/UserInfoView/Textures/CreatorBubbles/ShowBubble_9038.png`
- 角饰 `LeftUp`:1 层、1 个动效 → 源 `Assets/Arts/UI/UIWidgets/UserInfoView/ChatBubblePrefabs/ChatBubbleEff_9038/LeftUp.prefab` + `LeftUp_Game.prefab`,壳在 `Assets/Loadable/UI/UIWidgets/UserInfoView/ChatBubblePrefabs/ChatBubbleEff_9038/`
- 角饰 `RightUp`:1 层、1 个动效 → 源 `Assets/Arts/UI/UIWidgets/UserInfoView/ChatBubblePrefabs/ChatBubbleEff_9038/RightUp.prefab` + `RightUp_Game.prefab`,壳在 `Assets/Loadable/UI/UIWidgets/UserInfoView/ChatBubblePrefabs/ChatBubbleEff_9038/`
- 角饰 `RightDown`:1 层、1 个动效 → 源 `Assets/Arts/UI/UIWidgets/UserInfoView/ChatBubblePrefabs/ChatBubbleEff_9038/RightDown.prefab` + `RightDown_Game.prefab`,壳在 `Assets/Loadable/UI/UIWidgets/UserInfoView/ChatBubblePrefabs/ChatBubbleEff_9038/`

## 还要手动加的配置(Assets/Loadable/UI/UIWidgets/UserInfoView/ChatBubbleConfig.json)

交付包不会改已有的配置文件(避免覆盖别人同时加的条目),把下面的条目加进数组末尾:

```json
{
  "Id": 9038,
  "Name": "巫灵夜游会聊天气泡(示例)",
  "PgcId": "120109038",
  "IconName": "ChatBubbleIcon_9038",
  "MiniSize": {
    "x": 2,
    "y": 1
  },
  "Boarder": {
    "x": 1,
    "y": 0.7
  },
  "DefColor": {
    "r": 1.0,
    "g": 1.0,
    "b": 1.0,
    "a": 1.0
  },
  "TxtColor": {
    "r": 0.470588,
    "g": 0.341176,
    "b": 0.270588,
    "a": 1.0
  },
  "LayoutOffset": {
    "left": 80,
    "right": 100,
    "top": 20,
    "bottom": 15
  },
  "CornerEffectPrefabPaths": [
    "LeftUp",
    "RightUp",
    "RightDown"
  ]
}
```

## 导入后

- CreatorBubbles 文件夹被 UserInfoBubbleView 图集打包:Unity 打开后图集会重新打包,.spriteatlas 的变化一起提交。
- PgcId 按现有号段 1201000NN 推的,和服务端 / 策划确认一下。
- 3D 头顶气泡的角饰位置由 AvatarChatBox.SetText 按角写死的内缩量摆放,_Game 版位置按同样规则换算,进游戏看一眼。
