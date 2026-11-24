"""Turn raw ConPTY bytes into clean log lines."""

from __future__ import annotations

import re


_ANSI_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)
_PAUSE_MARK = "press any key to continue"


def strip_ansi(text: str) -> str:
    cleaned = _ANSI_RE.sub("", text)
    return cleaned.replace("\x00", "").replace("\x07", "").replace("0011Ignore", "")


def contains_pause_prompt(text: str) -> bool:
    return _PAUSE_MARK in text.lower()


class LineAssembler:
    """Join console chunks. CRLF ends a line; a bare CR overwrites the current line."""

    def __init__(self, max_line: int = 8000) -> None:
        self._buffer = ""
        self._max_line = max_line
        self._trailing_cr = False

    def feed(self, text: str) -> list[str]:
        lines: list[str] = []
        if self._trailing_cr:
            self._trailing_cr = False
            if text.startswith("\n"):
                lines.append(self._take())
                text = text[1:]
            else:
                self._buffer = ""
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\r":
                if index + 1 < len(text) and text[index + 1] == "\n":
                    lines.append(self._take())
                    index += 2
                    continue
                if index + 1 == len(text):
                    self._trailing_cr = True
                    break
                self._buffer = ""
                index += 1
                continue
            if char == "\n":
                lines.append(self._take())
                index += 1
                continue
            if char == "\b":
                self._buffer = self._buffer[:-1]
            else:
                self._buffer += char
                if len(self._buffer) > self._max_line:
                    lines.append(self._take())
            index += 1
        if contains_pause_prompt(self._buffer):
            lines.append(self._take())
        return lines

    def flush(self) -> list[str]:
        if not self._buffer:
            return []
        return [self._take()]

    def _take(self) -> str:
        line = self._buffer
        self._buffer = ""
        return line.rstrip()
