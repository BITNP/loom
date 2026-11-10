"""Waycast hub connection for the text input module.

A module connects to the hub /ws/modules endpoint, advertises its capability as
the first frame, and after the hub acknowledges it sends input frames over the
same full-duplex connection.  The wire contract (ADR-0008) is implemented
locally in loom.wire as plain JSON; the module and the core are separate
microservices that talk only over the network and share no Python package.

This module is input-only: it never receives output_unit frames and holds no
core logic.  Console lines are operator instructions, but turn-taking and
interruption remain the core Agent's decisions (ADR-0011): every line sent is
exactly one input frame triggering one Invocation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Self
from urllib.parse import urlencode, urlparse, urlunparse

import websockets

from loom.wire import dumps, make_frame, parse_frame

LOGGER = logging.getLogger(__name__)

MODULE_NAME = "loom"
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
        self._reader: asyncio.Task[None] | None = None

    @property
    def name(self) -> str:
        return self._name

    def _ws_uri(self) -> str:
        parts = urlparse(self._hub_url.rstrip("/") + "/ws/modules")
        query = urlencode({"token": self._token}) if self._token else parts.query
        return urlunparse(parts._replace(query=query))

    def _connect_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"open_timeout": 10.0}
        if self._tls_ca:
            import ssl

            kwargs["ssl"] = ssl.create_default_context(cafile=self._tls_ca)
        return kwargs

    async def _read_loop(self) -> None:
        """Drain the socket so remote closure cancels the sender promptly."""
        try:
            while True:
                frame = parse_frame(await self._ws.recv())
                LOGGER.debug("ignoring frame type %s", frame["type"])
        except (websockets.ConnectionClosed, ConnectionError, OSError):
            LOGGER.debug("hub connection closed (reader)")
        finally:
            with contextlib.suppress(Exception):
                await self._ws.close()

    async def __aenter__(self) -> Self:
        uri = self._ws_uri()
        try:
            self._ws = await websockets.connect(uri, **self._connect_kwargs())
        except OSError as exc:
            raise HubConnectionError(f"cannot reach hub at {uri}: {exc}") from exc
        capability: dict[str, Any] = {
            "name": self._name,
            "kind": "input",
            "input": {"description": CAPABILITY_INPUT_DESCRIPTION},
        }
        try:
            await self._ws.send(dumps(make_frame("capability", self._name, capability)))
            ack = parse_frame(await self._ws.recv())
            if ack["type"] != "capability" or not ack["payload"].get("accepted"):
                raise HubConnectionError(f"hub did not accept capability: {dumps(ack)}")
        except HubConnectionError:
            await self._ws.close()
            raise
        except Exception as exc:
            await self._ws.close()
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
        payload = {"content": content, "source": source, "metadata": metadata or {}}
        await self._ws.send(dumps(make_frame("input", self._name, payload)))

    async def __aexit__(self, *exc_info: object) -> None:
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass
            self._reader = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None


__all__ = ["MODULE_NAME", "HubConnectionError", "InputClient"]
