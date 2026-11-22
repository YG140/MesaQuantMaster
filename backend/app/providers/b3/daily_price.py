from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from defusedxml.common import DefusedXmlException
from defusedxml import ElementTree as SafeET

from app.providers.b3.exceptions import B3NotConfiguredError, B3ParseError
from app.providers.b3.models import B3DailyPrice

# Nomes de tag XML confirmados no catálogo oficial "Definição - Catálogo de
# Mensagens e Arquivos - Preços e Índices" (b3.com.br, v1.3, 07/10/2021),
# seção "BVBG.186.01 - EquitiesSimplifiedPriceReport", mensagem
# "PriceReport" (bvmf.217.01). A ESTRUTURA do elemento repetido por
# instrumento (nome do wrapper) não estava disponível na amostra pública
# consultada durante a auditoria -- usa-se aqui "PricRpt" sob o elemento
# raiz, coerente com o nome da mensagem "PriceReport" documentado no
# catálogo. Isto é uma suposição EXPLÍCITA, não uma confirmação: revalidar
# contra um arquivo BVBG.186 real assim que uma fonte pública confirmada
# existir (ver B3NotConfiguredError abaixo -- fetch() nunca finge sucesso).
_RECORD_WRAPPER = "PricRpt"


class B3DailyPriceSource:
    """Parser do arquivo oficial BVBG.186.01 (EquitiesSimplifiedPriceReport)
    -- fechamento oficial EOD de ações, NUNCA cotação live/intraday (ver
    schema: todos os campos de preço são atributos consolidados do pregão
    de referência, sem timestamp intraday).

    `parse()` é totalmente funcional e testável com fixtures sintéticas
    baseadas no schema oficial. `fetch()` (download real) levanta
    B3NotConfiguredError por padrão: a documentação oficial da B3
    (UP2DATA "Available Data") classifica BVBG.186 como produto do
    "Legacy Channel", que exige acesso contratado -- nenhuma URL pública
    determinística foi confirmada durante a auditoria. Configurar
    `settings.B3_BVBG186_URL` (nunca inventado) habilita o download real
    sem alterar o parser.
    """

    dataset = "bvbg186_eod"

    def __init__(self, url: str | None = None):
        self.url = url or None

    def is_configured(self) -> bool:
        return bool(self.url)

    def fetch(self) -> bytes:
        if not self.is_configured():
            raise B3NotConfiguredError(
                "BVBG.186 (EquitiesSimplifiedPriceReport) não possui URL pública "
                "confirmada configurada -- é um produto B3 do Legacy Channel "
                "(UP2DATA), que exige acesso contratado. Configure "
                "B3_BVBG186_URL somente se uma fonte pública real for "
                "confirmada."
            )
        raise B3NotConfiguredError(
            "Download de BVBG.186 configurado mas ainda não implementado "
            "nesta versão -- somente o parser foi validado."
        )

    @staticmethod
    def parse(xml_bytes: bytes) -> list[B3DailyPrice]:
        try:
            root = SafeET.fromstring(xml_bytes)
        except (ET.ParseError, DefusedXmlException) as exc:
            raise B3ParseError(f"XML BVBG.186 inválido ou inseguro: {exc}") from exc

        blocks = _find_all(root, _RECORD_WRAPPER)
        if not blocks:
            blocks = [root]
        return [_parse_block(block) for block in blocks]


def _parse_block(block: ET.Element) -> B3DailyPrice:
    trading_symbol = _text(block, "TckrSymb")
    reference_date_raw = _text(block, "Dt")
    if not trading_symbol or not reference_date_raw:
        raise B3ParseError(
            "Registro BVBG.186 sem TckrSymb/Dt -- identidade do instrumento "
            "ou data de referência ausente."
        )
    try:
        reference_date: date = datetime.strptime(reference_date_raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise B3ParseError(f"Data de referência BVBG.186 inválida: {exc}") from exc

    return B3DailyPrice(
        trading_symbol=trading_symbol,
        reference_date=reference_date,
        open_price=_decimal(_text(block, "FrstPric")),
        high_price=_decimal(_text(block, "MaxPric")),
        low_price=_decimal(_text(block, "MinPric")),
        average_price=_decimal(_text(block, "TradAvrgPric")),
        close_price=_decimal(_text(block, "LastPric")),
        trade_count=_integer(_text(block, "RglrTxsQty")),
        traded_quantity=_decimal(_text(block, "FinInstrmQty")),
        national_financial_volume=_decimal(_text(block, "NtlFinVol")),
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_all(elem: ET.Element, local_name: str) -> list[ET.Element]:
    return [e for e in elem.iter() if _local_name(e.tag) == local_name]


def _text(elem: ET.Element, local_name: str) -> str | None:
    for candidate in elem.iter():
        if _local_name(candidate.tag) == local_name and candidate.text:
            return candidate.text.strip()
    return None


def _decimal(raw: str | None) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise B3ParseError(f"Valor decimal BVBG.186 inválido: {raw!r}") from exc


def _integer(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(Decimal(raw))
    except InvalidOperation as exc:
        raise B3ParseError(f"Valor inteiro BVBG.186 inválido: {raw!r}") from exc
