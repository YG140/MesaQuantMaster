from decimal import Decimal

from app.engines.strategy_engine import StrategyEngine


class StrategyService:

    def __init__(self):
        pass

    def analyze(
        self,
        strategy: str,
        indicators: dict,
    ) -> dict:

        strategy = strategy.lower()

        if strategy == "graham":

            approved = StrategyEngine.graham(
                pl=Decimal(str(indicators["pl"])),
                pvp=Decimal(str(indicators["pvp"])),
            )

        elif strategy == "bazin":

            approved = StrategyEngine.bazin(
                dividend_yield=Decimal(str(indicators["dividend_yield"])),
            )

        elif strategy == "buy_and_hold":

            approved = StrategyEngine.buy_and_hold(
                roe=Decimal(str(indicators["roe"])),
                dividend_yield=Decimal(str(indicators["dividend_yield"])),
            )

        elif strategy == "momentum":

            approved = StrategyEngine.momentum(
                current_price=Decimal(str(indicators["current_price"])),
                moving_average_200=Decimal(str(indicators["moving_average_200"])),
            )

        elif strategy == "magic_formula":

            approved = StrategyEngine.magic_formula(
                roe=Decimal(str(indicators["roe"])),
                ev_ebit=Decimal(str(indicators["ev_ebit"])),
            )

        else:

            raise ValueError("Estratégia não suportada.")

        return {
            "strategy": strategy,
            "approved": approved,
        }

    def score(
        self,
        **criteria,
    ) -> int:

        return StrategyEngine.score(
            **criteria,
        )
