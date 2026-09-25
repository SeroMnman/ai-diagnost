"""
Запуск команд и парсинг кратких выжимок.

Ответственность:
  - запустить argv через subprocess.run без shell=True;
  - ограничить вывод по размеру;
  - соблюсти таймаут;
  - собрать summary через регулярки.

Никаких решений о том, что запускать. Только исполнение.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time

from config import CMD_OUTPUT_LIMIT, CMD_TIMEOUT_S
from history.models import CommandResult

log = logging.getLogger(__name__)


# ------------------------------------------------------------ summary

def _summarize_ping(stdout: str) -> str:
    """'loss 0%, avg 4ms' или 'loss 100%'."""
    loss_m = re.search(r"\((\d+)%\s*loss\)", stdout)
    avg_m = re.search(r"Average\s*=\s*(\d+)ms", stdout)
    if not loss_m:
        return "нет статистики"
    loss = int(loss_m.group(1))
    avg = f", avg {avg_m.group(1)}ms" if avg_m else ""
    return f"loss {loss}%{avg}"


def _summarize_tracert(stdout: str) -> str:
    """'hops N, last K'."""
    hops = re.findall(r"^\s*(\d+)\s+", stdout, re.MULTILINE)
    if not hops:
        return "нет данных"
    return f"hops {len(hops)}, last {hops[-1]}"


def _summarize_nslookup(stdout: str) -> str:
    m = re.search(r"Address:\s*([0-9a-fA-F:.]+)", stdout)
    return f"addr {m.group(1)}" if m else "нет ответа"


def _summarize_ipconfig(stdout: str) -> str:
    ip_m = re.search(r"IPv4.*?:\s*([0-9.]+)", stdout)
    gw_m = re.search(r"Default Gateway.*?:\s*([0-9.]+)", stdout)
    parts = []
    if ip_m:
        parts.append(f"ip {ip_m.group(1)}")
    if gw_m:
        parts.append(f"gw {gw_m.group(1)}")
    return ", ".join(parts) if parts else "нет данных"


def _summarize_route(stdout: str) -> str:
    n = len(re.findall(r"^\s*0\.0\.0\.0", stdout, re.MULTILINE))
    return f"default routes {n}"


def _summarize_netstat(stdout: str) -> str:
    return f"established {stdout.count('ESTABLISHED')}"


def _summarize_wmic_os(stdout: str) -> str:
    m = re.search(r"Caption=(.+)", stdout)
    return m.group(1).strip() if m else "нет данных"


def _summarize_nicconfig(stdout: str) -> str:
    m = re.search(r'IPAddress=\{"([0-9.]+)"', stdout)
    return f"ip {m.group(1)}" if m else "нет данных"


def _summarize_uptime(stdout: str) -> str:
    m = re.search(r"LastBootUpTime=(\S+)", stdout)
    return f"boot {m.group(1)}" if m else ""


def _summarize_flush(stdout: str) -> str:
    return "выполнено"


_SUMMARIZERS = {
    "ping_gateway":   _summarize_ping,
    "ping_8888":      _summarize_ping,
    "ping_alt":       _summarize_ping,
    "ping_big_q":     _summarize_ping,
    "ping_big_f":     _summarize_ping,
    "ping_mtu":       _summarize_ping,
    "ping_domain":    _summarize_ping,
    "tracert":        _summarize_tracert,
    "nslookup":       _summarize_nslookup,
    "ipconfig":       _summarize_ipconfig,
    "route_print":    _summarize_route,
    "netstat":        _summarize_netstat,
    "wmic_os":        _summarize_wmic_os,
    "wmic_nicconfig": _summarize_nicconfig,
    "wmic_uptime":    _summarize_uptime,
    "flush_dns":      _summarize_flush,
    "release_ip":     _summarize_flush,
    "renew_ip":       _summarize_flush,
}


def _summarize(action_id: str, stdout: str) -> str:
    fn = _SUMMARIZERS.get(action_id)
    if fn is None:
        return ""
    try:
        return fn(stdout)
    except Exception as e:  # noqa: BLE001
        log.debug("summarizer упал для %s: %s", action_id, e)
        return ""


# ------------------------------------------------------------ запуск

def run_one(
    action_id: str,
    argv: list[str],
    timeout_s: float = CMD_TIMEOUT_S,
) -> CommandResult:
    """
    Запустить одну команду.

    Никогда не бросает: любая ошибка упаковывается в CommandResult
    с отрицательным rc.
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            shell=False,
        )
        duration = time.monotonic() - start
        stdout = (proc.stdout or "")[:CMD_OUTPUT_LIMIT]
        stderr = (proc.stderr or "")[:CMD_OUTPUT_LIMIT]
        return CommandResult(
            cmd=" ".join(argv),
            rc=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_s=round(duration, 2),
            summary=_summarize(action_id, stdout),
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            cmd=" ".join(argv),
            rc=-1,
            stdout="",
            stderr=f"таймаут {timeout_s} с",
            duration_s=round(time.monotonic() - start, 2),
            summary="таймаут",
        )
    except FileNotFoundError as e:
        return CommandResult(
            cmd=" ".join(argv),
            rc=-2,
            stdout="",
            stderr=f"команда не найдена: {e}",
            duration_s=round(time.monotonic() - start, 2),
            summary="не найдена",
        )
    except Exception as e:  # noqa: BLE001
        return CommandResult(
            cmd=" ".join(argv),
            rc=-3,
            stdout="",
            stderr=f"ошибка запуска: {e}",
            duration_s=round(time.monotonic() - start, 2),
            summary="ошибка",
        )