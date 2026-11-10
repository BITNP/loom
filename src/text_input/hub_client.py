"""Waycast hub connection for the text input module.

A module connects to the hub /ws/modules endpoint, advertises its capability as
the first frame, and after the hub acknowledges it sends input frames over the
same full-duplex connection.  The wire contract (ADR-0008) is implemented
locally in text_input.wire as plain JSON; the module and the core are separate
microservices that talk only over the network and share no Python package.

This module is input-only: it never receives output_unit frames and holds no
core logic.  Console lines are operator instructions, but turn-taking and
interruption remain the core Agent's decisions (ADR-0011): every line sent is
exactly one input frame triggering one Invocation.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from contextlib import AsyncExitStack
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

import httpx2
from httpx2.websockets import (
    WebSocketDisconnect,
    WebSocketNetworkError,
    WebSocketUpgradeError,
)

from text_input.wire import dumps, make_frame, parse_frame

LOGGER = logging.getLogger(__name__)

MODULE_NAME = "text_input"
CAPABILITY_INPUT_DESCRIPTION = (
    "console input typed by a human operator on a text console: each line is a "
    "direct instruction or question for Raspberry Girl and may ask to change the "
    "topic, stop or interrupt the current speech, or intervene in what is on "
    "screen; treat operator lines as authoritative intent, but only you decide "
    "how and when to act on them (including sending a presenter control stop)"
)


class HubConnectionError(RuntimeError):
    """Raised when the hub rejects the module connection."""


class InputClient:
    """Async context manager providing connection admission and send_input().

    Usage:

        async with InputClient(hub_url=url, token="") as client:
            await client.send_input("停下来，讲讲第二页")

    The client keeps the socket open until the context exits; the reconnect
    loop is the caller's responsibility (main.run_forever wraps this).  An
    input-only module receives nothing but the acknowledgement, yet the reader
    task still drains the socket so a dropped connection surfaces immediately
    instead of at the next send.
    """

    def __init__(
        self,
        *,
        hub_url: str,
        token: str,
        tls_ca_path: str | None = None,
        name: str = MODULE_NAME,
    ) -> None:
        self._hub_url = hub_url
        self._token = token
        self._tls_ca = tls_ca_path
        self._name = name
        self._ws: Any = None
        self._exit_stack: AsyncExitStack | None = None
        self._reader: asyncio.Task[None] | None = None
        # reader 观察到对端关闭时记录异常：此后 send_input 立即以同一异常失败，
        # 让外层重连循环在下一行输入上马上发现断线（与旧 websockets 里
        # reader 主动 close 后 send 抛错的行为对齐）。
        self._dropped: Exception | None = None

    @property
    def name(self) -> str:
        return self._name

    def _ws_uri(self) -> str:
        parts = urlparse(self._hub_url.rstrip("/") + "/ws/modules")
        query = urlencode({"token": self._token}) if self._token else parts.query
        return urlunparse(parts._replace(query=query))

    def _client_kwargs(self) -> dict[str, Any]:
        # 与旧 websockets.connect 的裸连接语义一致：10s 握手时限、绝不读取
        # 环境代理变量（HTTP_PROXY 等不得劫持到 hub 的直连）。
        kwargs: dict[str, Any] = {
            "timeout": httpx2.Timeout(10.0),
            "trust_env": False,
        }
        if self._tls_ca:
            kwargs["verify"] = ssl.create_default_context(cafile=self._tls_ca)
        return kwargs

    async def _read_loop(self) -> None:
        """Drain the socket so remote closure cancels the sender promptly."""
        try:
            while True:
                frame = parse_frame(await self._ws.receive_text())
                LOGGER.debug("ignoring frame type %s", frame["type"])
        except (
            WebSocketDisconnect,
            WebSocketNetworkError,
            ConnectionError,
            OSError,
        ) as exc:
            self._dropped = exc
            try:  # 主动回应对端关闭（对齐旧 websockets reader 主动 close 的语义：
                await self._ws.close()  # 否则对端的 close 握手要空等 close_timeout）
            except Exception:  # noqa: BLE001 - 清理尽力而为
                pass
            LOGGER.debug("hub connection closed (reader)")

    async def __aenter__(self) -> "InputClient":
        uri = self._ws_uri()
        client = httpx2.AsyncClient(**self._client_kwargs())
        self._exit_stack = AsyncExitStack()
        self._exit_stack.push_async_callback(client.aclose)
        try:
            self._ws = await self._exit_stack.enter_async_context(client.websocket(uri))
        except (
            WebSocketUpgradeError,
            WebSocketNetworkError,
            httpx2.HTTPError,
            OSError,
        ) as exc:
            await self._exit_stack.aclose()
            self._exit_stack = None
            raise HubConnectionError(f"cannot reach hub at {uri}: {exc}") from exc
        capability: dict[str, Any] = {
            "name": self._name,
            "kind": "input",
            "input": {"description": CAPABILITY_INPUT_DESCRIPTION},
        }
        try:
            await self._ws.send_text(
                dumps(make_frame("capability", self._name, capability))
            )
            ack = parse_frame(await self._ws.receive_text())
            if ack["type"] != "capability" or not ack["payload"].get("accepted"):
                raise HubConnectionError(f"hub did not accept capability: {dumps(ack)}")
        except HubConnectionError:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._ws = None
            raise
        except Exception as exc:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._ws = None
            raise HubConnectionError("hub handshake failed") from exc
        self._reader = asyncio.create_task(self._read_loop())
        LOGGER.info("%s admitted to waycast hub (kind=input)", self._name)
        return self

    async def send_input(
        self,
        content: str,
        *,
        source: str = MODULE_NAME,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send one unified input frame; content is the typed console line."""
        if self._ws is None:
            raise RuntimeError("send_input before __aenter__")
        if self._dropped is not None:
            raise self._dropped
        payload = {"content": content, "source": source, "metadata": metadata or {}}
        try:
            await self._ws.send_text(dumps(make_frame("input", self._name, payload)))
        except (WebSocketDisconnect, WebSocketNetworkError, ConnectionError, OSError):
            raise
        except Exception as exc:  # noqa: BLE001 - wsproto 的底层协议错误同样意味着连接已断，收敛为 httpx2 的断线类型
            raise WebSocketNetworkError("hub connection dropped mid-send") from exc

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass
            self._reader = None
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self._ws = None


__all__ = ["InputClient", "HubConnectionError", "MODULE_NAME"]
