from __future__ import annotations

import socket


class MPDError(RuntimeError):
    pass


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class MPDClient:
    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = int(port)
        self.timeout = timeout

    def command(self, command: str, *, ignore_error: bool = False) -> list[str]:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                f = sock.makefile("rwb", buffering=0)
                hello = f.readline().decode("utf-8", "replace").strip()
                if not hello.startswith("OK MPD"):
                    raise MPDError(f"Unexpected MPD greeting: {hello}")
                f.write((command + "\n").encode())
                out: list[str] = []
                while True:
                    raw = f.readline()
                    if not raw:
                        raise MPDError("MPD connection closed")
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line == "OK":
                        return out
                    if line.startswith("ACK"):
                        if ignore_error:
                            return []
                        raise MPDError(line)
                    out.append(line)
        except Exception:
            if ignore_error:
                return []
            raise


def fields(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            out[key] = value
    return out
