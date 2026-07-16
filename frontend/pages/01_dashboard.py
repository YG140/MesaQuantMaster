from __future__ import annotations

import streamlit as st

from components.feedback import empty_state, show_api_error
from components.metrics import metric_grid
from components.navigation import render_sidebar
from services.api_client import ApiClient, ApiError
from services.portfolio_client import PortfolioClient
from utils.formatters import format_money, format_percent, to_decimal
from utils.session import (
    clear_session,
    get_access_token,
    require_authentication,
)

st.set_page_config(page_title="Dashboard - Mesa Quant", page_icon="MQ", layout="wide")


def decimal_to_float(value: object) -> float | None:
    amount = to_decimal(value)
    return float(amount) if amount is not None else None


require_authentication()

render_sidebar()
st.title("Inicio")

client = PortfolioClient(
    ApiClient(token_getter=get_access_token, on_unauthorized=clear_session)
)

try:
    dashboard = client.get_dashboard()
    portfolio = client.get_portfolio()
except ApiError as exc:
    show_api_error(exc)
    st.stop()

metric_grid(
    [
        ("Patrimonio", format_money(dashboard.get("patrimonio_total")), None),
        ("Valor investido", format_money(dashboard.get("valor_investido")), None),
        ("Lucro / prejuizo", format_money(dashboard.get("lucro_prejuizo")), None),
        ("Rentabilidade", format_percent(dashboard.get("rentabilidade")), None),
        ("Ativos", dashboard.get("ativos", 0), None),
        ("Operacoes", dashboard.get("operacoes", 0), None),
        ("Caixa", format_money(dashboard.get("caixa")), None),
        ("Proventos", format_money(dashboard.get("proventos")), None),
    ]
)

positions = portfolio.get("positions", [])
allocation = portfolio.get("allocation", [])
valuation_basis = portfolio.get("valuation_basis")

if not positions:
    st.subheader("Sua carteira ainda esta vazia.")
    st.write("Comece cadastrando uma compra ou importe sua carteira existente.")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Adicionar investimento", use_container_width=True):
            st.switch_page("pages/06_adicionar_investimento.py")
    with col_b:
        if st.button("Importar carteira existente", use_container_width=True):
            st.switch_page("pages/07_importar_carteira.py")
    st.stop()

st.subheader("Resumo de risco")
concentration = max(
    (to_decimal(position.get("allocation")) or to_decimal(0) for position in positions),
    default=to_decimal(0),
)
risk_level = (
    "Concentrado"
    if decimal_to_float(concentration) and decimal_to_float(concentration) >= 50
    else "Diversificado"
)
metric_grid(
    [
        ("Posicoes na carteira", len(positions), None),
        ("Maior concentracao", format_percent(concentration), None),
        ("Nivel de risco", risk_level, None),
        ("Alertas relevantes", "Sem alertas criticos", None),
    ]
)

st.subheader("Alocacao")
if allocation:
    if valuation_basis == "invested_amount":
        st.info(
            "Alocacao calculada pelo valor investido porque ainda nao ha cotacao atual."
        )
    st.bar_chart(
        [
            {
                "ativo": item.get("ticker"),
                "allocation": decimal_to_float(item.get("allocation")),
            }
            for item in allocation
        ],
        x="ativo",
        y="allocation",
    )
else:
    empty_state("Ainda nao ha valores suficientes para montar a alocacao.")
