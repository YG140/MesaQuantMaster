from __future__ import annotations

import streamlit as st


PRIMARY_PAGES = [
    ("Inicio", "pages/01_dashboard.py"),
    ("Minha carteira", "pages/02_carteira.py"),
    ("Adicionar investimento", "pages/06_adicionar_investimento.py"),
    ("Importar carteira", "pages/07_importar_carteira.py"),
]

ADVANCED_PAGES = [
    ("Analises", "pages/08_analises.py"),
    ("Simulador historico", "pages/05_backtesting.py"),
    ("Ativos", "pages/04_ativos.py"),
    ("Operacoes", "pages/03_operacoes.py"),
]


def render_sidebar() -> None:
    with st.sidebar:
        st.page_link("app.py", label="Mesa Quant Master")
        st.markdown("**Principal**")
        for label, page in PRIMARY_PAGES:
            st.page_link(page, label=label)

        st.markdown("**Ferramentas avancadas**")
        for label, page in ADVANCED_PAGES:
            st.page_link(page, label=label)
