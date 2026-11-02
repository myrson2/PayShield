# Milestone 3: Stateful Session Service, IDOR Defense & Device Revocation

**Date**: 2026-11-03

## 💡 Core Concept
Pairing cryptographically secure opaque tokens with one-way SHA-256 database hashing allows instant, server-side session invalidation on demand. Enforcing authorization boundaries directly within delete queries (`WHERE id = session_id AND user_id = user_id`) guarantees protection against Insecure Direct Object Reference (IDOR) vulnerabilities.

## 📝 Short Description
Milestone 3 establishes PayShield's session management engine across the repository and service layers ([`src/payshield/repository.py`](file:///C:/Users/merss/OneDrive/Documents/Side%20Projects/PayShield/src/payshield/repository.py) and [`src/payshield/service.py`](file:///C:/Users/merss/OneDrive/Documents/Side%20Projects/PayShield/src/payshield/service.py)). It governs the complete session lifecycle: generating high-entropy raw tokens, storing their SHA-256 digests at rest, validating incoming cookies against UTC expiration bounds, auditing active devices, revoking individual sessions securely, and mass-revoking sessions while sparing the caller's active device.

## 🛠️ Body

### Use Case
In financial and payroll environments, access must be revoked the exact second an employee resigns, is terminated, or reports a lost laptop. Stateless JWTs cannot be revoked immediately without complex, distributed distributed-denial-of-service-prone blocklists. By persisting sessions as SHA-256 hashes in the database, revoking access is an immediate single-row deletion. Furthermore, when employees manage logged-in devices from their account settings, strict IDOR controls prevent employees from crafting malicious payloads to terminate sessions belonging to colleagues or administrators.

### Code
From [`src/payshield/repository.py`](file:///C:/Users/merss/OneDrive/Documents/Side%20Projects/PayShield/src/payshield/repository.py) and [`src/payshield/service.py`](file:///C:/Users/merss/OneDrive/Documents/Side%20Projects/PayShield/src/payshield/service.py):

```python
# --- Repository Layer (Database Access) ---
class SessionRepository(BaseRepository):
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

# --- Service Layer (Business Logic & Orchestration) ---
class SessionService:
    def create_session(
        self, user_id: int, user_agent: str, ip_address: str, duration_minutes: int = 30
    ) -> SessionAuthResult:
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
        return SessionAuthResult(
            session=SessionResponse.model_validate(created),
            raw_token=raw_token
        )

    def revoke_session(self, session_id: int, user_id: Optional[int] = None) -> bool:
        return self.repository.delete_session(session_id, user_id)

    def revoke_all_sessions(self, user_id: int, keep_session_id: Optional[int] = None) -> int:
        return self.repository.delete_all_session(user_id, keep_session_id)
```

### Line-by-Line Explanation
- `raw_token = secrets.token_urlsafe(16)`: Generates a cryptographically strong, random string using system entropy suitable for bearer cookies.
- `hash_token_256(raw_token)`: Hashes the raw token before database insertion, ensuring the plaintext token is never persisted on disk.
- `SessionResponse.model_validate(created)`: Sanitizes the internal ORM entity into a clean Pydantic response model containing metadata while hiding sensitive token columns.
- `if user_id is not None: stmt = stmt.where(SessionModel.user_id == user_id)`: Enforces ownership verification at the SQL query level, rendering unauthorized IDOR deletion attempts completely ineffective.
- `if excluded_session_id is not None: stmt = stmt.where(SessionModel.id != excluded_session_id)`: Filters out the current active session during mass revocation so the user is not unexpectedly kicked out of their active session.
- `return len(result)`: Returns the exact count of invalidated sessions back to the caller for audit reporting.

---

## 🎯 Common Interview Questions (Socratic Method)

1. **Why choose stateful database-backed sessions over stateless JWTs in high-security applications like payroll?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   Stateless JWTs encode user identity and permissions directly within a signed token. Because the server does not store active tokens, a compromised JWT remains valid until its expiration timestamp arrives. In payroll systems—where an admin may need to instantly terminate access for a compromised device or a departing employee—stateful tokens allow immediate, $O(1)$ revocation by simply removing the session record from the database.
   </details>

2. **What is an Insecure Direct Object Reference (IDOR) vulnerability in session management, and how does our query prevent it?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   An IDOR vulnerability occurs when an API endpoint accepts an object identifier (e.g., `DELETE /sessions/42`) without validating whether the authenticated user actually owns that object. A regular employee could iterate session IDs and terminate sessions belonging to colleagues or executives. By adding `user_id == user_id` to the SQL query, the database itself enforces authorization: if the session exists but belongs to someone else, 0 rows match, and the request is safely rejected.
   </details>

3. **Why do we store the SHA-256 digest of session tokens rather than the raw tokens in the database?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   This enforces defense-in-depth against data breaches. If an attacker gains read-only access to the database (via an SQL injection, misconfigured backup dump, or snapshot leak), raw tokens would allow them to impersonate all active users immediately. Because SHA-256 is a one-way cryptographic hash with no known reversal, the stolen hashes cannot be used as authentication cookies against the API.
   </details>

4. **Why is timezone normalization (`expires_at.tzinfo is None`) critical when querying datetime columns in SQLite?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   SQLite does not have native timezone-aware datetime storage; it stores datetimes as plain strings. When SQLAlchemy loads a naive timestamp back into Python, its `tzinfo` attribute is `None`. Attempting to compare an offset-naive `datetime` with `datetime.now(timezone.utc)` (which is offset-aware) raises a fatal `TypeError: can't compare offset-naive and offset-aware datetimes`. Normalizing the timestamp before comparison prevents runtime 500 errors.
   </details>

5. **In `revoke_all_sessions`, why is the `keep_session_id` parameter essential for user experience and security?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   When a user notices suspicious activity on their account or updates their master password, they typically select "Log out of all other devices". If the application destroyed every single session without exception, the user's current connection would terminate immediately, kicking them back to the login screen and creating friction. `keep_session_id` allows targeted bulk revocation while preserving the user's current authenticated context.
   </details>
