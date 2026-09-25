"""
Белый список команд и валидация аргументов.

Задача: превратить action_id + параметры в готовый list[str]
для subprocess, отсеяв всё подозрительное на входе.

Никаких shell-строк. Только список аргументов.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Callable


class WhitelistError(ValueError):
    """Аргумент не прошёл валидацию или action_id неизвестен."""


# ------------------------------------------------------------ валидация

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,63}$"
)

_IFACE_RE = re.compile(r"^[A-Za-z0-9 _\-]{1,64}$")


def validate_ip(value: str) -> str:
    """IPv4 или IPv6. Возвращает нормализованную строку."""
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError as e:
        raise WhitelistError(f"некорректный IP: {value!r}") from e


def validate_domain(value: str) -> str:
    """Домен. Без схемы, без пути, без порта."""
    v = value.strip().lower().rstrip(".")
    if not _DOMAIN_RE.match(v):
        raise WhitelistError(f"некорректный домен: {value!r}")
    return v


def validate_iface(value: str) -> str:
    """Имя интерфейса. Разрешаем пробелы (у Windows бывают)."""
    v = value.strip()
    if not _IFACE_RE.match(v):
        raise WhitelistError(f"некорректное имя интерфейса: {value!r}")
    return v


# ------------------------------------------------------------ описание

@dataclass(frozen=True)
class CommandSpec:
    """
    Описание одной команды в белом списке.

    action_id   — идентификатор для pipeline и логов.
    builder     — функция, собирающая list[str].
    timeout_s   — индивидуальный таймаут.
    description — человекочитаемое описание.
    """

    action_id: str
    builder: Callable
    timeout_s: float | None = None
    description: str = ""


# ------------------------------------------------------------ builders

def _b_ping() -> list[str]:
    return ["ping", "-n", "4", "8.8.8.8"]


def _b_ping_gateway(gateway: str) -> list[str]:
    return ["ping", "-n", "4", validate_ip(gateway)]


def _b_ping_alt() -> list[str]:
    return ["ping", "-n", "4", "77.88.44.242"]


def _b_ping_big_quick() -> list[str]:
    return ["ping", "-n", "10", "-l", "1400", "8.8.8.8"]


def _b_ping_big_full() -> list[str]:
    return ["ping", "-n", "50", "-l", "1400", "8.8.8.8"]


def _b_ping_mtu() -> list[str]:
    # 1472 + 28 = 1500, стандартный MTU.
    return ["ping", "-n", "4", "-l", "1472", "-f", "8.8.8.8"]


def _b_ping_domain(domain: str) -> list[str]:
    return ["ping", "-n", "4", validate_domain(domain)]


def _b_nslookup(domain: str) -> list[str]:
    return ["nslookup", validate_domain(domain)]


def _b_tracert() -> list[str]:
    return ["tracert", "-d", "-h", "15", "8.8.8.8"]


def _b_ipconfig() -> list[str]:
    return ["ipconfig", "/all"]


def _b_route_print() -> list[str]:
    return ["route", "print"]


def _b_arp() -> list[str]:
    return ["arp", "-a"]


def _b_netstat() -> list[str]:
    return ["netstat", "-ano"]


def _b_wmic_os() -> list[str]:
    return ["wmic", "os", "get", "Caption,Version,BuildNumber", "/value"]


def _b_wmic_nicconfig() -> list[str]:
    return [
        "wmic", "nicconfig", "get",
        "IPAddress,DefaultIPGateway,DNSServerSearchOrder,Description",
        "/format:list",
    ]


def _b_wmic_uptime() -> list[str]:
    return ["wmic", "os", "get", "LastBootUpTime", "/value"]


def _b_net_session() -> list[str]:
    return ["net", "session"]


def _b_flush_dns() -> list[str]:
    return ["ipconfig", "/flushdns"]


def _b_release_ip() -> list[str]:
    return ["ipconfig", "/release"]


def _b_renew_ip() -> list[str]:
    return ["ipconfig", "/renew"]


# ------------------------------------------------------------ реестр

COMMANDS: dict[str, CommandSpec] = {
    # baseline — критический
    "wmic_os":         CommandSpec("wmic_os",         _b_wmic_os,         timeout_s=5.0,  description="ОС и версия"),
    "wmic_nicconfig":  CommandSpec("wmic_nicconfig",  _b_wmic_nicconfig,  timeout_s=10.0, description="Сетевые интерфейсы"),
    "ipconfig":        CommandSpec("ipconfig",        _b_ipconfig,        timeout_s=5.0,  description="ipconfig /all"),
    "route_print":     CommandSpec("route_print",     _b_route_print,     timeout_s=5.0,  description="Таблица маршрутов"),
    "net_session":     CommandSpec("net_session",     _b_net_session,     timeout_s=5.0,  description="Проверка прав"),

    # baseline — расширенный
    "arp":             CommandSpec("arp",             _b_arp,             timeout_s=5.0,  description="ARP-таблица"),
    "netstat":         CommandSpec("netstat",         _b_netstat,         timeout_s=10.0, description="Открытые соединения"),
    "wmic_uptime":     CommandSpec("wmic_uptime",     _b_wmic_uptime,     timeout_s=5.0,  description="Время загрузки"),

    # диагностика — быстрая
    "ping_gateway":    CommandSpec("ping_gateway",    _b_ping_gateway,    timeout_s=10.0, description="Пинг шлюза"),
    "ping_8888":       CommandSpec("ping_8888",       _b_ping,            timeout_s=10.0, description="Пинг 8.8.8.8"),
    "ping_alt":        CommandSpec("ping_alt",        _b_ping_alt,        timeout_s=10.0, description="Пинг 77.88.44.242"),
    "ping_big_q":      CommandSpec("ping_big_q",      _b_ping_big_quick,  timeout_s=30.0, description="Пинг 10×1400"),
    "tracert":         CommandSpec("tracert",         _b_tracert,         timeout_s=60.0, description="Трассировка"),

    # диагностика — полная
    "ping_big_f":      CommandSpec("ping_big_f",      _b_ping_big_full,   timeout_s=90.0, description="Пинг 50×1400"),
    "ping_mtu":        CommandSpec("ping_mtu",        _b_ping_mtu,        timeout_s=15.0, description="MTU-тест"),

    # диагностика — по домену
    "ping_domain":     CommandSpec("ping_domain",     _b_ping_domain,     timeout_s=15.0, description="Пинг домена"),
    "nslookup":        CommandSpec("nslookup",        _b_nslookup,        timeout_s=10.0, description="DNS-запрос"),

    # действия
    "flush_dns":       CommandSpec("flush_dns",       _b_flush_dns,       timeout_s=10.0, description="Сбросить DNS"),
    "release_ip":      CommandSpec("release_ip",      _b_release_ip,      timeout_s=15.0, description="Освободить IP"),
    "renew_ip":        CommandSpec("renew_ip",        _b_renew_ip,        timeout_s=30.0, description="Обновить IP"),
}


# ------------------------------------------------------------ сборка

def build(action_id: str, **kwargs) -> tuple[list[str], float]:
    """
    Вернуть (argv, timeout_s) для action_id.

    Бросает WhitelistError при неизвестном action_id или
    непрошедших валидацию аргументах.
    """
    spec = COMMANDS.get(action_id)
    if spec is None:
        raise WhitelistError(f"неизвестный action_id: {action_id!r}")
    argv = spec.builder(**kwargs)
    timeout = spec.timeout_s if spec.timeout_s is not None else 10.0
    return argv, timeout