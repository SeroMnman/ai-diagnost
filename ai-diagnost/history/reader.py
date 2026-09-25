"""
Чтение и парсинг log.jsonl.

Ответственность:
  - прочитать строки под локом;
  - распарсить в Run;
  - найти битые строки.

Задел на будущее: get_filtered — заглушка.
"""

from __future__ import annotations

import logging
from pathlib import Path

from filelock import FileLock, Timeout

from config import LOG_LOCK_TIMEOUT_S, LOG_PATH
from history.models import Run

log = logging.getLogger(__name__)


class LogReader:
    """Читает Run из log.jsonl."""

    def __init__(
        self,
        path: Path = LOG_PATH,
        lock_timeout_s: float = LOG_LOCK_TIMEOUT_S,
    ) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.lock_timeout_s = lock_timeout_s

    def _read_lines(self) -> list[str]:
        """Все строки файла под локом. Пустой список при занятом локе."""
        if not self.path.exists():
            return []
        lock = FileLock(str(self.lock_path), timeout=self.lock_timeout_s)
        try:
            with lock:
                return self.path.read_text(encoding="utf-8").splitlines()
        except Timeout:
            log.warning("лог занят, чтение пропущено")
            return []

    def get_last(self) -> Run | None:
        """Последний успешно распарсенный Run. None, если логов нет."""
        for line in reversed(self._read_lines()):
            try:
                return Run.from_json(line)
            except ValueError:
                continue
        return None

    def get_all(self) -> list[Run]:
        """Все успешно распарсенные Run в порядке файла."""
        runs: list[Run] = []
        for line in self._read_lines():
            try:
                runs.append(Run.from_json(line))
            except ValueError:
                continue
        return runs

    def get_broken_lines(self) -> list[tuple[int, str]]:
        """Список (номер строки, причина) для всех битых."""
        broken: list[tuple[int, str]] = []
        for i, line in enumerate(self._read_lines(), start=1):
            try:
                Run.from_json(line)
            except ValueError as e:
                broken.append((i, str(e)))
        return broken

    def get_filtered(self, **kwargs) -> list[Run]:
        """Задел: фильтры по дате, интенту, режиму. Следующая итерация."""
        raise NotImplementedError("фильтры — следующая итерация")