from pathlib import Path


INVESTMENT_PAGE = Path("frontend/pages/06_adicionar_investimento.py")


def test_investment_form_uses_friendly_asset_terms() -> None:
    source = INVESTMENT_PAGE.read_text(encoding="utf-8")

    assert "Ativo ou empresa" in source
    assert "Codigo do ativo" in source
    assert 'st.text_input("Ticker")' not in source


def test_current_price_does_not_replace_purchase_price_automatically() -> None:
    source = INVESTMENT_PAGE.read_text(encoding="utf-8")

    assert "Preco atual" in source
    assert "Preco de compra" in source
    assert "Usar preco atual como preco de compra" in source
    assert '"unit_price": str(unit_price)' in source
    assert (
        '"current_price"' not in source.split("portfolio_client.add_investment", 1)[1]
    )


def test_manual_fallback_and_partial_data_messages_are_visible() -> None:
    source = INVESTMENT_PAGE.read_text(encoding="utf-8")

    assert "Cadastrar manualmente" in source
    assert "Nao informado" in source
    assert "dados automaticos nao estavam disponiveis" in source
    assert "Tentar novamente" in source


def test_frontend_does_not_expose_provider_keys() -> None:
    frontend_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("frontend").rglob("*.py")
    )

    assert "BRAPI_TOKEN" not in frontend_sources
    assert "API_KEY" not in frontend_sources
    assert "Authorization: Bearer" not in frontend_sources
