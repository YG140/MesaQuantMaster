from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import streamlit as st


def metric_grid(items: Iterable[tuple[str, Any, Any | None]]) -> None:
    metrics = list(items)
    if not metrics:
        return

    columns = st.columns(min(4, len(metrics)))
    for index, (label, value, delta) in enumerate(metrics):
        with columns[index % len(columns)]:
            st.metric(label, value, delta=delta)
