# UI 预制体替换规范

> 背景:后续会有大量旧 UI 界面预制体由美术同学直接重做/替换。本文规定**怎样替换才不会破坏现有功能和逻辑**,并列出当前管线缺失的环节。
> 2026-09-28 起草,以"充值福利"新版视图(RechargeRewards)接入为试点案例;数据来自对全工程的只读审计(全量扫描,非抽样)。

## 1. 项目 UI 资源的既有结构(必须先理解)

### 1.1 双层预制体:Arts(源)→ Loadable(打包壳)

- **`Assets/Arts/UI/UIPanel/<面板名>/`**:源预制体所在地(全工程 1,621 个),**美术改这里**。
- **`Assets/Loadable/UI/<模块>/<面板名>/`**:热更 bundle 的打包入口(1,528 个 prefab),其中 **85%(1,296 个)是 Prefab Variant 薄壳**(约 120 行 YAML),通过 GUID 引用 Arts 源;改 Arts 源会自动透传到壳。
- 壳由右键菜单 **`Assets → Send To Loadable`**([ExportToLoadable.cs](Assets/Scripts/Editor/OtherTools/ExportToLoadable.cs))生成,路径规则 `Assets/Arts/... → Assets/Loadable/...`(注意:该工具直接覆盖、无校验,SpriteAtlas 是移动而非复制)。
- **三个必须检查的例外:**
  1. **15%(232 个)Loadable prefab 是"直接放置"的普通 prefab**,没有 Arts 源。改之前先确认类型:文件内有无 `m_SourcePrefab` 即可判断。
  2. **壳上可能带 override**(个别如 CabinBoxCmdPanel 有 67 处修改)。只改 Arts 源时,壳上 override 的那几个属性**不会**跟着变 —— 替换后两边都要过目。
  3. Loadable 与 Arts 的**目录结构并不总是镜像**(如 `Loadable/UI/Gashapon/X` 的源在 `Arts/UI/UIPanel/X`),移动过的壳要按 GUID 找源。

### 1.2 代码与预制体的三种耦合(= 三种破坏面,附实测规模)

| 耦合方式 | 实测规模(Assets/Scripts/UI,共 2,938 个 .cs) | 美术改什么会坏 |
|---|---|---|
| `[SerializeField]`/public 字段拖引用 | 1,127 个文件 | **删除/重建挂脚本的节点** → 引用变 None,运行时空指针 |
| **字符串查找节点** `transform.Find("xxx")` 等 | **187 个文件、698 处**(如 CommonRewardPanel.cs 一个文件 15 处;GameHallPanel.cs:167 甚至写死全路径 `"UIRoot/Canvas/CGVedio"`) | **重命名/挪动任何被查找的节点(含祖先)** → 运行时 NullReference,编译期完全查不出来 |
| 字符串反射 `UIAgentManager.CallPanelMethod(id, "方法名")` | 仅 7 处调用、5 个文件(UIManager.cs:118 反射接收,失败只打 LogError) | **重命名面板脚本的方法** → 功能静默失效(如舞蹈邀请通知) |

> 结论:字段引用是主流但**字符串查找面很大**(约每 15 个 UI 文件就有 1 个写死节点名)。美术替换前,程序必须先列出该面板代码里所有 `Find("...")` 的节点名清单交给美术,这些节点**名字和层级路径都不能动**。

### 1.3 其他硬约定(实测口径)

- **热更程序集**:清单在 `ProjectSettings/HybridCLRSettings.asset` 的 `hotUpdateAssemblyDefinitions`(15 个,含 GameUI/Game/GameData 等);**Assembly-CSharp 不在热更清单里** —— UI 代码必须放 `Assets/Scripts/UI/`(GameUI.asmdef)下,散落到无 asmdef 目录 = 真机热更失效。
- **图集**:全工程 161 个 spriteatlas,**全部 v1、bindAsDefault=1**;145 个用**文件夹 packable**,且指向 **Arts 侧的贴图源目录**;图集文件本身放在 Loadable 面板目录、与面板同名。导入器会强制关闭 enableRotation/enableTightPacking(SpriteAtlasChecker.cs 自动改)。
- **字体**:全 UI 只用 `Assets/Arts/Font/` 6 个字体(引用量:SourceHanSansCN-Heavy 831 / Medium 782 / Regular 384 / Montserrat-Black 255 / Bold 98 / Medium 19)。外部字体禁止入库;批量换字体用现成工具 [FontFinderReplaceTool.cs](Assets/Scripts/Editor/EditorTools/FontFinderReplaceTool.cs)。
- **面板注册管线**(新面板/改路径必读):面板登记在数据表 `GameConfig/UIPanel.xlsx` → `Assets/Arts/Config/Asset/UIPanel.asset`(`_ResPath` 写 Loadable 全路径);[UIEnumGenerator.cs](Assets/Scripts/Editor/UITools/UIEnumGenerator.cs) 检测到表变化会**自动重新生成 `PanelId.cs`** —— 千万不要手改 PanelId.cs。⚠️ 该配置表目录实际是指向 **Bud_Box_Common 子模块**的目录联接(见下)。
- **打包(xasset)**:配置在 `Assets/xasset/Config/Builds + Groups`。UIPanel 组(PackByTopSubFolder)的 entries 已含 `Loadable/UI/UIPanel、UIWidgets、ActivityCenterPanel、RechargePanel` 等 —— **在这些目录下新建面板子文件夹会自动进包、自动独立成 bundle,无需注册**;但在 `Loadable/UI` 下新建**平级目录**必须手动加进某个 Group(现有 4 个平级目录 Avatar/BaseWidgets/DemandResource/UIPanelTemp 未在任何 Group 中,属存量风险)。
- **Bud_Box_Common**:git 子模块,通过 **Assets 内 14 个 NTFS 目录联接**挂载(如 `Assets/Arts/Config/Asset`、`Assets/Arts/BoxCommon`、工程根 `GameConfig`);联接清单在 `Tools/BudBoxCommon/link-map.json`,新克隆/新分支要跑 `Tools/BudBoxCommon/Sync-BudBoxCommon.ps1`(或"一键设置.bat")恢复,否则大量引用丢失。
- **资源路径硬编码**:除配置表外,代码里还有约 20 处直接 `Loader.Load("Assets/Loadable/UI/...")` 字符串 —— **移动/重命名 prefab 前先全局搜路径**。

## 2. 美术直接替换预制体:安全操作规程

### 2.1 允许的做法(不会破坏功能)

1. 在**本工程内**修改 Arts 源预制体的:贴图、颜色、字号、布局、动效参数、新增**纯装饰**节点。
2. 替换 Image 的 sprite(新图放进该面板图集 packable 指向的文件夹)。

### 2.2 危险动作(必须走程序确认)

1. **重命名/删除/挪动任何节点** —— 除了字段引用,还可能被 698 处字符串 Find 命中(§1.2)。程序先给出该面板的"节点名保护清单"。
2. **删除/更换节点上的脚本组件**。
3. **在外部工程制作预制体再拷回来** —— 脚本 GUID 对不上必然 Missing Script。真实案例:
   - 2026-07:`underworld_effect.prefab` 从录屏工程拷入,`ETFXRotation` 脚本没跟来,Unity 拒绝保存该 prefab;
   - 存量:12 个 Emote 特效变体的**父 prefab GUID 不存在**(deskdance/pipa/miaojiang 系列,Editor.log 15 条 Missing Prefab Variant parent)—— 同类事故。
   - 确需外部制作,走 §3 交付管线。
4. **整体重建面板层级** —— 等于重绑所有字段,必须程序验收。
5. **删除脚本时不清引用**(程序侧危险动作):存量 5 个 UI prefab、14 个悬空组件即由两次"删代码不清 prefab"造成(2026-05 删 SoftMask 波及 3 个 OCTheatre 编辑器 prefab;2026-03 删 Wwise AkGameObj 波及 2 个 CataPanel prefab)。删公共组件脚本前先全局 grep 其 GUID。

### 2.3 替换后的自检清单(美术提交前)

- [ ] Console 无 `Missing Script` / `referenced script is missing` 报错
- [ ] 面板脚本 Inspector 所有字段**无 None/Missing**
- [ ] **根节点 Scale=1、Active=√、锚点正确**(真实案例:充值福利新视图源 prefab 根节点 scale 被存成 0,逻辑全部正常但整个界面不可见,排查半天)
- [ ] **所有节点 Layer=UI(5)**(真实案例:外部工程 Overlay 模式下 Default 层能显示,拷入主工程后 UI 相机按层剔除,整套界面一个像素不画、点击无响应且零报错;外部交付的 prefab 必查,批量改法:选根节点改 Layer 时选 "Yes, change children")
- [ ] 程序提供的"节点名保护清单"里的节点未改名、未挪层级
- [ ] 新贴图已进本面板图集(Pack Preview 可见);字体是项目 6 字体之一
- [ ] 若同名 Loadable 壳带 override:壳上 override 属性与新源核对过
- [ ] Play 模式打开面板走一遍主流程
- [ ] 可用现成工具批查:`预设引用丢失`(CheckPrefabReferMissMenu)、AtlasChecker、PrefabUIChecker(见 §4)

## 3. 外部封装工程交付 → 主工程接入:对齐总清单

> 以"充值福利 RechargeRewards"试点为准(2026-09-28 已跑通:界面可打开、12 档数据与服务端对齐、领取链路接通)。
> 下表每一条都对应试点中**真实踩过的坑**,按接入顺序排列。后续批量替换旧 UI,照此逐项过。

| # | 对齐项 | 不对齐的症状(试点实录) | 处理方式 |
|---|---|---|---|
| 1 | **交付物完整**:整个 `Assets/<模块>/` 目录**连 .meta**(保 GUID);去掉 Demo 场景/DemoHost/Editor 工具 | 缺 meta → Missing Script(7 月 underworld_effect 同类事故) | 压缩包必须含 meta;程序核对 prefab 引用的脚本 GUID 全部随包 |
| 2 | **程序集**:脚本进 `Assets/Scripts/UI/`(GameUI);自带命名空间(如 `Bud.RechargeRewards`) | 落到 Assembly-CSharp → 真机**热更失效**(热更清单无它) | 拷入时挪目录;先查主工程类名冲突 |
| 3 | **Layer 全树 = UI(5)** | 本次最大坑:190 个节点全是 Default(0),UI 相机按层剔除 → **零报错、零像素、点击无响应**(外部工程 Overlay 模式发现不了) | prefab 批量改 + 宿主实例化后 `SetLayerRecursively` 兜底(已内置于接入模板) |
| 4 | **根节点 RectTransform**:scale=1、锚点、Active | 根节点 scale 被存成 (0,0,0) → 同样整界面不可见 | 源头修正 + 实例化后强制归一(已内置) |
| 5 | **字体白名单**:只用 `Assets/Arts/Font/` 6 字体 | 34MB Noto 字体入包不可接受 | sed 批量换 GUID(本次 Bold→SourceHanSansCN-Heavy、Regular→Medium);或用现成 FontFinderReplaceTool |
| 6 | **图集**:散图 → 面板同名 `.spriteatlas`(packable=Arts 贴图文件夹) | 100+ 散图:drawcall/内存/包体全吃亏 | 图集放 Loadable 面板目录,平台压缩参数抄现有面板 |
| 7 | **打包与加载**:Loadable 变体壳 + xasset 已注册 entry | 不在已注册 entry 下 → 编辑器能跑、**真机 bundle 加载失败** | `Send To Loadable` 生成壳;放进已注册目录(如 `Loadable/UI/RechargePanel/`)自动进包 |
| 8 | **数据必须服务端驱动**:档位/奖励/状态来自接口,Catalog 仅作视觉配置 | Catalog 写死 8 档 vs 服务端实际 12 档 | Adapter 按金额对齐 + 配不上逐档报错点名;上线前 Catalog 与运营配置对版 |
| 9 | **.asset 中文序列化**:手改配置中文必须走 Inspector,或写成 `"引号+\uXXXX"` 转义 | 明文中文被转成不带引号的字面量 → 界面直接显示 `薰...` 乱码 | 已提供转义脚本;规范上配置改动一律 Inspector 改 |
| 10 | **面板框架整合**:BasePanel 外壳 + `UseNewView` 回退开关 + 加载失败自动回落旧版 | 面板打开异常后残留在 `window.panels` → 本次 Play 会话内重开全被 `Can not add BasePanel` 拒绝 | 外壳模式接入(不动 PanelId/配置表);调试时改完**必须退 Play 重进** |
| 11 | **交互出口收敛**:包内重复功能页(如自带钻石商城)禁用;返回/关闭接 `CloseSelf`;音效、埋点补齐 | 不收敛会出现双商城并存 | 所有出口只经 Adapter 一个类 |

**"打开了但看不见"排查口诀**(按命中率排序):**Layer → 根节点 scale/active → CanvasGroup alpha → Canvas 排序 → 面板框架状态(`Can not add`)** —— 前两个就是本次试点连踩的两个坑,全部零报错。

## 4. 现状盘点:工具已有不少,缺的是"强制"和几处断点

编辑器工具其实相当全(Assets/Editor + Assets/Scripts/Editor 共 308 个脚本):`预设引用丢失`扫描(CheckPrefabReferMissMenu)、AtlasChecker/AtlasCreater、PrefabUIChecker(RaycastTarget 审计)、UnreferencedScriptChecker、FontFinderReplaceTool、PrefabSpriteReplacer、CButton/CToggle 一键转换等。**真正缺失的是:**

| # | 缺口 | 现状证据 | 建议 |
|---|---|---|---|
| 1 | 检查工具没进流程,全靠自觉 | 存量 5 个 UI prefab 缺脚本(0.20%)、12 个变体断父,长期无人发现 | Missing Script/断父扫描进提交钩子或 CI,增量拒绝 |
| 2 | **字符串 Find 无任何检查工具** | 187 文件 698 处,断了只在运行时爆 | 新增编辑器工具:对指定 prefab 提取代码中 Find 的节点名并校验存在性;长期目标:新面板禁用字符串 Find |
| 3 | Send To Loadable 无校验、无同步检查 | 直接覆盖,壳 override 无 diff | 导出前 diff 提示 override;或加"重导出校验"模式 |
| 4 | 共享 UI 组件库缺失(跨工程 GUID) | 外部工程各自造轮子 → 每次接入都要换字体/图集 | 仿 Bud_Box_Common 做 Bud_UI_Common:CButton/CText/字体/通用底板连 meta 分发 |
| 5 | HotfixDll.json 手工维护 | HotfixDllEditor.RefreshOrCreatedHotfixDll() 首行 `return;` 已禁用 | 新增热更程序集要同时改 HybridCLRSettings + json,恢复或重写该工具 |
| 6 | 4 个 Loadable/UI 平级目录未注册打包 Group | Avatar/BaseWidgets/DemandResource/UIPanelTemp | 确认是否该进包;规范:新平级目录必须登记 xasset Group |
| 7 | 路径硬编码无守护 | 约 20 处 `Loader.Load("Assets/Loadable/UI/...")` | 移动/重命名 prefab 的 checklist 加"全局搜路径";长期收敛到配置表 |
| 8 | Bud_Box_Common 联接恢复无文档 | 新分支/新机器不跑 Sync 脚本即大面积丢引用 | 入职/换机文档写明跑 `Tools/BudBoxCommon/Sync-BudBoxCommon.ps1` |
| 9 | **外部封装用的模板工程缺失** | 试点里 Layer/字体/scale 三类坑全因外部工程环境与主工程不一致 | 做一个"BUD UI 底座"模板工程:UI 层、ScreenSpaceCamera、项目字体、CanvasScaler 参数、CButton/CText 组件库(连 meta 稳定 GUID)——从源头消灭 §3 表 3/4/5 类坑 |
| 10 | ~~交付导入体检工具缺失~~ **已建成(2026-09-28)** | 工具:[UIImportHealthChecker.cs](Assets/Editor/AssetsChecker/UIImportChecker/UIImportHealthChecker.cs)。Project 窗口选中 prefab/文件夹 → 右键 `Assets/BUD工具/UI导入体检`;检查 Missing Script、Layer≠UI、缩放为0、字体白名单、散图未入图集、TMP、自定义材质;支持"复制Markdown报告"贴 MR | 流程要求:外部交付包接入前必跑,报错=打回 |
| 11 | **自选类奖励数据写死在 Catalog** | 1888/8888 档选项名称、图标当前为占位 | choices 的名称/图标按 `optionalPgcList` 的 pgcId 走 PgcUtils 运行时拉取,Catalog 不再维护这份数据 |

## 5. 存量待修复清单(审计发现,建议排期)

1. OCTheatre 编辑器 3 个 prefab 的 SoftMask/SoftMaskable 悬空引用(删于 fea48db2f3,共 ~12 处):TheatreEditorEmoteAvatarItem / TheatreEditorOCItem / TheatreOptionEditBar。
2. CataPanel 2 个 prefab 的 Wwise AkGameObj 悬空引用(删于 6eb44870d3):HospitalCatalogPanel / UgcHospitalCatalogPanel。
3. 12 个 Emote 特效变体断父(deskdance/pipa/nishang/lusheng/miaojiang 1-4/dunhuang_4 等)—— 需从美术源工程补父 prefab 或解除变体。
4. 场景内 GlobalMainCamera 等 UI 范围外的 missing script(Editor.log 28 条)。

## 6. 本次试点(充值福利 RechargeRewards)落地记录

- 旧面板:`CumulativeRechargePanel`(PanelId=207);新视图脚本 8 个 + 适配层:`Assets/Scripts/UI/UIPanels/RechargePanel/RechargeRewards/`(GameUI 程序集);美术资源:`Assets/Arts/UI/UIPanel/RechargePanel/RechargeRewardsView/`;图集:`Assets/Loadable/UI/RechargePanel/RechargeRewardsView/`(RechargePanel 为已注册 entry,自动进包)。
- 已排除:Demo 场景、RechargeDemoHost、Editor 工具、Noto 字体(34MB);64 处字体引用已替换为项目字体。
- 入口切换:保留 PanelId=207 与配置表不动,`CumulativeRechargePanel.OnShow` 内加 `UseNewView` 开关(static bool,置 false 即整体回退旧版):开关开启时实例化 Loadable 壳、挂适配层、隐藏旧视觉;加载失败自动回落旧版。旧字段/旧逻辑一行未删。
- **试点结论(2026-09-28):模式已跑通** —— 界面正常打开、12 档与服务端对齐、领取链路接通。过程中踩坑与修复全部沉淀在 §3 对齐总清单。
- **本批全部改动均未提交**(验证期资产,git 工作区状态);回退方式:`UseNewView = false` 或直接丢弃工作区改动。
- 遗留待办:1888/8888 档选项与 348/5688 档图标为占位(§4-11 方案);真机验证 `RewardMultiply.shader`/图集内存;领取与"前往充值"全流程回归;正式化时走 MR 提交。
