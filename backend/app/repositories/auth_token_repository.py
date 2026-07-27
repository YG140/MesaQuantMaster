from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.auth_token import AuthToken


class AuthTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def latest(self, user_id: UUID, token_type: str) -> AuthToken | None:
        return (
            self.db.query(AuthToken)
            .filter(AuthToken.user_id == user_id, AuthToken.token_type == token_type)
            .order_by(AuthToken.created_at.desc())
            .first()
        )

    def get_by_hash(self, token_hash: str, token_type: str) -> AuthToken | None:
        return (
            self.db.query(AuthToken)
            .filter(
                AuthToken.token_hash == token_hash, AuthToken.token_type == token_type
            )
            .first()
        )

    def invalidate(self, user_id: UUID, token_type: str) -> None:
        self.db.query(AuthToken).filter(
            AuthToken.user_id == user_id,
            AuthToken.token_type == token_type,
            AuthToken.used_at.is_(None),
        ).update({"used_at": datetime.now(timezone.utc)})

    def create(self, token: AuthToken) -> AuthToken:
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def commit(self) -> None:
        self.db.commit()

    def delete_for_user(self, user_id: UUID) -> None:
        self.db.query(AuthToken).filter(AuthToken.user_id == user_id).delete()
        self.db.commit()
