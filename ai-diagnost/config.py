"""
Единая точка конфигурации.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------------------ пути

APPDATA = Path(os.getenv("APPDATA", str(Path.home())))
APP_DIR = APPDATA / "ai-diagnost"
LOG_DIR = APP_DIR / "logs"
LOG_PATH = LOG_DIR / "log.jsonl"

# ------------------------------------------------------------------ логи

LOG_MAX_LINES = int(os.getenv("LOG_MAX_LINES", "1000"))
LOG_LOCK_TIMEOUT_S = float(os.getenv("LOG_LOCK_TIMEOUT_S", "5.0"))

# ------------------------------------------------------------------ ИИ

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gigachat")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_BASE_URL = "https://api.giga.chat/v1"
LLM_MODEL = os.getenv("LLM_MODEL", "GigaChat")

# ------------------------------------------------------------------ команды

CMD_TIMEOUT_S = float(os.getenv("CMD_TIMEOUT_S", "10.0"))
CMD_OUTPUT_LIMIT = int(os.getenv("CMD_OUTPUT_LIMIT", "10000"))