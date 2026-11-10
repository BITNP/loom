"""Runtime configuration for the text input module.

All values come from the environment (the .env file is loaded first by main).
The only required setting is the waycast hub address; the token and TLS CA are
optional, mirroring the keys every Raspberry Girl module shares
(WAYCAST_HUB_URL / WAYCAST_HUB_TOKEN / WAYCAST_TLS_CA).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

WAYCAST_HUB_URL_KEY: Final = "WAYCAST_HUB_URL"
WAYCAST_HUB_TOKEN_KEY: Final = "WAYCAST_HUB_TOKEN"
WAYCAST_TLS_CA_KEY: Final = "WAYCAST_TLS_CA"

LOG_LEVEL_KEY: Final = "TEXT_IN_LOG_LEVEL"
DEFAULT_LOG_LEVEL: Final = "INFO"


class ConfigError(ValueError):
    """Raised when a required setting is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Settings:
    hub_url: str
    hub_token: str
    tls_ca_path: str | None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from an explicit mapping (tests) or os.environ."""
    source = os.environ if env is None else env
    hub_url = source.get(WAYCAST_HUB_URL_KEY, "").strip()
    if not hub_url:
        raise ConfigError(
            f"{WAYCAST_HUB_URL_KEY}: required setting is missing or empty"
        )
    if not hub_url.startswith(("ws://", "wss://")):
        raise ConfigError(f"{WAYCAST_HUB_URL_KEY}: must be a ws:// or wss:// URL")
    return Settings(
        hub_url=hub_url,
        hub_token=source.get(WAYCAST_HUB_TOKEN_KEY, "").strip(),
        tls_ca_path=(source.get(WAYCAST_TLS_CA_KEY, "").strip() or None),
    )


__all__ = [
    "DEFAULT_LOG_LEVEL",
    "LOG_LEVEL_KEY",
    "ConfigError",
    "Settings",
    "load_settings",
]
