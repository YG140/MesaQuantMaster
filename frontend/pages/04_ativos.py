from __future__ import annotations

import streamlit as st

from components.feedback import empty_state, show_api_error
from components.navigation import render_sidebar
from services.api_client import ApiClient, ApiError
from services.asset_client import AssetClient
from utils.session import (
    clear_session,
    get_access_token,
    require_authentication,
)

st.set_page_config(page_title="Ativos - Mesa Quant", page_icon="MQ", layout="wide")

require_authentication()

render_sidebar()
st.title("Ativos")

client = AssetClient(
    ApiClient(token_getter=get_access_token, on_unauthorized=clear_session)
)

with st.form("asset_form", clear_on_submit=True):
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        ticker = st.text_input("Codigo do ativo")
        asset_type = st.text_input("Tipo", value="STOCK")
    with col_b:
        name = st.text_input("Nome")
        sector = st.text_input("Setor")
    with col_c:
        currency = st.text_input("Moeda", value="BRL")
        country = st.text_input("Pais")
        exchange = st.text_input("Bolsa")

    submitted = st.form_submit_button("Cadastrar ativo", use_container_width=True)

if submitted:
    payload = {
        "ticker": ticker,
        "name": name,
        "asset_type": asset_type,
        "sector": sector or None,
        "country": country or None,
        "currency": currency or "BRL",
        "exchange": exchange or None,
    }
    try:
        client.create_asset(payload)
        st.success("Ativo cadastrado.")
        st.rerun()
    except ApiError as exc:
        show_api_error(exc)

try:
    assets = client.list_assets()
except ApiError as exc:
    show_api_error(exc)
    st.stop()

if assets:
    st.dataframe(assets, use_container_width=True, hide_index=True)
else:
    empty_state("Nenhum ativo cadastrado.")
