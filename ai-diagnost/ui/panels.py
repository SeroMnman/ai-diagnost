"""Инфо-панели: хранилище заполнено, битые записи."""

from __future__ import annotations

import streamlit as st


def render_storage_full(stats: dict) -> None:
    st.warning(
        f"Хранилище логов заполнено ({stats['total']} / {stats['limit']}). "
        f"Следующие записи начнут вытеснять старые."
    )


def render_broken_warning(stats: dict) -> None:
    st.error(
        f"Найдено повреждённых записей: {stats['broken']}. "
        f"Их можно удалить кнопкой «Очистить логи»."
    )