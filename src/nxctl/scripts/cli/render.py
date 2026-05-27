"""Terminal rendering helpers for NXCTL CLI output."""

from __future__ import annotations

import os
import re
import sys
import threading
import time
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, Sequence

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
GRAY = "\033[90m"

def _can_render_unicode() -> bool:
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    if "utf" in encoding:
        return True
    try:
        "\u2713\u2570\u2500\u280b".encode(encoding or "ascii")
        return True
    except Exception:
        return False


UNICODE = _can_render_unicode()

OK = "\u2713" if UNICODE else "+"
ERR = "\u2717" if UNICODE else "x"
WARN = "!"
BULLET = "\u2022" if UNICODE else "-"
ELLIPSIS = "\u2026" if UNICODE else "..."
HLINE = "\u2500" if UNICODE else "-"
VLINE = "\u2502" if UNICODE else "|"
TOP_LEFT = "\u256d" if UNICODE else "+"
TOP_RIGHT = "\u256e" if UNICODE else "+"
BOTTOM_LEFT = "\u2570" if UNICODE else "+"
BOTTOM_RIGHT = "\u256f" if UNICODE else "+"
SPINNER_FRAMES = (
    ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]
    if UNICODE
    else ["|", "/", "-", "\\"]
)


def strip_ansi(text: object) -> str:
    return ANSI_RE.sub("", str(text))


def visible_len(text: object) -> int:
    return len(strip_ansi(text))


def color(text: object, code: str) -> str:
    return f"{code}{text}{RESET}"


def green(text: object) -> str:
    return color(text, GREEN)


def red(text: object) -> str:
    return color(text, RED)


def yellow(text: object) -> str:
    return color(text, YELLOW)


def blue(text: object) -> str:
    return color(text, BLUE)


def cyan(text: object) -> str:
    return color(text, CYAN)


def gray(text: object) -> str:
    return color(text, GRAY)


def bold(text: object) -> str:
    return color(text, BOLD)


def pad(text: object, width: int) -> str:
    text = str(text)
    return text + (" " * max(0, width - visible_len(text)))


def truncate(text: object, width: int) -> str:
    text = str(text)
    if visible_len(text) <= width:
        return text
    raw = strip_ansi(text)
    return raw[: max(0, width - visible_len(ELLIPSIS))] + ELLIPSIS


def format_error(value: object, width: int = 180) -> str:
    """Return a compact, user-facing error message."""
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if not lines:
        return "-"

    important = [
        line for line in lines
        if line.strip().lower() not in {"error:", "error"}
        and any(token in line.lower() for token in ("error", "failed", "unknown", "denied", "refused", "limit"))
    ]
    summary = important[-1] if important else lines[0]
    first = lines[0]
    if first != summary and any(token in first.lower() for token in ("failed", "error")):
        summary = f"{first} ({summary})"
    return truncate(summary, width)


def format_datetime(value: object) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(max(0, seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def ttl_remaining(expires_at: object) -> tuple[str, bool]:
    if not expires_at:
        return "-", True
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except Exception:
            try:
                expires_at = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return "-", True
    if not isinstance(expires_at, datetime):
        return "-", True
    remaining = int((expires_at - datetime.now()).total_seconds())
    return format_duration(remaining), remaining >= 0


def status_text(status: object) -> str:
    value = str(status or "-").lower()
    if value in {"running", "active", "ready", "yes", "enabled"}:
        return green(value.capitalize())
    if value in {"dead", "error", "failed", "expired", "no", "disabled", "stopped"}:
        return red(value.capitalize())
    if value in {"warning", "inactive"}:
        return yellow(value.capitalize())
    return str(status or "-")


def step_ok(text: str) -> None:
    print(f"{green(OK)} {text}")


def step_warn(text: str) -> None:
    print(f"{yellow(WARN)} {text}")


def step_error(text: str) -> None:
    print(f"{red(ERR)} {text}")


def step_skip(text: str) -> None:
    print(f"{gray('-')} {text}")


class ProgressReporter:
    """Compact progress output for blocking CLI operations.

    In TTY mode this uses the existing spinner. In non-TTY/CI logs it prints a
    deterministic "..." line before the operation and a final status line after.
    """

    def __init__(self, indent: int = 0):
        self.prefix = " " * max(0, indent)

    def ok(self, text: str) -> None:
        print(f"{self.prefix}{green(OK)} {text}")

    def warn(self, text: str) -> None:
        print(f"{self.prefix}{yellow(WARN)} {text}")

    def error(self, text: str) -> None:
        print(f"{self.prefix}{red(ERR)} {text}")

    def skip(self, text: str) -> None:
        print(f"{self.prefix}{gray('-')} {text}")

    @contextmanager
    def step(self, label: str, success: str | None = None, failure: str | None = None):
        try:
            with spinner(f"{self.prefix}{label}"):
                yield
        except Exception as exc:
            message = failure or f"{label} failed"
            self.error(f"{message}: {format_error(exc)}")
            raise
        if success:
            self.ok(success)


@contextmanager
def suppress_input():
    """Temporarily suppress terminal input and flush the buffer (Linux/Unix only)."""
    try:
        import termios
        import tty
    except ImportError:
        yield
        return
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        yield
        return
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        new = termios.tcgetattr(fd)
        new[3] = new[3] & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, new)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        termios.tcflush(fd, termios.TCIFLUSH)


def print_section(title: str, text: str = "") -> None:
    if title:
        print(bold(title))
    if text:
        print(text)


@contextmanager
def spinner(label: str):
    """Small terminal spinner for long blocking operations."""
    if not sys.stdout.isatty() or logging.getLogger().getEffectiveLevel() <= logging.INFO:
        print(f"{gray(ELLIPSIS)} {label}")
        yield
        return

    done = threading.Event()

    def animate() -> None:
        index = 0
        while not done.is_set():
            frame = SPINNER_FRAMES[index % len(SPINNER_FRAMES)]
            sys.stdout.write(f"\r{blue(frame)} {label}")
            sys.stdout.flush()
            index += 1
            time.sleep(0.08)

    thread = threading.Thread(target=animate, daemon=True)
    thread.start()
    try:
        with suppress_input():
            yield
    finally:
        done.set()
        thread.join(timeout=0.2)
        sys.stdout.write("\r" + " " * (visible_len(label) + 4) + "\r")
        sys.stdout.flush()


def panel(title: str, rows: Sequence[tuple[str, object]], width: int = 72) -> str:
    label_width = max([visible_len(label) for label, _ in rows] + [0])
    inner_width = width - 2
    title_text = f" {title} "
    top = TOP_LEFT + HLINE + title_text + HLINE * max(0, inner_width - visible_len(title_text) - 1) + TOP_RIGHT
    bottom = BOTTOM_LEFT + HLINE * inner_width + BOTTOM_RIGHT
    lines = [top]
    for label, value in rows:
        label_part = pad(label, label_width)
        value_part = truncate(value, inner_width - label_width - 4)
        content = f"{label_part}  {value_part}"
        lines.append(f"{VLINE} {pad(content, inner_width - 2)} {VLINE}")
    lines.append(bottom)
    return "\n".join(lines)


def box(title: str, body: str, width: int = 96) -> str:
    inner_width = width - 2
    title_text = f" {title} "
    top = TOP_LEFT + HLINE + title_text + HLINE * max(0, inner_width - visible_len(title_text) - 1) + TOP_RIGHT
    bottom = BOTTOM_LEFT + HLINE * inner_width + BOTTOM_RIGHT
    lines = [top]
    for raw_line in (body or "").splitlines() or [""]:
        line = truncate(raw_line, inner_width - 2)
        lines.append(f"{VLINE} {pad(line, inner_width - 2)} {VLINE}")
    lines.append(bottom)
    return "\n".join(lines)


def table(headers: Sequence[str], rows: Sequence[Sequence[object]], max_widths: Sequence[int] | None = None) -> str:
    if not rows:
        return ""
    max_widths = list(max_widths or [32] * len(headers))
    widths = []
    for idx, header in enumerate(headers):
        width = visible_len(header)
        for row in rows:
            if idx < len(row):
                width = max(width, visible_len(row[idx]))
        widths.append(min(width, max_widths[idx] if idx < len(max_widths) else 32))

    header = "  ".join(pad(h, widths[idx]) for idx, h in enumerate(headers))
    sep = "  ".join(HLINE * width for width in widths)
    lines = [bold(header), gray(sep)]
    for row in rows:
        parts = []
        for idx in range(len(headers)):
            value = row[idx] if idx < len(row) else ""
            parts.append(pad(truncate(value, widths[idx]), widths[idx]))
        lines.append("  ".join(parts))
    return "\n".join(lines)


def export_rows(exports: Iterable[dict], detailed: bool = False) -> list[list[object]]:
    rows = []
    for exp in exports:
        status = str(exp.get("status") or "-").lower()
        icon = green(OK) if status == "running" else red(ERR) if status in {"dead", "failed", "error"} else yellow(WARN)
        row = [
            icon,
            exp.get("provider") or "-",
            exp.get("type") or "-",
            status_text(status),
            exp.get("port_label") or exp.get("port") or "-",
            exp.get("url") or exp.get("endpoint") or "-",
            exp.get("pid") or "-",
        ]
        if detailed:
            row.append(format_datetime(exp.get("created_at")))
        rows.append(row)
    return rows


def exports_table(exports: Sequence[dict], detailed: bool = False) -> str:
    if not exports:
        return gray("No active exports")
    headers = ["", "Provider", "Type", "Status", "Port", "URL", "PID"]
    widths = [2, 14, 8, 10, 12, 64, 8]
    if detailed:
        headers.append("Created")
        widths.append(20)
    return table(headers, export_rows(exports, detailed=detailed), widths)
