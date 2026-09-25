"""
Классификация запроса пользователя в intent.

MVP: правила по ключевым словам. Быстро, детерминированно.
Задел: LLM-классификатор, если правил не хватит.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


INTENT_INTERNET_DOWN = "internet_down"
INTENT_SITE_UNREACHABLE = "site_unreachable"
INTENT_SLOW = "slow"
INTENT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentResult:
    intent: str
    domain: str | None = None
    matched_by: str = ""


_RULES: list[tuple[str, re.Pattern, str]] = [
    (
        INTENT_SITE_UNREACHABLE,
        re.compile(
            r"(?:не\s+открыва|не\s+груз|не\s+работа|недоступ|"
            r"не\s+загружа)",
            re.IGNORECASE,
        ),
        "site_unreachable_kw",
    ),
    (
        INTENT_INTERNET_DOWN,
        re.compile(
            r"(?:нет\s+интернет|интернет\s+(?:пропал|упал|отвалил)|"
            r"не\s+подключ|нет\s+сети|без\s+интернета)",
            re.IGNORECASE,
        ),
        "internet_down_kw",
    ),
    (
        INTENT_SLOW,
        re.compile(
            r"(?:медлен|тормоз|лагает|низкая\s+скорость|"
            r"долго\s+груз)",
            re.IGNORECASE,
        ),
        "slow_kw",
    ),
]


_DOMAIN_RE = re.compile(
    r"\b((?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,63})\b"
)


def _extract_domain(text: str) -> str | None:
    m = _DOMAIN_RE.search(text)
    return m.group(1).lower() if m else None


def classify(request: str) -> IntentResult:
    """Определить intent по запросу."""
    text = request.strip()
    if not text:
        return IntentResult(INTENT_UNKNOWN, matched_by="empty")

    for intent, pattern, tag in _RULES:
        if pattern.search(text):
            domain = _extract_domain(text)
            if intent == INTENT_SITE_UNREACHABLE and not domain:
                return IntentResult(
                    INTENT_UNKNOWN,
                    matched_by=f"{tag}_no_domain",
                )
            return IntentResult(intent, domain=domain, matched_by=tag)

    return IntentResult(
        INTENT_UNKNOWN,
        domain=_extract_domain(text),
        matched_by="no_rule",
    )