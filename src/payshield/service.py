import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from payshield import SessionModel, hash_token_256, SessionSchema, SessionResponse
from payshield.repository import SessionRepository, UserRepository, PayrollRecordRepository
from payshield.schema import SessionAuthResult


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        """
        Initialize the session service with an active database session.
        """
        self.repository = repository

class PayrollRecordService:
    def __init__(self, repository: PayrollRecordRepository) -> None:
        self.repository = repository

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

        session_id =secrets.token_urlsafe(16)
        hash_session = hash_token_256(session_id)

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
        if not created:
            raise RuntimeError("Failed to create customer session in database.")

        safe_session = SessionResponse.model_validate(created)

        return SessionAuthResult (
            session=safe_session,
            raw_token=session_id
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
            active_only: bool = True
    ) -> list[SessionModel]:
        """
        Retrieve sessions associated with an employee.

        Args:
            user_id: The employee ID.
            active_only: If True, filters out expired sessions.

        Returns:
            List of session records ordered by created_at descending.
        """
        pass

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
        pass

    def revoke_all_sessions(
            self,
            user_id: int,
            keep_session_id: Optional[int] = None
    ) -> int:
        """
        Revoke all active sessions for a user, with optional retention for the current device.

        Args:
            user_id: The employee ID.
            keep_session_id: Optional session ID to keep active (e.g. current login).

        Returns:
            int: Total number of sessions revoked.
        """
        pass