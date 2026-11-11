"""Console loop: one line is one input frame; EOF stops, hub drops reconnect."""

from __future__ import annotations

import asyncio

import websockets

from loom import main as main_module
from loom.hub_client import MODULE_NAME
from loom.main import (
    RECONNECT_JITTER_RATIO,
    _with_reconnect_jitter,
    run_forever,
)
from loom.wire import dumps, make_frame, parse_frame


class _Lines:
    """Injectable console: canned lines, then EOF."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    async def __call__(self) -> str:
        if not self._lines:
            raise EOFError
        await asyncio.sleep(0)
        return self._lines.pop(0)


def test_lines_become_input_frames_blank_skipped() -> None:
    received: list[dict] = []
    done = asyncio.Event()

    async def handler(ws: websockets.ServerConnection) -> None:
        parse_frame(await ws.recv())  # capability
        await ws.send(dumps(make_frame("capability", MODULE_NAME, {"accepted": True})))
        async for raw in ws:
            frame = parse_frame(raw)
            received.append(frame)
            if len(received) == 2:
                done.set()

    async def scenario() -> None:
        server = await websockets.serve(handler, "127.0.0.1", 0)
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        runner = asyncio.create_task(
            run_forever(
                _Lines(["第一句", "   ", "第二句"]),
                hub_url=url,
                reconnect_base_delay=0.05,
            )
        )
        await asyncio.wait_for(done.wait(), timeout=5)
        await asyncio.wait_for(runner, timeout=5)  # EOF ends the loop
        server.close()
        await server.wait_closed()

    asyncio.run(scenario())
    assert [f["payload"]["content"] for f in received] == ["第一句", "第二句"]
    assert all(f["payload"]["source"] == MODULE_NAME for f in received)


def test_hub_drop_reconnects_and_keeps_forwarding() -> None:
    inputs: list[str] = []
    closed = asyncio.Event()
    second_arrived = asyncio.Event()
    connections = 0

    async def handler(ws: websockets.ServerConnection) -> None:
        nonlocal connections
        connections += 1
        connection_no = connections
        parse_frame(await ws.recv())  # capability
        await ws.send(dumps(make_frame("capability", MODULE_NAME, {"accepted": True})))
        frame = parse_frame(await ws.recv())
        inputs.append(frame["payload"]["content"])
        if connection_no == 1:
            await ws.close(code=4001, reason="test drop")
            closed.set()
            return
        second_arrived.set()
        async for _ in ws:  # hold the connection until the client leaves
            pass

    class _GatedLines:
        """Console that only offers line 2 once the drop has been observed."""

        def __init__(self) -> None:
            self._lines = ["打断一下", "第二句照发"]

        async def __call__(self) -> str:
            if not self._lines:
                raise EOFError
            if self._lines[0] == "第二句照发":
                await closed.wait()
                await asyncio.sleep(0.15)  # let the client reader see the close
            return self._lines.pop(0)

    async def scenario() -> None:
        server = await websockets.serve(handler, "127.0.0.1", 0)
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        runner = asyncio.create_task(
            run_forever(
                _GatedLines(),
                hub_url=url,
                reconnect_base_delay=0.05,
            )
        )
        await asyncio.wait_for(second_arrived.wait(), timeout=5)
        await asyncio.wait_for(runner, timeout=5)
        server.close()
        await server.wait_closed()

    asyncio.run(scenario())
    assert inputs == ["打断一下", "第二句照发"]
    assert connections == 2


def test_reconnect_jitter_within_bounds() -> None:
    for seconds in (0.0, 1.0, 30.0):
        for _ in range(100):
            value = _with_reconnect_jitter(seconds)
            assert (
                seconds * (1 - RECONNECT_JITTER_RATIO)
                <= value
                <= seconds * (1 + RECONNECT_JITTER_RATIO)
            )


def test_reconnect_backoff_doubles_until_capped(monkeypatch) -> None:
    """Unreachable hub: recorded pre-jitter delays double per failure, capped."""

    class _StopLoop(Exception):
        pass

    recorded: list[float] = []

    def record(seconds: float) -> float:
        recorded.append(seconds)
        if len(recorded) == 7:
            raise _StopLoop
        return 0.0

    async def scenario() -> None:
        server = await websockets.serve(lambda ws: None, "127.0.0.1", 0)  # never served
        port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()
        monkeypatch.setattr(main_module, "_with_reconnect_jitter", record)
        await run_forever(
            _Lines(["不会到达"]),
            hub_url=f"ws://127.0.0.1:{port}",
            reconnect_base_delay=1.0,
        )

    try:
        asyncio.run(scenario())
    except _StopLoop:
        pass
    assert recorded == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
