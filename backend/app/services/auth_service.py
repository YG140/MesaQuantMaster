from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register(self, name: str, email: str, password: str) -> User:
        existing_user = self.repository.get_by_email(email)

        if existing_user:
            raise ValueError("E-mail já cadastrado.")

        user = User(
            name=name,
            email=email,
            hashed_password=hash_password(password),
        )

        return self.repository.create(user)

    def authenticate(self, email: str, password: str) -> str:
        user = self.repository.get_by_email(email)

        if not user:
            raise ValueError("Usuário ou senha inválidos.")

        if not verify_password(password, user.hashed_password):
            raise ValueError("Usuário ou senha inválidos.")

        return create_access_token(
            {
                "sub": str(user.id),
                "email": user.email,
            }
        )
