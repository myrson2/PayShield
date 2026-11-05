from typing import Annotated

from fastapi import Depends, Request, status, HTTPException
from sqlalchemy.orm import Session

from payshield import get_db, UserModel
from payshield.repository import UserRepository, SessionRepository, PayrollRecordRepository
from payshield.service import UserService, SessionService, PayrollRecordService


def get_user_repository(
        db: Annotated[Session, Depends(get_db)]
) -> UserRepository:
    return UserRepository(db)

def get_session_repository(
        db: Annotated[Session, Depends(get_db)]
) -> SessionRepository:
    return SessionRepository(db)

def get_payroll_record_repository(
        db: Annotated[Session, Depends(get_db)]
) -> PayrollRecordRepository:
    return PayrollRecordRepository(db)

def get_user_service(
        repository: Annotated[UserRepository, Depends(get_user_repository)]
) -> UserService:
    return UserService(repository)

def get_session_service(
        repository: Annotated[SessionRepository, Depends(get_session_repository)]
) -> SessionService:
    return SessionService(repository)

def get_payroll_record_service(
        repository: Annotated[PayrollRecordRepository, Depends(get_payroll_record_repository)]
) -> PayrollRecordService:
    return PayrollRecordService(repository)

def get_current_user(
        request: Request,
        session_service: Annotated[SessionService, Depends(get_session_service)],
        user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserModel:
    raw_token = request.cookies.get("session_id")
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    session = session_service.validate_session(raw_token=raw_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    user = user_repository.get_by_id(user_id=session.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User does not exist",
        )

    return user




