# GLOSSARY

本模块专属术语。核心语义术语（Input module、Unified input、Invocation、话权决定等）见 [waycast/GLOSSARY.md](../waycast/GLOSSARY.md)。

**控制台输入 (console input)**:
操作者在文本控制台敲入的一个非空行；一行恰好对应一条 UnifiedInput 和一个 input
帧，模块不做任何聚合、改写或话权判断。
_Avoid_: 命令行、chat 消息、bot 指令

**操作员通道 (operator channel)**:
本模块对核心 Agent 的语义定位（capability input description）：这条输入来自人类
操作员，其指令是权威意图，但采取何种干预（含是否派发 presenter 控制单元 stop）
由 Agent 决定（ADR-0011）。
_Avoid_: 管理接口、后门指令
