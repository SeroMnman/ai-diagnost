"""
Сбор информации о системе.

Ответственность:
  - выполнить команды baseline через executor;
  - распарсить вывод в Baseline;
  - не падать, если что-то не распарсилось.

collect_critical() — для быстрой проверки.
collect_extended() — для полной (critical + расширение).
"""

from __future__ import annotations

import logging
import re

from core import whitelist
from core.executor import run_one
from history.models import Baseline, CommandResult

log = logging.getLogger(__name__)


# ------------------------------------------------------------ парсинг

def _wmic_field(stdout: str, field: str) -> str:
    m = re.search(rf"^{field}=(.*)$", stdout, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _parse_wmic_os(stdout: str) -> str:
    caption = _wmic_field(stdout, "Caption")
    build = _wmic_field(stdout, "BuildNumber")
    if caption and build:
        return f"{caption} (build {build})"
    return caption or "неизвестная ОС"


def _parse_wmic_list(value: str) -> list[str]:
    """'{"a","b"}' → ['a', 'b']."""
    if not value:
        return []
    inner = value.strip().strip("{}")
    if not inner:
        return []
    return [item.strip().strip('"') for item in inner.split(",") if item.strip()]


def _is_ipv4(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _parse_nicconfig(stdout: str) -> dict:
    """
    Находит первый блок с IPv4, не начинающимся на 169.254.
    Возвращает iface, ip, gateway, dns.
    """
    blocks = re.split(r"\r?\n\r?\n", stdout.strip())
    for block in blocks:
        ip_list = _parse_wmic_list(_wmic_field(block, "IPAddress"))
        ipv4 = [
            ip for ip in ip_list
            if _is_ipv4(ip) and not ip.startswith("169.254.")
        ]
        if ipv4:
            gw_list = _parse_wmic_list(_wmic_field(block, "DefaultIPGateway"))
            dns_list = _parse_wmic_list(_wmic_field(block, "DNSServerSearchOrder"))
            return {
                "iface": _wmic_field(block, "Description") or "",
                "ip": ipv4[0],
                "gateway": gw_list[0] if gw_list else "",
                "dns": dns_list,
            }
    return {}


def _parse_uptime(stdout: str) -> str | None:
    m = re.search(r"LastBootUpTime=(\S+)", stdout)
    return m.group(1) if m else None


def _detect_admin(result: CommandResult) -> bool | None:
    """
    net session:
      rc == 0                → админ
      rc != 0, stderr пусто  → не админ
      'service not started'  → неизвестно
    """
    if result.rc == 0:
        return True
    stderr_l = result.stderr.lower()
    if "service" in stderr_l or "служб" in stderr_l:
        return None
    return False


# ------------------------------------------------------------ сбор

def collect_critical() -> tuple[Baseline, list[CommandResult]]:
    """Быстрый baseline: ОС, сеть, маршруты, права."""
    results: list[CommandResult] = []

    argv, to = whitelist.build("wmic_os")
    r_os = run_one("wmic_os", argv, to)
    results.append(r_os)
    os_str = _parse_wmic_os(r_os.stdout)

    argv, to = whitelist.build("wmic_nicconfig")
    r_nic = run_one("wmic_nicconfig", argv, to)
    results.append(r_nic)
    nic = _parse_nicconfig(r_nic.stdout)

    argv, to = whitelist.build("route_print")
    r_route = run_one("route_print", argv, to)
    results.append(r_route)

    argv, to = whitelist.build("net_session")
    r_admin = run_one("net_session", argv, to)
    results.append(r_admin)
    admin = _detect_admin(r_admin)

    baseline = Baseline(
        os=os_str,
        iface=nic.get("iface", ""),
        ip=nic.get("ip", ""),
        gateway=nic.get("gateway", ""),
        dns=nic.get("dns", []),
        admin=admin,
        raw={
            "wmic_os": r_os.stdout,
            "wmic_nicconfig": r_nic.stdout,
            "route_print": r_route.stdout,
        },
    )
    return baseline, results


def collect_extended() -> tuple[Baseline, list[CommandResult]]:
    """Расширенный baseline: critical + arp + netstat + uptime."""
    baseline, results = collect_critical()

    argv, to = whitelist.build("arp")
    r_arp = run_one("arp", argv, to)
    results.append(r_arp)
    baseline.raw["arp"] = r_arp.stdout

    argv, to = whitelist.build("netstat")
    r_netstat = run_one("netstat", argv, to)
    results.append(r_netstat)
    baseline.raw["netstat"] = r_netstat.stdout

    argv, to = whitelist.build("wmic_uptime")
    r_uptime = run_one("wmic_uptime", argv, to)
    results.append(r_uptime)
    baseline.uptime = _parse_uptime(r_uptime.stdout)

    return baseline, results