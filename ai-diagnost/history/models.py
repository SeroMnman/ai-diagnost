"""
Модели данных приложения.

Центральный объект — Run. Всё остальное — его составные части.
Сериализация в JSON и обратно живёт здесь же, чтобы writer/reader
не знали деталей формата.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Baseline:
    """Снимок системы на момент проверки."""

    os: str
    iface: str
    ip: str
    gateway: str
    dns: list[str] = field(default_factory=list)
    admin: bool | None = None
    uptime: str | None = None
    mac: str | None = None
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class CommandResult:
    """Результат одной команды."""

    cmd: str
    rc: int
    stdout: str
    stderr: str
    duration_s: float
    summary: str = ""
    skipped: bool = False


@dataclass
class Verdict:
    """Вердикт ИИ по результатам проверки."""

    cause: str
    confidence: str  # "low" | "medium" | "high"
    actions: list[str] = field(default_factory=list)
    details: str = ""


@dataclass
class Run:
    """Один полный прогон. Одна строка в log.jsonl."""

    run_id: str
    ts_start: str
    ts_end: str
    mode: str  # "quick" | "full"
    request: str
    intent: str
    baseline: Baseline
    commands: list[CommandResult]
    verdict: Verdict
    early_exit: bool = False
    duration_s: float = 0.0

    def to_json(self) -> str:
        """Run → одна строка JSON, без переносов."""
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, line: str) -> "Run":
        """
        Строка JSON → Run.

        Бросает ValueError при невалидном JSON или несоответствии
        структуры. Reader ловит это и помечает строку как битую.
        """
        try:
            data: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"не JSON: {e}") from e

        try:
            baseline = Baseline(**data["baseline"])
            commands = [CommandResult(**c) for c in data["commands"]]
            verdict = Verdict(**data["verdict"])
            return cls(
                run_id=data["run_id"],
                ts_start=data["ts_start"],
                ts_end=data["ts_end"],
                mode=data["mode"],
                request=data["request"],
                intent=data["intent"],
                baseline=baseline,
                commands=commands,
                verdict=verdict,
                early_exit=data.get("early_exit", False),
                duration_s=data.get("duration_s", 0.0),
            )
        except (KeyError, TypeError) as e:
            raise ValueError(f"структура не соответствует Run: {e}") from e