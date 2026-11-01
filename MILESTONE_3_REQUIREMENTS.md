# 🛡️ Milestone 3: Session Service & Device Audit Management

**Target Module:** `src/payshield/session_service.py`  
**Test Suite:** `src/test/test_session_service.py`  
**Status:** In Progress (Requirements Defined)  

---

## 1. Objective & Security Rationale

Milestone 3 builds the business logic layer that manages employee login sessions, device audit logs, and real-time session invalidation.

### A. Stateful Opaque Tokens vs. Stateless JWTs
* **The Vulnerability:** With stateless JWTs, once an HR or payroll admin's token is issued, it cannot be revoked before expiration without building a distributed blocklist. If an admin loses their laptop or is terminated, the token remains valid.
* **The Solution:** PayShield issues opaque UUIDv4 tokens stored as SHA-256 hashes in the database. Revoking a session simply deletes the row, instantly cutting off access on subsequent requests.

### B. Device Audit Logging & Remote Management
* Employees and security administrators must be able to inspect active sessions (`user_agent`, `ip_address`, `created_at`, `expires_at`) to identify suspicious activity.

### C. IDOR Defense on Revocation
* Revoking a session by `session_id` must verify that the requesting user owns that session (`session.user_id == user_id`), preventing attackers from deleting other users' sessions.

---

## 2. Technical Specifications (`src/payshield/session_service.py`)

All session operations must be encapsulated within the `SessionService` class.

### 2.0 Class Skeleton (`SessionService`)

```python
class SessionService:
    def __init__(self, db: Session):
        """
        Initialize the session service with an active database session.
        """
        self.db = db

    def create_session(
        self,
        user_id: int,
        user_agent: str,
        ip_address: str,
        duration_minutes: int = 30
    ) -> tuple[SessionModel, str]:
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
        pass

    def validate_session(self, raw_token: str) -> Optional[SessionModel]:
        """
        Validate an incoming raw session token against active sessions.
        
        Args:
            raw_token: The plaintext token extracted from the client's cookie.
            
        Returns:
            SessionModel if found and not expired; None otherwise.
        """
        pass

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
```

---

### 2.1 Method Details: `create_session`
**Requirements:**
- Generate an opaque UUIDv4 raw token string: `raw_token = str(uuid.uuid4())`.
- Compute SHA-256 hex digest using `hash_token_256(raw_token)` from `payshield.security`.
- Compute expiration timestamp in UTC: `expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)`.
- Persist a new `Session` record in `self.db` with `user_id`, `session_token` (the hash), `user_agent`, `ip_address`, and `expires_at`.
- Commit and refresh the record.
- **Never store the `raw_token` in the database.** Return it only in the return tuple so it can be sent via `Set-Cookie` in the API layer.

---

### 2.2 Method Details: `validate_session`
**Requirements:**
- Guard against empty or None `raw_token` (return `None`).
- Hash `raw_token` using `hash_token_256(raw_token)`.
- Query `Session` from `self.db` by `session_token == hashed_token`.
- Compare `session.expires_at` against current UTC time (`datetime.now(timezone.utc)`).
- Return `None` if the token does not exist or has expired.
- Return the active `Session` object if valid.

---

### 2.3 Method Details: `list_user_sessions`
**Requirements:**
- Query all `Session` rows from `self.db` for `user_id`.
- If `active_only=True`, filter `expires_at > datetime.now(timezone.utc)`.
- Order results by `created_at.desc()`.

---

### 2.4 Method Details: `revoke_session`
**Requirements:**
- Query `Session` from `self.db` where `id == session_id`.
- If not found, return `False`.
- If `user_id` is provided, verify `session.user_id == user_id`. If mismatched, return `False` without deleting (IDOR protection).
- Delete the session, commit changes, and return `True`.

---

### 2.5 Method Details: `revoke_all_sessions`
**Requirements:**
- Query or delete all `Session` rows from `self.db` for `user_id`.
- If `keep_session_id` is supplied, exclude `id == keep_session_id`.
- Commit changes and return count of deleted records.

---

## 3. Implementation Guardrails & Edge Cases

1. **SQLite UTC Timezone Normalization**:
   - SQLite stores timestamps without timezone offsets. Ensure comparisons between `session.expires_at` and `datetime.now(timezone.utc)` handle timezone-aware or naive datetimes consistently to avoid `TypeError: can't compare offset-naive and offset-aware datetimes`.
2. **Opaque Token Leakage Prevention**:
   - The unhashed `raw_token` must never appear in logs, error traces, or database columns.
3. **Foreign Key Integrity**:
   - Ensure deleting a user cascades and removes their sessions automatically (verified in Milestone 1).

---

## 4. Test Specifications (`src/test/test_session_service.py`)

- [ ] **Creation & Hash Verification**: `create_session` returns a 36-character UUID string, while the DB row stores a 64-character SHA-256 hash.
- [ ] **Validation Success**: `validate_session` with valid `raw_token` returns matching `Session` record.
- [ ] **Validation Non-Existent Token**: `validate_session("invalid-uuid")` returns `None`.
- [ ] **Validation Expiration**: A session with past `expires_at` returns `None`.
- [ ] **Audit Listing**: `list_user_sessions` returns user sessions ordered newest first and respects `active_only`.
- [ ] **Revocation Success**: Calling `revoke_session` deletes the session and subsequent `validate_session` returns `None`.
- [ ] **Revocation IDOR Protection**: Attempting to revoke user A's session using user B's `user_id` returns `False` and leaves the session intact.
- [ ] **Revoke All Sessions**: `revoke_all_sessions` removes all user sessions (or leaves `keep_session_id` intact when specified).

---

## 5. Verification Command

```bash
pytest src/test/test_session_service.py -v
```
