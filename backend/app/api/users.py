from fastapi import APIRouter, Depends

from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(
    prefix="/users",
    tags=["Usuários"],
)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Retorna o usuário autenticado",
)
def get_me(
    current_user: User = Depends(get_current_active_user),
):
    """
    Retorna os dados do usuário autenticado.
    """
    return current_user
