from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime

from defusedxml.common import DefusedXmlException
from defusedxml import ElementTree as SafeET

from app.providers.b3.exceptions import B3NotConfiguredError, B3ParseError
from app.providers.b3.models import B3Instrument

# Nomes de tag XML confirmados no catálogo oficial "Definição - Catálogo de
# Mensagens e Arquivos - Cadastro de Instrumento" (BVBG.028.02
# InstrumentReport, v2.6, 24/10/2017, b3.com.br). A ESTRUTURA do elemento
# repetido por instrumento (nome do wrapper) não estava disponível na
# amostra pública consultada durante a auditoria -- usa-se aqui "Instrm",
# convenção comum em mensagens ISO 20022 de cadastro de instrumento. Isto é
# uma suposição EXPLÍCITA: revalidar contra um arquivo BVBG.028 real assim
# que uma fonte pública confirmada existir (ver B3NotConfiguredError).
_RECORD_WRAPPER = "Instrm"


class B3InstrumentRegistrySource:
    """Parser do arquivo oficial BVBG.028.02 (InstrumentReport / "Cadastro
    de Instrumento"). Metadados apenas -- nunca preço/volume.

    `parse()` é totalmente funcional e testável com fixtures sintéticas
    baseadas no schema oficial. `fetch()` levanta B3NotConfiguredError
    por padrão pelo mesmo motivo documentado em B3DailyPriceSource (produto
    do Legacy Channel/UP2DATA, sem URL pública confirmada durante a
    auditoria)."""

    dataset = "bvbg028_instruments"

    def __init__(self, url: str | None = None):
        self.url = url or None

    def is_configured(self) -> bool:
        return bool(self.url)

    def fetch(self) -> bytes:
        if not self.is_configured():
            raise B3NotConfiguredError(
                "BVBG.028 (InstrumentReport) não possui URL pública confirmada "
                "configurada -- é um produto B3 do Legacy Channel (UP2DATA), "
                "que exige acesso contratado. Configure B3_BVBG028_URL "
                "somente se uma fonte pública real for confirmada."
            )
        raise B3NotConfiguredError(
            "Download de BVBG.028 configurado mas ainda não implementado "
            "nesta versão -- somente o parser foi validado."
        )

    @staticmethod
    def parse(xml_bytes: bytes) -> list[B3Instrument]:
        try:
            root = SafeET.fromstring(xml_bytes)
        except (ET.ParseError, DefusedXmlException) as exc:
            raise B3ParseError(f"XML BVBG.028 inválido ou inseguro: {exc}") from exc

        blocks = _find_all(root, _RECORD_WRAPPER)
        if not blocks:
            blocks = [root]
        return [_parse_block(block) for block in blocks]


def _parse_block(block: ET.Element) -> B3Instrument:
    trading_symbol = _text(block, "TckrSymb")
    if not trading_symbol:
        raise B3ParseError("Registro BVBG.028 sem TckrSymb -- identidade ausente.")

    maturity_raw = _text(block, "MtrtyDt")
    maturity_date: date | None = None
    if maturity_raw:
        try:
            maturity_date = datetime.strptime(maturity_raw, "%Y-%m-%d").date()
        except ValueError as exc:
            raise B3ParseError(f"MtrtyDt BVBG.028 inválida: {exc}") from exc

    return B3Instrument(
        trading_symbol=trading_symbol,
        isin=_text(block, "ISIN"),
        market_identifier_code=_text(block, "MktIdrCd"),
        currency=_text(block, "TradgCcy"),
        cfi_code=_text(block, "CFICd"),
        segment=_text(block, "Sgmt"),
        market_code=_text(block, "Mkt"),
        maturity_date=maturity_date,
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
