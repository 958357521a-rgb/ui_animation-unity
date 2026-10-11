# BUD UI Studio · 新同事上手说明

> 写给接手这个文件夹的同事和她的 Claude Code。Claude Code 打开本文件夹时会自动读 `CLAUDE.md`,那里会指到这份文件。
> 三份文档分工:**本文件** = 在新电脑上跑起来、怎么操作这个系统;`HANDOFF.md` = 当前进度、下一步、待拍板的事、踩过的坑;`CLAUDE.md` = 改代码时不能破坏的硬规则。
> 文档里的"原作者"指把文件夹交出来的同事;`HANDOFF.md` 里的"用户"也是指原作者。原作者在自己电脑上和 Claude 定下的决定、踩过的坑整理在 `docs/经验与决定.md`(那些记忆不会跟着仓库走)。更新于 2026-10-10。

## 给同事本人:开始用

1. **拿到工作台**:原作者在 GitHub 上把私有仓库共享给你(邮件里点接受邀请)。装 [GitHub Desktop](https://desktop.github.com/),登录后 File → Clone repository 选这个仓库,放到任意位置(路径里有中文也没关系)。也可以用命令行 `git clone <仓库地址>`。
2. **双击文件夹里的「安装与自检.bat」**:逐项检查 Python、Pillow、Node.js、浏览器、工作台服务、AI 重绘、Unity,缺什么照提示补(缺 Pillow 会自动装)。没装 Python 时它会告诉你怎么装,装好再双击一次。
3. **工程数据**:仓库里不带工程文件(几十 MB,含游戏美术资源)。新需求直接在工作台「＋ 新建任务」;要接着做原作者的任务,向原作者要工程文件(`.budui.json`,或任务首页「导出全部任务」得到的文件),放进 `projects/` 后点「载入工程」,或在任务首页「从工程文件导入」。
4. **AI 重绘(可选)**:对 Claude 说「按 ONBOARDING.md 第 7 节,按我电脑的配置把 AI 重绘环境装好」。它会先查你的显卡、显存、内存、硬盘,挑最合适的模型版本,下载前告诉你要下多大的文件,你同意了才下;装好后试跑一张给你看效果和用时。
5. **用 Claude Code 打开这个文件夹**(桌面版在 Code 页选择文件夹;命令行版在文件夹里运行 `claude`),对它说:**「按 ONBOARDING.md 帮我把工作台跑起来」**。之后直接用中文说要做什么就行,比如「把 Figma 里新的总览画板导进来」「重新配一下动效」「覆盖到 Unity」。

## 更新到新版本

原作者改了工作台会推到 GitHub。你这边:GitHub Desktop 点「Fetch origin」→「Pull origin」(命令行 `git pull`)。然后:

1. 关掉正在跑的本地服务再重开(桌面「BUD UI Studio」图标起的是后台服务,在任务管理器结束 `pythonw.exe`,再双击图标;Claude 桌面版让它重启 `budui-studio` 预览)。不重开的话服务还是旧代码,新功能会报错。
2. 刷新工作台页面(Ctrl+F5)。
3. 你在浏览器里做的任务存在浏览器本地,`projects/` 也不在仓库里,更新碰不到它们。
4. 不要直接改仓库里的文件再 pull(会冲突);要改工作台本身,先和原作者说好谁改。

## 这个系统是什么

一个本地单文件网页工具(`BUD_UI_Studio.html`,零依赖),把 Figma 设计稿变成 BUD_CHINA 主工程(Unity)能用的 UI 预制体:

```
Figma 设计稿 ──导入──▶ 工作台还原图层(文字可编辑,其余切图)──▶ 一键配动效/交互、连页面跳转
            ──▶ ▶ 试玩(像真机一样点)──▶ 导出 .unitypackage(prefab + meta + 贴图 + C# 视图脚本)──▶ 接入主工程
```

- 一张 Figma 总览画板 = 工作台里的一个模块 = 主页 + 详情页 + 弹窗。
- 当前在做的是**充值福利**模块(模块名 `RechargeRewardsOverview`,10 页),工程文件在 `projects/`。
- 另有 **AI 统一风格**工具(`dev/restyle/`):用 Qwen Image 2.1 按 207 / 钻石页的新风格批量重绘旧界面的切图,尺寸和透明轮廓不变,可以原路径替换进主工程。
- 最新进度以 `HANDOFF.md` 为准。2026-10-09:充值福利已经通过「覆盖到 Unity」换进主工程 207 累充面板(模块 `Sign`,`projects/Sign.budui.json`),原作者进游戏验证过数据、位置、动效;钻石页(GemPack)也已写入;主工程改动原作者还**没提交**。下面是 09-29 时的旧记录:这 10 页是用旧流程(先拉主页,再「＋加页面」批量补)通过链接 + Token 从真实设计稿导进来的,试玩和导出都跑通了。现在的「整张画板一次导入」和「✦ 一键配动效全部页面」是 2026-09-29 新改的,只在模拟画板上测过,**还没用真实画板跑过**。**导出的包还没有真正接进过 Unity 主工程**(见下文「接入主工程」)。

## 第一次打开:Claude 按顺序做

### 1. 读文档

`CLAUDE.md`(已自动加载)→ 本文件 → `HANDOFF.md` → `docs/经验与决定.md`。`HANDOFF.md` 里"等用户拍板的事",同事拿不准的先和原作者确认。

### 2. 检查环境

先让同事双击「安装与自检.bat」(或 Claude 直接跑 `python dev/setup_check.py`),按输出补齐;下表是各项的用途。

| 需要 | 用途 | 怎么确认 |
|---|---|---|
| Python 3 | 本地服务 `dev/studio_server.py`:托管工作台,并能把工程写回 `projects/` | `python --version`。不认 `python` 就试 `py -3`(Windows)或 `python3`(macOS),并把 `.claude/launch.json` 里**两个配置**的命令都改掉:用 `python3` 就把 `runtimeExecutable` 改成 `"python3"`;用 `py -3` 要拆开写,`runtimeExecutable` 写 `"py"`,`runtimeArgs` 开头加一项 `"-3"` |
| Chrome 或 Edge | 运行工作台 | — |
| Node.js 20.15+(可选) | 改代码后的自检:`dev/offline_check.js` 要 18+,`dev/plugin_selftest.js` 要 20.15+ / 22.2+ | `node --version` |
| 思源黑体(可选) | 只影响画布预览:没装会用微软雅黑代替,字重和 Unity 里看到的不一样;导出不受影响 | — |
| Figma 桌面版(可选) | 安装导出插件 | — |
| Unity 2022.3.32f1 + BUD_CHINA 主工程(接入时才需要) | 导入交付包 | 文档里的 `E:\BUDGCB\BUD_CHINA` 是原作者电脑上的路径,**先问同事她的主工程在哪**;详见「接入主工程」 |

### 3. 选定在哪个浏览器里工作(重要)

工程自动保存在浏览器本地存储里,按"哪个浏览器 + 哪个地址"分开存:内置浏览器面板和她自己的 Chrome 是两份;`localhost` 和 `127.0.0.1` 是两份;双击打开的 `file://` 又是一份。在一处载入的工程,换一处打开看到的是空画布。

- **用 Claude Code 桌面版**:就在内置浏览器面板里用 http://localhost:8791(Claude 也能看到和操作同一个页面)。
- **用命令行版**:固定用她自己的 Chrome/Edge 打开 http://localhost:8791。

### 4. 启动工作台

- **桌面版**:`preview_start` 启动 `budui-studio`(`.claude/launch.json` 已配好,即 `python dev/studio_server.py 8791`),打开根地址会自动跳到工作台。
- **命令行版**:请同事在文件夹里开终端运行 `python dev/studio_server.py 8791`,**窗口别关**,再打开上面的地址。
- 提示 8791 被占用:可能是服务已经在跑(直接打开地址),也可能是别的程序。第一次用时浏览器里还没有数据,换个端口没有损失(**别换成 8792**,那是测试端口);换了之后就一直用新地址。
- 没装 Python 也能用:双击 `BUD_UI_Studio.html` 用 Chrome/Edge 打开,只是不能写回 `projects/`(见「存档」)。

### 4a. 桌面应用(推荐日常这样打开)

- 双击文件夹里的 **`创建桌面快捷方式.bat`**,桌面上会出现「BUD UI Studio」图标。双击它:本地服务(8791)没在跑就在后台无窗口启动(「覆盖到 Unity」要用),然后用 **Edge 的应用窗口**打开工作台(独立窗口,没有地址栏和标签页,任务栏单独一个图标)。没装 Edge 时用 Chrome。
- 应用窗口里的工程数据就是"Edge + 直接打开这个 html"那一份。以前在别的浏览器(比如夸克、Chrome)里做的任务要搬一次:在原来的浏览器里打开工作台 → 任务首页「导出全部任务」→ 得到一个文件 → 应用窗口里任务首页「从工程文件导入」选它。导入保留任务原来的 id,重复导入会跳过已有的任务。
- 夸克等国产浏览器不支持应用窗口模式(会开成普通标签页),所以固定用 Edge。文件夹挪了位置,重新运行一次 `创建桌面快捷方式.bat`。
- 后台服务没有窗口,要停的话在任务管理器里结束 `pythonw.exe`(一般不用管)。

### 4b. 局域网共享(可选:让别人不装任何东西直接用)

- 在共享的电脑上双击文件夹里的 **`启动局域网共享.bat`**(桌面版也可以让 Claude 启动 `budui-studio-lan`),窗口里会打印「局域网链接(发给同事):http://<IP>:8790/」,把这个链接发给同一局域网的人,用 Chrome/Edge 打开即可。窗口别关,关掉就停止共享;共享电脑休眠或换网络后 IP 可能变,以窗口里打印的为准。
- 别人打不开:多半是 Windows 防火墙拦了 → 共享的电脑第一次启动时弹窗要点「允许访问」;或者在「Windows 安全中心 → 防火墙和网络保护 → 允许应用通过防火墙」里给 Python 勾上对应网络。这是系统安全设置,要电脑主人自己点,Claude 不改。
- 打开局域网链接的人:工程存在**他自己的浏览器**里,互不影响;点左上角任务名 →「从共享文件夹载入」可以直接选共享电脑 `projects/` 里的工程。可以导入素材、配动效、试玩、「导出交付包」「保存工程」(下载到他自己电脑)。
- 为了安全,局域网里的其他电脑**不能**「覆盖到 Unity」、不能写回共享电脑的文件夹,也读不到 `backups/`、`dev/` 等文件;要覆盖进主工程,把「保存工程」得到的文件发给共享电脑上的人,或在共享电脑上操作。

### 5. 载入工程(新电脑必做)

1. 工程文件不在仓库里(`.gitignore` 排除了 `projects/`),向原作者要文件放进 `projects/`。有原作者导出的「全部任务」文件就优先导它(任务首页「从工程文件导入」),所有任务一次到位;否则请同事点工具栏「载入工程」→ 选 `projects/Sign.budui.json`(约 33 MB,最新的充值福利,含全部贴图,要等几秒)。系统的选文件窗口 Claude 操作不了。
2. 载入后会成为一个任务(左上角显示任务名)。以左侧「页面」列表为准,`Sign` 应有 11 页:🏠 05 奖励总览;📄 06 圣天使之翼 / 07 自选特效 / 10 发型 / 11 鞋子(可领取)/ 12 鞋子(已领取)/ 14 自选动作;🗨 04 福利规则 / 08 确认兑换 / 09 兑换成功 / 13 领取成功。模块名框里是 `Sign`。
3. 之后会自动保存到这个浏览器;同一浏览器、同一地址刷新后会回到上次的任务。

### 6. 连上 Figma(真要导入时再做)

- **链接 + Token**:这 10 页就是这样导进来的(当时是旧流程,见上文"进度")。用同事自己的 Figma Token,创建时 Scopes 只开 **File content = Read-only**(不是名字很像的 File comments);她的 Figma 账号要能打开这份设计稿。「查看/协作」席位每月只有个位数的接口次数:整张画板导入一次大约用 3 次(读结构 1 次 + 每 100 张切图 1 次)。
- **Figma 插件**(不消耗额度):安装见 `figma-plugin/README.md`。**还没在真实 Figma 里装过**,原作者之前决定暂缓,要不要启用先和原作者商量。
- 设计稿是 Figma 里的总览画板「Unity中间版」,链接不在文件夹里,向原作者要。
- 原作者的 Figma 文件 **lijixiantest**(207 / 钻石页的可编辑图层、AI 重绘的模板和新旧对照)在原作者自己的团队里,请原作者在 Figma 里把文件共享给同事的账号。Claude 读写 Figma 用的是 Claude 的 Figma 连接器,要用同事自己的 Figma 账号授权;「查看」席位读取类工具每月只有 20 次,写入不限。

### 7. AI 重绘(可选:批量统一旧界面风格)

- 工具:`dev/restyle/restyle.py`(重绘切图)、`dev/restyle/prefab_sprites.py`(列出一个 prefab 用到的全部切图)、`dev/restyle/swap_in_place.py`(把新切图原路径换进主工程:默认只演练,`--apply` 才写,旧图备份到 `backups/<时间>-restyle/`,`--undo` 还原)。做法和踩坑见 `docs/经验与决定.md` 的「AI 重绘」。
- 这一步由 Claude 按这台电脑的配置来搭,工作台本身不带模型。需要的东西:
  1. **ComfyUI 0.37 或更新**(要有 Qwen Image 2.1 的节点 `TextEncodeQwenImage21`、`QwenImage21Cache`):Windows 便携版在 https://github.com/comfyanonymous/ComfyUI/releases(选 NVIDIA 版),解压到工作台文件夹以外的地方。端口用 8188,保持默认只听本机(**不要**加 `--listen 0.0.0.0` 开到局域网)。
  2. **三类模型**,官方来源 https://huggingface.co/Comfy-Org/Qwen-Image-2.1 ,国内网络用 https://modelscope.cn/models/Comfy-Org/Qwen-Image-2.1 (同名仓库,文件一样):主模型放 `ComfyUI/models/diffusion_models/`(`qwen_image_2.1_bf16` 或 `qwen_image_2.1_int8_convrot`)、文本编码放 `text_encoders/`(`qwen3vl_8b_bf16` 或 `qwen3vl_8b_int8_convrot`)、VAE 放 `vae/`(`qwen_image_2.1_vae_bf16`)。原作者用的是 int8 主模型 + int8 文本编码(约 16 GB)。
- **先查配置再选**:`nvidia-smi`(显卡、显存、驱动版本)、内存、磁盘剩余空间(留 25 GB 以上)。

  | 显存 | 建议 |
  |---|---|
  | 24 GB 以上 | int8(原作者配置,RTX 4090 每张 20~30 秒)或 bf16 |
  | 12~16 GB | int8;`models.local.json` 里 `cache_device` 设 `cpu` |
  | 6~8 GB(如 RTX 2060) | 先试 int8:ComfyUI 加 `--lowvram` 启动,`models.local.json` 写 `{"cache_device": "cpu", "cache_dtype": "int8", "res": 768}`。太慢或爆显存,再找更小的量化版本(比如 GGUF:要装 ComfyUI-GGUF 自定义节点,`unet_loader` / `clip_loader` 改成 `UnetLoaderGGUF` / `CLIPLoaderGGUF`;原作者电脑上没测过这种组合,装好先跑自检) |

  - 内存最好 32 GB 以上:显存不够时模型放在内存里来回搬。
  - 驱动下限由 ComfyUI 便携版里 PyTorch 的 CUDA 版本决定(CUDA 13 要 580 以上,CUDA 12 要 528 以上);驱动旧就先升级,或者换 CUDA 版本低一点的便携版。自检会对照着检查。
  - 20 系显卡(如 2060)不原生支持 bf16,ComfyUI 会自动转换,能用但慢一些。
  - 下载的东西只从上面的官方地址或可信的作者那里拿。
- **装好后**:把实际用的文件名、加载节点、缓存设置写进 `dev/restyle/models.local.json`(格式同 `dev/restyle/models.json`,只写要改的项,不进仓库)→ 启动 ComfyUI → 双击「安装与自检.bat」选 Y 试跑一张,把用时和对比图给用户看。`restyle.py` 和自检都按这份配置来。
- Claude 守则:下载前先告诉用户文件名、来源和大小,用户同意再下(几个 GB 的文件)。原作者决定不跨电脑共享 AI,每台电脑用自己的 ComfyUI。实测跑不动的电脑就不做 AI 重绘,工作台其他功能(导入 Figma、配动效、试玩、覆盖到 Unity)都不需要显卡。

## 怎么操作这个系统

### 界面在哪

- 顶部第一行 **① 从 Figma 获取**:导入插件包 / 粘贴链接 + Token「拉取画板」/ 导入切图 PNG / 底图对照。
- 顶部第二行 **② 编辑**:模块名、适配窗口、「🔒 布局已锁定 / 🔓 可拖动布局」切换、↺ 还原 Figma 布局、↶ 撤销、✦ 一键配动效、▶ 试玩、清空画布、保存工程 / 载入工程;最右边 **③ 导出交付包** 和 **覆盖到 Unity**。
- 左侧:页面列表(🏠 主页 / 📄 页面 / 🗨 弹窗,「＋加页面」)+ 当前页的节点树;右侧:选中节点的属性面板。

### 常用任务怎么做

| 同事说 | 做法 |
|---|---|
| 把 Figma 画板导进来 | 先「保存工程」备份。粘贴总览画板链接 →「拉取画板」(或插件导出 `.budfig.json` →「导入插件包」)。会列出全部界面让她勾选:默认全选,说明页不勾,主页自动选名字带"总览/主页"的。点「导入 N 个界面」后一次导入成一个模块,每页配好动效和交互,连好跳转。模块里已有页面时默认「补充到当前模块」,只加新界面。前提:各界面是总览画板的直接子层,比例接近 2436×1125;插件不能展开 Section,要选中里面的界面。整板导入还没在真实画板上跑过,第一次用完核对一下页面数、弹窗识别和跳转 |
| 只补几个界面 | 同上,用补充模式;或左侧「＋加页面」(要求这个浏览器拉取过这张画板的目录、顶栏还是同一个画板链接、填了 Token,每次都耗额度;用插件的直接重新导入插件包选「补充」) |
| 设计稿改了,已有的页要更新 | 补充模式**不会更新**已有的同名页(标"已在模块中")。二选一:① 先切到那一页,用那个界面自己的链接「拉取画板」(或只导出那个界面的插件包)→ 选「替换当前正在编辑的页面」,这一页的跳转会自动补连(别的页不动),但这页手动改过的设置会丢;② 选「重新导入为新模块」全部重建,所有手动设置都会丢 |
| 做另一个模块 / 新的改版任务 | 左上角「＋ 新建任务」:填任务名(中文)和模块名(英文,和别的任务重名会提示),得到空白画布,再导入这个任务的素材。点左上角的任务名打开**任务首页**:所有任务的缩略图、模块名、最近导出 / 覆盖到 Unity 的目标,能切换、编辑信息、复制、存成文件、标记完成、删除(进回收站,可恢复)。每个任务各自记住素材、动效、Figma 链接和覆盖目标,互不影响。自动连跳转的规则是按充值福利写的(发型/鞋子/翅膀卡片、领取成功/确认兑换/规则弹窗),其他模块的跳转多半要在「点击后」手动配 |
| 重新配动效/交互 | 「✦ 一键配动效」:全部页面一起重配并重新连跳转,**会覆盖手动改过的交互设置**,Ctrl+Z 一步撤销(撤销记录只在内存里,刷新就没了) |
| 改某个按钮点了去哪 | 选中节点;不是按钮的先勾「可点击」→ 属性面板「点击后」选打开页面/打开弹窗/显示隐藏/数字遮罩 → 再选目标。注意:以后再「补充」界面或点「✦ 一键配动效」,被设成「仅触发事件」的卡片、领取、兑换、规则按钮可能又被自动连上跳转,做完记得复查 |
| 位置被拖乱了 | 「↺ 还原 Figma 布局」只恢复位置尺寸,动效交互保留。**目前只有主页存了原稿坐标**,其余 9 页是旧版本导入的:新电脑上要先粘贴画板链接 + Token「拉取画板」一次(读到目录后可以取消导入),再在各页点还原(每页用 1 次额度,之后就记住了) |
| 测一下效果 | 「▶ 试玩」:从主页开始点;要看程序会收到的回调,点试玩条上的「事件日志」展开(默认收起);Esc 退出 |
| 导出给主工程 | 确认模块名(英文、首字母大写)→「导出交付包」→ 浏览器下载 `模块名.unitypackage`,并弹出生成器自检报告。通过本地服务打开时还会**另存一份到文件夹里的 `exports/`**,弹窗里有路径:内置浏览器面板的下载去向没验证过,以 `exports/` 为准。报告是按生成规则写的"出厂自检",不是实测;真正的检查在 Unity 里做 |
| 直接替换主工程里的预制体(迭代更新) | 「覆盖到 Unity」:填 Unity 工程目录(含 Assets 的那层,只存在本机浏览器)→ 目标 prefab:**不知道旧资源在哪也没关系**,第一次打开会自动「按界面文字找」——用本模块所有页面的文字在主工程 UI prefab 里比对,列出最像的旧 prefab(标出它是哪个面板 / PanelId、对上了哪几句),点一个就填入并体检;也可以在框里输面板名、PanelId 或界面上的一句中文点「查找」。选 Loadable 壳会自动换成它的源 prefab→「体检」→「确认覆盖」。主工程已有的 .meta GUID、同名同层级节点的 ID 原样沿用,Loadable 壳 / 面板配置 / 外壳引用不断;被覆盖和删除的文件备份在 `backups/<时间>/`。目标是主工程里的面板(配置表按 PanelId 加载它)时,会同时生成面板外壳 `<模块>Panel`:面板能正常打开、主页返回键关闭面板;像「前往充值」这种点了就该关掉面板的按钮,在按钮属性「点击后」选「关闭整个面板」;其余「仅触发事件」的按钮(领取等)和服务端数据要程序在 `<模块>Panel.Logic.cs` 里接,接之前界面显示的是设计稿占位数据。目标是别的面板里的子视图(如充值界面的钻石页 GemPackView,根上挂着取数 / 下单的业务脚本)时,不带面板外壳,改为生成 `<模块>Controller`,逻辑写在 `<模块>Controller.Logic.cs`;没有这个文件时体检标红、不能覆盖。手写的 Logic 文件放一份在 `unity-reference/<模块名>/`:主工程里缺它时(第一次覆盖、或删过模块目录)会随覆盖一起写进去,已有的永远不动。目标会记在工程里,下次打开对话框自动体检。**本地服务要开着**(`python dev/studio_server.py`,8791);工作台直接双击打开(file://)或用 http://localhost:8791 打开都行,两种打开方式各存各的工程数据;覆盖完切回 Unity 窗口自动导入 |
| 有些图不换,继续用旧的(比如奖励图标) | 选中那张图 → 属性面板勾「沿用旧资源」(有同名的图会出现「同名 N 个也标上」,一次标完)→ 点「选旧资源…」输入旧图的名字(如 `Cumulative_Icon`),从主工程的缩略图里点一张;画布上会直接显示旧图,并有橙色虚线和「旧」角标。底部状态栏「沿用旧资源 N 个 ›」能看全部、点「定位」跳过去。覆盖到 Unity 时这些节点直接引用主工程的旧图、不写新切图,体检里会列出来;没指定旧图的按目标 prefab 里同位置节点原来的图自动沿用,找不到会提示(比如 207 已经覆盖过一次,原来的图已经被换掉,就得手动指定)。要本地服务开着 |
| 在 Unity 里实机截图验收(可选) | 跟 Claude 说「在 Unity 里渲染一遍看看」。它跑 `dev/unity_preview.py`:验收脚本临时带进 Unity 工程、跑完自动删,截图和报告在 `exports/unity_preview/`。**要先关掉 Unity 编辑器**(开着时工程被锁,工具会直接拒绝) |
| 接进 Unity | 现在优先用上面的「覆盖到 Unity」;手动导入 `.unitypackage` 的做法见下一节 |

### 存档

- 「保存工程」= 把当前任务下载成一个 `.budui.json`(含贴图);「载入工程」把工程文件加成一个新任务(当前任务是空白的就直接装进当前任务)。
- 同一个任务在两个窗口里打开时,后打开的那个会暂停自动保存(画布上方黄条),点「在这里继续编辑」才接手,避免互相覆盖。
- 要把浏览器里最新的工程直接写回文件夹(比如打包交接前),工作台必须是通过 `dev/studio_server.py` 打开的。在工作台页面里执行下面这行,会写到 `projects/<模块名>.budui.json`(同名文件会被覆盖,先和同事确认)。桌面版由 Claude 在面板里执行;命令行版请同事按 F12 打开控制台(Console)粘贴执行(Chrome/Edge 第一次往控制台粘贴时会拦住,要先照提示手动输入 `allow pasting` 回车)。

```js
proj.module = $("#moduleName").value; fetch("/api/save-project?name=" + encodeURIComponent(proj.module || "project"), {method: "POST", body: JSON.stringify(proj)}).then(r => r.json())
```

## 接入主工程(手动导入交付包的做法)

2026-10-09 起日常迭代走「覆盖到 Unity」(上表),207 累充面板就是这样换进去的。下面是手动导入 `.unitypackage` 的做法和早期记录,需要 Unity 程序参与。Claude 要改主工程代码,得在主工程目录里另开会话。

**先确认这几件事:**
- 主工程在哪台电脑、哪个路径;Unity 版本 2022.3.32f1。新克隆或新分支的主工程要先跑 `Tools/BudBoxCommon/Sync-BudBoxCommon.ps1`(`docs/UI预制体替换规范.md` §1.3),否则大量引用丢失。
- **试点在主工程里的改动都还没提交**(规范 §6,截至 2026-09-28 的记录;以原作者的说法为准):她拉下来的主工程里没有充值福利新视图、`UseNewView` 开关,很可能也没有「UI导入体检」菜单。**请原作者先提交**。本文件夹 `unity-reference/` 里只有「UI导入体检」工具能单独拷进去用;`CumulativeRechargePanel.cs` 是改过的整个旧面板,拷进去会覆盖主工程的同名面板,它和 `RechargeRewardsServerAdapter.cs` 都依赖不在文件夹里的试点视图脚本,编译会失败,只能对照着看。
- 业务上怎么接:替换旧面板 `CumulativeRechargePanel`(PanelId=207)里试点接好的视图,还是另开面板?这件事还没定,问原作者。

**导入和放置(按规范 §3):**
1. 先查主工程有没有同名类,再在 Unity 里双击 `模块名.unitypackage`(或 Assets → Import Package → Custom Package)导入。落点已按规范写在包里:脚本 → `Assets/Scripts/UI/UIPanels/<模块名>/`(GameUI 程序集;别挪出 `Assets/Scripts/UI/`,否则落进 Assembly-CSharp,真机热更失效);切图、prefab、README → `Assets/Arts/UI/UIPanel/<模块名>/`。meta / GUID 随包,prefab 里的引用导入即生效。要放到别的面板目录(如试点的 `RechargePanel/` 下),导入后在 Unity 里拖动整个目录即可,GUID 不变。
2. 面板同名图集放 Loadable 面板目录 → `Assets → Send To Loadable` 生成壳,放进已注册的 entry 目录(如 `Loadable/UI/RechargePanel/`)→ BasePanel 外壳 + `UseNewView` 回退开关。
3. 写 Adapter:生成的视图(`Bud.<模块名>.<模块名>View`)对外有 `onAction(事件标识)`、`onCloseRequested`、`onPageChanged(页面节点名)`、`ApplyServerState(IDictionary<string,string> 标识→文字)`、`OpenPage` / `OpenPopup` / `Back`、`SetReducedMotion(bool)`。`onPageChanged` 只在打开页面或返回上一页时抛出(弹窗不抛),名字格式 `Page_<序号>_<页名>`,例如 `Page_1_10 · 发型奖励详情 / 可领取`,序号就是 `OpenPage` 的参数,Adapter 靠它判断当前是哪一页。按钮标识表、动态文本标识表在交付包里的 `README.md`。`unity-reference/RechargeRewardsServerAdapter.cs` 绑的是试点手写视图的另一套接口(`onClaimRequested` 等),只能参考思路,要按新接口重写。
4. 选中 prefab 或文件夹,右键 `Assets/BUD工具/UI导入体检`。主工程里没有这个菜单的话,把 `unity-reference/UIImportHealthChecker.cs` 放到主工程 `Assets/Editor/AssetsChecker/UIImportChecker/`。建图集之前报"未进入图集"属正常。
5. 编译或导入报错:回来修生成模板(`genViewCs` / `genMotionCs` / `genClickFeedbackCs` / `genPrefab`),修之前先对照主工程里的同类真实资产(`CLAUDE.md`)。

**说明**:2026-10-09 起导出的 GUID 按落点路径、fileID 按节点层级路径生成,同一模块再导出不变,重新导入会原地更新;迭代替换主工程里已有的 prefab 用「覆盖到 Unity」,它还会沿用主工程里已有的 GUID 和节点 ID。

## Claude 操作守则(重要)

1. 回复用简体中文。使用者多是设计/产品同学,说按钮名和看得见的效果,少说代码术语。
2. **同事可能正在同一个页面里操作**:不要往她正在用的标签页发自动点击。同一个地址的所有标签页共用一份工程:在另一个标签页里点一下页面列表、切锁定、改页面类型都会自动保存,把那个标签页打开时的旧副本写回去,覆盖她的改动。所以同地址的其他标签页只能用脚本读数据,不能点界面。`window.__test_build()` 会替换当前工程,绝不在她的工作地址上跑。
3. 需要做交互或导入测试时,开**隔离环境**:
   - `preview_start` 启动 `budui-studio-test`(端口 8792,浏览器存储和 8791 各存各的)。要在里面用真实工程,不用系统选文件窗口,直接在测试页里执行:`fetch("/projects/RechargeRewardsOverview.budui.json").then(r => r.json()).then(p => { proj = p; ensurePages(); $("#moduleName").value = proj.module || ""; let mx = 0; walkAll(n => { mx = Math.max(mx, parseInt(String(n.id).slice(1), 10) || 0); }); uid = mx + 1; selId = null; renderAll(); fitStage(); })`。注意 8792 和 8791 共用同一个 `projects/` 和 `exports/` 文件夹:**测试页里不要执行"写回 projects/"那行**,测试导出后记得删掉 `exports/` 里的测试文件;
   - 或用内置浏览器打开 `BUD_UI_Studio.html` 得到的 data: 快照页:没有本地存储,可以放心测。改完 html 后快照页可能被自动重开,注入的模拟数据要重新注入;
   - Figma 接口在测试页里替换 `window.fetch` 来模拟,不消耗真实额度。
4. 内置浏览器会吞掉原生 `alert/confirm/prompt`:界面提示只用页面内对话框(`showMsg` / `askPick` / `askConfirm` / `toast`)。
5. 改完代码的自检:
   - 语法:把 `BUD_UI_Studio.html` 里的 `<script>` 抽出来跑 `node --check`;
   - **`node dev/offline_check.js`**:不开浏览器,拿 `projects/` 里的真实工程跑多页导出结构校验(Layer、fileID 引用、页面节点和 CanvasGroup、View 的 pages[] 接线、跳转按钮的 OpenPage/OpenPopup 序号、C# 括号、标识唯一、`.unitypackage` 结构和 GUID 引用闭合);加 `--reconfigure` 会先模拟点一次「✦ 一键配动效」,列出会被改掉的设置;加 `--out 文件.unitypackage` 会在校验通过后直接写出交付包(不开浏览器导出,用的是 `projects/` 里的工程文件,不是浏览器里的最新状态);
   - `window.__test_build()`:只造一个单页测试面板,快速看 prefab / View / Motion,不覆盖点击反馈和多页导航。只在隔离页里跑;
   - 切图规则:`node dev/plugin_selftest.js`(工作台和插件两份规则必须同步并一起升版本)。
6. 生成模板、字体 GUID、Layer=UI 这些"构造保证"不要改,细则见 `CLAUDE.md`;更多踩过的坑见 `HANDOFF.md`(内置浏览器相关的几条只适用于桌面版)。
7. 这台电脑上没有原作者的 Claude 记忆:原作者的产品决定、覆盖主工程踩过的坑、AI 重绘的经验在 `docs/经验与决定.md`,动手前读一遍。
8. `CLAUDE.md` 里的在线「提交规范」链接是原作者的私有文档,很可能打不开:主工程接入以 `docs/UI预制体替换规范.md` 为准,生成器的实际行为以代码为准。`docs/` 里 `Assets/...` 开头的相对链接只在主工程仓库里能点开。

## 文件地图

| 路径 | 是什么 |
|---|---|
| `BUD_UI_Studio.html` | 软件本体(单文件 HTML + JS,零依赖) |
| `projects/` | 工程文件(含贴图,**不在仓库里**,向原作者要):`Sign.budui.json` = 最新的充值福利(11 页,已覆盖进 207);`GemPack.budui.json` = 钻石页 |
| `安装与自检.bat`、`dev/setup_check.py` | 新电脑环境自检(选 Y 会试跑一张 AI 重绘) |
| `dev/restyle/` | AI 重绘工具(见「7. AI 重绘」);`templates/` 是统一风格的参考图 |
| `docs/经验与决定.md` | 原作者的产品决定和踩坑记录(从原作者的 Claude 记忆整理) |
| `dev/restyle/models.json`、`models_config.py` | AI 重绘用哪几个模型、加载节点、缓存设置、默认分辨率(原作者电脑的配置);每台电脑自己的改动写在 `dev/restyle/models.local.json`(不进仓库) |
| `.gitignore` | 不进仓库的:工程文件、备份、导出物、本机口令、本机模型配置 |
| `figma-plugin/` | Figma 导出插件(`manifest.json` / `code.js` / `ui.html`)和安装说明 |
| `dev/studio_server.py` | 本地服务:托管工作台 + `POST /api/save-project` 写回工程 + `POST /api/save-export` 把交付包另存到 `exports/` |
| `exports/` | 导出时自动生成:交付包 `.unitypackage` 的另存副本(打包交接时不需要带) |
| `dev/offline_check.js` | 离线体检:在 Node 里跑页面脚本,校验真实工程的导出结构 |
| `dev/plugin_selftest.js` | 插件回归测试(在 Node 里模拟 Figma 环境) |
| `docs/UI预制体替换规范.md` | 主工程侧规范:资源结构、替换规程、接入对齐总清单(§3)、试点记录(§6) |
| `unity-reference/` | 主工程接入参考代码:`Sign/SignPanel.Logic.cs`(207 的业务逻辑)、`GemPack/`(钻石页逻辑草稿)、试点版外壳面板 / Adapter、UI 导入体检工具。覆盖到 Unity 时主工程缺 Logic 文件会从这里带进去 |
| `dev/unity_preview.py`、`dev/unity/` | Unity 截图验收工具(脚本临时带进 Unity 工程,跑完删掉) |
| `backups/` | 「覆盖到 Unity」前自动备份的主工程旧文件(本机生成,不随包分发) |
| `.claude/launch.json` | Claude Code 预览配置:`budui-studio`(8791,日常用)、`budui-studio-test`(8792,测试用)、`budui-studio-lan`(8790,局域网共享)、`budui-studio-lan-test`(8793,测局域网共享用) |
| `启动局域网共享.bat` | 双击开局域网共享(8790),窗口里打印发给同事的链接 |
| `创建桌面快捷方式.bat`、`dev/app_launch.*`、`dev/make_shortcut.ps1`、`dev/app.ico` | 桌面应用:快捷方式 → `app_launch.vbs`(无窗口)→ `app_launch.ps1`(后台起 8791 服务 + Edge `--app` 打开 file:// 工作台) |
| `README.md` | 使用说明(给人看的完整功能介绍) |

## 常见问题

| 现象 | 原因和处理 |
|---|---|
| 打开工作台是空画布 | 先点左上角任务名看任务首页,工程可能在另一个任务里;都没有就是这个浏览器 + 地址里还没有工程 →「载入工程」,或者她在另一处(另一个浏览器/地址)载入过 |
| 覆盖更新后「覆盖到 Unity」报错或说服务是旧版 | 本地服务还是旧代码在跑 → 关掉服务窗口重新启动,再刷新页面 |
| 拉取画板报 403 | Token 权限选错(要 File content 只读),或她的 Figma 账号打不开这个文件 |
| 拉取画板报 429 | 接口额度用完 → 改用插件(先和原作者商量),或请有「完整/开发」席位的同事生成 Token |
| 「还原 Figma 布局」提示"没有记录来源界面" | 该页是旧版本导入的,没存原稿坐标 → 先「拉取画板」读一次目录再还原(见上表) |
| 预览里的字和 Unity 里粗细不一样 | 本机没装思源黑体,预览用了代替字体;导出不受影响 |
| 双击 html 打开后没法写回 `projects/` | 写回只有 `studio_server.py` 支持 → 用「保存工程」下载,或改用本地服务打开 |
| 导进 Unity 后界面不显示或点不动 | 先跑 `UI导入体检`,再按规范 §3 的排查口诀:Layer → 根节点 scale/active → CanvasGroup alpha → Canvas 排序 → 面板框架状态 |
