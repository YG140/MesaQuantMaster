from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user

from app.core.database import get_db

from app.models.user import User

from app.repositories.asset_repository import (
    AssetRepository,
)

from app.repositories.operation_repository import (
    OperationRepository,
)

from app.schemas.order import (
    OrderCreate,
    OrderResponse,
)

from app.services.order_service import (
    OrderService,
)

router = APIRouter(
    prefix="/orders",
    tags=["Home Broker"],
)


def get_service(
    db: Session,
):

    return OrderService(
        asset_repository=AssetRepository(db),
        operation_repository=OperationRepository(db),
    )


@router.post(
    "",
    response_model=OrderResponse,
)
def execute_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    try:

        return service.execute(
            current_user,
            data,
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
