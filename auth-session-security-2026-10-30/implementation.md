# Implementation Plan: Authentication & Session Security

> **Feature Directory:** `specs/feature/auth-session-security-2026-10-30`  
> **Milestone:** Milestone 1 — The Working Code Dictionary (Phase 1)  
> **Status:** Approved for Implementation  
> **Last Updated:** 2026-10-30

---

## 1. Technical Architecture & File Modifications

To achieve persistent, hashed session security and non-blocking cryptography, the following codebase files will be modified or introduced:

```text
backend/src/
├── utilities.py                  # Add SHA-256 token hashing & async threadpool bcrypt helpers
├── repository/
│   └── SessionRepository.py      # Database operations for session CRUD & hash lookups
├── service/
│   ├── AuthenticationService.py  # Async registration and login logic with threadpool hashing
│   └── SessionService.py         # Business operations for session validation and purge
├── controller/
│   └── AuthenticationController.py # Remove in-memory dict, wire DB session lookup into get_current_user
└── dependencies.py               # Dependency injection for SessionRepository & SessionService
```

---

## 2. Component Design & Code Blueprint

### 2.1 Cryptographic Helpers (`src/utilities.py`)

Add SHA-256 hashing for opaque session tokens and wrap synchronous `bcrypt` operations in `asyncio.to_thread`:

```python
import hashlib
import asyncio
import bcrypt

def hash_token_sha256(token: str) -> str:
    """Compute SHA-256 digest of an opaque session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)

async def async_hash_password(password: str) -> str:
    """Offload CPU-bound bcrypt hashing to worker threadpool."""
    return await asyncio.to_thread(hash_password, password)

async def async_verify_password(plain_password: str, hashed_password: str) -> bool:
    """Offload CPU-bound bcrypt verification to worker threadpool."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)
```

---

### 2.2 Database Persistence (`src/repository/SessionRepository.py`)

Implement dedicated database queries for the [`Session`](file:///C:/Users/merss/Documents/CodePeek/backend/src/model/models.py#L25) entity:

```python
from datetime import datetime, timezone
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import select, delete
from repository.BaseRepository import BaseRepository
from model.models import Session

class SessionRepository(BaseRepository[Session]):
    def __init__(self, db: DBSession) -> None:
        super().__init__(db, Session)

    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> Session:
        session = Session(
            user_id=user_id,
            session_token=token_hash,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_by_token_hash(self, token_hash: str) -> Session | None:
        stmt = select(Session).where(Session.session_token == token_hash)
        return self.db.scalar(stmt)

    def delete_by_token_hash(self, token_hash: str) -> bool:
        session = self.get_by_token_hash(token_hash)
        if session:
            self.db.delete(session)
            self.db.commit()
            return True
        return False

    def purge_expired_sessions(self) -> int:
        now = datetime.now(timezone.utc)
        stmt = delete(Session).where(Session.expires_at < now)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount
```

---

### 2.3 Service Layer (`src/service/AuthenticationService.py`)

Update authentication logic to use threadpool password verification:

```python
from datetime import datetime, timezone, timedelta
import uuid
from utilities import async_hash_password, async_verify_password, hash_token_sha256

class AuthenticationService:
    def __init__(self, user_repo: UserRepository, session_repo: SessionRepository) -> None:
        self.user_repo = user_repo
        self.session_repo = session_repo

    async def register(self, user_data: dict) -> User:
        # Check uniqueness
        if self.user_repo.get_by_email(user_data["email"]):
            raise EmailAlreadyExistsException()
        if self.user_repo.get_by_username(user_data["username"]):
            raise UserAlreadyExistsException()
            
        hashed_password = await async_hash_password(user_data["password"])
        new_user = User(
            username=user_data["username"],
            email=user_data["email"],
            password=hashed_password,
            role="user",
            created_at=datetime.now(timezone.utc)
        )
        return self.user_repo.create(new_user)

    async def authenticate(self, username: str, password: str) -> User:
        user = self.user_repo.get_by_username(username)
        if not user or not await async_verify_password(password, user.password):
            raise InvalidCredentialsError()
        return user

    def create_user_session(self, user_id: int, lifetime_seconds: int) -> tuple[str, Session]:
        raw_token = str(uuid.uuid4())
        token_hash = hash_token_sha256(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds)
        db_session = self.session_repo.create_session(user_id, token_hash, expires_at)
        return raw_token, db_session
```

---

### 2.4 Unified `get_current_user` Dependency & Controller Refactor (`src/controller/AuthenticationController.py`)

1. **Delete in-memory `temp_session`:** Completely remove `temp_session: dict[str, SessionModel] = {}`.
2. **Refactor `get_current_user`:**
   ```python
   def get_current_user(
       request: Request,
       session_repo: Annotated[SessionRepository, Depends(get_session_repository)],
       user_repo: Annotated[UserRepository, Depends(get_user_repository)]
   ) -> UserCurrent:
       raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
       if not raw_token:
           raise HTTPException(
               status_code=status.HTTP_401_UNAUTHORIZED,
               detail="Not authenticated or session expired"
           )

       token_hash = hash_token_sha256(raw_token)
       session_record = session_repo.get_by_token_hash(token_hash)
       
       if not session_record:
           raise HTTPException(
               status_code=status.HTTP_401_UNAUTHORIZED,
               detail="Not authenticated or session expired"
           )

       # Check expiration
       now_utc = datetime.now(timezone.utc)
       expires_at = session_record.expires_at
       if expires_at.tzinfo is None:
           expires_at = expires_at.replace(tzinfo=timezone.utc)

       if now_utc >= expires_at:
           session_repo.delete_by_token_hash(token_hash)
           raise HTTPException(
               status_code=status.HTTP_401_UNAUTHORIZED,
               detail="Session expired. Please log in again."
           )

       user = user_repo.get(session_record.user_id)
       if not user:
           raise HTTPException(
               status_code=status.HTTP_401_UNAUTHORIZED,
               detail="User not found"
           )

       return UserCurrent.model_validate(user)
   ```

---

## 3. Step-by-Step Implementation Sequence

1. **Phase 1.1: Cryptography & Threadpool Helpers**
   - Implement `hash_token_sha256`, `async_hash_password`, and `async_verify_password` in `src/utilities.py`.
2. **Phase 1.2: Repository Implementation**
   - Write repository methods for `SessionRepository` to handle hashed token lookups, creation, and deletion.
3. **Phase 1.3: Service Refactoring**
   - Update `AuthenticationService` to coordinate between `UserRepository` and `SessionRepository`.
4. **Phase 1.4: Controller Cleanup**
   - Remove `temp_session` from `AuthenticationController.py`.
   - Update `register`, `login`, and `logout` route handlers to be asynchronous and use the new service methods.
   - Refactor `get_current_user` to rely solely on the database.
5. **Phase 1.5: Verification**
   - Run test suite and verify session records in the test database.

---

## 4. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Timezone mismatch on expiration check** | Ensure all timestamps explicitly use `timezone.utc` before performing comparisons. |
| **High SQLite write lock contention on rapid sessions** | SQLite with `aiosqlite` is optimized for Milestone 1 single-user/small-group usage. WAL mode (`PRAGMA journal_mode=WAL`) can be enabled if concurrent locks occur. |
| **Orphaned sessions accumulated over time** | Implement `SessionRepository.purge_expired_sessions()` which can be triggered during login or periodically. |
