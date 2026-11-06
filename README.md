# 树莓娘文本输入模块

本仓库是树莓娘（Raspberry Girl）体系中的**文本输入模块**：把操作者在控制台敲入的每一行文本作为一个 waycast 输入帧发送给核心。核心是 [waycast](../waycast/README.md)；本模块是它的一个输入模块（capability.kind = "input"），完全按 waycast 的 wire 契约（ADR-0008）工作，不包含任何核心逻辑。模块与核心是独立的微服务：两者之间只通过网络（WebSocket + wire JSON 帧）通信，本仓库不依赖 waycast 的任何 Python 包。

它是树莓娘各输入通道（语音、弹幕、IM……）之外最简单的一个：**人在键盘前 = 一条输入通道**。定位为管理端的初级形态——操作者用它直接向树莓娘下指令、纠正话题、要求停下当前讲话；未来管理端能力（结构化指令、多会话等）在本仓库上生长，不进核心。

## 职责边界

- **控制台输入**：从 stdin 逐行读取，一行就是一条控制台输入，即一条 UnifiedInput（`content` = 行文本，`source`/`module` = `text_input`），不做合并、不做 partial/final 标记。
- **发送输入帧**：连接 hub `/ws/modules`，首帧 capability 广告（input-only），随后经同一条连接发送 input 帧。
- 模块**不参与话权与打断判断**（ADR-0011）：任何抵达 hub 的 input 帧都触发一次 Invocation；"要不要打断当前讲话、如何干预"由核心 Agent 决定。capability 的对 Agent 描述把这条通道说明为操作员指令（权威意图），但行动方式仍归 Agent。
- 最简基本版的已知边界（有意为之，留待管理端演进）：断线期间敲入的行由终端行缓冲
  兜住、重连后照发；正在发送的那一行由模块持有、重连后重发一次；但已被 socket
  收走恰又在断线瞬间丢失的帧无法找回（输入侧没有 ACK 通道，waycast 契约如此）。
  无输入历史；单实例控制台；超过 8192 字符的行丢弃。

## 与 waycast 的关系

- 帧格式、capability 结构、连接令牌来自 waycast wire 协议（waycast/src/waycast/wire.py）；本仓库在 `src/text_input/wire.py` 本地实现该客户端侧契约（纯 JSON over WebSocket，无包依赖），不修改协议本身，互操作以 waycast 的实现为权威。
- capability 的 input description 会进入核心 Agent 的系统提示词（waycast capability catalog），是这条通道对 Agent 的语义说明书。

## 运行前提

- Python 3.12+ 与 uv（https://docs.astral.sh/uv/）。
- 已启动且可达的 waycast hub（例如 ws://127.0.0.1:8000），以及分配给文本输入的连接令牌（hub 无令牌校验时留空）。

## 安装与配置

```sh
uv sync --locked
cp .env.example .env   # 至少填 WAYCAST_HUB_URL
```

| 键 | 必填 | 说明 |
| --- | --- | --- |
| `WAYCAST_HUB_URL` | 是 | hub 地址（ws:// 或 wss://） |
| `WAYCAST_HUB_TOKEN` | 否 | 模块连接令牌 |
| `WAYCAST_TLS_CA` | 否 | wss 使用的 CA 文件 |
| `TEXT_IN_LOG_LEVEL` | 否 | 本模块日志级别（默认 INFO） |

## 运行

```sh
uv run --locked text-input
```

出现 `text_input> ` 提示符后，每敲一行回车就发一条输入帧；`Ctrl-D`（EOF）正常退出，`Ctrl-C` 即刻退出。hub 不可达时模块每 3 秒重连一次。

## 开发

```sh
uv run --locked pytest -q        # 测试（本地起假 hub，离线可跑）
uv run --locked ruff check .
uv run --locked basedpyright
```
