from __future__ import annotations

from datetime import date

import streamlit as st

from components.feedback import show_api_error
from components.navigation import render_sidebar
from services.api_client import ApiClient, ApiError
from services.brokerage_client import BrokerageClient
from services.portfolio_client import PortfolioClient
from utils.session import clear_session, get_access_token, require_authentication

st.set_page_config(
    page_title="Importar carteira - Mesa Quant",
    page_icon="MQ",
    layout="wide",
)

require_authentication()

render_sidebar()
st.title("Importar carteira inicial")
st.caption(
    "Use esta tela para registrar posicoes atuais consolidadas, sem cadastrar cada "
    "negociacao historica."
)

api = ApiClient(token_getter=get_access_token, on_unauthorized=clear_session)
brokerage_client = BrokerageClient(api)
portfolio_client = PortfolioClient(api)

try:
    brokerages = brokerage_client.list_brokerages()
except ApiError as exc:
    show_api_error(exc)
    st.stop()

brokerage_options = {item["name"]: item["id"] for item in brokerages}
brokerage_labels = list(brokerage_options) + ["Outra corretora"]

selected_brokerage = st.selectbox("Corretora", brokerage_labels)
new_brokerage = ""
if selected_brokerage == "Outra corretora":
    new_brokerage = st.text_input("Nome da corretora")

default_rows = [
    {
        "codigo": "",
        "nome": "",
        "tipo": "STOCK",
        "quantidade": 0.0,
        "preco_medio": 0.0,
        "data_referencia": date.today(),
        "observacao": "",
    }
]

rows = st.data_editor(
    default_rows,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
)

valid_rows = [
    row
    for row in rows
    if row.get("codigo") or row.get("quantidade") or row.get("preco_medio")
]

if valid_rows:
    st.subheader("Previa")
    st.dataframe(valid_rows, use_container_width=True, hide_index=True)

if st.button("Confirmar importacao", use_container_width=True):
    try:
        if selected_brokerage == "Outra corretora":
            brokerage = brokerage_client.create_brokerage(new_brokerage)
            brokerage_id = brokerage["id"]
        else:
            brokerage_id = brokerage_options[selected_brokerage]

        payload_positions = []
        for row in valid_rows:
            payload_positions.append(
                {
                    "ticker": row.get("codigo"),
                    "name": row.get("nome") or row.get("codigo"),
                    "asset_type": row.get("tipo") or "STOCK",
                    "quantity": str(row.get("quantidade") or 0),
                    "average_price": str(row.get("preco_medio") or 0),
                    "reference_date": (
                        row.get("data_referencia").isoformat()
                        if row.get("data_referencia")
                        else None
                    ),
                    "notes": row.get("observacao") or None,
                }
            )

        result = portfolio_client.import_initial_portfolio(
            {
                "brokerage_id": brokerage_id,
                "positions": payload_positions,
            }
        )
        st.success(
            "Carteira importada: "
            f"{result.get('operations_created', 0)} posicoes registradas."
        )
        if st.button("Ver minha carteira", use_container_width=True):
            st.switch_page("pages/02_carteira.py")
    except (ApiError, AttributeError, KeyError) as exc:
        if isinstance(exc, ApiError):
            show_api_error(exc)
        else:
            st.error("Revise os dados da importacao antes de confirmar.")
