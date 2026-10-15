# 交接说明(2026-09-29)

BUD UI Studio 从 BUD_CHINA 主工程会话中拆出,作为独立项目继续开发。本文件是新会话的起点。
**文件夹已打包交给同事**:她在新电脑上第一次打开时,先按 `ONBOARDING.md` 跑起工作台、载入工程;本文件里的"用户"指原作者。

## 现在做到哪了

- **工作台软件**:`BUD_UI_Studio.html`(单文件,零依赖)。支持从 Figma 拉取界面(REST 链接 + Token,或 Figma 插件导出包)、逐层还原(文字可编辑,其余切图,裁剪超宽分组生成滚动区)、一键配动效/交互、多页面(主页 + 详情页 + 弹窗)、试玩模式(点击反馈、跳转、滚动、事件日志)、导出 Unity 交付包(prefab + meta + 贴图 + View/Motion/ClickFeedback 脚本)。
- **当前工程**:`projects/RechargeRewardsOverview.budui.json`(27 MB,含全部贴图)= 充值福利模块,10 页:
  - 主页 05 奖励总览;
  - 详情页 10 发型 / 11 鞋子 / 06 圣天使之翼(未达标)/ 07 自选特效 / 14 自选动作;
  - 弹窗 04 福利规则 / 08 确认兑换 / 09 兑换成功 / 13 领取成功;
  - 11 条自动跳转,布局已锁定,主页布局已按 Figma 原坐标复原。
  - 只有主页存了 Figma 原稿坐标(`figma` 字段)和 `figmaId`;其余 9 页是旧版本导入的,没有:在没有画板目录缓存的电脑上,要先「拉取画板」读一次目录,「↺ 还原 Figma 布局」才能用。
  - 打开方式:工作台在 `http://localhost:8791` 打开时会从浏览器本地(IndexedDB)自动恢复;换了浏览器、端口或主机名(`localhost` ≠ `127.0.0.1`)就点「载入工程」选这个文件。
- **Figma 插件**:`figma-plugin/`(不走 REST、不耗额度),已在本机模拟环境测过(`node dev/plugin_selftest.js`),**还没在真实 Figma 里装过**。用户说"先别管插件",暂缓。
- **2026-09-29 改为整张总览画板一次导入**:用户明确要"一键全部导入、统一配交互和动效",不要"选一个界面开始制作"。现在拉取总览画板 / 导入多界面插件包 → 勾选对话框(默认全选、说明页不勾、自动猜主页)→ 整体导入为一个模块并连好跳转;已有模块默认「补充」。已在隔离的测试页用模拟画板测过(REST 无缓存/有缓存、插件包、补充/重建、＋加页面、单界面三选一、导出结构校验),**还没用用户真实的「Unity中间版」画板跑过**。
- **同日为交接给同事做了整理**:新增 `ONBOARDING.md`(新电脑上手 + 操作手册)、`dev/offline_check.js`(离线校验真实工程的导出结构)、`.claude/launch.json` 的测试配置 `budui-studio-test`(8792);本地服务改成多线程、根地址跳到工作台,并新增交付包另存到 `exports/`(内置浏览器面板的下载不好找);单界面「替换」后只给这一页补连跳转;导出包 README 的接入说明改成按规范 §3 分目录放置。
- **同日「✦ 一键配动效」改为全部页面一起配**(用户要求):先全部复位再逐页识别,最后重连跳转,Ctrl+Z 一步撤销。用 `projects/RechargeRewardsOverview.budui.json` 离线跑过:270 个节点零变化、11 条跳转一致,说明该工程目前没有会被覆盖的手动交互设置。

- **2026-10-09 工作台改为多任务**(原作者要求:充值福利只是其中一个改版任务,后面会有很多板块):左上角任务名 → 任务首页(卡片 + 缩略图,进行中 / 已完成 / 全部 / 回收站,搜索),「＋ 新建任务」= 空白画布 + 任务名 / 模块名 / Figma 链接 / 备注;每个任务各存一份工程(素材、动效、交互、Figma 链接、覆盖目标),卡片上显示最近导出和最近覆盖到 Unity 的 prefab。旧的单工程第一次打开时自动迁移成第一个任务(名字取主页标题,如「充值福利」),原数据键 `project` 保留没删。已在 8792 测试页测过:迁移、新建、切换来回数据不串、复制、标记完成、回收站恢复 / 彻底删除、载入工程成新任务、两个窗口开同一任务时后开的只读 + 接手;`node dev/offline_check.js` 全部通过(生成器没动)。**原作者的 file:// 页面刷新一次就会迁移**,迁移后把任务名改成想要的(如「充值福利改版」)。钻石充值页应作为一个新任务来做。

- **2026-10-09 局域网共享**(原作者要求:给别人一个局域网链接直接用):`启动局域网共享.bat` / launch 配置 `budui-studio-lan` = `studio_server.py 8790 --lan`,原作者电脑当时的链接是 http://10.10.0.241:8790/(以太网,网络类型为"公用";python.exe 已有入站允许规则,含公用网络)。非本机只读白名单文件,POST 一律 403,页面在局域网地址上拦下「覆盖到 Unity」;任务首页新增「从共享文件夹载入」(`GET /api/projects`)。本机用局域网 IP 访问模拟测过:白名单 / 403 / 路径穿越都对,局域网页面载入 Sign 11 页正常;**还没从另一台电脑实际打开过**。

- **2026-10-09 桌面应用**(原作者要求把工作台作为应用放到桌面):桌面已建好「BUD UI Studio」快捷方式(Edge 应用窗口 + 后台 8791 服务),实测双击弹出独立窗口。发现原作者默认浏览器是**夸克**,工作台数据一直在夸克里;夸克不支持 `--app`,原作者选改用 Edge。**数据已搬好(19:00)**:新增免点击搬家 `BUD_UI_Studio.html#handoff-export`(全部任务经 8791 服务写到 `projects/全部任务_搬家.budui.json`)/ `#handoff-import`(从服务读回导入),Claude 用夸克打开前者、用 Edge `--app` 打开后者完成;夸克里只有 1 个任务「充值福利」(模块 Sign,14 页,193 张贴图,注意比 `projects/Sign.budui.json` 的 11 页多,原作者浏览器里还带着 01/02/03 页),Edge 里已导入(IndexedDB 41 MB)。搬家文件挪到了 `backups/handoff/夸克全部任务_20261009-1900.budui.json` 留底;夸克里的数据没删。**以后原作者的工作数据在 Edge 应用窗口里**。

- **2026-10-09 沿用旧资源**(原作者要求:有些资源不替换、继续用旧的,比如 207 的奖励图标,以后的任务都要能单独标出来):属性面板「沿用旧资源」+「选旧资源…」(搜主工程 UI 切图、带缩略图)+ 画布橙色标注 + 状态栏清单;覆盖时 prefab 直接引用旧图、不写新切图。已测:离线检查新增一项通过;8790 测试页里对真实主工程只读体检——Sign 主页 7 个 Reward/Icon 标上后,指定了 Cumulative_Icon_1 的那个沿用成功,另外 6 个提示「这个位置已经是上次覆盖进去的新切图」(207 已被覆盖过,自动找不回原图,要逐个指定)。**原作者说过 207 这次不用处理**。顺带修了:pythonw 后台起服务(桌面应用)时没有控制台,请求日志一写就掐断连接 → 服务启动时把 stdout/stderr 指到 devnull;8791 已用新代码在后台重启(pythonw,不再挂在某个 Claude 会话的预览下)。

## 已验证 / 未验证

| 项 | 状态 |
|---|---|
| 导出结构(YAML 引用闭合、全 UI 层、10 页 CanvasGroup、View 导航接线、C# 括号平衡) | ✅ 已自动校验(`node dev/offline_check.js` 可复现) |
| 试玩:卡片→详情→返回、领取→领取成功弹窗→确定、数字遮罩、滚动区拖动 | ✅ 已测 |
| **导出的 prefab / C# 在 Unity 里真正导入、编译、打开** | ❌ 还没做(管线最后一环,最重要) |
| Figma 插件在真实 Figma 里安装运行 | ❌ 未做 |

## 下一步(按优先级)

1. 在工作台点「导出交付包」得到 `模块名.unitypackage`(10-09 起由 zip 改为 Unity 包,落点已按规范 §3 写在包里:脚本 `Assets/Scripts/UI/UIPanels/<模块名>/`,切图/prefab/README `Assets/Arts/UI/UIPanel/<模块名>/`;**2026-10-09 已用 Unity 2022.3.32f1 命令行模式导入原作者电脑上的主工程并编译通过**:0 个编译错误,新脚本零警告,三个类型已编进 GameUI.dll,prefab 导入无报错,除这两个新目录外主工程无其他文件变化;导入的文件目前以未跟踪状态留在主工程里)→ 下一步在编辑器里打开 prefab 看效果 → 跑 `BUD工具/UI导入体检`(工具源码见 `unity-reference/UIImportHealthChecker.cs`)→ 打开 prefab 看效果。编译或导入有错,回来修生成模板(`genViewCs` / `genMotionCs` / `genClickFeedbackCs` / `genPrefab`)。
   - **2026-10-09 画面验收**(没开编辑器:临时脚本 `Assets/Editor/BudUIStudioPreviewTemp.cs` 用 batchmode 逐页渲染截图到 `exports/unity_preview/` + 反射调用 UI导入体检):体检 0 错误 / 108 警告(全是"未进入 SpriteAtlas",按规范要等建图集);10 页全部铺满、字体全在白名单、无文字超框、无缺失脚本。**发现并已修一个导出 bug**:贴图文件名去重区分大小写,主页 `Reward_Icon_2..6` 与详情页 `reward_icon_2..6` 在 Windows/Unity 里是同一个文件、互相覆盖 → 6 个图标变白块。`buildPackage` 改为内容相同的切图只出一个文件 + 文件名不区分大小写去重(119 个资产 20.5 MB → 52 个 5.7 MB),`assetName` 同步改;`offline_check.js` 的落点重复检查改成不区分大小写(旧生成器会被它判失败)。原作者同意后已删掉旧导入、导入新包(编译通过)、重新渲染:10 页全部 0 个缺贴图 Image,白块消失,体检 0 错误 / 114 警告(仍全是图集);临时脚本已删,主工程 git 状态与导入前基线一致(两个模块目录仍为未跟踪)。之后(14:50 起)原作者打开了 Unity 编辑器,14:59 两个模块目录被删掉了(不是 Claude 删的,应是原作者在编辑器里删的)——主工程里目前没有这个模块。
   - **2026-10-09 新增「覆盖到 Unity」**(原作者要求:后续大量旧资源迭代替换,要一键覆盖进主工程里的目标 prefab):工具栏「导出交付包」旁边。经本地服务直接读写主工程:目标 prefab 原地覆盖,已有 .meta 一律不动(GUID 不变 → Loadable 壳、UIPanel 配置表、外壳引用不断),旧 prefab 里同名同层级节点沿用原 fileID(壳的 override 不断);选中 Loadable 壳会自动换成它的源 prefab;切图目录里新版不用的旧切图删除;被覆盖/删除的文件备份到 `backups/<时间>/`。覆盖前体检列出:节点 ID 沿用数、会消失的业务脚本(根节点挂面板脚本 = 标红,必须勾选确认)、壳上会失效的 override、面板配置条目、代码里 Find 会落空的节点路径。同时导出改为稳定 ID(GUID 按落点路径、fileID 按节点层级路径派生),再导出逐字节不变。**已测**:沙盒工程(scratchpad 里拷的主工程脚本 + 旧随机 ID 的模块 + 造的壳 + 真实 CumulativeRechargePanel 源/壳/配置表)里迭代覆盖 0 个 meta 变化、1178 个对象 ID 全部沿用;删节点后只少该节点 4 个对象、旧切图连 meta 删除并备份;覆盖旧面板时壳的 21 处 override(全指向根节点)保持有效;外站请求 403、越界路径拒绝。对真实主工程只做过只读体检(CumulativeRechargePanel:冷启动 185 秒→优化后热缓存 5 秒)。**还没往真实主工程写过、没在打开的 Unity 编辑器里看过覆盖后的自动导入。** 同日按原作者要求把截图验收收编为工作台工具 `dev/unity_preview.py`(脚本源在 `dev/unity/`,运行时临时带进 Unity、跑完删除);在 scratchpad 新建的空 Unity 2022.3.32f1 工程里验证过:「覆盖到 Unity」新建目标写入的 52 个文件真实 Unity 导入编译通过,10 页渲染正常,临时目录清理干净(编译失败那次也清理干净);对开着编辑器的主工程会直接拒绝。 同日又按原作者要求让直接双击打开的工作台(file://)也能用「覆盖到 Unity」:原作者平时就在 file:///D:/lijixian/BUD_UI_Studio/BUD_UI_Studio.html 工作(数据在那个地址的浏览器存储里,localhost 看不到);页面连本机 8791 服务、靠 `dev/local_token_8791.js` 里的口令通过校验。无头 Chrome / Edge 以 file:// 打开真实工作台跑通体检 + 写入。又因为接手的人不知道旧资源路径(之前是贴截图给 Claude 去找),对话框第一次打开会自动「按界面文字找」最像的旧 prefab,并标出面板号;对真实主工程只读测试:充值福利模块排第一的就是 `CumulativeRechargePanel.prefab`(面板 207),点它自动体检。
   - **2026-10-09 原作者用「覆盖到 Unity」把模块 `Sign`(工作台里的模块名)覆盖进了 207 `CumulativeRechargePanel.prefab`**,进游戏后返回和「前往充值」都没反应:根节点没有 BasePanel,框架 CreatePanel 失败,prefab 只是残留在画布上。已加面板外壳(`<模块>Panel.cs`,对主工程 GameUI.dll 编译通过)+ 按钮「点击后 → 关闭整个面板」;**待原作者刷新工作台、把「前往充值」设成关闭整个面板、再覆盖一次后进游戏验证**。之后还要程序写 `SignPanel.Logic.cs`:拉 IAPDataManager.GetProductInfo 的累充数据灌 ApplyServerState、领取按钮接接口(可参考 `unity-reference/RechargeRewardsServerAdapter.cs` 思路);目前界面数字是设计稿占位。
   - **同日已写好 `Assets/Scripts/UI/UIPanels/Sign/SignPanel.Logic.cs`(手写业务逻辑,工作台不碰)**:原作者要求「只换素材和补动效,不影响服务端数据」——数据只读 `IAPDataManager.GetProductInfo().rechargeBenefits`,领取逐行照搬旧 `CumulativeRechargeItem.ClaimSingleItem`(POST ClaimRechargeBenifits → CommonRewardPanel → 广播 RefreshCumData),自选档交给旧 208/209 面板,前往充值 = CloseSelf,没有新增任何请求。卡片按金额对上服务端档位;设计稿只有 8 档(6/30/68/98/188/648/1288/3688),服务端多出来的档复制卡片补上(图标走旧图集 `Cumulative_Icon_<序号>`),设计稿有而服务端没有的档隐藏 + 报错;状态条黄/紫底图按服务端状态切换;进度条按累计金额落在卡片之间的位置(跟滚动走);详情页的领取按钮换成走旧流程(不再不等服务端就弹「领取成功」)。同时把新生成器会输出的 `ResetToHome/GetButton/GetText` 补进了主工程的 `SignView.cs`(原文件备份在 backups/20261009-163308/),并放了 `SignPanel.cs`;5 个脚本用 Unity 自带 Roslyn 对主工程程序集编译通过(0 错误)。**还没进游戏跑过**:要原作者刷新工作台、再「覆盖到 Unity」一次(根节点挂上 SignPanel),然后进游戏验证数据、领取、自选、前往充值。已知限制:详情页里的描述文字和「累计充值 X 元解锁」仍是设计稿静态内容;五选一的选择用的是旧 208 面板。
   - **16:37 原作者删掉 Sign 目录重新覆盖,`SignPanel.Logic.cs` 跟着丢了**(工作台不生成它),进游戏仍是占位数据、前往充值无反应(日志全是「还没接业务逻辑」)。已恢复,并在 `unity-reference/Sign/` 留了副本;覆盖体检现在会在面板缺 Logic 文件时提醒。前往充值改为:充值界面(102)开着就关掉自己回去,否则关掉自己并打开充值界面钻石页。切页过渡改为新页面盖在旧页面上滑入、旧页面保持不透明(原来两页同时半透明会露出面板后面的界面),生成器与工作台试玩同步改,主工程 SignView.cs 的 Transit 已直接换成新版本(备份在 backups/)。5 个脚本对主工程程序集编译通过;**待原作者切回 Unity 编译后进游戏验证**。
   - 原作者进游戏后:**服务端数据已通**(累计 13244 元、各档已领取、已解锁全部档位都对)。剩下卡片排版错(卡片挤在中间、补出来的卡叠在一起、打开时左右闪):Layout 读了父节点改尺寸后还没更新的 localPosition。已改为只用锚点坐标算位置 + 打开时 StopMovement 并把滚动定在最左边 + 数据到之前隐藏卡片区;编译通过,**待原作者再进游戏看**。
   - 原作者确认卡片位置正常,但打开时第一档先在最左、弹到右边再弹回:生成的 Motion 在 Awake 记下设计稿位置,进场动画结束 Restore 把卡片拉回设计稿位置(ClickFeedback 同理)。**生成器已改**:Motion / ClickFeedback 只在当前位置上叠加偏移、播完只撤自己那部分(GrowX 改为 x 缩放 + 位置补偿,不改宽度);主工程 SignMotion.cs / SignClickFeedback.cs 已用新生成器重出(旧的备份在 backups/20261009-165333/);Logic 的进度条对齐改为按 x 缩放算,数据到后卡片区 0.2 秒淡入。编译通过,原作者进游戏确认**207 的问题都解决了**(数据、位置、不闪)。原作者决定**先不提交**主工程改动。
   - **下一个任务:钻石充值页(还没做)**。现状:Sign 模块里的「01 · 钻石商城」页被一起覆盖进了 207,没有入口,也不是真正的钻石页。真正的钻石页 = 充值界面 102(`RechargePanel.prefab`,多标签容器)里「BUD钻充值」标签(RechargeId.GemPack = 8),由 `RechargeViewConfig.asset` 的 `_ViewPrefab` 指向 `Assets/Loadable/UI/RechargePanel/Views/GemPackView.prefab`(直接放置的 prefab,17 个节点,10 个嵌套 prefab),被 `RechargePanel.CreateRechargeView` 实例化进 `viewContent`——是子视图,不是面板。根节点脚本 `IAPGemPackView`:商品来自 `IAPDataManager.GetGemPackProducts()` / `GetProductInfo`,点格子 → 官方渠道先开 `ConfirmPaymentPanel` 选支付方式 → `PackPurchaseUtils.Inst.StartPurchase(...)` 真付钱,成功后 ShowReward;还有累充入口 `_btn_Cumlative` + 红点;格子是嵌套的 `IAPGemItemView`;文字有 `LocalizationComponent`(多语言)。设计稿「01 · 钻石商城」是整个充值界面的 PS 分层效果图(左侧页签、顶部货币栏、返回键 + 中间 6 格 ¥6/30/68/128/328/648、X60~X7100、+20~+620 首充加赠),价格数字都是切图。
     **原作者已拍板**:① 只换钻石页内容区(覆盖 GemPackView.prefab;左侧页签 / 顶部栏 / 返回键沿用现有充值界面外框,不动 RechargePanel.prefab);② 让设计把每个钻石格做成组、价格 / 钻石数 / 加赠改成文字图层(能按服务端商品数据刷新)。
     **做法(等设计稿)**:钻石页单独作为一个工作台模块(别再塞进 Sign),只含内容区;覆盖目标 GemPackView.prefab(生成器已修:根上是普通脚本的子视图不再被误判成面板、不会带 BasePanel 外壳);逻辑脚本照搬 IAPGemPackView 的取数与下单调用(ConfirmPaymentPanel + StartPurchase,不新增请求),先写好、离线编译通过、原作者确认后再覆盖;覆盖前看体检里「嵌套使用」有没有别的 prefab 引用 GemPackView(当前查到没有)。同时把 Sign 里的「01 · 钻石商城」和「02/03 充值到账」页从 Sign 模块里删掉再覆盖一次 207。
   - **2026-10-09 傍晚:钻石页的准备做完了,等设计稿**(原作者:设计稿到了以后作为单独模块导入,覆盖 GemPackView.prefab,逻辑照搬 IAPGemPackView 的取数和下单,不改支付流程)。
     - 生成器新增**子视图外壳**:覆盖目标不是面板、但旧根节点挂着业务脚本时(GemPackView 根上是 IAPGemPackView),根节点挂生成的 `<模块>Controller`(普通 MonoBehaviour,partial),业务逻辑写在手写的 `<模块>Controller.Logic.cs`;没有 Logic 时体检标红不能覆盖。`offline_check.js` 加了对应检查。
     - 「覆盖到 Unity」现在会把 `unity-reference/<模块名>/*.Logic.cs` 的副本在主工程缺 Logic 时随同一批写进去(partial 单独先放进主工程会因外壳类不存在而编译失败;删过模块目录也能自动找回 Sign 的 Logic),已有的永远不动。**改了 studio_server.py:8791 服务要重启后才有这个功能**(没重启也能覆盖 207,只是不会自动带 Logic)。
     - 逻辑草稿 `unity-reference/GemPack/GemPackController.Logic.cs`(模块名按 `GemPack` 写的):取数 GetGemPackProducts / GetProductInfo、点格子 ConfirmPaymentPanel → PackPurchaseUtils.StartPurchase → CommonRewardPanel、累充入口 → 207 + 红点、UGC 页签打点、PACKAGE_TYPE_US 分支,逐行照搬,不新增请求;显示上的差别写在文件头。**顶部 `DesignCells` 的标识是占位的(gemCell1~6 / …Price / …Gems / …Bonus,累充入口 cumulativeEntry)**,设计稿导入后按 README 事件表改。已用生成器造同标识的假模块,对主工程程序集离线编译通过(国内包和 PACKAGE_TYPE_US 都 0 错误);对真实 GemPackView.prefab 只读体检:判为子视图、不带 BasePanel、Logic 随覆盖带入、无阻断项、没有别的 prefab 引用它(GetMoreGemsPanel 用的是自己 prefab 里的 IAPGemPackView,不受影响,IAPGemPackView.cs 不能删)。
     - 设计稿到了的步骤:工作台新建模块 `GemPack`(只含内容区)→ 整体导入 → 每个钻石格设成可点击「仅触发事件」(别接弹窗,下单走 Logic),价格 / 钻石数勾「动态文本」→ 对齐 Logic 里的 DesignCells → 离线编译 → 原作者确认 → 覆盖到 `Assets/Loadable/UI/RechargePanel/Views/GemPackView.prefab`(它不是壳,是直接放置的 prefab)。首充加赠国内包服务端不下发,保留设计稿文字。
   - **17:21 钻石页和 207 都已写进主工程(原作者确认后)**:设计稿就是 Sign 里的「01 · 钻石商城」页(原作者「保存工程」导出 Sign.budui.json)。
     - 新工程 `projects/GemPack.budui.json`(模块 GemPack,1 页,只含内容区):去掉左侧页签 / 顶部货币栏 / 返回键 / 「热销」标题(充值界面外框自己画,且外框 Tab 等节点排在 viewContent 之后、盖在上面;viewContent 全屏,所以沿用设计稿全屏坐标和背景);六格合图与图标合图按格子中线裁成每格一张,每格 = 可点击容器 `gemCell1~6`(仅触发事件)+ 底板 + 图标 + 加赠角标 / 热销 / 最划算切图 + 动态文字 `gemCellNPrice`(思源 Heavy 42)、`gemCellNGems`(Montserrat Bold 37,与设计稿切图字形一致);右侧卡 = `cumulativeEntry`(打开 207)。构建脚本思路:按坐标裁切 + 切图换文字;用主工程字体合成预览与设计稿逐格对过。
     - `projects/Sign.budui.json` = 删掉「01 · 钻石商城」「02 / 03 充值到账」后的 Sign(11 页,没有按钮指向被删的页)。**原作者工作台里的 Sign 任务还是 14 页**:要么在工作台删这三页,要么「任务 → 从工程文件导入」这两个文件(GemPack 也要导入,以后迭代用)。原始导出在原作者 Downloads\Sign.budui.json。
     - 写入:GemPackView.prefab 原地覆盖(GUID 4821b175… 不变,根节点 GemPackView + GemPackController,Logic 从 unity-reference 带入),32 个文件;207 重新覆盖 53 个文件、删 Sign/Art 旧切图 50 个(删掉的页上的图)。备份 `backups/20261009-172136`、`backups/20261009-172137`。删页后页节点名里的序号变了,207 只有主页 90 个节点沿用原 fileID(壳的 21 处 override 都指根节点,仍有效;Logic 不用页名)。两边脚本对主工程程序集离线编译 0 错误。
     - **待原作者切回 Unity 编译后进游戏验证**:充值界面「BUD钻充值」页签显示 6 档价格 / 钻石数是否为服务端数据、点格子走官方支付确认(真付钱,建议用测试渠道 / 测试账号)、右侧「充值福利」卡打开 207;207 不再有钻石商城页。设计稿没有累充红点(Logic 已支持,加了名字含「红点」的节点即可)。
2. 主工程接入参考试点已跑通的范式:`unity-reference/CumulativeRechargePanel.cs`(外壳面板 + `UseNewView` 回退开关)、`unity-reference/RechargeRewardsServerAdapter.cs`(服务端数据 → 视图、领取回调 → HTTP)。**注意这两份绑的是试点手写的 `Bud.RechargeRewards.RechargeRewardsView`(`onClaimRequested` 等)和写死的 prefab 路径**;生成的视图接口是 `onAction(key)` / `onCloseRequested` / `onPageChanged` / `ApplyServerState` / `OpenPage` / `OpenPopup` / `Back`,Adapter 要按新接口重写。试点在主工程里的改动按规范 §6 记录还没提交,只在原作者电脑的工作区里。

## 等用户拍板的事

- 裙子 / 社区商品币 / 长椅贴贴 三张卡在 Figma 里没有详情稿:让设计补,还是先借用发型详情页当通用模板(正式版本本来就是一个模板页按奖励填数据)。
- 五选一详情页(07/14)的 5 个选项还不能点选切换,要不要做"单选"交互。
- 12(鞋子 / 已领取)状态稿要不要加入(领取后的状态)。
- Figma 插件何时恢复推进。
- 接入方式:替换旧面板 `CumulativeRechargePanel`(PanelId=207)里试点接好的视图,还是另开面板。

## 踩过的坑(新会话必读)

- **用户会在浏览器面板里同时亲自试玩**:往面板发自动点击做测试,会和用户操作互相干扰。**同一个地址的标签页共用一份 IndexedDB**(10-09 起按任务分键 `task:<id>`;同一任务后打开的标签页会自动只读,但它照样会在目录里出现、"接手"会让用户那边暂停保存)。所以同地址的其他标签页只能用脚本读数据,不能点界面、不能调 `takeOverTask`。要改动工程的测试,一律开隔离环境:`preview_start budui-studio-test`(端口 8792)或 data: 快照页(做法见 `ONBOARDING.md` 守则 3)。8792 和 8791 共用 `projects/`、`exports/` 文件夹,测试页里不要写回工程。
- 本地服务原来是单线程的,浏览器预先开的空连接会把它卡住,之后的保存/导出请求全部挂起(09-29 已改成多线程;如果看到保存请求一直没响应,先查是不是跑的旧版服务)。
- 内置浏览器面板会拦截原生 `alert/confirm/prompt`(被吞掉,用户看不到);只能用页面内的 dialog/toast。
- `javascript_tool` 单次最多等 45 秒;长任务在页面里跑,分段轮询。
- **Figma REST 额度**:查看/协作席位的 Token(响应头 `x-figma-rate-limit-type: low`)每月只有个位数次数。用户现在的 Token 额度正常,但每次读结构都耗额度,别随手调接口。画板目录已缓存在浏览器 localStorage。
- Token scope 必须是 `file_content:read`(用户曾误选成 `file_comments:read`)。
- `window.__test_build()` 会替换当前工程,画布上有用户数据时不要跑。
- 内置浏览器面板**隐藏时**:截图常超时(重试一两次通常能成);`<dialog>` 的 close 事件会延迟到页面重绘才触发,关掉的对话框暂时还留在 DOM 里 → 测试脚本只找 `dialog[open]`。
- 改完 `BUD_UI_Studio.html` 后,桌面版可能自动把它重新打开成一个新的 data: 快照标签页:之前注入的模拟数据(假 Figma 接口、localStorage 桩)全没了,要重新注入。

## 相关路径

- 主工程:`E:\BUDGCB\BUD_CHINA`(原作者电脑上的路径;Unity 2022.3.32f1,URP 14;UI 代码必须在 GameUI 程序集;每面板一个图集;Arts 源 prefab / Loadable 打包壳双层结构;新克隆要先跑 `Tools/BudBoxCommon/Sync-BudBoxCommon.ps1`)
- 规范:`docs/UI预制体替换规范.md`(主工程原件在 `E:\BUDGCB\BUD_CHINA\Docs\`)
- 提交者规范在线文档:https://claude.ai/code/artifact/655a23b1-ab6d-4bf0-8f99-8c2b34a1740e(原作者私有,别人多半打不开)

## 2026-10-10 追加

- **AI 统一风格**:原作者本机 ComfyUI(8188)+ Qwen Image 2.1,模板 = 207 + 钻石页新稿。重绘工具 `dev/restyle/restyle.py`,试点对比图 `exports/restyle_pilot/`(旧钻石格 4 张:卡片 / 角标 / 横条可用,光效和图标不能重绘,极端长宽比要补边,提示词要保主色)。**还没定第一个试点面板**;8189 是别的项目的 ComfyUI,别用。
- **Figma**:原作者装了 Figma 桌面版,要一个自己的文件 `lijixiantest` 放 207 / 钻石页 / 重绘试点。插件新增「从工作台导入」命令(工程 → 图层),导入用的文件和字体在 `exports/figma_lijixiantest/`。Figma 官方 MCP 连接器只能读稿,建内容只能靠插件。**还没在真实 Figma 里跑过**(只过了 `dev/plugin_import_selftest.js` 模拟测试)。
- **Figma 文件 `lijixiantest` 已建好(10-10,经 Figma 官方 MCP 连接器直接写入,不用插件)**:https://www.figma.com/design/4OGWcyPBXwt7b5Zdvbq4fP(原作者自己的团队 lijixian's team)。三页:「207 累充福利 · Sign」11 个界面 294 个图层、「钻石充值页 · GemPack」1 个界面 49 个图层(都是可编辑图层:切图 = 图片填充拉伸铺满,文字 = Noto Sans SC / Montserrat 可编辑文字)、「AI 重绘 · 风格模板与试点」5 张参考图。做法与脚本在 `exports/figma_lijixiantest/_build/`(compact.js 压节点 → gen_build.js 生成 use_figma 脚本 → upload_assets 按节点上传、按内容去重后复制 imageHash → 改成 CROP 单位变换拉伸)。原作者两个团队都是 View 席位:MCP 读取类工具每月 20 次,写入类(use_figma / upload_assets / create_new_file)不计;use_figma 里不能用 setPluginData。
- **xisi 第一阶段商业化 → 207 风格(10-10 晚)**:xisi「旧资源的规划」第一阶段 9 个界面里 8 个做了整屏 AI 效果图(充值福利 = 旧 207 已做成 Sign,跳过),赛季累充福利落到 10 张单张切图(SeasonCumulativeView 自有的卡片底 ×4、价格牌 ×2、眼睛开关 ×2、进度条 ×2,尺寸 / 透明轮廓与旧图一致,未写回主工程)。全部放在 lijixiantest 第 3 页分区「xisi 第一阶段商业化 · 统一风格」(6:2),左旧右新。工作目录 `exports/xisi_restyle/`(screens_out = 效果图,season_slices/new = 新切图);新工具 `dev/restyle/prefab_sprites.py`(列 prefab 用到的切图)、样式板 `dev/restyle/templates/style_swatch.png`、`restyle.py` 加了 `--neg` 和防照抄检查。效果图会改动文字数字、把金卡改成紫色、抹掉背景角色,只能定方向;货币图标没动,「7 个货币再优化」待原作者指定。
- **xisi 其余 7 个界面落到单张切图(10-10 晚,未写回主工程)**:原作者说「先不写进主工程,我先检查素材统一性」。7 个界面的 prefab 都在 `Assets/Arts/Config/Asset/RechargeViewConfig.asset`(_ViewPrefab 存路径字符串):VIP月卡会员 = VipMonthPack、超值礼包 = LimitedRechargeGiftPack、特惠月卡 = AnniversaryMonthCardView、每日充值礼 = DailyRechargePanel、首充活动 = FirstChargeOneYuanView、累充6元福利 = FirstChargeSixYuan、兑换码 = RedeemCodeView。人工挑了 52 张自有切图重绘(编号在 `exports/xisi_restyle/run_screens.py`,总览图 `own_sheets/`;和别的界面共用的不动,只在本批内共用的 item.png 一起换),成功 47 张、失败 5 张沿用旧图(超值礼包两条深紫栏底、特惠月卡 tipbg、每日充值礼 PayBg 和大横条)。提示词 `slice_prompt2.txt` 加了「保主色」,`slice_prompt3.txt` 再加「深色区保持深色」(超值礼包卡底的黑色价格带上压着白色价格字,第一次被画浅了)。赛季累充另出了保主色版(粉卡保住粉色;两条进度条照抄参考图,沿用第一版)。成品:`screen_slices/<界面>/new/` 只放合格的(失败的在 `new_failed/`),各界面 `list.json` 给 `dev/restyle/swap_in_place.py` 用(新工具:原地换图,默认演练,`--apply` 才写,备份到 `backups/<时间>-restyle/`,`--undo` 还原;赛季累充 10 张已演练通过,只有 SeasonCumulativeView 和它的图集在用)。Figma:lijixiantest 第 3 页新分区「xisi 第一阶段 · 其余界面单张切图」(10:2,在 6:2 右边),赛季累充三版对比 + 7 个界面新旧对照,生成脚本 `exports/xisi_restyle/gen_figma.js` + 上传 `up2.js`。
- **交付给同事(10-10 夜)**:原作者定了代码走私有 GitHub 仓库、同事没有大显存显卡 → AI 重绘用原作者电脑共享。新增:`.gitignore`(排除 projects/ backups/ exports/、本机口令、`dev/ai_remote.json`);`安装与自检.bat` + `dev/setup_check.py`(Python/Pillow/Node/Git/浏览器/工作台服务/AI/Unity 逐项检查,选 Y 试跑一张重绘);`studio_server.py` 加 AI 转发口 `/api/ai/*`(口令 `dev/ai_share_key.txt` 首次启动生成、不变;只放行上传/提交/进度/取图/状态/节点信息,提交的任务只能用重绘那 9 种节点;ComfyUI 仍只听 127.0.0.1),`--lan` 启动时打印给同事的 `dev/ai_remote.json` 内容;`restyle.py` 支持 `dev/ai_remote.json` 或 `--server/--key`;提示词放进 `dev/restyle/prompts/`;原作者 Claude 记忆整理成 `docs/经验与决定.md`;ONBOARDING 改为 Git 交付流程并加「7. AI 重绘」。已测:从本机局域网 IP 访问测试口(8793)——无口令 / 错口令 403、越权接口 404、越权节点 403、读口令文件 403、局域网写工程 403;正确口令下 restyle.py 完整跑通、自检 --smoke 25 秒通过。**还没从同事电脑实际连过**;工程数据走 U 盘(projects/ + 任务首页「导出全部任务」)。
- **交付方式改了(10-10 夜,原作者)**:同事显卡是 RTX 2060,原作者「最好不要再通过我这边共享使用工作台」→ 上一条里的 AI 转发口(`/api/ai/*`、`dev/ai_share_key.txt`、`restyle.py --server/--key`、`dev/ai_remote.json`)已整个删掉;改为 U 盘带 AI 环境包 `exports/交付给同事_U盘/AI重绘环境/`(精简 ComfyUI 便携版 + 3 个模型,带「启动 ComfyUI.bat」「启动 ComfyUI(显存不够时用).bat」「校验模型.bat」),同事本机实测;自检加了显卡 / 显存 / 驱动(CUDA 13 要 580+)/ 内存检测,显存 <12 GB 时试跑自动用 768 分辨率并报用时。2060 上能不能出图、多慢,**还没实测**。
  - 环境包已在原作者电脑上验证:拷出来的 3 个模型 SHA256 校验通过;在新位置用 8190 端口启动 ComfyUI 0.37,认出 3 个模型和 Qwen 2.1 节点;测试生成的 user/input/temp 已删。整个 U 盘文件夹 20.03 GB,U 盘要 exFAT / NTFS(FAT32 放不下 4 GB 以上的模型文件)。
- **交付方式再改(10-11,原作者)**:「只封装工作台,缺少的模型让她的 claude 帮她下载最适合她本机配置的版本」→ U 盘文件夹 `exports/交付给同事_U盘/`(20 GB 环境包、工程副本)已删。模型配置从代码里抽出:`dev/restyle/models.json`(原作者 4090 的 int8 组合)+ 每台电脑自己的 `models.local.json`(不进仓库),可改主模型 / 文本编码 / VAE 文件名、加载节点(GGUF 用 UnetLoaderGGUF / CLIPLoaderGGUF)、`QwenImage21Cache` 的缓存设备和精度、默认分辨率;`restyle.py` 和自检都读它。自检按 ComfyUI 的 PyTorch CUDA 版本查驱动下限。ONBOARDING「7. AI 重绘」改写成给 Claude 的按显存选模型指南(官方源 HF / ModelScope 的 Comfy-Org/Qwen-Image-2.1)。已测:默认配置自检通过;文件名对不上、GGUF 节点没装都能报清楚;`cache_device=cpu + cache_dtype=int8 + res 768` 出图正常(4090 上 8 秒)。GGUF 组合没测过(原作者电脑上没有这类模型)。
- **已推到 GitHub(10-11)**:https://github.com/958357521a-rgb/ui_animation-unity ,`main` 分支。**目前是公开仓库**(原作者知情:「先做成公开的,后续我再修改」),里面有 `unity-reference/` 的主工程业务代码和 `dev/restyle/templates/` 的 3 张美术模板图,提醒原作者改成私有(改私有后同事要被邀请为 Collaborator 才能拉取)。已核对远端没有 projects/、backups/、exports/、本机口令和 models.local.json。以后改了工作台要 commit + push,同事 pull 更新;待办:原作者邀请同事,同事的 Claude 按 ONBOARDING 第 7 节在 RTX 2060 上装 ComfyUI + 模型并实测。

## 2026-10-13 资源批处理管线(框架)

- 原作者要求:在工作台里搭批量处理 UI 资源的管线——接本地桌面版 Figma、按提交的标准和参考批量处理切好图的资源(主页皮肤、头像框等)、一键加晃动 / 变色这类简单动效、生成可直接提交的 unitypackage;**先搭框架,细节后补**。选的方案:插件 + 本地服务桥接 / AI 重绘 + 规则检查 / 新增 + 替换都支持 / Animator 动画片段。
- 做了:工具栏「资源批处理」→ `pipeline.html`;核心 `dev/pipeline/`(说明见 `dev/pipeline/README.md`);服务 `/api/pipeline/*`、`/api/bridge/*`;插件新命令「资源批处理」(`figma-plugin/batch.html`,manifest 只放行 localhost:8791);头像框标准(新增:底框 / 预览进 CreatorHeadCycle 图集文件夹,上 / 下层特效 = Arts 源 prefab + Loadable 壳 + Animator + .anim/.controller,README 给出 HeadCycleConfig.json 条目;替换:沿用旧 .meta)和「通用 · 原地换图」标准;6 种动效预设(晃动 / 浮动 / 抖动 / 呼吸 / 闪烁 / 变色)。
- 已测:`python dev/pipeline_selftest.py` 全过;`node dev/plugin_batch_selftest.js` 15 项全过(原有两个插件自测仍全过);8792 测试页走通「模拟插件发送(用头像框 36 的真实部件和位置)→ 收件 → AI 重绘 2 张 → 改动效 → 检查(编号 36 重名被拦下)→ 打包 → 替换模式沿用旧 GUID → 放回 Figma → 模拟插件取回」;两份交付包导入空白 Unity 2022.3.32f1 工程零报错,prefab / 壳 / Animator / 曲线绑定全部解析,动画采样数值与设定一致。
- **没做 / 待原作者补**:主页皮肤等其他资源的标准(换哪些图、放哪、配置怎么写);设计稿与 Unity 的尺寸比例(现在 1:1);一键写入配置 / 直接写进主工程;插件还没在真实桌面版 Figma 里跑过。本机设置 `dev/pipeline/settings.local.json` 已填主工程路径 E:\BUDGCB\BUD_CHINA。
- **10-13 晚交给同事审核**:原作者说「我这个是先帮 UI 先行跑的,到时候她会通过 GitHub 去拉取」→ 暂定规范列在 `docs/资源批处理_暂定规范.md`(每条带依据和待确认,文末有给她 Claude 的审核步骤和审核记录表),简明使用说明 `docs/资源批处理_使用说明.md`;示例 `samples/`(头像框 36 号部件做的 `头像框_9036` + 布局 / 示例动效 / 3 张 AI 示例图 + 示例交付包;工作台示例工程 GemPack.budui.json),`python dev/pipeline_demo.py [--job]` 一键放进中转箱 / 建好示例任务。8791 服务已重启到新代码。
- **10-13 深夜:入口改成任务首页页签**(原作者:「两个管线直接在状态栏做两个独立的页签互不影响,功能按钮放在各自页签内」)→ 任务首页顶栏「界面改版 / 资源批处理」两个页签,资源批处理内嵌 `pipeline.html?embed=1`(只加载一次,切页签不丢状态),配对码 / 主工程路径显示在首页顶栏(postMessage);编辑界面工具栏的「资源批处理」跳到这个页签。
- **10-13 深夜:补齐其余四类装扮的标准**(原作者:「还有主页皮肤、称号、聊天气泡框等,去 Unity 或 Figma 找以往的资源补齐」)→ 只读调查主工程,个人页「装扮」共五类(主页皮肤 / 头像框 / 聊天气泡 / 昵称框 / 称号),新增 `standards/chat_bubble.json`、`title.json`、`nickname_frame.json`、`home_skin.json` + `dev/pipeline/builders.py`(对照 ChatBubbleEff_38、Title_41/43、Nickname19、Theme_45),详见 `dev/pipeline/README.md` 总表和 `docs/资源批处理_暂定规范.md` I 节。页面加了九宫格输入、每个资源的「配置条目字段」表单(名称 / 说明 / 颜色……)。测过:`pipeline_types_selftest.py` 全过、头像框交付包和改动前逐字节一致;六个包导入空白 Unity 2022.3.32f1 工程零报错,35 个 prefab 全部加载、无空贴图、动画绑定和采样正常。**发现并修了**:交付包原来用中文任务名做文件名,Unity 解包会失败(Couldn't decompress package)→ 改成英文 `<标准>_<编号>_<尾号>.unitypackage`,示例包改名 `avatar_frame_9036_sample.unitypackage`。没做:称号扫光、昵称框 17 号那种嵌套 Left / Right 子 prefab;各类 PgcId 号段要和服务端确认。
- **10-14 凌晨:四类示例 + 刷新停在原界面**(原作者:「新增的分类也要做示例」「每次刷新都自动跳到界面改版的工作台,应该是当前界面刷新」)→ `samples/pipeline/` 新增 chat_bubble_9038(主工程气泡 38)、title_9043(称号 43)、nickname_frame_9019(昵称框 19)、home_skin_9045(主页皮肤 45),位置按主工程 prefab 换算,九宫格 / 配置字段取自主工程;`pipeline_demo.py` 加 `--all`(全部示例)、`--out`(更新示例输出)、layout.json 支持 borders / fields、同名示例任务先删后建;本机已跑 `--all --job --out`,五个示例任务在 8791 的批处理列表里。四个示例包导入空白 Unity 工程零报错,64 个 prefab、40 段动画多点采样全部正常。刷新:工作台记 sessionStorage `budui_view`,内嵌批处理页用 `?job=` 恢复打开的任务;8792 测过三种刷新(批处理页签 + 打开的任务 / 首页 / 编辑界面)都停在原处。
- **10-14:两个管线页签常驻**(原作者:「切换到界面改版以后管线页签就不见了,这两个页签应该常驻」)→ 编辑界面顶栏也放「界面改版 / 资源批处理」页签,工具栏末尾的「资源批处理」按钮去掉;点「界面改版」回到离开前的位置(编辑界面或任务卡片)。8792 测过编辑界面 ↔ 批处理 ↔ 任务卡片来回切换。已推到 GitHub main(ca0e02d)。仓库继续公开(原作者 10-14 确认「仓库继续公开,不用处理」),示例里带主工程美术。
- **10-14:两条管线都有任务中心**(原作者:「两个管线页签内都缺少任务中心,去管理、编辑、删除、导出任务;资源批处理要按类型归纳,不要笼统放一起」)→ 界面改版:原有任务首页就是任务中心,入口改名「▦ 任务中心 · 任务名」、首页顶栏标「任务中心」、卡片「保存为文件」改叫「导出」。资源批处理:新做任务中心(按类型分区 + 状态 / 类型筛选 + 搜索;打开 / 编辑信息 / 复制 / 导出任务包或交付包 / 标记完成 / 回收站恢复 / 彻底删除 / 导入任务 / 导出全部),左边栏按类型分组可折叠,任务页加面包屑和同样的管理按钮;删除改成先进回收站。自测 `pipeline_types_selftest.py` [5] 节覆盖这些操作;8792 实测卡片上每个按钮。8791 已重启到新代码。

## 2026-10-12 追加(同事电脑,从旧会话「UI工作台熟悉」归档)

- **同事电脑已装好**:RTX 2060 12GB(驱动 546,只支持 CUDA 12)、内存 64GB,本机没有 BUD_CHINA 主工程。仓库克隆在 `E:\ui_animation-unity`;旧文件夹 `E:\BUD_UI_Studio` 是 10-09 的非 git 旧版(和仓库比对过:仓库全部更新,旧版里没有要搬回来的东西),整体备份在 `E:\BUD_UI_Studio_backup_20261012`(不含 projects/),两个工程文件 `RechargeRewardsOverview` / `Sign.budui.json` 已复制进新目录的 `projects/`。桌面快捷方式「BUD UI Studio」已建好并实测能打开。
- **AI 重绘环境**:ComfyUI 0.39.0 便携版 nvidia_cu126 在 `F:\ComfyUI\ComfyUI_windows_portable`(torch 2.14+cu126,显卡可用),启动用 `run_bud_lowvram.bat`(`--lowvram`、8188、只听本机);模型 int8 主模型 + int8 文本编码 + VAE,来自 HuggingFace;`models.local.json` = cpu / int8 / 768(ONBOARDING §7 表里 2060 那一行)。归档时文本编码模型还在续传(约 5.9/8.7 GB),**试跑出图和耗时还没实测**。
- **推送**:同事让 Claude 改完、自检通过后直接 commit + push。改工作台核心代码前仍按 ONBOARDING 先和原作者说好谁改。
- **待确认的导入问题(09-29 同事在旧版上碰到)**:① 没有文字的进度条被当成整张切图放在滚动区外,横向滑动时轨道不动,看起来缺后半段(根因:切图规则只展开含文字的分组);② 长椅贴贴卡被挤压;③「01 钻石商城」和「显示隐藏」底板没导进来。旧会话没修,也没确认最新版是否还有。要修进度条就改 `buildScreenFromFigma`,同步插件 `planRenderIds` 并升级 RULES。
- **小问题(不急)**:生成的 View 脚本注释里带 `TODO 联调时可改为强类型参数`(`BUD_UI_Studio.html` 的 `ApplyServerState` 模板),会随导出进主工程;`studio_server.py` 的 `end_headers` 对所有来源开 CORS(写接口另有 Origin / 口令校验);全局变量 `history` 和 `window.history` 重名。
- 旧会话的原始记录在 `docs/会话归档/`(只在本机,不进仓库)。

## 2026-10-15 S18 赛季通行证:试玩跳转 + 动效
- 用户的 S18 任务是 10-15 11:24 从插件包(`exports/bridge_screens/20261015-112404930.budfig.json`,9 个界面)导入的,早于「按名字自动连线」提交,所以工程里没有跳转;**在该任务里点一次「✦ 一键配动效」即可补上**(会整体重配本模块的交互和动效,Ctrl+Z 可撤销)。
- 本次修:页签(每日/每周/赛季任务)互切改为 `switchPage`(不压栈,返回 / 「赛季奖励」直接回主页);热区收拢 + 补认滚动区 + 全屏图层组展开配动效(详见 CLAUDE.md「一键配动效/交互」);试玩时装饰图不再挡点击。旧三个工程 `--reconfigure` 结果与改前一致。
- 还连不上的:「购买等级 / 购买通行证」—— Figma 里有「02 · 解锁通行证 · 分层拼装」(380:3750)但那次没导出,在插件里补发这一屏、导入时选「补充到当前模块」后再点一键配动效,「购买通行证」会连到它;「套装预览 / 预览50级大奖 / 规则」没有对应界面;08「已达兑换上限」是 06 的状态稿,没有入口按钮。
- 离线复现脚本思路:在 Node 里跑页面脚本 → `importScreens(插件包 frames, render, {mode:"new"})` → 检查各页可点元素和跳转(同 offline_check 的空 DOM 桩)。
