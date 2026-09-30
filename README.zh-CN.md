# Prompt-to-Scene

**用指令让 AI 在 Blender 建模，放进 Unity 或 UE，再继续修改同一个资产。**

[English](README.md) · [UE 使用说明](docs/unreal.md) · [资产约定](docs/asset-contract.md) · [验证记录](docs/verification.md)

这是一个开源 MCP 服务，配有 Unity 和 Unreal 编辑器插件。你的 AI 客户端负责理解自然语言并编写 Blender Python；本项目负责执行、转换、导入、摆放和回读导入结果。

> v0.2 实验版本：静态不透明道具；支持 Unity Built-in／URP 和 Unreal Editor。项目不自带大模型或文生 3D 模型。具体测试版本见验证记录。

![内置木箱示例在 Unity 中的实际渲染，两种材质配色](docs/images/unity-preview.png)

*内置 Blender 脚本生成的模型，在 Unity 中摆放两种配色后实际渲染。*

## 使用体验

> “做一个一米高的木箱，带金属包边，导入当前配置的引擎项目，加上碰撞。”
>
> “把木头颜色调深，箱子加高 25%，更新刚才那个箱子。”

同一个资产 ID 对应同一个 Unity Prefab 或 UE Static Mesh。已有场景实例的位置保留；UE 的 Actor 身份、标签和名称也保留。AI 必须读取与本次请求 ID 匹配的 `imported` 回执，才能确认成功。`queued` 表示仍在等待编辑器。

## 安装

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/) 和 Blender 4.2。再准备 Unity 2022.3 或 UE 5.7 编辑器。

```bash
git clone https://github.com/316sandon12/prompt-to-scene.git
cd prompt-to-scene
uv sync --locked
```

**Unity：** Package Manager → Add package from disk，选择 `unity/Packages/com.prompttoscene.bridge/package.json`。打开场景，退出 Play Mode，等待编译结束。

**UE：** 把 `unreal/PromptToScene` 文件夹复制到项目的 `Plugins/PromptToScene`，在 Edit → Plugins 中启用 Prompt-to-Scene，然后重启编辑器。插件声明了 Python Editor Script Plugin 和 Editor Scripting Utilities 依赖，无需编译 C++。打开关卡，退出 Play In Editor。此工作流需要启用图形的完整编辑器。

也可以从 [v0.2.0 发布页](https://github.com/316sandon12/prompt-to-scene/releases/tag/v0.2.0)下载 UE 插件 ZIP，把其中的 `PromptToScene` 文件夹解压到项目的 `Plugins` 目录。

按[英文 README 的 MCP 配置](README.md#3-register-the-mcp-server)注册服务，填写：

| 环境变量 | Unity | Unreal |
| --- | --- | --- |
| `PTS_PROJECT` | Unity 项目文件夹的绝对路径 | `.uproject` 文件的绝对路径 |
| `PTS_ENGINE` | `unity` | `unreal` |
| `PTS_BLENDER` | Blender 可执行文件路径 | Blender 可执行文件路径 |

省略 `PTS_ENGINE` 可自动识别。原来的 `PTS_UNITY_PROJECT` 配置仍可使用。想让 AI 同时操作两个引擎，可以注册两个不同名称的 MCP 服务，分别配置目标项目。

## 先验证工具链

保持目标编辑器打开，可以不用 AI 先运行示例：

```bash
# Unity：Y 轴向上，位置单位米
uv run prompt-to-scene --project "/你的/Unity项目" build crate --script examples/crate.py --position 2 0 3 --wait 30

# UE：Z 轴向上，工具接收米，插件自动换算为厘米
uv run prompt-to-scene --project "/你的/UE项目/MyProject.uproject" build crate --script examples/crate.py --position 2 3 0 --wait 30
```

Unity 结果在 `Assets/PromptToScene/crate/`；UE 结果在 `/Game/PromptToScene/crate/`，并自动放入当前关卡。场景或关卡仍需正常保存。`--wait 30` 最多等待 30 秒，超时不会取消导入；JSON 返回真实状态。命令退出码 2 表示引擎错误、请求已被替代或等待超时。

`examples/textured_cube.py` 可以验证基础色贴图和法线贴图，自行生成纹理，无需下载资产。建议在目标项目 `.gitignore` 中加入 `.prompt-to-scene/`，排除本地队列、日志和源文件历史。

## AI 可以调用的工具

| 工具 | 功能 |
| --- | --- |
| `inspect_target` | 读取引擎、坐标约定、Blender 路径、编辑器心跳及任务 |
| `build_asset` | 执行完整建模脚本，保存源文件并提交导入任务 |
| `publish_blend` | 导入已保存 `.blend` 中的 `Export` 集合 |
| `get_asset_status` | 按请求 ID 查询或等待最多 30 秒，返回引擎实际结果 |

`build_asset` 每次运行独立的后台 Blender 进程。用其他 Blender MCP 建模后，可以先保存文件，再调用 `publish_blend` 衔接。

## v0.2 的改进

- 新增 UE 编辑器插件：Static Mesh、原生 PBR 材质、碰撞和 Actor 摆放。
- UE 自动处理米／厘米，以及 Blender／UE 法线贴图方向差异。
- FBX 材质槽使用稳定标识，保留中文、空格等原始材质名称的对应关系。
- 导入结果支持等待、心跳新鲜度检测和旧请求识别，后台 Blender 执行不会阻塞 MCP 的其他查询。
- 同时保留 Unity 的资产路径、Prefab GUID 和更新行为。

从 v0.1 升级时，请同时更新服务端和 Unity 插件。新版发布 schema 2 请求，旧插件会拒绝；新版 Unity 插件仍能处理已排队的 schema 1 请求。

## 当前范围

支持静态网格、Principled BSDF 不透明材质、基础色／金属度／粗糙度常量，以及直接连接的基础色和切线空间法线贴图。必须有 `Export` 集合，修改器需提前应用。

程序化贴图烘焙、金属度／粗糙度贴图、透明材质、骨骼动画和 UE Blueprint 生成功能尚未实现。渲染器的灯光与色彩管理不同，导入正确不意味着画面逐像素一致。

Unity 更新受管理的 `Visual` 子节点、根节点 BoxCollider 和材质属性；自定义脚本放在 Prefab 根节点。UE 会合并导出网格，更新同一路径下的 Static Mesh、碰撞和生成材质图，并保留已有 Actor。不要手工修改工具生成的几何和材质图。

Blender Python 以本地用户权限执行，不提供脚本沙箱。工具本身不会上传项目或模型；AI 客户端的数据处理由其自身设置决定。中途导入失败没有完整事务回滚，请正常使用版本控制。

## 开发与开源

采用 MIT 许可证，欢迎提交可复现的模型和导入问题。引擎和第三方工具遵循各自许可证。参见 [CONTRIBUTING.md](CONTRIBUTING.md)。
