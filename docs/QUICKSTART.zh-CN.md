# 从下载到第一个模型

这份教程使用 v0.4 安装程序。你不需要理解 MCP、Python 环境或 FBX 导出参数。

## 先准备这些软件

- Blender：当前实际验证版本为 4.2.0；[下载 Blender 4.2 LTS](https://www.blender.org/download/lts/4-2/)。
- Unity 2022.3 的 Built-in/URP 项目，或 UE 5.7 项目。项目必须已创建，Unity 编辑器须已激活。
- Codex 或 DeepSeek Harness：先确认它能正常回答你的问题。Harness 使用已安装的 `dsh` 和现有 profile，例如 `web`；本插件不是 DeepSeek 网页聊天的扩展。

Blender 不用一直打开；程序会在后台启动它。你的引擎项目和生成数据不会被本桥接程序上传；AI 客户端自身的数据使用规则由该客户端决定。

## 1. 下载并打开

打开 [Releases](https://github.com/316sandon12/prompt-to-scene/releases/latest)，下载对应 ZIP，先完整解压。

| 系统 | 文件与打开方式 |
| --- | --- |
| Windows x64 | `Prompt-to-Scene-windows-x64.zip`；双击 `Prompt-to-Scene.exe`，旁边的 `prompt-to-scene-core.exe` 要保留 |
| Mac M 系列芯片 | `Prompt-to-Scene-macos-arm64.zip`；打开 `Prompt-to-Scene.app` |
| 其他平台 | 暂用源码方式：`uv sync --locked`，然后 `uv run prompt-to-scene-app` |

程序在浏览器打开一个只监听本机的设置页。Mac 版本未公证；若系统拦截，在确认下载来自此仓库后使用“系统设置 → 隐私与安全 → 仍要打开”。Windows 未签名构建也可能显示系统提示。不要关闭系统安全保护来安装它。

## 2. 连接游戏项目

在第一栏选择已有项目，或者点 **浏览项目**。Unity 选择含 `Assets`、`ProjectSettings` 的项目根文件夹；UE 选择含 `.uproject` 的根文件夹，也可以粘贴 `.uproject` 路径。发现多个 `.uproject` 时请指定具体文件。

点击 **连接并准备项目**。它会：

- 记住这个项目，并检测 Blender；未找到时，在高级设置中选择 Blender 应用或 `blender.exe`。
- 安装 Unity 包，或安装 UE 插件并启用所需的 Python/Editor Scripting 依赖。
- 更新前备份旧桥接目录；为 UE 项目描述文件保留备份。
- 将 `.prompt-to-scene/` 加入项目的 `.gitignore`，避免把任务、日志和模型历史意外提交。

Unity 等待编译完成；UE 重启一次并打开一个关卡。退出 Play/PIE 模式。页面显示“编辑器已连接”后即可继续。

## 3. 选择 AI 客户端

**Codex：**点击 **安装 Codex 插件**。程序使用 Codex 自带的插件命令注册本地插件和配套建模 skill，然后重启 Codex、开始一个新对话。

**DeepSeek Harness：**选择你实际使用的 profile，例如 `web` 或 `desktop`，点击 **安装 Harness 插件**。重启该 profile。程序安装原生 Harness bundle，通过官方 MCP client 连接同一套工具。不同 profile 相互独立；给正在使用的那个安装即可。

未检测到客户端时，在“手动选择客户端程序”里选择 `codex`/`codex.exe` 或 `dsh`。Harness 的 Node/pnpm 环境仍由 Harness 自己的安装提供。只有远程浏览器服务、没有本机 Harness 运行环境时，无法直接访问本机游戏编辑器。

无需在 Prompt-to-Scene 重新填写模型 API Key。插件安装不会改变客户端的审批或沙箱配置；如果宿主限制了本地文件或进程访问，按该宿主正常提示授权即可。

## 4. 生成第一个模型

先点击设置页的 **生成示例木箱**。这一步不用 AI，也能运行 Blender → 引擎导入的整条链路。任务会经过“正在建模 → 等待引擎导入 → 已导入”。只有最后一个状态才代表成功。

模型会出现在当前场景相机附近，优先落在有碰撞的场景表面上；无表面时使用零高度地面。可以点预览，或者到引擎里查看选中的物体。

然后在 AI 客户端新对话中输入：

> 用 Prompt-to-Scene 做一张 1.5 米宽、0.8 米深的木桌，放进当前项目。完成后给我看实际预览。

资产路径是 Unity 的 `Assets/PromptToScene/` 或 UE 的 `/Game/PromptToScene/`。你需要像平常一样保存场景/关卡。

## 创作工作台

连接好项目后，可以在工作台保存美术风格、选择九种道具、比较三个造型、修改部件或按场景摆放。先试“先比较三种造型”，选好后制作成品；草稿不会进入引擎。

新功能的具体按钮和提示词见 [六项创作功能教程](AUTHORING.zh-CN.md)。内置道具自动准备 UV 和烘焙贴图，不用手动导出材质。

## 5. 用对话继续修改

先在引擎中选中刚生成的物体，再说：

> 只把我选中的这个物体缩小 20%，其他实例保持原样。

> 只把它的 Wood 材质改成绿色。

> 撤销刚才的颜色修改。

修改位置、旋转、缩放和颜色会直接操作实例。要求改变这款模型的结构，例如“桌子加高 10 厘米，其他不变”，则会保留已有配方参数并更新共享资产。不同实例的现有变换保留。

> 恢复这款模型的上一版。

模型版本恢复使用之前成功导入的 `.blend`，重新导入同一资产；实例编辑撤销使用保存的编辑快照。这两种操作不同，AI 会根据上下文选择。删除了本地历史或对象后，不能保证恢复；这不替代 Git。

## 切换客户端、项目或更新

Codex 与 Harness 共用本机 `~/.prompt-to-scene`（Windows 为用户目录下的 `.prompt-to-scene`），不需要复制聊天记录。模型参数与历史保存在项目目录里。

切换项目时重新打开安装程序、连接目标项目。它不会仅因另一个引擎窗口获得焦点而更换目标。更新时下载新版，重新连接项目并点客户端安装按钮；按提示重启。旧桥接备份位于项目的 `.prompt-to-scene/bridge-backups/`。

从手动配置的旧版升级：停用旧的 Prompt-to-Scene MCP 注册，避免新旧服务器同时出现。环境变量 `PTS_PROJECT`、`PTS_UNITY_PROJECT` 会覆盖设置页连接；保留它们只适合需要固定目标的高级用法。

## 常见状态

| 现象 | 应该做什么 |
| --- | --- |
| 找不到 Blender | 在高级设置中选择程序文件；Mac 可选择 Blender.app |
| 一直等待导入 | 打开连接的那个项目，退出 Play，等待编译；UE 首次安装后重启 |
| 客户端里没有工具 | 确认安装到正在使用的 Harness profile；重启客户端并开始新对话 |
| AI 等待超时 | 任务仍保留；继续查看原任务，不要重复生成 |
| 没有选中的受管理物体 | 在引擎选中由此工具生成的根对象或其子网格 |
| 材质不受支持 | 改成基础 Principled BSDF/支持的贴图连接；不会静默做有损转换 |
| 预览失败 | 打开真实可渲染的编辑器视口，重试预览；模型可能已导入成功 |
| 点击取消后仍导入了 | 正在执行的原生导入不能强制中断；以该任务最终回执为准 |

编辑器离线时，排队任务的取消会在编辑器下次处理队列时确认。自动修复仅针对可处理的脚本/材质错误，最多两次；不会为一个离线编辑器反复重建。

更详细的边界、复现命令与已验证版本见 [验证记录](verification.md)、[资产约定](asset-contract.md) 和 [架构](architecture.md)。
