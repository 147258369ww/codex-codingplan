"""Tests for logging utility helpers."""

import io
import re

from codex_proxy.logging_utils import (
    format_bytes,
    format_duration,
    generate_request_id,
    should_use_color,
    truncate_text,
)


def test_generate_request_id_has_expected_shape():
    request_id = generate_request_id()

    assert re.fullmatch(r"req_[0-9a-f]{4}", request_id)


def test_truncate_text_marks_truncated_values():
    truncated, was_truncated = truncate_text("x" * 25, limit=20)

    assert was_truncated is True
    assert truncated == "xxxxxx...<truncated>"
    assert len(truncated) == 20


def test_truncate_text_leaves_short_values_unchanged():
    text, was_truncated = truncate_text("short", limit=10)

    assert was_truncated is False
    assert text == "short"


def test_format_helpers_return_compact_values():
    assert format_bytes(684) == "684B"
    assert format_bytes(1536) == "1.5KB"
    assert format_duration(2.31) == "2.31s"


def test_should_use_color_respects_tty_and_no_color(monkeypatch):
    class TtyStream(io.StringIO):
        def isatty(self):
            return True

    class NonTtyStream(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.delenv("NO_COLOR", raising=False)
    assert should_use_color(TtyStream()) is True
    assert should_use_color(NonTtyStream()) is False

    monkeypatch.setenv("NO_COLOR", "1")
    assert should_use_color(TtyStream()) is False
