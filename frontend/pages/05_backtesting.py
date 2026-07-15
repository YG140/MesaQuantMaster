from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

import streamlit as st

from components.feedback import empty_state, show_api_error
from components.metrics import metric_grid
from components.navigation import render_sidebar
from services.api_client import ApiClient, ApiError
from services.backtesting_client import BacktestingClient
from utils.formatters import format_decimal, format_money, format_percent
from utils.session import (
    clear_session,
    get_access_token,
    require_authentication,
)

st.set_page_config(
    page_title="Simulador historico - Mesa Quant",
    page_icon="MQ",
    layout="wide",
)


def parse_price_points(raw_text: str) -> list[dict[str, str]]:
    rows = []
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Linha {line_number}: use data,fechamento.")
        timestamp = parse_timestamp(parts[0], line_number)
        close = parse_positive_decimal(parts[1], line_number)
        rows.append({"timestamp": timestamp, "close": str(close)})

    if not rows:
        raise ValueError("Informe pelo menos um ponto de preco.")
    return rows


def parse_signal_points(raw_text: str) -> list[dict[str, str]]:
    rows = []
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Linha {line_number}: use data,sinal.")
        signal = parts[1].upper()
        if signal not in {"BUY", "SELL", "HOLD"}:
            raise ValueError(f"Linha {line_number}: sinal deve ser BUY, SELL ou HOLD.")
        rows.append(
            {"timestamp": parse_timestamp(parts[0], line_number), "signal": signal}
        )
    return rows


def parse_timestamp(raw_value: str, line_number: int) -> str:
    try:
        value = datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(f"Linha {line_number}: data invalida.") from exc
    return value.isoformat()


def parse_positive_decimal(raw_value: str, line_number: int) -> Decimal:
    try:
        value = Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(f"Linha {line_number}: preco invalido.") from exc
    if value <= 0:
        raise ValueError(f"Linha {line_number}: preco deve ser maior que zero.")
    return value


require_authentication()

render_sidebar()
st.title("Simulador historico")
st.caption(
    "Simule como uma estrategia teria se comportado usando precos do passado. "
    "Isso nao preve resultados futuros."
)

client = BacktestingClient(
    ApiClient(token_getter=get_access_token, on_unauthorized=clear_session)
)

default_series = "\n".join(
    [
        "2026-01-02,10.00",
        "2026-01-03,10.50",
        "2026-01-04,10.20",
        "2026-01-05,11.00",
        "2026-01-06,11.30",
    ]
)

with st.form("backtesting_form"):
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        initial_capital = st.number_input(
            "Capital inicial",
            min_value=1.0,
            value=10000.0,
            step=100.0,
        )
        mode = st.radio("Sinais", ["Estrategia momentum", "Sinais manuais"])
    with col_b:
        moving_average_window = st.number_input(
            "Janela da media",
            min_value=1,
            value=3,
            step=1,
        )
        fee_percent = st.number_input("Custo percentual", min_value=0.0, step=0.01)
    with col_c:
        fixed_fee = st.number_input("Custo fixo", min_value=0.0, step=0.01)

    historical_text = st.text_area(
        "Serie historica: data,fechamento",
        value=default_series,
        height=150,
    )
    manual_signals = st.text_area(
        "Sinais manuais: data,BUY|SELL|HOLD",
        value="",
        height=100,
        disabled=mode != "Sinais manuais",
    )
    benchmark_text = st.text_area(
        "Benchmark opcional: data,fechamento",
        value="",
        height=100,
    )

    submitted = st.form_submit_button("Executar simulacao", use_container_width=True)

if submitted:
    try:
        historical_data = parse_price_points(historical_text)
        payload = {
            "initial_capital": str(initial_capital),
            "historical_data": historical_data,
            "fee_percent": str(fee_percent),
            "fixed_fee": str(fixed_fee),
        }
        if mode == "Estrategia momentum":
            payload["strategy"] = {
                "name": "momentum",
                "moving_average_window": moving_average_window,
            }
        else:
            payload["signals"] = parse_signal_points(manual_signals)

        benchmark_data = (
            parse_price_points(benchmark_text) if benchmark_text.strip() else None
        )
        if benchmark_data is not None:
            payload["benchmark_data"] = benchmark_data

        result = client.run(payload)
        st.session_state["last_backtesting_result"] = result
    except ValueError as exc:
        st.error(str(exc))
    except ApiError as exc:
        show_api_error(exc)

result = st.session_state.get("last_backtesting_result")
if not result:
    empty_state("Execute uma simulacao historica para visualizar os resultados.")
    st.stop()

metric_grid(
    [
        ("Patrimonio final", format_money(result.get("final_equity")), None),
        ("Retorno total", format_percent(result.get("total_return_percent")), None),
        ("Benchmark", format_percent(result.get("benchmark_return_percent")), None),
        ("Excesso", format_percent(result.get("excess_return_percent")), None),
        ("Drawdown maximo", format_percent(result.get("max_drawdown_percent")), None),
        ("Taxas", format_money(result.get("total_fees")), None),
        ("Trades", result.get("trades_count", 0), None),
        ("Taxa de acerto", format_percent(result.get("win_rate_percent")), None),
    ]
)

equity_curve = result.get("equity_curve", [])
if equity_curve:
    st.subheader("Curva patrimonial")
    st.line_chart(
        [
            {
                "timestamp": item.get("timestamp"),
                "equity": float(item.get("equity")),
            }
            for item in equity_curve
        ],
        x="timestamp",
        y="equity",
    )

trades = result.get("trades", [])
if trades:
    st.subheader("Trades")
    st.dataframe(
        [
            {
                "entrada": trade.get("entry_date"),
                "preco_entrada": format_money(trade.get("entry_price")),
                "saida": trade.get("exit_date"),
                "preco_saida": format_money(trade.get("exit_price")),
                "quantidade": format_decimal(trade.get("quantity")),
                "lucro_liquido": format_money(trade.get("net_profit")),
                "retorno": format_percent(trade.get("return_percent")),
            }
            for trade in trades
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    empty_state("Nenhum trade fechado retornado pelo simulador historico.")
