"""
Удаление и статистика логов.

Ответственность:
  - удалить всё;
  - удалить битые строки;
  - отдать статистику.

Задел: delete_older_than, delete_first_n, delete_last_n.
"""

from __future__ import annotations

import logging
from pathlib import Path

from filelock import FileLock, Timeout

from config import LOG_LOCK_TIMEOUT_S, LOG_MAX_LINES, LOG_PATH
from history.models import Run
from history.reader import LogReader

log = logging.getLogger(__name__)


class LogManager:
    """Деструктивные операции над логом и статистика."""

    def __init__(
        self,
        path: Path = LOG_PATH,
        lock_timeout_s: float = LOG_LOCK_TIMEOUT_S,
    ) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.lock_timeout_s = lock_timeout_s
        self.reader = LogReader(path, lock_timeout_s)

    def _with_lock(self, fn):
        """Обёртка: выполнить fn под локом. None при таймауте."""
        lock = FileLock(str(self.lock_path), timeout=self.lock_timeout_s)
        try:
            with lock:
                return fn()
        except Timeout:
            log.warning("лог занят, операция пропущена")
            return None

    def delete_all(self) -> int:
        """Удалить все записи. Возвращает число удалённых."""
        def _do() -> int:
            if not self.path.exists():
                return 0
            n = len(self.path.read_text(encoding="utf-8").splitlines())
            self.path.write_text("", encoding="utf-8")
            return n

        return self._with_lock(_do) or 0

    def delete_broken_lines(self) -> int:
        """Удалить строки, которые не парсятся как Run."""
        def _do() -> int:
            if not self.path.exists():
                return 0
            lines = self.path.read_text(encoding="utf-8").splitlines()
            good: list[str] = []
            removed = 0
            for line in lines:
                try:
                    Run.from_json(line)
                    good.append(line)
                except ValueError:
                    removed += 1
            if removed:
                text = "\n".join(good)
                if text:
                    text += "\n"
                self.path.write_text(text, encoding="utf-8")
            return removed

        return self._with_lock(_do) or 0

    def get_stats(self) -> dict:
        """Статистика: всего, битых, лимит, размер в КБ."""
        lines = self.reader._read_lines()
        broken = self.reader.get_broken_lines()
        size_kb = (
            round(self.path.stat().st_size / 1024, 1)
            if self.path.exists()
            else 0.0
        )
        return {
            "total": len(lines),
            "broken": len(broken),
            "limit": LOG_MAX_LINES,
            "size_kb": size_kb,
        }

    # --------------------------------------------------------- задел

    def delete_older_than(self, days: int) -> int:
        """Задел: удалить записи старше N дней."""
        raise NotImplementedError

    def delete_first_n(self, n: int) -> int:
        """Задел: удалить первые N записей."""
        raise NotImplementedError

    def delete_last_n(self, n: int) -> int:
        """Задел: удалить последние N записей."""
        raise NotImplementedError