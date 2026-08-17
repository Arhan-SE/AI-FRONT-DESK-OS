"""Preflight check. Run before a demo:

    make dev-check

Catches the failures that are embarrassing to discover on stage: a process
down, a missing credential, or — the one that cost an evening — LiveKit
advertising an IP address the machine no longer has.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys

from genesis.db import pool
from genesis.settings import settings

OK, WARN, FAIL = "  ok  ", " warn ", " FAIL "


def _line(state: str, label: str, detail: str = "") -> None:
    print(f"[{state}] {label:<26} {detail}")


def _port_open(port: int) -> bool:
    """Try every address localhost resolves to.

    Vite binds IPv6 only, so an IPv4-only probe reports it as down while a
    browser reaches it perfectly well. A preflight that cries wolf is worse
    than no preflight.
    """
    try:
        candidates = socket.getaddrinfo("localhost", port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    for family, socktype, proto, _canon, addr in candidates:
        with socket.socket(family, socktype, proto) as s:
            s.settimeout(1.0)
            if s.connect_ex(addr) == 0:
                return True
    return False


def _udp_bound_address(port: int) -> str | None:
    """Which address holds the UDP media socket, via lsof."""
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iUDP:{port}"],
            capture_output=True, text=True, timeout=5,
        ).stdout.splitlines()
    except Exception:
        return None
    for row in out[1:]:
        parts = row.split()
        if parts and ":" in parts[-1]:
            return parts[-1].rsplit(":", 1)[0]
    return None


def _machine_ips() -> set[str]:
    ips = {"127.0.0.1"}
    for iface in ("en0", "en1"):
        try:
            ip = subprocess.run(
                ["ipconfig", "getifaddr", iface],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            if ip:
                ips.add(ip)
        except Exception:
            pass
    return ips


def check_livekit() -> bool:
    """The media socket's address must still belong to this machine.

    LiveKit picks an address at startup and advertises it to browsers. If the
    machine's IP changes afterwards, signalling still connects — so the browser
    reports a generic disconnect — while media is sent to an address that no
    longer exists.
    """
    if not _port_open(7880):
        _line(FAIL, "LiveKit", "not running — start it with `make livekit`")
        return False

    bound = _udp_bound_address(7882)
    if bound is None:
        _line(WARN, "LiveKit", "running, but the media socket could not be inspected")
        return True

    if bound in _machine_ips():
        _line(OK, "LiveKit", f"media on {bound}:7882, address is current")
        return True

    _line(
        FAIL,
        "LiveKit",
        f"advertising {bound} but this machine is {', '.join(sorted(_machine_ips() - {'127.0.0.1'}))
        or 'offline'} — RESTART `make livekit`",
    )
    return False


async def main() -> None:
    ok = True

    for label, port in (("API", 8000), ("Dashboard", 5173)):
        if _port_open(port):
            _line(OK, label, f"listening on :{port}")
        else:
            _line(FAIL, label, f"nothing on :{port}")
            ok = False

    ok &= check_livekit()

    try:
        health = await pool.healthcheck()
        _line(
            OK,
            "Database",
            f"postgres {health['postgres']} · {health['customers']} customers, "
            f"{health['appointments']} jobs",
        )
    except Exception as exc:
        _line(FAIL, "Database", str(exc)[:70])
        ok = False
    finally:
        await pool.close_pool()

    _line(OK if settings.ai_enabled else FAIL, "OpenAI key",
          "set" if settings.ai_enabled else "missing — voice will not work")
    ok &= settings.ai_enabled

    if settings.telegram_enabled:
        _line(OK, "Telegram", "token set")
    else:
        _line(WARN, "Telegram", "no token — outreach will be blocked by the Guard")

    print()
    print("Ready." if ok else "Not ready — fix the FAIL lines above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
