"""
Анализ результатов проверки через LLM (GigaChat).
"""

from __future__ import annotations

import json
import logging
import re
import uuid

import requests
from openai import OpenAI

from config import (
    GIGACHAT_BASE_URL,
    GIGACHAT_CLIENT_SECRET,
    GIGACHAT_SCOPE,
    LLM_MODEL,
)
from core.intent import IntentResult
from history.models import Baseline, CommandResult, Verdict

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты сетевой диагност. Тебе дают снимок системы и вывод диагностических команд.
Определи наиболее вероятную причину проблемы.

Верни СТРОГО JSON:
{
  "cause": "краткая причина на русском (1 строка)",
  "confidence": "low" | "medium" | "high",
  "actions": ["action_id1", "action_id2"],
  "details": "развёрнутое объяснение на русском (2-5 предложений)"
}
"""

ALLOWED_ACTIONS = [
    "flush_dns", "renew_ip", "release_ip",
    "ping_gateway", "ping_8888", "ping_alt",
    "ping_big_q", "ping_domain", "nslookup", "tracert",
]


# ------------------------------------------------------------ OAuth

def _get_gigachat_token() -> str:
    """
    Получить access-токен GigaChat.
    Токен действует 30 минут. Для нашего объёма запрашиваем каждый раз.
    """
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Bearer {GIGACHAT_CLIENT_SECRET}",
    }
    data = {"scope": GIGACHAT_SCOPE}

    resp = requests.post(url, headers=headers, data=data, timeout=15, verify=False)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ------------------------------------------------------------ форматирование

def _format_baseline(b: Baseline) -> str:
    lines = [
        f"OS: {b.os}",
        f"Interface: {b.iface or 'неизвестно'}",
        f"IP: {b.ip or 'неизвестно'}",
        f"Gateway: {b.gateway or 'неизвестно'}",
        f"DNS: {', '.join(b.dns) if b.dns else 'неизвестно'}",
        f"Admin: {b.admin}",
    ]
    if b.uptime:
        lines.append(f"Last boot: {b.uptime}")
    return "\n".join(lines)


def _format_commands(commands: list[CommandResult]) -> str:
    blocks = []
    for c in commands:
        if c.skipped:
            blocks.append(f"$ {c.cmd}\n[пропущено из-за раннего выхода]")
            continue
        header = f"$ {c.cmd}  (rc={c.rc}, {c.duration_s}s)"
        body = c.stdout.strip() or c.stderr.strip() or "[пусто]"
        if len(body) > 2000:
            body = body[:2000] + "\n...[обрезано]"
        blocks.append(f"{header}\n{body}")
    return "\n\n".join(blocks)


def _build_user_message(request, intent, baseline, commands) -> str:
    return (
        f"Запрос пользователя: {request}\n"
        f"Определённый интент: {intent.intent}\n"
        f"Домен (если есть): {intent.domain or 'нет'}\n\n"
        f"=== BASELINE ===\n{_format_baseline(baseline)}\n\n"
        f"=== КОМАНДЫ ===\n{_format_commands(commands)}\n\n"
        f"=== ДОПУСТИМЫЕ action_id ===\n{', '.join(ALLOWED_ACTIONS)}\n"
    )


# ------------------------------------------------------------ парсинг

def _strip_markdown(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _parse_verdict(raw: str) -> Verdict:
    cleaned = _strip_markdown(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"ответ модели не JSON: {e}") from e

    cause = str(data.get("cause", "")).strip()
    confidence = str(data.get("confidence", "low")).lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "low"

    raw_actions = data.get("actions", [])
    if not isinstance(raw_actions, list):
        raw_actions = []
    actions = [a for a in raw_actions if a in ALLOWED_ACTIONS]

    details = str(data.get("details", "")).strip()

    if not cause:
        raise ValueError("пустой cause в ответе модели")

    return Verdict(cause=cause, confidence=confidence, actions=actions, details=details)


def _fallback_verdict(reason: str) -> Verdict:
    return Verdict(
        cause="не удалось получить автоматический анализ",
        confidence="low",
        actions=[],
        details=reason,
    )


# ------------------------------------------------------------ основной вызов

def analyze(request, intent, baseline, commands) -> Verdict:
    """
    Отправить данные в GigaChat и вернуть Verdict.
    Никогда не бросает: при ошибке — fallback-Verdict.
    """
    if not GIGACHAT_CLIENT_SECRET:
        return _fallback_verdict(
            "GIGACHAT_CLIENT_SECRET не задан. Проверь .env."
        )

    # Получаем токен
    try:
        token = _get_gigachat_token()
    except Exception as e:
        log.exception("не удалось получить токен GigaChat")
        return _fallback_verdict(f"Ошибка авторизации GigaChat: {e}")

    client = OpenAI(api_key=token, base_url=GIGACHAT_BASE_URL)
    user_msg = _build_user_message(request, intent, baseline, commands)

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
    except Exception as e:
        log.exception("ошибка вызова GigaChat")
        return _fallback_verdict(f"Ошибка обращения к GigaChat: {e}")

    raw = response.choices[0].message.content or ""

    try:
        return _parse_verdict(raw)
    except ValueError as e:
        log.warning("не удалось распарсить ответ модели: %s", e)
        return _fallback_verdict(
            f"Модель вернула неожиданный ответ. Сырой текст: {raw[:500]}"
        )