from __future__ import annotations

from datetime import date

import streamlit as st

from components.feedback import empty_state, show_api_error
from components.navigation import render_sidebar
from services.api_client import ApiClient, ApiError
from services.asset_client import AssetClient
from services.operation_client import OperationClient
from utils.formatters import format_decimal, format_money
from utils.session import (
    clear_session,
    get_access_token,
    require_authentication,
)

st.set_page_config(page_title="Operacoes - Mesa Quant", page_icon="MQ", layout="wide")

require_authentication()

render_sidebar()
st.title("Operacoes")

api = ApiClient(token_getter=get_access_token, on_unauthorized=clear_session)
asset_client = AssetClient(api)
operation_client = OperationClient(api)

try:
    assets = asset_client.list_assets()
except ApiError as exc:
    show_api_error(exc)
    st.stop()

if not assets:
    empty_state("Cadastre um ativo antes de registrar operacoes.")
else:
    asset_options = {
        f"{asset['ticker']} - {asset['name']}": asset["id"] for asset in assets
    }
    with st.form("operation_form", clear_on_submit=True):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            selected_asset = st.selectbox("Ativo", list(asset_options.keys()))
            operation_label = st.segmented_control(
                "Tipo",
                ["Compra", "Venda"],
                default="Compra",
            )
            operation_date = st.date_input("Data", value=date.today())
        with col_b:
            quantity = st.number_input("Quantidade", min_value=0.0, step=1.0)
            unit_price = st.number_input("Preco unitario", min_value=0.0, step=0.01)
        with col_c:
            fees = st.number_input("Taxas", min_value=0.0, step=0.01)
            taxes = st.number_input("Impostos", min_value=0.0, step=0.01)
        notes = st.text_area("Observacoes")

        submitted = st.form_submit_button(
            "Registrar operacao", use_container_width=True
        )

    if submitted:
        payload = {
            "asset_id": asset_options[selected_asset],
            "operation_type": "BUY" if operation_label == "Compra" else "SELL",
            "operation_date": operation_date.isoformat(),
            "quantity": str(quantity),
            "unit_price": str(unit_price),
            "fees": str(fees),
            "taxes": str(taxes),
            "notes": notes or None,
        }
        try:
            operation_client.create_operation(payload)
            st.success("Operacao registrada.")
            st.rerun()
        except ApiError as exc:
            show_api_error(exc)

try:
    operations = operation_client.list_operations()
except ApiError as exc:
    show_api_error(exc)
    st.stop()

if not operations:
    empty_state("Nenhuma operacao registrada.")
    st.stop()

asset_by_id = {asset["id"]: asset for asset in assets}
rows = []
for item in operations:
    asset = asset_by_id.get(item.get("asset_id"), {})
    rows.append(
        {
            "data": item.get("operation_date"),
            "ativo": asset.get("ticker", item.get("asset_id")),
            "tipo": "Compra" if item.get("operation_type") == "BUY" else "Venda",
            "quantidade": format_decimal(item.get("quantity")),
            "preco_unitario": format_money(item.get("unit_price")),
            "taxas": format_money(item.get("fees")),
            "impostos": format_money(item.get("taxes")),
            "observacoes": item.get("notes"),
        }
    )

st.dataframe(rows, use_container_width=True, hide_index=True)
