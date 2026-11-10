"""Settings come from the shared waycast keys only."""

from __future__ import annotations

import pytest

from text_input.config import ConfigError, load_settings


def test_minimal_settings_and_optional_defaults() -> None:
    settings = load_settings({"WAYCAST_HUB_URL": "ws://127.0.0.1:8000"})
    assert settings.hub_url == "ws://127.0.0.1:8000"
    assert settings.hub_token == ""
    assert settings.tls_ca_path is None


def test_optional_settings_are_trimmed() -> None:
    settings = load_settings(
        {
            "WAYCAST_HUB_URL": " wss://hub.example:9443 ",
            "WAYCAST_HUB_TOKEN": "  tok  ",
            "WAYCAST_TLS_CA": "  /ca.pem ",
        }
    )
    assert settings.hub_url == "wss://hub.example:9443"
    assert settings.hub_token == "tok"
    assert settings.tls_ca_path == "/ca.pem"


def test_blank_tls_ca_is_none() -> None:
    settings = load_settings({"WAYCAST_HUB_URL": "ws://h", "WAYCAST_TLS_CA": "   "})
    assert settings.tls_ca_path is None


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"WAYCAST_HUB_URL": "   "},
        {"WAYCAST_HUB_URL": "http://127.0.0.1:8000"},
    ],
)
def test_hub_url_required_and_scheme_checked(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        load_settings(env)
