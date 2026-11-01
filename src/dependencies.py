from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from payshield import get_db
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
