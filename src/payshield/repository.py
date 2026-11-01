from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session

from payshield import SessionModel


class BaseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

class UserRepository(BaseRepository):
    def __init__(self, db: Session) -> None:
        super().__init__(db)

class PayrollRecordRepository(BaseRepository):
    def __init__(self, db: Session) -> None:
        super().__init__(db)

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

    def get_list_session(self, user_id: int, active_only: bool = True) -> list[SessionModel]:
        stmt = select(SessionModel).where(SessionModel.user_id == user_id)
        if active_only:
            now = datetime.now(timezone.utc)
            stmt = stmt.where(SessionModel.expires_at > now)
        stmt = stmt.order_by(SessionModel.created_at.desc())
        return list(self.db.scalars(stmt).all())
