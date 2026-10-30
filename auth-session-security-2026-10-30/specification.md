# Feature Specification: Authentication & Session Security

> **Feature Directory:** `specs/feature/auth-session-security-2026-10-30`  
> **Milestone:** Milestone 1 — The Working Code Dictionary (Phase 1)  
> **Status:** Approved for Implementation  
> **Last Updated:** 2026-10-30

---

## 1. Feature Overview & Objectives

This feature establishes the production-grade authentication and session security foundation for CodePeek. 

In accordance with the [CodePeek Constitution](file:///C:/Users/merss/Documents/CodePeek/specs/constitution.md) and [Tech Stack](file:///C:/Users/merss/Documents/CodePeek/specs/tech-stack.md), CodePeek rejects stateless JWTs in favor of server-side session cookies. This specification defines the transition from temporary in-memory session dictionaries (`temp_session`) to persistent, database-backed session records where tokens are stored strictly as cryptographic hashes. It also requires offloading computationally expensive password hashing (`bcrypt`) to worker threads to prevent event loop starvation.

---

## 2. Strategic Alignment & Mission Fit

- **Aligns with [Mission](file:///C:/Users/merss/Documents/CodePeek/specs/mission.md):** Provides a friction-free, secure user identity boundary so developers can safely own and access their personal code vault without leaking snippets or session state.
- **Aligns with [Roadmap](file:///C:/Users/merss/Documents/CodePeek/specs/roadmap.md):** Delivers Phase 1 of Milestone 1, enabling user registration, login, logout, and authenticated current-user resolution.

---

## 3. Core Architectural Invariants

1. **Server-Side Session Storage (No JWTs):**
   - Authentication tokens are opaque, random UUIDv4 identifiers.
   - Raw tokens are transmitted exclusively through HTTP-only cookies.
   - Active sessions are stored in the database [`Session`](file:///C:/Users/merss/Documents/CodePeek/backend/src/model/models.py#L25) table (`session` table) to survive application restarts and multi-process deployments.
2. **Persistent Hashed Session Tokens:**
   - Raw session tokens must **never** be stored in the database in plaintext.
   - When a session is created, the server computes a **SHA-256** hash of the token and writes only the hash to the `session_token` column.
   - During authentication, incoming cookies are hashed with SHA-256 before looking up the session in the database.
3. **Non-Blocking Cryptography (Threadpools):**
   - `bcrypt.hashpw` and `bcrypt.checkpw` are CPU-intensive operations.
   - All password hashing and verification calls must be executed off the async event loop using `asyncio.to_thread` (or Starlette's `run_in_threadpool`).
4. **Unified Authentication Dependency:**
   - Every protected route must depend exclusively on a single FastAPI dependency: `get_current_user`.
   - `get_current_user` extracts the cookie, computes the SHA-256 hash, retrieves the unexpired session, and resolves the authenticated [`User`](file:///C:/Users/merss/Documents/CodePeek/backend/src/model/models.py#L9).

---

## 4. Detailed Technical Specification

### 4.1 Session Cookie Security Parameters

| Attribute | Value | Description |
|---|---|---|
| **Name** | `session_id` | Name of the authentication cookie (configurable via settings). |
| **HttpOnly** | `True` | Prohibits client-side JavaScript access (`document.cookie`), mitigating XSS risks. |
| **SameSite** | `Lax` | Protects against CSRF on state-changing cross-origin requests while permitting top-level navigation. |
| **Path** | `/` | Cookie applies across all backend routes. |
| **Max-Age** | `1800` | 30 minutes (configurable via `SESSION_EXPIRE_SECONDS`). |
| **Secure** | `False` (dev) / `True` (prod) | Enforced over HTTPS in deployed environments. |

### 4.2 Database Schema Alignment

The feature leverages the existing SQLAlchemy model [`Session`](file:///C:/Users/merss/Documents/CodePeek/backend/src/model/models.py#L25):

- **Table:** `session`
- **Columns:**
  - `id`: `Integer`, Primary Key, autoincrement.
  - `user_id`: `Integer`, Foreign Key referencing `users.id` with `ondelete="CASCADE"`, indexed.
  - `session_token`: `String(255)`, unique, indexed, stores `sha256(raw_uuid)`.
  - `expires_at`: `DateTime(timezone=True)`, non-nullable timestamp.
  - `created_at`: `DateTime`, non-nullable creation timestamp.

---

## 5. API Contracts & Endpoint Specifications

### 5.1 Register User
- **Route:** `POST /auth/session-user/register`
- **Content-Type:** `application/json`
- **Request Body:**
  ```json
  {
    "username": "developer123",
    "email": "dev@example.com",
    "password": "SuperSecretPassword!"
  }
  ```
- **Responses:**
  - `201 Created`: Returns `UserResponse` (`id`, `username`, `email`, `role`, `created_at`).
  - `409 Conflict`: Returned when email or username is already registered.
  - `422 Unprocessable Entity`: Validation failure on missing fields or weak formats.

### 5.2 Login User
- **Route:** `POST /auth/session-user/login`
- **Content-Type:** `application/x-www-form-urlencoded` (`OAuth2PasswordRequestForm`)
- **Request Body:** `username=developer123&password=SuperSecretPassword!`
- **Behavior:**
  1. Offload password check to worker thread via `async_verify_password`.
  2. Generate random `raw_token = str(uuid.uuid4())`.
  3. Compute `token_hash = sha256(raw_token.encode('utf-8')).hexdigest()`.
  4. Write new `Session` record with `session_token=token_hash` and `expires_at = now + 1800s`.
  5. Set response cookie `session_id=raw_token; HttpOnly; SameSite=Lax; Max-Age=1800; Path=/`.
- **Responses:**
  - `200 OK`: Returns `UserCurrent` (`id`, `username`, `email`, `role`).
  - `401 Unauthorized`: Returned on unknown username or invalid password.

### 5.3 Logout User
- **Route:** `POST /auth/session-user/logout`
- **Headers:** Includes `Cookie: session_id=<raw_token>`
- **Behavior:**
  1. Extract `raw_token` from cookie.
  2. Compute `token_hash = sha256(raw_token.encode('utf-8')).hexdigest()`.
  3. Delete matching `Session` row from the database.
  4. Instruct client to delete cookie by setting `Max-Age=0`.
- **Responses:**
  - `204 No Content`: Successfully logged out.
  - `401 Unauthorized`: No active session found or invalid cookie.

### 5.4 Get Current Authenticated User
- **Route:** `GET /auth/session-user/user`
- **Dependency:** `Depends(get_current_user)`
- **Responses:**
  - `200 OK`: Returns `UserResponse` for authenticated user.
  - `401 Unauthorized`: Missing cookie, expired session, or unverified token.

---

## 6. Acceptance Criteria

- [ ] Zero usage of in-memory session dictionaries (`temp_session` eliminated).
- [ ] Session tokens stored in SQLite strictly as SHA-256 hashes.
- [ ] Active sessions survive complete server restarts.
- [ ] Password hashing and verification do not block the asyncio event loop.
- [ ] Expired sessions return HTTP 401 and are cleaned up.
- [ ] Unit and integration test suite passes cleanly with pytest.
