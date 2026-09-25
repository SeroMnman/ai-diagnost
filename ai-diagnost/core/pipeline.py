"""
Оркестрация проверки.

Ответственность:
  - определить пул команд по интенту и режиму;
  - собрать baseline;
  - выполнить команды с ранним выходом (только quick);
  - отправить в analyzer;
  - собрать Run.

Никакой работы с файлами логов и UI. Только логика прогона.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Callable

from core import baseline as baseline_mod
from core import whitelist
from core.analyzer import analyze
from core.executor import run_one
from core.intent import (
    INTENT_INTERNET_DOWN,
    INTENT_SITE_UNREACHABLE,
    INTENT_SLOW,
    INTENT_UNKNOWN,
    classify,
)
from history.models import CommandResult, Run

log = logging.getLogger(__name__)


# ------------------------------------------------------------ пулы

POOLS: dict[str, dict[str, list[str]]] = {
    INTENT_INTERNET_DOWN: {
        "quick": ["ping_gateway", "ping_8888", "ping_alt", "tracert"],
        "full":  ["ping_gateway", "ping_8888", "ping_alt",
                  "ping_big_f", "ping_mtu", "tracert"],
    },
    INTENT_SITE_UNREACHABLE: {
        "quick": ["ping_gateway", "ping_8888", "nslookup",
                  "ping_domain", "tracert"],
        "full":  ["ping_gateway", "ping_8888", "nslookup",
                  "ping_domain", "tracert", "ping_big_f", "ping_mtu"],
    },
    INTENT_SLOW: {
        "quick": ["ping_gateway", "ping_8888", "ping_big_q", "tracert"],
        "full":  ["ping_gateway", "ping_8888", "ping_big_f",
                  "ping_mtu", "tracert"],
    },
    INTENT_UNKNOWN: {
        "quick": ["ping_gateway", "ping_8888", "ping_alt"],
        "full":  ["ping_gateway", "ping_8888", "ping_alt",
                  "ping_big_f", "tracert"],
    },
}


# ------------------------------------------------------------ ранний выход

def _ping_failed(result: CommandResult) -> bool:
    if result.rc != 0:
        return True
    if result.summary.startswith("loss 100%"):
        return True
    return False


def _should_continue(
    prev: dict[str, CommandResult],
    next_action: str,
) -> bool:
    """
    prev — словарь action_id → CommandResult для выполненных.
    next_action — что собираемся запускать.

    True, если запускать имеет смысл.
    """
    gw = prev.get("ping_gateway")
    external = prev.get("ping_8888")

    # Шлюз не пингуется — стоп всему.
    if gw is not None and _ping_failed(gw):
        return False

    # Внешний пинг не прошёл — пропускаем всё, что требует связи.
    if external is not None and _ping_failed(external):
        if next_action in ("ping_big_q", "ping_big_f", "ping_mtu", "tracert"):
            return False

    return True


# ------------------------------------------------------------ выполнение

def _execute_pool(
    pool: list[str],
    mode: str,
    domain: str | None,
    gateway: str | None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[list[CommandResult], bool]:
    """Выполнить пул команд с ранним выходом (только quick)."""
    results: list[CommandResult] = []
    by_id: dict[str, CommandResult] = {}
    early_exit = False

    for idx, action_id in enumerate(pool):
        if on_progress:
            on_progress(idx, len(pool), action_id)

        if mode == "quick" and not _should_continue(by_id, action_id):
            log.info("ранний выход: пропускаем %s", action_id)
            result = CommandResult(
                cmd=f"[{action_id}]",
                rc=0,
                stdout="",
                stderr="",
                duration_s=0.0,
                summary="пропущено",
                skipped=True,
            )
            results.append(result)
            by_id[action_id] = result
            early_exit = True
            continue

        # Сборка kwargs под конкретный action_id.
        kwargs: dict[str, str] = {}
        if action_id in ("ping_domain", "nslookup") and domain:
            kwargs["domain"] = domain
        elif action_id == "ping_gateway":
            if not gateway:
                # Шлюз не определён в baseline — пропускаем без запуска.
                log.warning("ping_gateway: шлюз не определён, пропускаем")
                result = CommandResult(
                    cmd="[ping_gateway]",
                    rc=-5,
                    stdout="",
                    stderr="шлюз не определён в baseline",
                    duration_s=0.0,
                    summary="нет шлюза",
                    skipped=True,
                )
                results.append(result)
                by_id[action_id] = result
                continue
            kwargs["gateway"] = gateway

        try:
            argv, timeout = whitelist.build(action_id, **kwargs)
        except whitelist.WhitelistError as e:
            log.error("сборка команды %s упала: %s", action_id, e)
            result = CommandResult(
                cmd=f"[{action_id}]",
                rc=-4,
                stdout="",
                stderr=f"ошибка сборки: {e}",
                duration_s=0.0,
                summary="ошибка",
            )
            results.append(result)
            by_id[action_id] = result
            continue

        result = run_one(action_id, argv, timeout)
        results.append(result)
        by_id[action_id] = result

    if on_progress:
        on_progress(len(pool), len(pool), "готово")

    return results, early_exit


# ------------------------------------------------------------ основной вход

def run_check(
    request: str,
    mode: str,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> Run:
    """
    Полный прогон проверки.

    mode: 'quick' | 'full'.
    on_progress: колбэк для UI.

    Никогда не бросает: при ошибке возвращает Run с fallback-Verdict.
    """
    if mode not in ("quick", "full"):
        raise ValueError(f"неизвестный режим: {mode!r}")

    run_id = _make_run_id()
    ts_start = datetime.now().isoformat(timespec="seconds")

    # --- baseline
    log.info("baseline: старт")
    if mode == "quick":
        baseline, baseline_cmds = baseline_mod.collect_critical()
    else:
        baseline, baseline_cmds = baseline_mod.collect_extended()

    # --- intent
    intent_result = classify(request)
    log.info("intent: %s (%s)", intent_result.intent, intent_result.matched_by)

    # --- пул
    pool = POOLS.get(intent_result.intent, POOLS[INTENT_UNKNOWN])[mode]

    # --- выполнение
    diag_results, early_exit = _execute_pool(
        pool, mode, intent_result.domain, baseline.gateway, on_progress
    )

    all_commands = baseline_cmds + diag_results

    # --- анализ
    verdict = analyze(request, intent_result, baseline, all_commands)

    ts_end = datetime.now().isoformat(timespec="seconds")
    duration = (
        datetime.fromisoformat(ts_end) - datetime.fromisoformat(ts_start)
    ).total_seconds()

    return Run(
        run_id=run_id,
        ts_start=ts_start,
        ts_end=ts_end,
        mode=mode,
        request=request,
        intent=intent_result.intent,
        baseline=baseline,
        commands=all_commands,
        verdict=verdict,
        early_exit=early_exit,
        duration_s=round(duration, 2),
    )


def _make_run_id() -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:3]
    return f"{ts}-{suffix}"