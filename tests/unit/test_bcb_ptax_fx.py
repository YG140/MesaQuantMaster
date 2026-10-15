"""PTAX oficial e produção segura: nenhuma taxa inventada."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.core.production_guard import assert_production_ready
from app.services.bcb_fx_service import BcbPtaxFxService, FxUnavailableError


NOW = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)


def ptax_sample(*, rate="5.1208", minutes=45, closing="Fechamento"):
    local = (NOW - timedelta(minutes=minutes) - timedelta(hours=3))
    return {
        "cotacaoCompra": 5.12,
        "cotacaoVenda": rate,
        "dataHoraCotacao": local.strftime("%Y-%m-%d %H:%M:%S"),
        "tipoBoletim": closing,
    }


def client_for(values, status=200):
    def callback(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "olinda.bcb.gov.br"
        assert "/CotacaoMoedaPeriodo(" in request.url.path
        assert "'USD'" in request.url.params["@moeda"]
        assert request.url.params["$format"] == "json"
        return httpx.Response(status, json={"value": values})
    return httpx.Client(transport=httpx.MockTransport(callback))


def test_ptax_closing_venda_preferred_over_previous_boletins():
    entries = [
        ptax_sample(rate="5.0011", closing="Intermediário"),
        ptax_sample(rate="5.1208", closing="Fechamento"),
        ptax_sample(rate="5.0212", minutes=60 * 27, closing="Fechamento"),
    ]
    with client_for(entries) as client:
        sample = BcbPtaxFxService(client).latest_usd_brl(now=NOW)
    assert sample.rate_brl_per_usd == Decimal("5.1208")
    assert sample.quoted_at.tzinfo is not None
    assert sample.indicative_only
    assert "não cotação de execução" in sample.disclaimer


def test_ptax_absent_weekend_or_unverified_boletim_is_not_guessed():
    with client_for([ptax_sample(closing="Intermediário")]) as client:
        with pytest.raises(FxUnavailableError, match="fechamento"):
            BcbPtaxFxService(client).latest_usd_brl(now=NOW)


@pytest.mark.parametrize("bad_rate", ["NaN", "-1", "0", "Infinity", "1001"])
def test_bad_or_implausible_ptax_is_rejected(bad_rate):
    with client_for([ptax_sample(rate=bad_rate)]) as client:
        with pytest.raises(FxUnavailableError):
            BcbPtaxFxService(client).latest_usd_brl(now=NOW)


def test_old_ptax_is_never_reused():
    with client_for([ptax_sample(minutes=60 * 24 * 10)]) as client:
        with pytest.raises(FxUnavailableError):
            BcbPtaxFxService(client).latest_usd_brl(now=NOW)


def test_http_rate_limit_and_broken_json_fail_closed():
    with client_for([], status=429) as client:
        with pytest.raises(FxUnavailableError):
            BcbPtaxFxService(client).latest_usd_brl(now=NOW)
    with httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=b"not-json")
    )) as client:
        with pytest.raises(FxUnavailableError):
            BcbPtaxFxService(client).latest_usd_brl(now=NOW)


def secure_config(**overrides):
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://demo@db.internal:5432/mesa_quant",
        "SECRET_KEY": "s" * 64,
        "DEBUG": False,
        "API_DOCS_ENABLED": False,
        "SECURITY_HSTS_ENABLED": True,
        "FRONTEND_ORIGINS": ["https://localhost"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_production_guard_accepts_valid_backend():
    assert assert_production_ready(secure_config()) is None


@pytest.mark.parametrize("bad_settings", [
    {"DATABASE_URL": "sqlite:///tmp/lost_on_restart.db"},
    {"SECRET_KEY": "change-me-in-local-env"},
    {"DEBUG": True},
    {"API_DOCS_ENABLED": True},
    {"SECURITY_HSTS_ENABLED": False},
    {"FRONTEND_ORIGINS": ["http://localhost:5173"]},
])
def test_production_guard_rejects_insecure_configuration(bad_settings):
    with pytest.raises(RuntimeError, match="produção insegura"):
        assert_production_ready(secure_config(**bad_settings))


def test_development_environment_has_no_production_lock():
    assert assert_production_ready(secure_config(APP_ENV="development")) is None
