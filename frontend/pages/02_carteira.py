from __future__ import annotations

import streamlit as st

from components.feedback import empty_state, show_api_error
from components.metrics import metric_grid
from components.navigation import render_sidebar
from services.api_client import ApiClient, ApiError
from services.portfolio_client import PortfolioClient
from utils.formatters import (
    format_decimal,
    format_money,
    format_percent,
    to_decimal,
)
from utils.session import (
    clear_session,
    get_access_token,
    require_authentication,
)

st.set_page_config(page_title="Carteira - Mesa Quant", page_icon="MQ", layout="wide")


def decimal_to_float(value: object) -> float | None:
    amount = to_decimal(value)
    return float(amount) if amount is not None else None


require_authentication()

render_sidebar()
st.title("Minha carteira")

client = PortfolioClient(
    ApiClient(token_getter=get_access_token, on_unauthorized=clear_session)
)

try:
    portfolio = client.get_portfolio()
except ApiError as exc:
    show_api_error(exc)
    st.stop()

metric_grid(
    [
        ("Total investido", format_money(portfolio.get("total_invested")), None),
        ("Valor de mercado", format_money(portfolio.get("total_market_value")), None),
        ("Lucro / prejuizo", format_money(portfolio.get("total_profit")), None),
        ("Rentabilidade", format_percent(portfolio.get("profitability")), None),
    ]
)

positions = portfolio.get("positions", [])
if not positions:
    st.subheader("Sua carteira ainda esta vazia.")
    st.write(
        "Adicione seu primeiro investimento ou importe a carteira que voce ja tem."
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Adicionar investimento", use_container_width=True):
            st.switch_page("pages/06_adicionar_investimento.py")
    with col_b:
        if st.button("Importar carteira existente", use_container_width=True):
            st.switch_page("pages/07_importar_carteira.py")
    st.stop()

rows = [
    {
        "ativo": item.get("ticker"),
        "nome": item.get("asset_name"),
        "quantidade": format_decimal(item.get("quantity")),
        "preco_medio": format_money(item.get("average_price")),
        "valor_investido": format_money(item.get("invested_amount")),
        "preco_atual": format_money(item.get("current_price")),
        "valor_mercado": format_money(item.get("market_value")),
        "lucro_prejuizo": format_money(item.get("unrealized_profit")),
        "alocacao": format_percent(item.get("allocation") or item.get("weight")),
    }
    for item in positions
]

st.dataframe(rows, use_container_width=True, hide_index=True)

chart_rows = [
    {
        "ativo": item.get("ticker"),
        "alocacao": decimal_to_float(item.get("allocation") or item.get("weight")),
    }
    for item in positions
    if item.get("allocation") is not None or item.get("weight") is not None
]
if chart_rows:
    st.subheader("Alocacao")
    if portfolio.get("valuation_basis") == "invested_amount":
        st.info(
            "Alocacao calculada pelo valor investido porque ainda nao ha cotacao atual."
        )
    st.bar_chart(chart_rows, x="ativo", y="alocacao")
else:
    empty_state("Ainda nao ha valores suficientes para montar a alocacao.")
