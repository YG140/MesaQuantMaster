from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.operation import Operation


class OperationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, operation: Operation) -> Operation:
        self.db.add(operation)
        self.db.commit()
        self.db.refresh(operation)
        return operation

    def add(self, operation: Operation) -> Operation:
        self.db.add(operation)
        self.db.flush()
        return operation

    def get_by_id(self, operation_id: UUID) -> Operation | None:
        return self.db.query(Operation).filter(Operation.id == operation_id).first()

    def list(self) -> list[Operation]:
        return self.db.query(Operation).order_by(Operation.operation_date.desc()).all()

    def list_by_user(self, user_id: UUID) -> list[Operation]:
        return (
            self.db.query(Operation)
            .filter(Operation.user_id == user_id)
            .order_by(Operation.operation_date.desc())
            .all()
        )

    def list_by_asset(self, asset_id: UUID) -> list[Operation]:
        return (
            self.db.query(Operation)
            .filter(Operation.asset_id == asset_id)
            .order_by(Operation.operation_date.desc())
            .all()
        )

    def update(self, operation: Operation) -> Operation:
        self.db.commit()
        self.db.refresh(operation)
        return operation

    def list_by_user_and_asset(self, user_id: UUID, asset_id: UUID) -> list[Operation]:
        return (
            self.db.query(Operation)
            .filter(Operation.user_id == user_id, Operation.asset_id == asset_id)
            .order_by(Operation.operation_date.asc(), Operation.created_at.asc())
            .all()
        )

    def delete(self, operation: Operation) -> None:
        self.db.delete(operation)
        self.db.commit()
