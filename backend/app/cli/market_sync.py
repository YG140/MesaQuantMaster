import argparse
import json
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.database import SessionLocal
from app.providers.brapi_provider import BrapiProvider
from app.repositories.asset_repository import AssetRepository
from app.repositories.market_sync_repository import MarketSyncRepository
from app.schemas.market_sync import MarketSyncRequest
from app.services.market_sync_service import MarketSyncService
from app.services.market_service import MarketService


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Sincronização controlada de mercado")
    command.add_argument("--tickers", nargs="+", required=True)
    command.add_argument("--max-assets", type=int, default=20)
    command.add_argument("--max-calls", type=int, default=1)
    command.add_argument("--timeout", type=float, default=10)
    command.add_argument("--offline", action="store_true")
    command.add_argument("--apply", action="store_true")
    command.add_argument("--confirm-apply", action="store_true")
    command.add_argument("--expected-database")
    command.add_argument("--backup")
    return command


def main() -> None:
    args = parser().parse_args()
    database = make_url(settings.DATABASE_URL).database
    if args.apply:
        if not args.confirm_apply:
            raise SystemExit("Apply exige --confirm-apply.")
        if not args.expected_database or args.expected_database != database:
            raise SystemExit("Banco atual não corresponde a --expected-database.")
        if not args.backup or not Path(args.backup).is_file():
            raise SystemExit("Apply exige arquivo de backup existente.")

    db = SessionLocal()
    try:
        service = MarketSyncService(
            asset_repository=AssetRepository(db),
            sync_repository=MarketSyncRepository(db),
            provider=(
                None
                if args.offline
                else MarketService(BrapiProvider(timeout_seconds=args.timeout))
            ),
        )
        report = service.run(
            MarketSyncRequest(
                tickers=args.tickers,
                max_assets=args.max_assets,
                max_calls=args.max_calls,
                timeout_seconds=args.timeout,
                offline=args.offline,
            ),
            apply=args.apply,
        )
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
