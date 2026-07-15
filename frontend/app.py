from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.feedback import show_api_error  # noqa: E402
from services.api_client import ApiClient, ApiError  # noqa: E402
from services.auth_client import AuthClient  # noqa: E402
from utils.session import (  # noqa: E402
    clear_session,
    get_access_token,
    initialize_session,
    logout,
    set_authenticated_session,
    validate_session,
)

st.set_page_config(
    page_title="Mesa Quant Master",
    page_icon="MQ",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def build_auth_client(token: str | None = None) -> AuthClient:
    return AuthClient(
        ApiClient(
            token_getter=(lambda: token if token is not None else get_access_token()),
            on_unauthorized=clear_session,
        )
    )


def render_login() -> None:
    st.title("Mesa Quant Master")
    st.caption(
        "Terminal financeiro para carteira, operacoes, ativos e simulador historico."
    )

    tab_login, tab_register = st.tabs(["Login", "Criar conta"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("E-mail", key="login_email")
            password = st.text_input("Senha", type="password", key="login_password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)

        if submitted:
            try:
                token_data = build_auth_client().login(email=email, password=password)
                token = token_data["access_token"]
                user = build_auth_client(token).me()
                set_authenticated_session(token, user)
                st.rerun()
            except (ApiError, KeyError) as exc:
                clear_session()
                if isinstance(exc, ApiError):
                    show_api_error(exc)
                else:
                    st.error("Resposta de autenticacao invalida.")

    with tab_register:
        with st.form("register_form"):
            name = st.text_input("Nome")
            email = st.text_input("E-mail", key="register_email")
            password = st.text_input("Senha", type="password", key="register_password")
            submitted = st.form_submit_button("Criar conta", use_container_width=True)

        if submitted:
            try:
                build_auth_client().register(name=name, email=email, password=password)
                st.success("Conta criada. Use suas credenciais para entrar.")
            except ApiError as exc:
                clear_session()
                show_api_error(exc)


initialize_session()

if validate_session():
    pages = {
        "Principal": [
            st.Page(
                "pages/01_dashboard.py",
                title="Inicio",
                url_path="inicio",
                default=True,
            ),
            st.Page(
                "pages/02_carteira.py",
                title="Minha carteira",
                url_path="carteira",
            ),
            st.Page(
                "pages/06_adicionar_investimento.py",
                title="Adicionar investimento",
                url_path="adicionar-investimento",
            ),
            st.Page(
                "pages/07_importar_carteira.py",
                title="Importar carteira",
                url_path="importar-carteira",
            ),
        ],
        "Ferramentas avancadas": [
            st.Page("pages/08_analises.py", title="Analises", url_path="analises"),
            st.Page(
                "pages/05_backtesting.py",
                title="Simulador historico",
                url_path="simulador-historico",
            ),
            st.Page("pages/04_ativos.py", title="Ativos", url_path="ativos"),
            st.Page("pages/03_operacoes.py", title="Operacoes", url_path="operacoes"),
        ],
    }
    with st.sidebar:
        user = st.session_state.get("current_user") or {}
        st.title("Mesa Quant")
        st.caption(user.get("email", "Usuario autenticado"))
        if st.button("Encerrar sessao", use_container_width=True):
            logout()
else:
    pages = [st.Page(render_login, title="Login", default=True)]

st.navigation(pages).run()
