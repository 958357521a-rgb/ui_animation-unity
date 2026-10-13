# 示例资源

让刚拉下仓库的人能马上看懂流程,不至于面对一片空白。素材来自主工程(公开仓库里请勿再扩散)。

| 路径 | 是什么 | 怎么用 |
|---|---|---|
| `pipeline/avatar_frame_9036/` | 资源批处理示例:主工程头像框 36 号的底框、预览图和 8 个上层部件,`layout.json` 写了每张切图的位置(相对 256×256 画框左上角)、示例动效;`ai_examples/` 是 3 张 AI 重绘示例新图(含 `_compare.png` 新旧对比) | `python dev/pipeline_demo.py --job` 建好示例任务;或不加 `--job`,当成 Figma 插件发来的一批放进中转箱,在页面上「从 Figma 收件」 |
| `pipeline/avatar_frame_9036/示例输出/` | 示例任务生成的交付包和 README(编号 9036,不会和主工程已有的重名) | 直接导入空白 Unity 工程看结构:底框 / 预览进头像框图集文件夹,上层特效 = 源 prefab + Loadable 壳 + Animator 动画 |
| `workbench/GemPack.budui.json` | 工作台示例工程:钻石充值页(1 页,已覆盖进主工程 GemPackView) | 工作台「载入工程」选它,看导入后的图层、交互、动效 |

使用说明:`docs/资源批处理_使用说明.md`;暂定规范(待审核):`docs/资源批处理_暂定规范.md`。
