from streamlit.testing.v1 import AppTest


def test_app_without_token_shows_login_first() -> None:
    app = AppTest.from_file("frontend/app.py")

    app.run(timeout=30)

    assert not app.exception
    assert [title.value for title in app.title] == ["Mesa Quant Master"]
    assert [tab.label for tab in app.tabs] == ["Login", "Criar conta"]
    assert [button.label for button in app.button] == ["Entrar", "Criar conta"]
    assert not app.metric
    assert not app.dataframe


def test_private_pages_do_not_render_without_token() -> None:
    private_pages = [
        "frontend/pages/01_dashboard.py",
        "frontend/pages/02_carteira.py",
        "frontend/pages/03_operacoes.py",
        "frontend/pages/04_ativos.py",
        "frontend/pages/05_backtesting.py",
        "frontend/pages/06_adicionar_investimento.py",
        "frontend/pages/07_importar_carteira.py",
        "frontend/pages/08_analises.py",
    ]

    for page in private_pages:
        app = AppTest.from_file(page)
        app.run(timeout=30)

        assert not app.exception
        assert not app.title


def test_navigation_labels_prioritize_main_flows() -> None:
    source = open("frontend/components/navigation.py", encoding="utf-8").read()

    assert '"Inicio"' in source
    assert '"Minha carteira"' in source
    assert '"Adicionar investimento"' in source
    assert '"Importar carteira"' in source
    assert "Ferramentas avancadas" in source
    assert '"Simulador historico"' in source


def test_dashboard_uses_friendly_risk_text_without_raw_json() -> None:
    source = open("frontend/pages/01_dashboard.py", encoding="utf-8").read()

    assert "Resumo de risco" in source
    assert "Posicoes na carteira" in source
    assert "Maior concentracao" in source
    assert "quantidade_posicoes" not in source
    assert "maior_concentracao_percentual" not in source


def test_empty_portfolio_pages_offer_clear_actions() -> None:
    dashboard = open("frontend/pages/01_dashboard.py", encoding="utf-8").read()
    portfolio = open("frontend/pages/02_carteira.py", encoding="utf-8").read()

    assert "Sua carteira ainda esta vazia." in dashboard
    assert "Adicionar investimento" in dashboard
    assert "Importar carteira existente" in dashboard
    assert "Sua carteira ainda esta vazia." in portfolio
