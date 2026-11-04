from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session

from payshield import SessionModel, UserModel, PayrollRecordModel

class BaseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

class UserRepository(BaseRepository):
    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def create(self, user: UserModel) -> UserModel:
        self.db.add(user)
        try:
            self.db.commit()
            # Only refresh AFTER a successful commit
            self.db.refresh(user)
            return user
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Username or email already exists"
            )
        except SQLAlchemyError:
            # Good safety net: clean up session on any unexpected DB error
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="An internal server error occurred"
            )

    def get_by_id(self, user_id: int) -> Optional[UserModel]:
        user_id = select(UserModel).where(UserModel.id == user_id)
        result = self.db.scalar(user_id)
        return result

    def get_by_username(self, username: str) -> Optional[UserModel]:
        username = select(UserModel).where(UserModel.username == username)
        result = self.db.scalar(username)
        return result

    def get_by_email(self, email: str) -> Optional[UserModel]:
        get_email = select(UserModel).where(UserModel.email == email)
        result = self.db.scalar(get_email)
        return result

class PayrollRecordRepository(BaseRepository):
    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def get_by_user_id(self, user_id: int) -> Optional[PayrollRecordModel]:
        payroll_record = (
            select(PayrollRecordModel)
            .where(PayrollRecordModel.user_id == user_id)
        )

        result = self.db.scalar(payroll_record)
        return result

class SessionRepository(BaseRepository):
    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def create(self, session: SessionModel) -> SessionModel:
        self.db.add(session)
        try:
            self.db.commit()
            # Only refresh AFTER a successful commit
            self.db.refresh(session)
            return session
        except IntegrityError:
            self.db.rollback()
            raise
        except SQLAlchemyError:
            # Good safety net: clean up session on any unexpected DB error
            self.db.rollback()
            raise

    def get_by_token(self, token: str) -> SessionModel | None:
        get_token = select(SessionModel).where(SessionModel.session_token == token)
        return self.db.scalar(get_token)

    def get_list_session(self, user_id: int) -> list[SessionModel]:
        stmt = (select(SessionModel)
                .where(SessionModel.user_id == user_id,
                       SessionModel.expires_at > datetime.now(timezone.utc))
                ).order_by(SessionModel.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def delete_session(self, session_id: int, user_id: Optional[int] = None) -> bool:
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        if user_id is not None:
            stmt = stmt.where(SessionModel.user_id == user_id)

        session = self.db.scalar(stmt)
        if not session:
            return False
        self.db.delete(session)
        self.db.commit()
        return True

    def delete_all_session(self, user_id: int, excluded_session_id: Optional[int] = None) -> int:
        stmt = select(SessionModel).where(SessionModel.user_id == user_id)
        if excluded_session_id is not None:
            stmt = stmt.where(SessionModel.id != excluded_session_id)

        result = list(self.db.scalars(stmt).all())

        if not result:
            return 0

        for session in result:
            self.db.delete(session)

        self.db.commit()
        return len(result)
