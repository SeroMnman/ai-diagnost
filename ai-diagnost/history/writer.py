"""
Запись прогонов в log.jsonl.

Ответственность:
  - взять лок на файл (filelock);
  - дописать одну строку;
  - обрезать верхние при переполнении;
  - отпустить лок.

Никакой логики парсинга или удаления здесь нет.
"""

from __future__ import annotations

import logging
from pathlib import Path

from filelock import FileLock, Timeout

from config import LOG_LOCK_TIMEOUT_S, LOG_MAX_LINES, LOG_PATH
from history.models import Run

log = logging.getLogger(__name__)


class LogWriter:
    """Пишет Run в log.jsonl с локом и авто-обрезкой."""

    def __init__(
        self,
        path: Path = LOG_PATH,
        max_lines: int = LOG_MAX_LINES,
        lock_timeout_s: float = LOG_LOCK_TIMEOUT_S,
    ) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.max_lines = max_lines
        self.lock_timeout_s = lock_timeout_s
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, run: Run) -> bool:
        """
        Дописать Run в лог.

        True — успех. False — лог занят, запись пропущена.
        Второй случай не ошибка: пользователь получит результат
        на экране, просто он не попадёт в историю.
        """
        lock = FileLock(str(self.lock_path), timeout=self.lock_timeout_s)
        try:
            with lock:
                self._trim_if_needed()
                self._append_line(run.to_json())
            return True
        except Timeout:
            log.warning(
                "не удалось взять лок на %s за %.1f с — запись пропущена",
                self.path,
                self.lock_timeout_s,
            )
            return False

    def _append_line(self, line: str) -> None:
        """Append + flush. Файл всегда в UTF-8."""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")
            f.flush()

    def _trim_if_needed(self) -> None:
        """
        Если строк >= max_lines, оставить последние (max_lines - 1).
        Вызывается под локом — гонок нет.
        """
        if not self.path.exists():
            return

        lines = self.path.read_text(encoding="utf-8").splitlines()
        if len(lines) < self.max_lines:
            return

        keep = lines[-(self.max_lines - 1):]
        log.info(
            "лог переполнен (%d строк), обрезаю до %d",
            len(lines),
            len(keep),
        )
        self.path.write_text("\n".join(keep) + "\n", encoding="utf-8")