"""Auditoria LOCAL de cotações COTAHIST para simulações walk-forward.

Uso (sem rede):
  PYTHONPATH=backend python backend/scripts/audit_b3_historical_prices.py \
    --request backtest-historico.json --archive COTAHIST_A2026.ZIP \
    --output auditoria-precos.json

Os ZIPs devem ser fornecidos legalmente pelo usuário; não faz download B3.
Não altera o banco, não transforma cotação bruta em retorno ajustado.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from app.engines.b3_historical_price_audit import B3HistoricalPriceAudit
from app.schemas.portfolio_validation import WalkForwardRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Confere preços históricos em COTAHIST local, sem rede.")
    parser.add_argument("--request", type=Path, required=True, help="JSON WalkForwardRequest")
    parser.add_argument("--archive", action="append", type=Path, required=True, help="ZIP COTAHIST local")
    parser.add_argument("--output", type=Path, required=True, help="JSON de auditoria, não de rentabilidade")
    args = parser.parse_args()
    if args.request.stat().st_size > 2 * 1024 * 1024:
        parser.error("JSON de entrada excede 2 MiB.")
    try:
        request = WalkForwardRequest.model_validate_json(
            args.request.read_text(encoding="utf-8")
        )
        report = B3HistoricalPriceAudit.verify(request, args.archive)
    except (OSError, ValueError, ValidationError) as exc:
        parser.error(f"Auditoria recusada: {exc}")
    # Não cria relatório parcial se houver preço conflitante.
    args.output.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Conferidas {report.matched_quotes} cotações NÃO AJUSTADAS "
        f"em {len(report.archives)} arquivo(s). "
        "Rentabilidade de carteiras NÃO validada."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
