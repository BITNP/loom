# 更名为机杼（Loom）

## Status

accepted

## Context

树莓娘体系确立诗意命名族（waycast ADR-0015）：核心 waycast 中文名「道枢」，三个模块仓库取「一模块一首诗」的中英双名。本模块取 **机杼 / Loom**：雅卡尔打孔卡是程序之源，Ada Lovelace 以「织出代数花纹」定义计算机；「织」又暗合网协「织网」。命名全文见 README「命名来历」。本 ADR 是本仓库第一条决策记录（此前该仓库无 docs/adr/）。

## Decision

本仓库自 2026-11-10 起使用下列标识符，旧标识符全部废止（不再用于新设计）：

| 层面 | 旧 | 新 |
| --- | --- | --- |
| 仓库 / 目录 | raspberrygirl-text-input | loom |
| Python 包名与目录 | `text_input`（src/text_input） | `loom`（src/loom） |
| pyproject 项目名 | raspberrygirl-text-input | loom |
| CLI 命令 | `text-input` | `loom` |
| 环境变量前缀 | `TEXT_IN_` | `LOOM_` |
| wire 模块名（MODULE_NAME、input 帧 source） | `text_input` | `loom` |

本 ADR 之前的历史文档与 git 历史保持原文不改写，按本表读解旧标识符。

## Consequences

- 部署环境的 .env 需把 `TEXT_IN_*` 键改名为 `LOOM_*`（本机已完成）；`.env.example` 同步。
- wire 模块名变化会进入核心全局记忆与能力目录（Agent 可见的模块名变为 `loom`）；hub 侧无按模块名绑定的令牌，无需核心改动。
- GitHub 远端仓库改名是网页端手工操作，克隆 URL 需另行更新。
- waycast GLOSSARY 与各仓库间交叉引用同步改用新名。
