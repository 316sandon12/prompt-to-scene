# Prompt-to-Scene

**用指令让 AI 在 Blender 建模，放进 Unity，再继续修改同一个资产。**

[English](README.md) · [资产约定](docs/asset-contract.md) · [验证记录](docs/verification.md)

这是一个开源 MCP 服务与 Unity 插件。你的 AI 客户端负责理解自然语言并编写 Blender Python；本项目负责执行、转换、导入、摆放和回读导入结果。

> v0.1 实验版本：支持静态不透明道具、Unity Built-in 和 URP。UE 尚未实现。项目不自带大模型，也不自带文生 3D 模型。

![内置木箱示例在 Unity 中的实际渲染，两种材质配色](docs/images/unity-preview.png)

*内置 Blender 脚本生成的模型，在 Unity 中摆放两种配色后实际渲染。参见[验证记录](docs/verification.md)。*

## 使用体验

> “做一个一米高的木箱，带金属包边，放进 Unity 的 [2, 0, 3]，加上碰撞。”
>
> “把木头颜色调深，包边改薄，更新刚才那个箱子。”

同一个资产 ID 对应同一个 Prefab。Unity 中已有实例的位置和 Prefab 根节点组件保留。AI 必须读取与本次请求 ID 匹配的 `imported` 回执，才能确认成功；`queued` 只表示已导出并等待引擎处理。

## 安装

1. 安装 Python 3.11+、uv、Blender 4.2+，准备已激活的 Unity 2022.3+。
2. 克隆仓库，运行 `uv sync --locked`。
3. Unity 的 Package Manager → Add package from disk，选择 `unity/Packages/com.prompttoscene.bridge/package.json`。
4. 打开目标场景，退出 Play Mode，等待编译完成。
5. 按 [英文 README 的 MCP 配置](README.md#3-register-the-mcp-server)填写服务器路径、Unity 项目路径和 Blender 可执行文件路径。

第一次可以不用 AI，直接验证工具链：

```bash
uv run prompt-to-scene --project /你的/Unity项目 build crate --script examples/crate.py --position 2 0 3
uv run prompt-to-scene --project /你的/Unity项目 status crate
```

导入结果位于 `Assets/PromptToScene/crate/`。插件会把场景标记为已修改，仍需正常保存场景。建议在 Unity 项目的 `.gitignore` 中加入 `.prompt-to-scene/`，排除本地任务、日志和源文件历史。

还可以用 `examples/textured_cube.py` 验证基础色贴图和法线贴图；它会自行生成示例纹理，无需下载外部资产。

## AI 可以调用的工具

| 工具 | 功能 |
| --- | --- |
| `inspect_target` | 读取目标项目、Blender 路径及 Unity 最近的心跳信息 |
| `build_asset` | 执行 AI 编写的完整建模脚本，保存源文件并提交导入任务 |
| `publish_blend` | 导入已保存的 `.blend` 中名为 `Export` 的集合 |
| `get_asset_status` | 读取 Unity 实际返回的资产路径、GUID、尺寸、网格数量和错误 |

`build_asset` 每次运行一个独立的后台 Blender 进程。它不会直接控制已经打开的 Blender 窗口。如果用其他 Blender MCP 建模，先保存文件，再调用 `publish_blend` 即可衔接。

## 首版范围

支持静态网格、Principled BSDF 不透明材质、基础色/金属度/粗糙度常量，以及直接连接的基础色贴图和切线空间法线贴图。必须有 `Export` 集合，修改器需提前应用。

不支持的节点会明确报错。程序化贴图烘焙、金属度/粗糙度贴图、透明材质、骨骼动画和 UE 将在后续版本处理。不要把“导入成功”等同于三个渲染器中的画面完全一致。

重新生成会更新受工具管理的 `Visual` 子节点、根节点 BoxCollider 和材质属性。自定义脚本放在 Prefab 根节点。已有场景实例的变换不会被新请求中的初始位置覆盖。

Blender Python 以本地用户权限执行，不提供脚本沙箱。源文件保存在目标项目的 `.prompt-to-scene/work/`。工具本身不会上传项目或模型；AI 客户端的数据处理由它自己的设置决定。

## 开发与开源

采用 MIT 许可证。欢迎提交可复现的模型、导入问题和引擎适配改进。请查看 [CONTRIBUTING.md](CONTRIBUTING.md)。
