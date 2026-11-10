"""Client-side wire envelope: frames match the waycast contract (ADR-0008)."""

from __future__ import annotations

import pytest

from text_input.wire import (
    PROTOCOL_VERSION,
    WireError,
    dumps,
    make_frame,
    parse_frame,
)


def test_make_frame_round_trip() -> None:
    frame = make_frame("input", "text_input", {"content": "你好"}, request_id="r1")
    parsed = parse_frame(dumps(frame))
    assert parsed["protocol_version"] == PROTOCOL_VERSION
    assert parsed["type"] == "input"
    assert parsed["module"] == "text_input"
    assert parsed["request_id"] == "r1"
    assert parsed["payload"] == {"content": "你好"}


def test_defaults_are_explicit() -> None:
    frame = make_frame("capability", "text_input")
    assert frame["payload"] == {}
    assert frame["request_id"] is None


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1,2]",
        dumps({"protocol_version": 2, "type": "input", "module": "m"}),
        dumps({"protocol_version": PROTOCOL_VERSION, "module": "m"}),
        dumps({"protocol_version": PROTOCOL_VERSION, "type": "input"}),
        dumps(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": "input",
                "module": "m",
                "payload": [1],
            }
        ),
    ],
)
def test_parse_rejects_malformed_frames(raw: str) -> None:
    with pytest.raises(WireError):
        parse_frame(raw)


def test_parse_accepts_dict_and_bytes() -> None:
    assert parse_frame(make_frame("input", "m"))["type"] == "input"
    assert parse_frame(dumps(make_frame("input", "m")).encode())["module"] == "m"
