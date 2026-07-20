from __future__ import annotations

from datetime import datetime, timezone


class CvmOpenDataProvider:
    """Ponto de integração para sincronizações controladas dos dados abertos CVM.

    O provider não baixa a base inteira em uma requisição de usuário. A execução
    deve ser disparada por rotina administrativa e persistida antes do consumo.
    """

    provider_name = "CVM Dados Abertos"

    def synchronization_metadata(self) -> dict:
        return {
            "provider": self.provider_name,
            "mode": "scheduled",
            "supports": ["fii_reports", "financial_statements"],
            "checked_at": datetime.now(timezone.utc),
        }
