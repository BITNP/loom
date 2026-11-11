"""Text input module entry point: stdin console -> waycast input frames.

One typed line is one console input is one unified input frame: no batching,
no partial/final marking, no turn-taking involvement (ADR-0011).  The module
is the simplest possible operator console.  A line stays owned by the module
until the socket accepts it, so a line whose send fails is resent after
reconnect; the terminal's own line buffer keeps lines typed while the hub is
down.  A frame the socket took but the network lost in the instant of a drop
cannot be recovered (inputs carry no acknowledgement channel).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from collections.abc import Awaitable, Callable
from typing import Final

import websockets
from dotenv import load_dotenv

from loom.config import DEFAULT_LOG_LEVEL, LOG_LEVEL_KEY, load_settings
from loom.hub_client import MODULE_NAME, HubConnectionError, InputClient

LOGGER = logging.getLogger(__name__)

# Hub reconnect backoff, the schedule shared by loom / aria / lumen: start at
# BASE, double per failed attempt up to MAX, jitter +-20% so modules that were
# dropped together do not retry in lockstep, reset once a connection is up.
HUB_RECONNECT_BASE_SECONDS: Final = 1.0
HUB_RECONNECT_MAX_SECONDS: Final = 30.0
RECONNECT_JITTER_RATIO: Final = 0.2
MAX_LINE_LENGTH: Final = 8192


def _with_reconnect_jitter(seconds: float) -> float:
    """Seconds to actually sleep for ``seconds``: uniform jitter of +-20%."""
    spread = seconds * RECONNECT_JITTER_RATIO
    return seconds + random.uniform(-spread, spread)


# An async callable returning one raw console line; raises EOFError at end.
LineReader = Callable[[], Awaitable[str]]


async def _stdin_line() -> str:
    return await asyncio.to_thread(input, f"{MODULE_NAME}> ")


async def run_forever(
    read_line: LineReader = _stdin_line,
    *,
    hub_url: str,
    hub_token: str = "",
    tls_ca_path: str | None = None,
    reconnect_base_delay: float = HUB_RECONNECT_BASE_SECONDS,
) -> None:
    """Read console lines and forward each as an input frame until EOF.

    Returns cleanly on EOF (stdin closed); any hub failure retries with
    exponential backoff from ``reconnect_base_delay`` (doubled per failure,
    capped at HUB_RECONNECT_MAX_SECONDS, jittered), reset after a connection
    is established.
    """
    pending: str | None = None  # line owned by the module until the socket takes it
    delay = reconnect_base_delay
    while True:
        try:
            async with InputClient(
                hub_url=hub_url, token=hub_token, tls_ca_path=tls_ca_path
            ) as client:
                delay = reconnect_base_delay  # connection is up: back to first retry
                while True:
                    if pending is not None:
                        await client.send_input(pending, source=MODULE_NAME)
                        LOGGER.debug("resent held line after reconnect")
                        pending = None
                        continue
                    try:
                        line = (await read_line()).strip()
                    except EOFError:
                        LOGGER.info("console closed; exiting")
                        return
                    if not line:
                        continue
                    if len(line) > MAX_LINE_LENGTH:
                        LOGGER.warning("dropping overlong line (%d chars)", len(line))
                        continue
                    pending = line
                    await client.send_input(line, source=MODULE_NAME)
                    pending = None
        except HubConnectionError as exc:
            sleep_seconds = _with_reconnect_jitter(delay)
            LOGGER.warning("hub unavailable: %s; retrying in %.2fs", exc, sleep_seconds)
            await asyncio.sleep(sleep_seconds)
        except (websockets.ConnectionClosed, ConnectionError, OSError):
            sleep_seconds = _with_reconnect_jitter(delay)
            LOGGER.warning("hub connection dropped; retrying in %.2fs", sleep_seconds)
            await asyncio.sleep(sleep_seconds)
        delay = min(delay * 2, HUB_RECONNECT_MAX_SECONDS)


def main() -> None:
    load_dotenv()
    level = (
        os.environ.get(LOG_LEVEL_KEY, DEFAULT_LOG_LEVEL).strip().upper()
        or DEFAULT_LOG_LEVEL
    )
    logging.basicConfig(level=getattr(logging, level, logging.INFO))
    settings = load_settings()
    try:
        asyncio.run(run_forever(hub_url=settings.hub_url, hub_token=settings.hub_token))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
