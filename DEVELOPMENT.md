# 树莓娘文本输入模块 · 开发者文档

本文面向**开发本模块的人**：与 waycast 的协议关系、代码组织与开发/测试命令。
安装、配置与运行请看用户文档 [README.md](README.md)；术语见 [GLOSSARY.md](GLOSSARY.md)。

## 与 waycast 的关系

- 帧格式、capability 结构、连接令牌来自 waycast wire 协议（waycast/src/waycast/wire.py）；本仓库在 `src/loom/wire.py` 本地实现该客户端侧契约（纯 JSON over WebSocket，无包依赖），不修改协议本身，互操作以 waycast 的实现为权威。
- capability 的 input description 会进入核心 Agent 的系统提示词（waycast capability catalog），是这条通道对 Agent 的语义说明书。

## 开发

```sh
uv run --locked pytest -q        # 测试（本地起假 hub，离线可跑）
uv run --locked ruff check .
uv run --locked basedpyright
```

测试覆盖 capability 握手、派发帧内容、断线重连与配置校验（本地假 hub，离线可跑）。
