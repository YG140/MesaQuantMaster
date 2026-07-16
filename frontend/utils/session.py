from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitAPIException

TOKEN_KEY = "access_token"
USER_KEY = "current_user"
SESSION_VALIDATED_KEY = "session_validated"


def initialize_session() -> None:
    st.session_state.setdefault(TOKEN_KEY, None)
    st.session_state.setdefault(USER_KEY, None)
    st.session_state.setdefault(SESSION_VALIDATED_KEY, False)


def get_access_token() -> str | None:
    token = st.session_state.get(TOKEN_KEY)
    return str(token) if token else None


def get_token() -> str | None:
    return get_access_token()


def set_authenticated_session(token: str, user: dict[str, Any]) -> None:
    sanitized_user = dict(user)
    sanitized_user.pop("password", None)
    sanitized_user.pop("hashed_password", None)
    st.session_state[TOKEN_KEY] = token
    st.session_state[USER_KEY] = sanitized_user
    st.session_state[SESSION_VALIDATED_KEY] = True


def set_session(token: str, user: dict[str, Any]) -> None:
    set_authenticated_session(token, user)


def clear_session() -> None:
    st.session_state[TOKEN_KEY] = None
    st.session_state[USER_KEY] = None
    st.session_state[SESSION_VALIDATED_KEY] = False


def is_authenticated() -> bool:
    return bool(
        get_access_token()
        and st.session_state.get(USER_KEY)
        and st.session_state.get(SESSION_VALIDATED_KEY)
    )


def validate_session(
    user_loader: Callable[[str], dict[str, Any]] | None = None,
) -> bool:
    initialize_session()
    token = get_access_token()
    if not token:
        clear_session()
        return False

    loader = user_loader or _load_current_user
    try:
        user = loader(token)
    except Exception:
        clear_session()
        return False

    if not isinstance(user, dict) or not user:
        clear_session()
        return False

    set_authenticated_session(token, user)
    return True


def require_authentication() -> bool:
    if validate_session():
        return True

    clear_session()
    for page in ("frontend/app.py", "app.py"):
        try:
            st.switch_page(page)
            break
        except StreamlitAPIException:
            continue
    st.stop()


def require_auth() -> bool:
    return require_authentication()


def logout() -> None:
    clear_session()
    st.rerun()


def _load_current_user(token: str) -> dict[str, Any]:
    from services.api_client import ApiClient
    from services.auth_client import AuthClient

    client = AuthClient(
        ApiClient(
            token_getter=lambda: token,
            on_unauthorized=clear_session,
        )
    )
    return client.me()
