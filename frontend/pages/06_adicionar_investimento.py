from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st

from components.feedback import show_api_error
from components.navigation import render_sidebar
from services.api_client import ApiClient, ApiError
from services.brokerage_client import BrokerageClient
from services.market_client import MarketClient
from services.portfolio_client import PortfolioClient
from utils.formatters import format_money
from utils.session import clear_session, get_access_token, require_authentication

st.set_page_config(
    page_title="Adicionar investimento - Mesa Quant",
    page_icon="MQ",
    layout="wide",
)

MIN_SEARCH_CHARS = 2


def display_value(value: Any) -> str:
    if value is None or value == "":
        return "Nao informado"
    return str(value)


def suggestion_label(asset: dict[str, Any]) -> str:
    parts = [
        asset.get("ticker"),
        asset.get("name"),
        asset.get("asset_type"),
        asset.get("exchange"),
        asset.get("country"),
    ]
    return " - ".join(display_value(part) for part in parts)


@st.cache_data(ttl=60, show_spinner=False)
def search_market_assets(
    base_url: str,
    token: str | None,
    query: str,
) -> list[dict[str, Any]]:
    client = MarketClient(ApiClient(base_url=base_url, token_getter=lambda: token))
    return client.search_assets(query, limit=8)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_market_asset(
    base_url: str,
    token: str | None,
    ticker: str,
) -> dict[str, Any]:
    client = MarketClient(ApiClient(base_url=base_url, token_getter=lambda: token))
    return client.get_asset(ticker)


require_authentication()

render_sidebar()
st.title("Adicionar investimento")

api = ApiClient(token_getter=get_access_token, on_unauthorized=clear_session)
brokerage_client = BrokerageClient(api)
market_client = MarketClient(api)
portfolio_client = PortfolioClient(api)

try:
    brokerages = brokerage_client.list_brokerages()
except ApiError as exc:
    show_api_error(exc)
    st.stop()

brokerage_options = {item["name"]: item["id"] for item in brokerages}
brokerage_labels = list(brokerage_options) + ["Outra corretora"]

st.subheader("Dados do ativo")
st.info(
    "Dados de mercado em ambiente MVP: provider BRAPI com catalogo e precos "
    "simulados. Nao trate o preco atual exibido como cotacao real."
)
asset_query = st.text_input("Ativo ou empresa", placeholder="PETR4 ou Petrobras")
manual_mode = st.checkbox("Cadastrar manualmente", value=False)

selected_asset: dict[str, Any] | None = None
provider_unavailable = False

if not manual_mode and len(asset_query.strip()) >= MIN_SEARCH_CHARS:
    try:
        with st.spinner("Buscando ativos..."):
            results = search_market_assets(
                api.base_url, get_access_token(), asset_query
            )
    except ApiError:
        provider_unavailable = True
        st.warning(
            "Nao foi possivel consultar os dados automaticos agora. "
            "Tente novamente ou continue com o cadastro manual."
        )
        if st.button("Tentar novamente"):
            st.cache_data.clear()
            st.rerun()
    else:
        if results:
            selected_label = st.selectbox(
                "Selecione o ativo",
                [suggestion_label(asset) for asset in results],
            )
            selected_index = [suggestion_label(asset) for asset in results].index(
                selected_label
            )
            try:
                selected_asset = fetch_market_asset(
                    api.base_url,
                    get_access_token(),
                    results[selected_index]["ticker"],
                )
            except ApiError:
                selected_asset = results[selected_index]
                st.info(
                    "Alguns dados automaticos nao estavam disponiveis. "
                    "Preencha manualmente o que faltar."
                )
        else:
            st.info(
                "Nenhum ativo encontrado. Voce pode tentar outro termo ou cadastrar "
                "manualmente."
            )
elif not manual_mode and asset_query:
    st.caption("Digite pelo menos 2 caracteres para buscar.")

if provider_unavailable:
    manual_mode = True

if selected_asset and not manual_mode:
    current_price = selected_asset.get("current_price")
    currency = selected_asset.get("currency") or "R$"
    st.markdown("**Dados preenchidos automaticamente**")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Ativo", display_value(selected_asset.get("ticker")))
    col_b.metric("Preco atual", format_money(current_price, currency))
    col_c.metric("Tipo", display_value(selected_asset.get("asset_type")))
    col_d.metric("Bolsa", display_value(selected_asset.get("exchange")))

    st.dataframe(
        [
            {
                "Nome": display_value(selected_asset.get("name")),
                "Setor": display_value(selected_asset.get("sector")),
                "Pais": display_value(selected_asset.get("country")),
                "Moeda": display_value(selected_asset.get("currency")),
                "Ultima cotacao": display_value(selected_asset.get("last_updated")),
                "Provider": display_value(selected_asset.get("provider")),
            }
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    current_price = None
    selected_asset = None

st.subheader("Dados da compra")
with st.form("investment_form"):
    col_a, col_b = st.columns(2)
    with col_a:
        selected_brokerage = st.selectbox("Corretora", brokerage_labels)
        new_brokerage = ""
        if selected_brokerage == "Outra corretora":
            new_brokerage = st.text_input("Nome da corretora")

        ticker = st.text_input(
            "Codigo do ativo",
            value=(selected_asset or {}).get("ticker", ""),
            disabled=bool(selected_asset),
        )
        name = st.text_input(
            "Nome",
            value=(selected_asset or {}).get("name") or "",
        )
        asset_type = st.text_input(
            "Tipo",
            value=(selected_asset or {}).get("asset_type") or "STOCK",
        )
    with col_b:
        operation_date = st.date_input("Data da compra", value=date.today())
        quantity = st.number_input("Quantidade", min_value=0.0, step=1.0)
        default_unit_price = 0.0
        if (
            selected_asset
            and operation_date == date.today()
            and st.form_submit_button(
                "Usar preco atual como preco de compra",
                use_container_width=True,
            )
        ):
            default_unit_price = float(current_price or 0)
        unit_price = st.number_input(
            "Preco de compra",
            min_value=0.0,
            value=default_unit_price,
            step=0.01,
        )
        fees = st.number_input("Taxas", min_value=0.0, step=0.01)
        taxes = st.number_input("Impostos", min_value=0.0, step=0.01)
    notes = st.text_area("Observacao")

    submitted = st.form_submit_button("Salvar investimento", use_container_width=True)

if submitted:
    try:
        if selected_brokerage == "Outra corretora":
            brokerage = brokerage_client.create_brokerage(new_brokerage)
            brokerage_id = brokerage["id"]
        else:
            brokerage_id = brokerage_options[selected_brokerage]

        portfolio_client.add_investment(
            {
                "brokerage_id": brokerage_id,
                "ticker": ticker,
                "name": name,
                "asset_type": asset_type,
                "operation_date": operation_date.isoformat(),
                "quantity": str(quantity),
                "unit_price": str(unit_price),
                "fees": str(fees),
                "taxes": str(taxes),
                "notes": notes or None,
            }
        )
        st.success("Investimento adicionado com sucesso.")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Ver minha carteira", use_container_width=True):
                st.switch_page("pages/02_carteira.py")
        with col_b:
            if st.button("Adicionar outro investimento", use_container_width=True):
                st.rerun()
    except (ApiError, KeyError) as exc:
        if isinstance(exc, ApiError):
            show_api_error(exc)
        else:
            st.error("Nao foi possivel confirmar a corretora selecionada.")
