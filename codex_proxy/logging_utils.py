"""Utilities for concise logging output."""

from __future__ import annotations

import os
import secrets
from typing import Any


def generate_request_id() -> str:
    """Generate a short request identifier."""
    return f"req_{secrets.token_hex(2)}"


def truncate_text(value: str, limit: int) -> tuple[str, bool]:
    """Truncate text to a maximum length and mark whether it was shortened."""
    if len(value) <= limit:
        return value, False
    return value[:limit] + "...<truncated>", True


def format_bytes(size: int) -> str:
    """Format a byte size using compact human-readable units."""
    if size < 1024:
        return f"{size}B"
    return f"{size / 1024:.1f}KB"


def format_duration(seconds: float) -> str:
    """Format a duration in fixed two-decimal seconds."""
    return f"{seconds:.2f}s"


def should_use_color(stream: Any) -> bool:
    """Return True when the stream is a TTY and color output is allowed."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())
