from __future__ import annotations

import streamlit as st

from services.api_client import ApiError, UnauthorizedError


def show_api_error(error: ApiError) -> None:
    if isinstance(error, UnauthorizedError):
        st.error("Sessao expirada ou rejeitada. Faca login novamente.")
        return
    st.error(error.message)


def empty_state(message: str) -> None:
    st.info(message)
