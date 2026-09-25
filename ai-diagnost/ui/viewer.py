"""Рендер Run в человекочитаемый вид."""

from __future__ import annotations

import streamlit as st

from history.models import Run


def render_run(run: Run) -> None:
    st.subheader(f"Прогон {run.run_id} ({run.mode}, {run.duration_s}s)")

    st.markdown(f"**Запрос:** {run.request}")
    st.markdown(f"**Интент:** `{run.intent}`")
    if run.early_exit:
        st.info("Был ранний выход — часть команд пропущена.")

    st.markdown("### Вердикт")
    st.markdown(f"**Причина:** {run.verdict.cause}")
    st.markdown(f"**Уверенность:** {run.verdict.confidence}")
    if run.verdict.details:
        st.markdown(run.verdict.details)
    if run.verdict.actions:
        st.markdown(
            "**Рекомендуемые действия:** " + ", ".join(run.verdict.actions)
        )

    with st.expander("Baseline"):
        b = run.baseline
        st.write({
            "OS": b.os,
            "Interface": b.iface,
            "IP": b.ip,
            "Gateway": b.gateway,
            "DNS": b.dns,
            "Admin": b.admin,
            "Uptime": b.uptime,
        })

    with st.expander("Команды", expanded=False):
        for c in run.commands:
            if c.skipped:
                st.markdown(f"`{c.cmd}` — *пропущено*")
                continue
            st.markdown(
                f"**`{c.cmd}`** — rc={c.rc}, {c.duration_s}s, {c.summary}"
            )
            st.code(c.stdout or c.stderr or "[пусто]", language="text")