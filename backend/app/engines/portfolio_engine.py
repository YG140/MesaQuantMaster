from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Mapping

from app.schemas.portfolio import PortfolioPosition, PortfolioSummary


class PortfolioEngine:
    """
    Engine responsavel por todos os calculos da carteira.

    Nao acessa banco.
    Nao acessa APIs.
    Apenas processa dados.
    """

    @staticmethod
    def calculate_positions(
        operations: list[Any],
        assets_by_id: Mapping[Any, Any],
    ) -> list[PortfolioPosition]:
        portfolio = defaultdict(
            lambda: {
                "quantity": Decimal("0"),
                "invested": Decimal("0"),
            }
        )

        for operation in sorted(
            operations,
            key=lambda item: item.operation_date,
        ):
            position = portfolio[operation.asset_id]
            fees = operation.fees or Decimal("0")
            taxes = operation.taxes or Decimal("0")
            total_cost = operation.quantity * operation.unit_price + fees + taxes

            if operation.operation_type == "BUY":
                position["quantity"] += operation.quantity
                position["invested"] += total_cost
            elif operation.operation_type == "SELL":
                if operation.quantity > position["quantity"]:
                    raise ValueError(
                        "Quantidade solicitada para venda supera a disponivel. "
                        f"Disponivel: {position['quantity']}. "
                        f"Solicitada: {operation.quantity}."
                    )

                average_price = position["invested"] / position["quantity"]

                position["quantity"] -= operation.quantity
                position["invested"] -= average_price * operation.quantity

        positions = []

        for asset_id, data in portfolio.items():
            if data["quantity"] <= 0:
                continue

            asset = assets_by_id.get(asset_id)
            if asset is None:
                continue

            average_price = data["invested"] / data["quantity"]

            positions.append(
                PortfolioPosition(
                    asset_id=asset.id,
                    ticker=asset.ticker,
                    asset_name=asset.name,
                    quantity=data["quantity"],
                    average_price=average_price,
                    invested_amount=data["invested"],
                    current_price=None,
                    market_value=None,
                    unrealized_profit=None,
                    unrealized_profit_percent=None,
                )
            )

        return sorted(
            positions,
            key=lambda position: position.ticker,
        )

    @staticmethod
    def total_invested(
        positions: list[PortfolioPosition],
    ) -> Decimal:
        return sum(
            (position.invested_amount for position in positions),
            Decimal("0"),
        )

    @staticmethod
    def total_market_value(
        positions: list[PortfolioPosition],
    ) -> Decimal:
        return sum(
            (position.market_value or Decimal("0") for position in positions),
            Decimal("0"),
        )

    @classmethod
    def total_profit(
        cls,
        positions: list[PortfolioPosition],
    ) -> Decimal:
        return cls.total_market_value(positions) - cls.total_invested(positions)

    @classmethod
    def total_loss(
        cls,
        positions: list[PortfolioPosition],
    ) -> Decimal:
        profit = cls.total_profit(positions)

        if profit >= 0:
            return Decimal("0")

        return abs(profit)

    @classmethod
    def profitability(
        cls,
        positions: list[PortfolioPosition],
    ) -> Decimal:
        invested = cls.total_invested(positions)

        if invested == 0:
            return Decimal("0")

        return ((cls.total_profit(positions) / invested) * Decimal("100")).quantize(
            Decimal("0.01")
        )

    @classmethod
    def allocation(
        cls,
        positions: list[PortfolioPosition],
    ) -> list[dict]:
        valuation_basis = cls.valuation_basis(positions)
        total = cls.total_valuation(positions, valuation_basis)

        if total == 0:
            return []

        allocation = []

        for position in positions:
            value = cls.position_valuation(position, valuation_basis)
            weight = (value / total) * Decimal("100")
            rounded_weight = weight.quantize(Decimal("0.01"))

            allocation.append(
                {
                    "asset_id": position.asset_id,
                    "ticker": position.ticker,
                    "market_value": position.market_value,
                    "invested_amount": position.invested_amount,
                    "valuation_value": value,
                    "valuation_basis": valuation_basis,
                    "allocation": rounded_weight,
                    "weight": rounded_weight,
                }
            )

        return sorted(
            allocation,
            key=lambda item: item["allocation"],
            reverse=True,
        )

    @classmethod
    def concentration(
        cls,
        positions: list[PortfolioPosition],
    ) -> list[dict]:
        return cls.allocation(positions)

    @staticmethod
    def total_positions(
        positions: list[PortfolioPosition],
    ) -> int:
        return len([position for position in positions if position.quantity > 0])

    @staticmethod
    def position_valuation(
        position: PortfolioPosition,
        valuation_basis: str,
    ) -> Decimal:
        if valuation_basis == "market_value":
            return position.market_value or Decimal("0")
        return position.invested_amount or Decimal("0")

    @classmethod
    def total_valuation(
        cls,
        positions: list[PortfolioPosition],
        valuation_basis: str,
    ) -> Decimal:
        return sum(
            (
                cls.position_valuation(position, valuation_basis)
                for position in positions
            ),
            Decimal("0"),
        )

    @classmethod
    def valuation_basis(
        cls,
        positions: list[PortfolioPosition],
    ) -> str | None:
        market_total = cls.total_market_value(positions)
        if market_total > 0:
            return "market_value"

        invested_total = cls.total_invested(positions)
        if invested_total > 0:
            return "invested_amount"

        return None

    @classmethod
    def weight_positions(
        cls,
        positions: list[PortfolioPosition],
    ) -> list[PortfolioPosition]:
        allocation = cls.allocation(positions)
        allocation_by_asset = {
            item["asset_id"]: item["allocation"] for item in allocation
        }
        valuation_basis_by_asset = {
            item["asset_id"]: item["valuation_basis"] for item in allocation
        }

        return [
            position.model_copy(
                update={
                    "allocation": allocation_by_asset.get(
                        position.asset_id,
                        Decimal("0"),
                    ),
                    "weight": allocation_by_asset.get(
                        position.asset_id,
                        Decimal("0"),
                    ),
                    "valuation_basis": valuation_basis_by_asset.get(position.asset_id),
                }
            )
            for position in positions
        ]

    @classmethod
    def summarize(
        cls,
        positions: list[PortfolioPosition],
    ) -> PortfolioSummary:
        weighted_positions = cls.weight_positions(positions)

        return PortfolioSummary(
            total_invested=cls.total_invested(weighted_positions),
            total_market_value=cls.total_market_value(weighted_positions),
            total_profit=cls.total_profit(weighted_positions),
            profitability=cls.profitability(weighted_positions),
            allocation=cls.allocation(weighted_positions),
            valuation_basis=cls.valuation_basis(weighted_positions),
            positions=weighted_positions,
        )
