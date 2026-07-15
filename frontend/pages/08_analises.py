from __future__ import annotations

import streamlit as st

from components.feedback import empty_state, show_api_error
from components.metrics import metric_grid
from components.navigation import render_sidebar
from services.api_client import ApiClient, ApiError
from services.portfolio_client import PortfolioClient
from utils.formatters import format_percent, to_decimal
from utils.session import clear_session, get_access_token, require_authentication

st.set_page_config(page_title="Analises - Mesa Quant", page_icon="MQ", layout="wide")

require_authentication()

render_sidebar()
st.title("Analises")

client = PortfolioClient(
    ApiClient(token_getter=get_access_token, on_unauthorized=clear_session)
)

try:
    portfolio = client.get_portfolio()
except ApiError as exc:
    show_api_error(exc)
    st.stop()

positions = portfolio.get("positions", [])
if not positions:
    empty_state("Sua carteira ainda esta vazia.")
    st.stop()

largest = max(positions, key=lambda item: to_decimal(item.get("allocation")) or 0)
metric_grid(
    [
        ("Posicoes analisadas", len(positions), None),
        ("Maior peso", format_percent(largest.get("allocation")), None),
        ("Ativo mais representativo", largest.get("ticker"), None),
        ("Base da alocacao", portfolio.get("valuation_basis"), None),
    ]
)
