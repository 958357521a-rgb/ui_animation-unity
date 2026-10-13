# 资源批处理(pipeline)

批量处理切好图的 UI 资源(头像框、皮肤、通用切图……):

```
桌面版 Figma ──插件「资源批处理」发送选中──▶ 工作台中转箱 ──▶ 批处理任务(pipeline.html)
   ▲                                                         │ AI 重绘(本机 ComfyUI + Qwen Image 2.1)
   └──── 插件「取回处理结果」(新切图摆在原资源右边) ◀── 放回 Figma │ 规则检查(按「标准」)
                                                             │ 配动效(晃动 / 浮动 / 抖动 / 呼吸 / 闪烁 / 变色 → Animator 动画)
                                                             ▼ 生成 .unitypackage(+ README:要手动加的配置条目)
```

2026-10-13 搭的框架,规则是暂定的、待接手同事审核:`docs/资源批处理_暂定规范.md`;给人看的简明说明:`docs/资源批处理_使用说明.md`;示例:`samples/`(`python dev/pipeline_demo.py --job`)。头像框(新增 / 替换)完整可用,并在空白 Unity 2022.3.32f1 工程里导入验证过;主页皮肤等其他资源的「标准」等补充细节后再加。

## 怎么用

1. 工作台工具栏「资源批处理」(或打开 `pipeline.html`)。右上角填主工程路径(检查编号重名、替换模式读旧 .meta 要用),记下**配对码**。
2. 桌面版 Figma:插件 → BUD UI Studio →「资源批处理」(开发版插件第一次要「插件 → 开发 → 从清单导入」选 `figma-plugin/manifest.json`)。填工作台地址和配对码,「测试连接」。
3. 在 Figma 里选中资源:**每个资源 = 一个画框或分组**(名字带编号,如「头像框_40」),里面**每个子图层 = 一张切图**,子图层名决定它的角色(见下)。点「发送」。
4. 工作台里新建任务(选标准、新增 / 替换)→「从 Figma 收件」→ 勾要 AI 重绘的切图 →「AI 重绘」→ 按需改角色、动效 →「规则检查」→「生成 unitypackage」。没有 Figma 时也能「上传本地切图」(没有位置信息,全部居中)。
5. 想在 Figma 里看结果:「放回 Figma」→ 插件里「取回处理结果」。

## 文件

| 文件 | 作用 |
|---|---|
| `pipeline.html`(仓库根目录) | 批处理页面;http://localhost:8791/pipeline.html 或双击打开都行 |
| `dev/pipeline/pipeline_core.py` | 任务存档、中转箱、AI 调度(调 `dev/restyle/restyle.py`)、规则检查、打包 |
| `dev/pipeline/unity_yaml.py` | 生成切图 meta、特效 prefab、Loadable 壳、.anim、.controller(逐字段对齐主工程 HeadTopEffect_36) |
| `dev/pipeline/unitypackage.py` | 写 .unitypackage |
| `dev/pipeline/standards/*.json` | 「标准」:每类资源一个文件 |
| `dev/pipeline/templates/sprite.png.meta` | 切图导入设置(主工程头像框部件的原样) |
| `dev/studio_server.py` | `/api/pipeline/<动作>`(只认本机工作台页面)、`/api/bridge/*`(只认本机 + 配对码) |
| `figma-plugin/batch.html`、`code.js` 末尾 | 插件「资源批处理」命令 |
| `exports/pipeline/<任务 id>/` | 任务数据:`job.json`、`in/`(原图)、`out/`(AI 新图)、`build/`(交付包 + README) |
| `exports/pipeline/_bridge/` | 中转箱:`inbox/`(插件发来的)、`outbox/`(等插件取回的) |
| `dev/bridge_key.txt`、`dev/pipeline/settings.local.json` | 配对码、本机主工程路径(都不进仓库) |

## 「标准」格式(`standards/<id>.json`)

| 字段 | 说明 |
|---|---|
| `id` / `name` | 标识 / 显示名 |
| `replaceOnly` | 只支持替换(原地换图) |
| `idFrom` | 从资源名里取编号的正则(新增模式要编号,如 `(\d+)\s*$`) |
| `roles` | 切图角色:`label`、`match`(按切图名认角色的正则,不区分大小写)、`default`(都不匹配时用它)、`size`(标准尺寸,不符只提示)、`path`(单张图的落点,`{id}` 替换成编号)、`effect`(进哪个特效 prefab) |
| `effects` | 特效 prefab 名(`{id}`) |
| `effectDirs` | 部件图目录、Arts 源 prefab 目录、Loadable 壳目录、根节点尺寸、`unitsPerPx`(设计稿 1 像素 = 多少 Unity 单位) |
| `config` | 要手动加进哪个配置文件、条目模板(值末尾 `?` = 有对应内容才写;`{id:int}` 写成数字) |
| `rules` | `requireAlpha`、`keepInputSize`(新图必须和原图同尺寸)、`maxBytes`、`maxOutlineGrowth`(新图画出原轮廓的比例上限) |
| `ai` | 参考图(`refs`,相对仓库根目录)、提示词文件、`keepShape` |
| `motionDefaults` | 某角色默认带的动效 |

头像框(`avatar_frame`)按主工程 2026-10-13 的现状写:底框 `CreatorHeadCycle/HeadCycle_<id>.png`(该文件夹被 UserInfoHeadView 图集打包)、预览 `HeadCycle_<id>_Pre.png`、上层 / 下层特效 `HeadTopEffect_<id>` / `HeadBottomEffect_<id>`(Arts 源 + Loadable 壳 + Animator,部件图和动画在 `HeadEffect_<id>/`)、配置 `HeadCycleConfig.json`。子图层名:`底框…` → 底框,`…预览 / …_pre` → 预览,`上…` → 上层特效,`下…` → 下层特效,`参考… / _…` → 不导出,其余 → 上层特效。

## 动效

每层一个预设,参数:幅度、周期(秒)、错开(秒)、变色的目标颜色。一个特效 prefab 一个动画片段,长度 = 各层最长周期,短周期的层在片段里重复整数次;每条曲线首尾相等,循环不跳。

| 预设 | Unity 里改什么 | 幅度单位 |
|---|---|---|
| 晃动 | 绕 z 轴来回转(localEulerAngles.z) | 度 |
| 浮动 / 抖动 | anchoredPosition 的 y / x 来回 | Unity 单位 |
| 呼吸 | 缩放 1 ↔ 1+幅度 | 倍数增量 |
| 闪烁 | Image 透明度 1 ↔ 1−幅度 | 0~1 |
| 变色 | Image 颜色 白 ↔ 目标色(颜色乘在贴图上,白 = 原色) | 强度 0~1 |

动画绑定按节点名的 CRC32 匹配,所以特效里的节点名和部件图文件名一律用英文(中文切图名换成 `Layer_01`…,只在工作台里显示中文)。页面左侧的预览是浏览器里的近似,以 Unity 为准。

## 新增 vs 替换

- **新增**:按标准落点放新文件,GUID 按落点路径派生(同一任务再生成逐字节不变)。检查会挡住主工程里已有同编号的资源。配置文件**不自动改**(避免覆盖别人同时加的条目),README 给出要加的条目。
- **替换**:每张切图填「替换主工程里的」路径;包里沿用那张图原来的 .meta(GUID、九宫格、图集都不变),只换 PNG;要求同尺寸。替换模式不导出动效。也可以用 `dev/restyle/swap_in_place.py` 直接写进主工程(默认演练、自动备份)。

## 自测

```
python dev/pipeline_selftest.py        # 合成切图走一遍「收件 → 动效 → 检查 → 打包 → 放回」,拆包校验引用 / Layer / 动画绑定 / 循环
node dev/plugin_batch_selftest.js      # 模拟 Figma 环境测插件「资源批处理」命令
```

`pipeline_selftest.py --keep <目录>` 会留下交付包,可以拿去 Unity 空工程里导入实测(2026-10-13 做过:导入零报错,prefab / 壳 / Animator / 曲线绑定全部解析,采样数值与设定一致)。

## 还没做 / 待补

- 主页皮肤(ProfileTheme)等其他资源的标准:换哪些图、放哪、配置怎么写,等原作者补充。
- 设计稿和 Unity 的尺寸比例(现在 1 设计像素 = 1 Unity 单位,头像框部件与主工程一致)。
- 「写入配置 / 直接写进主工程」一键完成(现在是生成包 + 手动加配置条目)。
- 插件「资源批处理」还没在真实的桌面版 Figma 里跑过(只过了模拟测试);批量 AI 是逐个资源串行跑。
