# 🛡️ Milestones 4 & 5: FastAPI Application, Auth Dependency & Security Verification

**Target Modules:**
- `src/payshield/repository.py` (User & Payroll repositories)
- `src/payshield/service.py` (User & Payroll services)
- `src/dependencies.py` (`get_current_user` authentication dependency)
- `src/payshield/routers/auth.py` (Authentication & session management endpoints)
- `src/payshield/routers/payroll.py` (Confidential payroll business endpoints)
- `src/app.py` (FastAPI application assembly & router mounting)

**Test Suites:**
- `src/test/test_api_integration.py` (End-to-end integration & security verification)

**Status:** Ready for Implementation

---

## 1. Objectives & Security Rationale

### A. Non-Negotiable Cookie Security Standards
Stateless JWTs stored in browser `localStorage` are vulnerable to Cross-Site Scripting (XSS) and cannot be revoked without stateful blocklists. PayShield eliminates client-side token exposure:
* **`HttpOnly=True`**: Prevents browser scripts, malicious extensions, or injected XSS payloads from reading the session cookie.
* **`SameSite="lax"`**: Defends against Cross-Site Request Forgery (CSRF) on state-changing requests.
* **`Path="/"`**: Ensures consistent cookie transmission across all API endpoints.
* **`Max-Age=1800`**: Sets explicit 30-minute client-side lifetime, synchronized with server-side `expires_at`.

### B. IDOR Defense on Session Invalidation
Session revocation must never accept an untrusted `session_id` without validating ownership. Any attempt by user A to revoke user B's session must result in a `404 Not Found` or `403 Forbidden`, leaving user B's session intact.

### C. Principle of Least Privilege in Payroll Access
An employee must only ever be able to retrieve their own payroll compensation record (`GET /api/v1/payroll/me`). Attempting to view another employee's salary is mathematically impossible because the user ID is resolved exclusively from the verified server-side session.

---

## 2. Technical Specifications: Milestone 4 (Web Application & Routes)

### 2.1 Repository & Service Layer Foundation

Before wiring HTTP endpoints, `UserRepository`, `UserService`, `PayrollRecordRepository`, and `PayrollRecordService` must be completed:

#### `UserRepository` ([`src/payshield/repository.py`](file:///C:/Users/merss/OneDrive/Documents/Side%20Projects/PayShield/src/payshield/repository.py))
- `create(user: UserModel) -> UserModel`: Persists a new user record and handles `IntegrityError` if username or email already exists.
- `get_by_id(user_id: int) -> Optional[UserModel]`: Retrieves a user by primary key.
- `get_by_username(username: str) -> Optional[UserModel]`: Case-sensitive or lowercase lookup by username.
- `get_by_email(email: str) -> Optional[UserModel]`: Lookup by email.

#### `UserService` ([`src/payshield/service.py`](file:///C:/Users/merss/OneDrive/Documents/Side%20Projects/PayShield/src/payshield/service.py))
- `register_user(username: str, email: str, password: str, role: str = "employee") -> UserResponse`:
  - Validates that username and email are not already registered (raises `HTTPException(status_code=400, detail="Username or email already registered")` or custom domain exception).
  - Uses `await async_hash_password(password)` to compute the bcrypt hash off the async event loop.
  - Persists the new `UserModel` and returns a sanitized `UserResponse`.
- `authenticate_user(username: str, password: str) -> Optional[UserModel]`:
  - Queries user by `username`.
  - If found, calls `await async_verify_password(password, user.hashed_password)`.
  - Returns the `UserModel` if valid; `None` if invalid or not found.

#### `PayrollRecordRepository` & `PayrollRecordService`
- `PayrollRecordRepository.get_by_user_id(user_id: int) -> Optional[PayrollRecordModel]`: Retrieves the single associated payroll record.
- `PayrollRecordService.get_my_salary(user_id: int) -> Optional[PayrollRecordResponse]`: Returns the sanitized `PayrollRecordResponse` for the authenticated employee.

---

### 2.2 Unified Authentication Dependency (`src/dependencies.py`)

All protected endpoints require an authenticated user resolved via FastAPI's dependency injection system:

```python
async def get_current_user(
    request: Request,
    session_service: Annotated[SessionService, Depends(get_session_service)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserModel:
    """
    Extracts the 'session_id' cookie from the request, verifies its validity and UTC
    expiration via SessionService, and returns the authenticated UserModel.
    
    Raises:
        HTTPException(status_code=401, detail="Authentication required") if cookie is missing,
        invalid, expired, or references a nonexistent user.
    """
```

**Requirements:**
1. Extract cookie value using `request.cookies.get("session_id")` (or `Cookie(default=None)`).
2. If missing, immediately raise `HTTPException(status_code=401, detail="Not authenticated")`.
3. Call `session = session_service.validate_session(raw_token=raw_cookie)`.
4. If `session` is `None` (expired, revoked, or non-existent hash), raise `HTTPException(status_code=401, detail="Invalid or expired session")`.
5. Look up `user = user_repository.get_by_id(session.user_id)`. If user not found, raise `HTTPException(status_code=401, detail="User not found")`.
6. Return the active `UserModel`.

---

### 2.3 Modular API Routers

#### Router A: Authentication & Sessions (`src/payshield/routers/auth.py`)
Mounted under prefix `/auth` with tag `Authentication`:

1. **`POST /register`**
   - **Body:** `RegisterRequest` (`username: str`, `email: EmailStr`, `password: str`)
   - **Status Code:** `201 Created`
   - **Response:** `UserResponse`
   - **Errors:** `400 Bad Request` if username or email is already taken.

2. **`POST /login`**
   - **Body:** `LoginRequest` (`username: str`, `password: str`)
   - **Logic:**
     - Authenticates credentials via `user_service.authenticate_user(username, password)`.
     - On failure: raises `HTTPException(status_code=401, detail="Invalid credentials")`.
     - Extracts client metadata: `user_agent = request.headers.get("user-agent", "unknown")`, `ip_address = request.client.host`.
     - Issues session: `session_service.create_session(user_id=user.id, user_agent=..., ip_address=...)`.
     - Sets cookie:
       ```python
       response.set_cookie(
           key="session_id",
           value=auth_result.raw_token,
           httponly=True,
           samesite="lax",
           max_age=1800,
           path="/",
       )
       ```
   - **Response:** `SessionResponse` (metadata of the created session)

3. **`POST /logout`**
   - **Dependency:** `current_user: Annotated[UserModel, Depends(get_current_user)]`
   - **Logic:**
     - Extracts `raw_cookie = request.cookies.get("session_id")`.
     - Hashes token and finds active session ID.
     - Calls `session_service.revoke_session(session_id=session.id, user_id=current_user.id)`.
     - Deletes cookie on client:
       ```python
       response.delete_cookie(key="session_id", path="/", httponly=True, samesite="lax")
       ```
   - **Response:** `{"message": "Logged out successfully"}`

4. **`GET /sessions`**
   - **Dependency:** `current_user: Annotated[UserModel, Depends(get_current_user)]`
   - **Logic:** Calls `session_service.list_user_sessions(user_id=current_user.id)`.
   - **Response:** `list[SessionResponse]`

5. **`POST /sessions/revoke/{session_id}`**
   - **Dependency:** `current_user: Annotated[UserModel, Depends(get_current_user)]`
   - **Logic:** Calls `session_service.revoke_session(session_id=session_id, user_id=current_user.id)`.
   - **Response:**
     - If `True`: `{"message": "Session revoked successfully"}`
     - If `False`: raises `HTTPException(status_code=404, detail="Session not found or unauthorized")` (preventing IDOR).

6. **`POST /sessions/revoke-all`**
   - **Dependency:** `current_user: Annotated[UserModel, Depends(get_current_user)]`
   - **Logic:**
     - Resolves the current session ID from `request.cookies.get("session_id")`.
     - Calls `session_service.revoke_all_sessions(user_id=current_user.id, keep_session_id=current_session.id)`.
   - **Response:** `{"revoked_count": count, "message": "All other sessions revoked"}`

---

#### Router B: Confidential Payroll (`src/payshield/routers/payroll.py`)
Mounted under prefix `/payroll` with tag `Payroll`:

1. **`GET /me`**
   - **Dependency:** `current_user: Annotated[UserModel, Depends(get_current_user)]`
   - **Logic:** Queries `payroll_service.get_my_salary(user_id=current_user.id)`.
   - **Response:** `PayrollRecordResponse`
   - **Errors:** `404 Not Found` if no payroll record has been initialized for this employee.

---

### 2.4 FastAPI App Assembly (`src/app.py`)

Mount routers cleanly onto the main application instance:

```python
from fastapi import FastAPI
from payshield.routers import auth_router, payroll_router

app = FastAPI(
    title="PayShield Security Portal",
    description="Enterprise HR & Payroll Session Security Engine",
    version="1.0.0",
    root_path="/api/v1"
)

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(payroll_router, prefix="/payroll", tags=["Payroll"])
```

---

## 3. Technical Specifications: Milestone 5 (Security & Integration Test Suite)

All integration tests must be implemented in `src/test/test_api_integration.py` utilizing `httpx.AsyncClient` with `ASGITransport` (or `starlette.testclient.TestClient`).

### 3.1 Test Scenarios & Invariant Checks

- [ ] **Test 1: Full Employee Authentication Journey**
  - Register employee `alice_hr`.
  - Login with valid credentials; verify HTTP `200 OK`.
  - Assert `Set-Cookie` header contains `session_id=...`, `HttpOnly`, `SameSite=lax`, and `Path=/`.
  - Call `GET /api/v1/payroll/me` passing the returned cookie; assert successful salary retrieval.
  - Call `POST /api/v1/auth/logout`; assert response includes expired cookie (`Max-Age=0`).
  - Subsequent call to `GET /api/v1/payroll/me` must immediately fail with `401 Unauthorized`.

- [ ] **Test 2: Remote Device Eviction**
  - Login as `alice_hr` on "Device A" (Desktop); receive `cookie_a`.
  - Login as `alice_hr` on "Device B" (Mobile); receive `cookie_b`.
  - Device A queries `GET /api/v1/auth/sessions`, identifies Device B's session ID, and calls `POST /api/v1/auth/sessions/revoke/{device_b_session_id}`.
  - Device B attempts to call `GET /api/v1/payroll/me` with `cookie_b`; must fail with `401 Unauthorized`.
  - Device A attempts to call `GET /api/v1/payroll/me` with `cookie_a`; must still succeed with `200 OK`.

- [ ] **Test 3: IDOR Exploitation Prevention**
  - Register and login `bob_employee` (obtaining `cookie_bob`).
  - Register and login `charlie_employee` (obtaining `cookie_charlie` and `session_charlie_id`).
  - Bob calls `POST /api/v1/auth/sessions/revoke/{session_charlie_id}` using `cookie_bob`.
  - Request must fail with `404 Not Found` (or `403 Forbidden`).
  - Charlie calls `GET /api/v1/payroll/me` using `cookie_charlie`; session must remain 100% active and intact.

- [ ] **Test 4: Cookie Tampering & Cryptographic Hash Defense**
  - Login and capture valid `session_id` cookie.
  - Tamper with one character of the cookie token (e.g. modify last hex digit).
  - Attempt request to `/payroll/me`; must return `401 Unauthorized`.
  - Query SQLite `sessions` table directly using SQL `SELECT session_token FROM sessions`.
  - Assert that **only 64-character SHA-256 hex strings exist in the database**, and the raw cookie value appears nowhere in any column.

- [ ] **Test 5: UTC Session Expiration Enforcement**
  - Login and obtain valid session.
  - Artificially update `expires_at` in the SQLite database to 5 minutes in the past (`datetime.now(timezone.utc) - timedelta(minutes=5)`).
  - Attempt `GET /payroll/me` with the expired cookie; must fail with `401 Unauthorized`.

- [ ] **Test 6: Mass Revocation with Active Device Preservation**
  - Create 3 concurrent sessions for the same user.
  - Call `POST /api/v1/auth/sessions/revoke-all`.
  - Assert returned `revoked_count == 2`.
  - Current caller session remains active; all other sessions return 401.

---

## 4. Verification Commands

Run the integration and security test suite:

```bash
uv run pytest src/test/test_api_integration.py -v
```

Run the entire project test suite across all milestones:

```bash
uv run pytest -v
```

---

## 5. Definition of Done Checklist

- [ ] `UserRepository` and `UserService` handle user creation and async bcrypt verification cleanly.
- [ ] `get_current_user` dependency protects secured endpoints and raises standard 401 errors.
- [ ] All session cookies include `HttpOnly`, `SameSite=Lax`, and `Path=/`.
- [ ] All routes in `src/payshield/routers/` are registered under `/api/v1`.
- [ ] All 6 integration and security tests in `test_api_integration.py` pass without warning or failure.
- [ ] Full regression suite passes 100%.
