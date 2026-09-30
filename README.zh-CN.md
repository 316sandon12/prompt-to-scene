# Prompt-to-Scene

**用一句话让 AI 在 Blender 生成模型，直接出现在 Unity 或 UE，再继续用对话修改。**

[English](README.md) · [下载最新版本](https://github.com/316sandon12/prompt-to-scene/releases/latest) · [新手完整教程](docs/QUICKSTART.zh-CN.md) · [实际测试记录](docs/verification.md)

现在支持 **Codex 和 DeepSeek Harness 插件**。两个客户端使用同一套项目连接、模型参数与版本记录。安装程序自带 Python，自动安装引擎桥接组件；无需手改 MCP 配置，也无需另买建模 API。

> v0.3 为实验版，面向静态、不透明道具。你仍需先安装 Blender、Unity 或 UE，以及能正常对话的 AI 客户端。自然语言理解由客户端现有模型提供。

## 最简单的开始方式

[**下载 Windows 版**](https://github.com/316sandon12/prompt-to-scene/releases/latest/download/Prompt-to-Scene-windows-x64.zip) · [**下载 Mac Apple Silicon 版**](https://github.com/316sandon12/prompt-to-scene/releases/latest/download/Prompt-to-Scene-macos-arm64.zip)

1. 解压并打开 **Prompt-to-Scene**。
2. 选择游戏项目，点击 **连接并准备项目**。
3. 点击 **安装 Codex 插件** 或 **安装 Harness 插件**，重启对应客户端，开始新对话。

保持引擎打开，退出 Play 模式。UE 首次安装桥接插件后需要重启一次。然后直接说：

> 用 Prompt-to-Scene 做一个带金属包边的木箱，放进当前项目。

也可以先点击安装页面的 **生成示例木箱**，不用 AI 就能验证整个流程。

下载包的系统首次打开提示、Blender 检测和客户端安装问题，都在 [新手教程](docs/QUICKSTART.zh-CN.md) 中说明。Mac 社区构建采用临时签名、未做 Apple 公证；Windows 社区构建未签名，首次运行可能需要系统确认。

![Unity 实际生成的预览](docs/images/workflow-unity.png)

*真实 Unity 测试返回的图片：两个箱子经历了单实例编辑、模型更新、版本恢复和预览。不是生成式效果图。*

## 接下来可以这样说

- “做一张 1.5 米宽的桌子，放在场景相机附近。”
- “把我选中的这个物体缩小 20%，沿 X 轴移动一米。”
- “只把这个箱子的木头变绿，其他箱子保持原样。”
- “撤销刚才的颜色修改。”
- “把这款桌子加高，其他设计保持原样。”
- “恢复这个模型的上一版，给我看引擎里的预览。”

木箱、桌子、椅子、路牌有可持续修改的参数配方；其他静态模型由 AI 编写 Blender Python。位置、旋转、缩放和单实例染色直接在引擎执行，无需重新建模。

## 已经做好的简化

| 以前需要做的事 | 现在的方式 |
| --- | --- |
| 手动复制 Unity/UE 插件、修改配置 | 选择项目后自动安装，更新前保留旧版备份 |
| 安装 Python、uv、编辑 MCP JSON | 下载程序后点击安装客户端插件 |
| 每个 AI 客户端重新配置项目 | 共用项目连接与模型历史 |
| 每次填写模型坐标 | 默认放到场景相机附近的碰撞表面，无表面时使用地面平面 |
| 等一个长调用、分不清是否导入成功 | 后台任务、准确请求编号和引擎回执 |
| “这个物体”靠 AI 猜 | 读取引擎实际选中对象 |
| 想改颜色却重新生成整个模型 | 原生实例编辑，支持撤销 |
| 修改后无法找回原版 | 保留成功版本的 `.blend`，支持恢复 |
| 只能看文字结果 | 返回真实引擎 PNG 预览 |

模型重建保留资产身份、现有实例的位置/旋转/缩放和本工具的染色覆盖。Unity 的自定义脚本适合放在 prefab 根对象；UE 保留 Actor 标签和名称。场景仍由你正常保存。

## 支持范围与验证

支持静态网格、基础 PBR 参数、直接连接的底色贴图和切线法线贴图；Unity 支持 Built-in/URP，UE 使用原生 Static Mesh、材质与 Actor。可以接收其他 Blender AI 工具生成的、符合 [资产约定](docs/asset-contract.md) 的 `.blend`。

暂不支持自动烘焙、透明材质、骨骼动画、HDRP 或任意节点材质无损转换。不同引擎的灯光和色彩管理可能导致画面差异。版本恢复与编辑撤销不等于整个项目的事务回滚。

已用真实 Blender 4.2、Unity 2022.3（Built-in/URP）、UE 5.7.2 验证；Codex 和 Harness 都完成了真实宿主工具调用。Windows 打包检查和 Windows 引擎实测是两回事，详见 [验证矩阵](docs/verification.md)。

贡献者可运行 `uv sync --locked`，然后 `uv run prompt-to-scene-app`。其他 MCP 客户端及命令行用法见 [手动配置](docs/manual-setup.md)。项目采用 MIT 协议。
