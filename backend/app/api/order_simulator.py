from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user

from app.core.database import get_db

from app.models.user import User

from app.repositories.asset_repository import AssetRepository
from app.repositories.operation_repository import OperationRepository

from app.schemas.order_simulator import (
    OrderSimulationRequest,
    OrderSimulationResponse,
)

from app.services.order_simulator_service import (
    OrderSimulatorService,
)

router = APIRouter(
    prefix="/order-simulator",
    tags=["Home Broker"],
)


def get_service(db: Session):

    return OrderSimulatorService(
        asset_repository=AssetRepository(db),
        operation_repository=OperationRepository(db),
    )


@router.post(
    "",
    response_model=OrderSimulationResponse,
)
def simulate_order(
    data: OrderSimulationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    try:

        return service.simulate(
            current_user,
            data,
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
