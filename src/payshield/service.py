import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from payshield import (
    SessionModel,
    UserModel,
    hash_token_256,
    SessionSchema,
    SessionResponse,
    UserResponse,
    PayrollRecordResponse, async_hash_password, async_verify_password,
)
from payshield.repository import SessionRepository, UserRepository, PayrollRecordRepository
from payshield.schema import SessionAuthResult, UserCreate


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        """
        Initialize the session service with an active database session.
        """
        self.repository = repository

    async def register_user(
            self,
            username: str,
            email: str,
            password: str,
            role: str = "employee"
    ) -> UserResponse:

        user_email = self.repository.get_by_email(email)
        user_username = self.repository.get_by_username(username)

        if user_email or user_username:
            raise HTTPException(
                status_code=400,
                detail="Username or email already registered"
            )

        hash_user_password = await async_hash_password(password)

        result = self.repository.create(UserModel(
            username=username,
            email=email,
            hashed_password=hash_user_password,
            role=role
        ))
        return UserResponse.model_validate(result)

    async def authenticate_user(
            self,
            username: str,
            password: str
    ) -> Optional[UserModel]:
        get_user = self.repository.get_by_username(username)

        if get_user is None:
            return None

        verify_pass = await async_verify_password(password, get_user.hashed_password)

        if not verify_pass:
            return None

        return get_user

class PayrollRecordService:
    def __init__(self, repository: PayrollRecordRepository) -> None:
        self.repository = repository

    def get_my_salary(self, user_id: int) -> Optional[PayrollRecordResponse]:
        payroll_record = self.repository.get_by_user_id(user_id)
        if payroll_record is None:
            return None
        return PayrollRecordResponse.model_validate(payroll_record)

class SessionService:
    def __init__(self, repository: SessionRepository) -> None:
        """
        Initialize the session service with an active database session.
        """
        self.repository = repository

    def create_session(
            self,
            user_id: int,
            user_agent: str,
            ip_address: str,
            duration_minutes: int = 30
    ) -> SessionAuthResult:
        """
        Generate an opaque session token, store its SHA-256 hash in the database,
        and return the database record along with the unhashed raw token.

        Args:
            user_id: ID of the authenticating user.
            user_agent: Client browser / device identifier string.
            ip_address: Client IP address string.
            duration_minutes: Lifetime of the session in minutes (default 30).

        Returns:
            tuple[SessionModel, str]: (db_session_record, raw_token)
        """

        raw_token = secrets.token_urlsafe(16)
        hash_session = hash_token_256(raw_token)

        now = datetime.now(timezone.utc)

        session_model = SessionSchema(
            user_id=user_id,
            user_agent=user_agent,
            ip_address=ip_address,
            session_token=hash_session,
            created_at=now,
            expires_at=now + timedelta(minutes=duration_minutes)
        )

        created = self.repository.create(SessionModel(**session_model.model_dump()))
        safe_session = SessionResponse.model_validate(created)

        return SessionAuthResult (
            session=safe_session,
            raw_token=raw_token
        )


    def validate_session(self, raw_token: str) -> Optional[SessionResponse]:
        """
        Validate an incoming raw session token against active sessions.

        Args:
            raw_token: The plaintext token extracted from the client's cookie.

        Returns:
            SessionModel if found and not expired; None otherwise.
        """

        if not raw_token:
            return None

        token = hash_token_256(raw_token)
        find_session = self.repository.get_by_token(token)

        if not find_session:
            return None

        now = datetime.now(timezone.utc)

        expires_at = find_session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now > expires_at:
            return None

        return SessionResponse.model_validate(find_session)

    def list_user_sessions(
            self,
            user_id: int,
    ) -> list[SessionResponse]:
        """
        Retrieve sessions associated with an employee.

        Args:
            user_id: The employee ID.

        Returns:
            List of session records ordered by created_at descending.
        """
        sessions = self.repository.get_list_session(user_id=user_id)

        return [
            SessionResponse.model_validate(session) for session in sessions
        ]

    def revoke_session(
            self,
            session_id: int,
            user_id: Optional[int] = None
    ) -> bool:
        """
        Invalidate and remove a specific session from the database.

        Args:
            session_id: The primary key ID of the session to revoke.
            user_id: Optional user ID to verify ownership (prevents IDOR).

        Returns:
            True if the session was found, authorized, and deleted; False otherwise.
        """
        return self.repository.delete_session(session_id, user_id)

    def revoke_all_sessions(
            self,
            user_id: int,
            keep_session_id: int
    ) -> int:
        """
        Revoke all active sessions for a user, with optional retention for the current device.

        Args:
            user_id: The employee ID.
            keep_session_id: Optional session ID to keep active (e.g. current login).

        Returns:
            int: Total number of sessions revoked.
        """
        return self.repository.delete_all_session(user_id, keep_session_id)