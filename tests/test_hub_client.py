"""Hub client frame contract: capability handshake and input frames match
waycast wire (ADR-0008), verified against a local in-process hub stand-in."""
from __future__ import annotations

import asyncio

import pytest
import websockets

from text_input.hub_client import MODULE_NAME, HubConnectionError, InputClient
from text_input.wire import dumps, make_frame, parse_frame


def _accepting_server(received: list[dict]) -> "asyncio.Future[websockets.WebSocketServer]":
    """A minimal hub: accept the capability, then record every frame sent."""

    async def handler(ws: websockets.ServerConnection) -> None:
        capability = parse_frame(await ws.recv())
        assert capability["type"] == "capability"
        assert capability["payload"]["kind"] == "input"
        received.append(capability)
        await ws.send(dumps(make_frame("capability", MODULE_NAME, {"accepted": True})))
        async for raw in ws:
            received.append(parse_frame(raw))

    return websockets.serve(handler, "127.0.0.1", 0)


def test_handshake_then_input_frames() -> None:
    received: list[dict] = []

    async def scenario() -> None:
        server = await _accepting_server(received)
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        async with InputClient(hub_url=url, token="t") as client:
            await client.send_input("停下,讲讲第二页")
        server.close()
        await server.wait_closed()

    asyncio.run(scenario())
    capability, first = received
    assert capability["payload"]["name"] == MODULE_NAME
    assert capability["payload"]["input"]["description"]
    assert first["type"] == "input"
    assert first["module"] == MODULE_NAME
    assert first["payload"] == {"content": "停下,讲讲第二页", "source": MODULE_NAME, "metadata": {}}


def test_hub_rejection_raises() -> None:
    async def handler(ws: websockets.ServerConnection) -> None:
        await ws.recv()
        await ws.send(dumps(make_frame("capability", MODULE_NAME, {"accepted": False})))

    async def scenario() -> None:
        server = await websockets.serve(handler, "127.0.0.1", 0)
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        try:
            with pytest.raises(HubConnectionError):
                async with InputClient(hub_url=url, token="t"):
                    pass
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_unreachable_hub_raises() -> None:
    async def scenario() -> None:
        with pytest.raises(HubConnectionError):
            async with InputClient(hub_url="ws://127.0.0.1:1", token=""):
                pass

    asyncio.run(scenario())
