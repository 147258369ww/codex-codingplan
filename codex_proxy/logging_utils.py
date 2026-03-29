"""Utilities for concise logging output."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime
from typing import Any


def generate_request_id() -> str:
    """Generate a short request identifier."""
    return f"req_{secrets.token_hex(2)}"


def truncate_text(value: str, limit: int) -> tuple[str, bool]:
    """Truncate text to a maximum length and mark whether it was shortened."""
    if len(value) <= limit:
        return value, False

    marker = "...<truncated>"
    if limit <= len(marker):
        return marker[:limit], True
    return value[: limit - len(marker)] + marker, True


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


class ConsoleFormatter(logging.Formatter):
    """Format concise console summaries with optional ANSI colors."""

    LEVEL_COLORS = {
        "DEBUG": "\033[90m",
        "INFO": "\033[36m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool = False) -> None:
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        level = f"{record.levelname:<8}"
        if self.use_color:
            color = self.LEVEL_COLORS.get(record.levelname)
            if color is not None:
                level = f"{color}{level}{self.RESET}"
        request_id = getattr(record, "request_id", "-")
        message = f"{timestamp}  {level}  {request_id:<8}  {record.getMessage()}"
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        if record.stack_info:
            message += "\n" + self.formatStack(record.stack_info)
        return message
