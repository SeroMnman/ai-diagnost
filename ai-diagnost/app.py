"""
Точка входа Streamlit. Один экран.

- инфо-панели (хранилище, битые записи)
- поле ввода запроса
- кнопки «Быстрая проверка» / «Полная проверка»
- прогресс во время выполнения
- результат последнего прогона (из session_state)
- кнопки «Показать последний лог» / «Очистить логи»
"""

from __future__ import annotations

import logging

import streamlit as st

from core.pipeline import run_check
from history.manager import LogManager
from history.reader import LogReader
from history.writer import LogWriter
from ui.panels import render_broken_warning, render_storage_full
from ui.viewer import render_run

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="AI-диагност", layout="wide")
st.title("AI-диагност ПК и сети")

# ------------------------------------------------------------ инфо-панели

manager = LogManager()
stats = manager.get_stats()

if stats["total"] >= stats["limit"]:
    render_storage_full(stats)

if stats["broken"] > 0:
    render_broken_warning(stats)

# ------------------------------------------------------------ форма

request = st.text_input(
    "Опиши проблему",
    placeholder="нет интернета / не открывается ozon.ru / медленно работает",
)

col1, col2 = st.columns(2)
with col1:
    quick = st.button("Быстрая проверка", use_container_width=True)
with col2:
    full = st.button("Полная проверка", use_container_width=True)

# ------------------------------------------------------------ запуск

if quick or full:
    if not request.strip():
        st.warning("Введи описание проблемы.")
    else:
        mode = "quick" if quick else "full"
        progress = st.progress(0.0, text="Сбор baseline...")

        def on_progress(cur: int, total: int, name: str) -> None:
            frac = cur / max(total, 1)
            progress.progress(frac, text=f"{name} ({cur}/{total})")

        with st.spinner("Выполняю проверку..."):
            run = run_check(request, mode, on_progress)

        progress.empty()

        writer = LogWriter()
        ok = writer.append(run)
        if not ok:
            st.warning("Лог занят другим процессом — запись пропущена.")

        st.session_state["last_run"] = run

# ------------------------------------------------------------ результат

if "last_run" in st.session_state:
    st.divider()
    render_run(st.session_state["last_run"])

# ------------------------------------------------------------ просмотр

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    if st.button("Показать последний прогон"):
        reader = LogReader()
        last = reader.get_last()
        if last is None:
            st.info("Логов пока нет.")
        else:
            render_run(last)
with col_b:
    if st.button("Очистить логи"):
        n = manager.delete_all()
        st.success(f"Удалено записей: {n}")
        st.session_state.pop("last_run", None)