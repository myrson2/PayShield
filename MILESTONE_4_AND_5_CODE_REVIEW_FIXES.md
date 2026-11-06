# 🛠️ Milestones 4 & 5 — Code Review Fix Plan

**Source:** Review of `src/payshield/service.py` and related classes (`repository.py`, `schema.py`, `model.py`, `dependencies.py`, `routers/auth.py`, `routers/payroll.py`, `app.py`).

**Current test status:** Existing suite passes (`21 passed`), but it does not cover the user service, payroll service, authentication dependency, routes, or Milestone 5 integration scenarios.

**Status legend:**
- 🔴 **Blocker** — must be fixed before Milestone 4/5 can work.
- 🟠 **High** — security or correctness issue that should be fixed before completion.
- 🟡 **Medium** — important robustness/maintainability issue.
- 🟢 **Low** — cleanup or hardening.

**Do not mark Milestone 4/5 complete until every 🔴 and 🟠 item is resolved and the full test suite passes without warnings.**

---

## Fix Checklist

- [x] FIX-01 — Fix registration crash (`password` passed to `UserModel`)
- [x] FIX-02 — Fix duplicate username/email lookup
- [x] FIX-03 — Remove public role assignment (privilege escalation)
- [x] FIX-04 — Return `404` when no payroll record exists
- [ ] FIX-05 — Implement `get_current_user()`
- [ ] FIX-06 — Implement authentication/session routers
- [ ] FIX-07 — Implement payroll router
- [ ] FIX-08 — Mount routers under `/api/v1`
- [ ] FIX-09 — Require ownership for session revocation
- [ ] FIX-10 — Align session token generation with the UUIDv4 invariant
- [ ] FIX-11 — Clean up session creation error handling
- [ ] FIX-12 — Prevent accidental raw-token exposure
- [ ] FIX-13 — Add request/password validation
- [ ] FIX-14 — Harden authentication timing and malformed-hash handling
- [ ] FIX-15 — Address blocking database calls in async routes
- [ ] FIX-16 — Clean up expired sessions
- [ ] FIX-17 — Make timezone handling explicit
- [ ] FIX-18 — Centralize and harden cookie settings
- [ ] FIX-19 — Unify repository/service error handling
- [ ] FIX-20 — Add service and integration tests
- [ ] FIX-21 — Fix test configuration and isolation
- [ ] FIX-22 — Replace import-time `create_tables()` and unify imports
- [ ] FIX-23 — Align revocation count semantics
- [ ] FIX-24 — Optional security hardening

---

## 🔴 Blocker Fixes

### FIX-01 — Fix registration crash (`password` passed to `UserModel`)

**Severity:** 🔴 Blocker  
**Files:** `src/payshield/service.py` (`UserService.register_user`), `src/payshield/schema.py`

**Problem:** `RegisterRequest.model_dump()` includes `password`, but `UserModel` has `hashed_password`, not `password`. Registration raises:

```text
TypeError: 'password' is an invalid keyword argument for UserModel
```

**Required change:**

- Build the `UserModel` explicitly and assign the bcrypt hash to `hashed_password`.
- Do not dump `RegisterRequest` directly into an ORM model.
- Prefer a dedicated internal schema such as `UserCreate` for persistence, separate from the HTTP request schema.

Illustrative shape:

```python
user_model = UserModel(
    username=username,
    email=email,
    hashed_password=hashed_password,
    role=role,
)
```

**Acceptance criteria:**

- A valid registration request creates a user successfully.
- The database contains a bcrypt hash in `hashed_password`.
- The plaintext password is never persisted.
- `UserResponse` is returned without the hash.

---

### FIX-02 — Fix duplicate username/email lookup

**Severity:** 🔴 Blocker  
**Files:** `src/payshield/service.py` (`UserService.register_user`)

**Problem:** The current code passes `username` to `get_by_email()`:

```python
user = self.repository.get_by_email(username)
```

This does not detect duplicate usernames or duplicate emails.

**Required change:**

- Check `get_by_username(username)` and `get_by_email(email)` separately.
- Keep the database unique constraints as the final authority.
- Handle the check-then-insert race with the repository's `IntegrityError` handling.
- Return `400 Bad Request` consistently for duplicates, as required by the milestone.

**Acceptance criteria:**

- Duplicate username → `400`.
- Duplicate email → `400`.
- Concurrent duplicate insert cannot create two rows.
- The error detail matches the milestone contract: `"Username or email already registered"`.

---

### FIX-03 — Remove public role assignment (privilege escalation)

**Severity:** 🔴 Blocker  
**Files:** `src/payshield/schema.py` (`RegisterRequest`), `src/payshield/service.py`

**Problem:** Public registration accepts and persists `role`. A client can self-register as `hr_admin` or any other privileged role.

**Required change:**

- Remove `role` from the public registration schema.
- Force public registration to `role="employee"`.
- If role assignment is needed, create a separate admin-only endpoint protected by `get_current_user` plus an authorization/role check.
- Validate role values with a `Literal` or enum in the internal schema if role assignment remains supported internally.

**Acceptance criteria:**

- A request containing `"role": "hr_admin"` cannot create an admin user through `/auth/register`.
- New public users always receive `employee`.
- Privileged role changes require an authorized administrative path.

---

### FIX-04 — Return `404` when no payroll record exists

**Severity:** 🔴 Blocker  
**Files:** `src/payshield/service.py` (`PayrollRecordService.get_my_salary`), `src/payshield/routers/payroll.py`

**Problem:** `PayrollRecordResponse.model_validate(None)` raises a validation error, producing a `500` instead of `404`.

**Required change:**

- Check whether `repository.get_by_user_id(user_id)` returned `None`.
- Return `None` or raise a domain-level not-found exception.
- In the router, convert that outcome into `HTTPException(status_code=404, detail="Payroll record not found")`.

**Acceptance criteria:**

- Existing payroll record → `200 OK` with `PayrollRecordResponse`.
- Missing payroll record → `404 Not Found`, not `500`.
- User ID always comes from `current_user.id`, never from a request parameter.

---

### FIX-05 — Implement `get_current_user()`

**Severity:** 🔴 Blocker  
**Files:** `src/dependencies.py`

**Problem:** The dependency is currently `pass`, so protected endpoints receive `None` instead of an authenticated user.

**Required change:**

1. Read the cookie via `request.cookies.get("session_id")`.
2. If missing, raise `HTTPException(status_code=401, detail="Not authenticated")`.
3. Call `session_service.validate_session(raw_token=raw_cookie)`.
4. If no valid session, raise `HTTPException(status_code=401, detail="Invalid or expired session")`.
5. Load the user via `user_repository.get_by_id(session.user_id)`.
6. If the user no longer exists, raise `HTTPException(status_code=401, detail="User not found")`.
7. Return the `UserModel`.

**Design consideration:** `logout` and `revoke-all` also need the current session ID. Either:

- return an auth context object containing both `user` and `session`, or
- re-validate the cookie in the auth router.

Returning an auth context avoids duplicate database lookups and makes the dependency easier to extend.

**Acceptance criteria:**

- Missing cookie → `401`.
- Tampered cookie → `401`.
- Expired session → `401`.
- Revoked session → `401`.
- Deleted/nonexistent user → `401`.
- Valid session → dependency returns the correct `UserModel`.

---

### FIX-06 — Implement authentication/session routers

**Severity:** 🔴 Blocker  
**Files:** `src/payshield/routers/auth.py`

**Problem:** Every endpoint is `pass`.

**Required endpoints and behavior:**

#### `POST /register`
- Body: `RegisterRequest` with only `username`, `email`, `password`.
- Status: `201 Created`.
- Response: `UserResponse`.
- Duplicate username/email → `400`.

#### `POST /login`
- Authenticate via `user_service.authenticate_user()`.
- Invalid credentials → `401` with `"Invalid credentials"`.
- Gather `user_agent` and `ip_address`.
- Create a session.
- Set the cookie:

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

- Return `auth_result.session` using `response_model=SessionResponse`.
- Never return `auth_result` itself, because it contains `raw_token`.

#### `POST /logout`
- Require `get_current_user`.
- Resolve the current session from the raw cookie.
- Revoke the session with ownership enforced.
- Delete the cookie:

```python
response.delete_cookie(
    key="session_id",
    path="/",
    httponly=True,
    samesite="lax",
)
```

- Return `{"message": "Logged out successfully"}`.

#### `GET /sessions`
- Require `get_current_user`.
- Return `session_service.list_user_sessions(user_id=current_user.id)`.

#### `POST /sessions/revoke/{session_id}`
- Require `get_current_user`.
- Call `revoke_session(session_id=session_id, user_id=current_user.id)`.
- `True` → success message.
- `False` → `404` with `"Session not found or unauthorized"`.
- Return `404` for both nonexistent and other-user sessions to prevent enumeration/IDOR.

#### `POST /sessions/revoke-all`
- Require `get_current_user`.
- Resolve the current session ID.
- Call `revoke_all_sessions(user_id=current_user.id, keep_session_id=current_session.id)`.
- Return `{"revoked_count": count, "message": "All other sessions revoked"}`.

**Acceptance criteria:**

- Login issues an `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=1800` cookie.
- Logout expires the cookie.
- Session listing returns only the current user's sessions.
- Revocation of another user's session returns `404`.
- Current session remains valid after `revoke-all`.

---

### FIX-07 — Implement payroll router

**Severity:** 🔴 Blocker  
**Files:** `src/payshield/routers/payroll.py`

**Problem:** `GET /me` is `pass`.

**Required change:**

- Depend on `get_current_user`.
- Call `payroll_service.get_my_salary(user_id=current_user.id)`.
- Return `PayrollRecordResponse`.
- If no record exists, return `404`.

**Acceptance criteria:**

- Employee can retrieve only their own payroll record.
- No request parameter can override the user ID.
- Missing record → `404`.

---

### FIX-08 — Mount routers under `/api/v1`

**Severity:** 🔴 Blocker  
**Files:** `src/app.py`, `src/payshield/routers/__init__.py`

**Problem:** `app.py` mounts only the old `controller` router. The new `auth_router` and `payroll_router` are never registered.

**Required change:**

- Include both routers explicitly with the required paths, for example:

```python
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(payroll_router, prefix="/api/v1/payroll", tags=["Payroll"])
```

- Do not rely on `root_path="/api/v1"` as a routing prefix. It is server/proxy metadata and is deprecated in current FastAPI versions.
- Keep route prefixes explicit so `httpx.ASGITransport` tests can call `/api/v1/...` directly.

**Acceptance criteria:**

- `POST /api/v1/auth/register` exists.
- `POST /api/v1/auth/login` exists.
- `GET /api/v1/payroll/me` exists.
- No reliance on deprecated `root_path` routing behavior.
- OpenAPI docs show the intended paths.

---

## 🟠 High-Priority Fixes

### FIX-09 — Require ownership for session revocation

**Severity:** 🟠 High  
**Files:** `src/payshield/service.py`, `src/payshield/repository.py`

**Problem:** `revoke_session(session_id, user_id=None)` silently disables the ownership filter when `user_id` is omitted.

**Required change:**

- Make `user_id` required on the application-facing revocation method.
- If administrative/system-wide revocation is needed, create a separate, explicitly named method with separate authorization.
- Ensure every route passes `current_user.id`.

**Acceptance criteria:**

- A session can never be deleted through the public path without matching `user_id`.
- IDOR tests remain green.

---

### FIX-10 — Align session token generation with the UUIDv4 invariant

**Severity:** 🟠 High  
**Files:** `src/payshield/service.py` (`SessionService.create_session`)

**Problem:** The project invariant specifies opaque random UUIDv4 session tokens; the implementation uses `secrets.token_urlsafe(16)`. This is cryptographically strong, but inconsistent with the project contract. The variable name `session_id` also conflates the raw token with the database ID.

**Required change:**

- Generate the raw token using the project-approved format (`uuid.uuid4()`).
- Rename `session_id` to `raw_token`.
- Keep storing only `hash_token_256(raw_token)` in the database.
- Keep the raw token only in the cookie and `SessionAuthResult`.

**Acceptance criteria:**

- Raw tokens follow the required format.
- Database stores only 64-character SHA-256 hex digests.
- Raw token never appears in logs, response bodies, or database columns.

---

### FIX-11 — Clean up session creation error handling

**Severity:** 🟠 High  
**Files:** `src/payshield/service.py`, `src/payshield/repository.py`

**Problem:**

- `if not created:` is unreachable because the repository either returns a model or raises.
- The repository re-raises raw SQLAlchemy exceptions while `UserRepository` converts them to `HTTPException`.
- The docstring says `tuple[SessionModel, str]`, but the method returns `SessionAuthResult`.
- The message says `"customer session"` instead of user/session terminology.

**Required change:**

- Remove the unreachable branch.
- Define one consistent error-handling strategy for repositories.
- Update the docstring to match `SessionAuthResult`.
- Fix the error message.

**Acceptance criteria:**

- Session creation behaves identically on success and failure through all layers.
- No dead code or misleading docstrings remain.

---

### FIX-12 — Prevent accidental raw-token exposure

**Severity:** 🟠 High  
**Files:** `src/payshield/schema.py`, `src/payshield/__init__.py`, `src/payshield/routers/auth.py`

**Problem:** `SessionAuthResult` contains `raw_token` and is a Pydantic model. If accidentally returned from a route, it serializes the raw cookie token into the response body. It is also not exported consistently with the other schemas.

**Required change:**

- Ensure login always returns `auth_result.session`, never `auth_result`.
- Keep `SessionAuthResult` internal or add an explicit internal import path.
- Do not add it to any public response model.
- Never log the raw token.

**Acceptance criteria:**

- Login response contains only safe session metadata.
- No response body ever contains `raw_token`.
- Token leakage tests pass.

---

### FIX-13 — Add request/password validation

**Severity:** 🟠 High  
**Files:** `src/payshield/schema.py`, `src/payshield/service.py`

**Problem:**

- `RegisterRequest.email` is `str`, not `EmailStr`.
- No password length/complexity rules exist.
- `bcrypt>=5.0.0` raises `ValueError` for passwords longer than 72 UTF-8 bytes.
- Long passwords currently become unhandled `500` errors during registration and login.
- `role` can be `None` if explicitly submitted, causing database failures.

**Required change:**

- Use `EmailStr` for email.
- Enforce password rules.
- Validate UTF-8 byte length, not just character count, because multibyte characters can exceed 72 bytes.
- Either reject over-limit passwords with `422` or define a pre-hashing strategy.
- Treat over-limit passwords during login as invalid credentials (`401`) rather than `500`.
- Use a `Literal`/enum for internal roles and reject `None`.
- Add reasonable maximum lengths for username, email, and password to prevent abuse.

**Acceptance criteria:**

- Invalid email → `422`.
- Over-limit password → clean `4xx`, not `500`.
- Valid registration and login still work.
- No role value outside the allowed set can be persisted.

---

### FIX-14 — Harden authentication timing and malformed-hash handling

**Severity:** 🟠 High (security hardening)  
**Files:** `src/payshield/service.py` (`UserService.authenticate_user`)

**Problem:**

- Unknown usernames return immediately; known usernames run bcrypt. The timing difference can reveal account existence.
- A malformed stored bcrypt hash raises `ValueError` and becomes a `500`.

**Required change:**

- When the user is missing, verify against a fixed dummy bcrypt hash to equalize timing.
- Catch `ValueError` from bcrypt and return `None`/authentication failure.
- Keep the public error response identical for unknown user and wrong password.

**Acceptance criteria:**

- Unknown user and wrong password both return `401`.
- Corrupted hash data does not produce a `500`.
- Authentication timing test or at least a manual check shows comparable behavior.

---

### FIX-15 — Address blocking database calls in async routes

**Severity:** 🟠 High  
**Files:** `src/dependencies.py`, `src/payshield/service.py`, `src/payshield/routers/*`

**Problem:** Async dependencies/routes call synchronous SQLAlchemy repositories directly, blocking the event loop during SQLite I/O.

**Required change (choose one):**

- Use synchronous dependency/route functions (`def`) where blocking DB work occurs so Starlette runs them in its threadpool, while keeping bcrypt offloaded with `asyncio.to_thread`.
- Or migrate the data layer to async SQLAlchemy and await all repository calls.

Do not mix blocking I/O directly inside `async def` request paths without offloading it.

**Acceptance criteria:**

- No synchronous database call runs directly on the event loop.
- Existing behavior and tests remain correct.

---

### FIX-16 — Clean up expired sessions

**Severity:** 🟠 High (housekeeping/security)  
**Files:** `src/payshield/repository.py`, `src/payshield/service.py`

**Problem:** Expired sessions are filtered from listings but never deleted. Rows accumulate indefinitely.

**Required change:**

- Add a repository method to delete expired sessions.
- Call cleanup on a defined schedule, on login, or during validation.
- Decide whether expired sessions must be retained for audit purposes; if so, document the retention policy.

**Acceptance criteria:**

- Expired sessions do not accumulate indefinitely.
- Expired sessions still fail validation with `401`.
- Active sessions are never deleted by cleanup.

---

## 🟡 Medium-Priority Fixes

### FIX-17 — Make timezone handling explicit

**Severity:** 🟡 Medium  
**Files:** `src/payshield/service.py`, `src/payshield/repository.py`

**Problem:** The code handles SQLite's naive datetimes by assigning UTC with `.replace(tzinfo=timezone.utc)`. This is correct only if all stored values are UTC. Aware non-UTC values are not converted correctly.

**Required change:**

- Document the UTC storage invariant.
- For aware values, use `astimezone(timezone.utc)`.
- Keep the naive-value compatibility path for SQLite.
- Ensure test fixtures store UTC timestamps.

**Acceptance criteria:**

- Naive SQLite datetimes are interpreted as UTC.
- Aware datetimes are converted to UTC before comparison.
- Expiration tests pass across timezone representations.

---

### FIX-18 — Centralize and harden cookie settings

**Severity:** 🟡 Medium  
**Files:** `src/payshield/config.py` (new or existing settings module), `src/payshield/routers/auth.py`, `src/payshield/service.py`

**Problem:** Session duration (`30` minutes) and cookie `max_age=1800` are separate literals. They can drift. Cookie settings are repeated across login/logout.

**Required change:**

- Define one source of truth for session duration and cookie name.
- Derive cookie `max_age` from the session duration.
- Centralize cookie attributes.
- Add `secure=True` for HTTPS deployments (environment-dependent).
- Consider `domain` if needed by deployment.
- Keep `httponly=True`, `samesite="lax"`, and `path="/"`.

**Acceptance criteria:**

- Cookie lifetime always matches server-side `expires_at`.
- Cookie flags are defined in one place.
- Production configuration can enable `Secure` without editing route logic.

---

### FIX-19 — Unify repository/service error handling

**Severity:** 🟡 Medium  
**Files:** `src/payshield/repository.py`, `src/payshield/service.py`

**Problem:**

- `UserRepository.create()` raises `HTTPException(409)`.
- `UserService.register_user()` raises `HTTPException(400)`.
- `SessionRepository.create()` re-raises raw SQLAlchemy errors.
- Delete methods do not handle commit failures.

**Required change:**

- Choose one consistent strategy:
  - repositories raise domain/database exceptions and services map them to HTTP errors, or
  - repositories raise `HTTPException` consistently (less clean but acceptable for this project).
- Use `400` for duplicate registration as required by the milestone.
- Ensure rollback happens on every failed write.
- Add rollback handling to delete methods.

**Acceptance criteria:**

- Duplicate registration always returns `400`.
- Unexpected database errors return a controlled `500` without leaking internals.
- No session is left in a failed transaction state after an exception.

---

### FIX-20 — Add service and integration tests

**Severity:** 🟡 Medium  
**Files:** `src/test/test_user_service.py` (new), `src/test/test_payroll_service.py` (new), `src/test/test_api_integration.py` (new)

**Required unit tests:**

`UserService`:
- Successful registration.
- Duplicate username.
- Duplicate email.
- Role injection attempt is ignored/rejected.
- Stored value is a bcrypt hash, never plaintext.
- Correct password authenticates.
- Wrong password returns `None`.
- Unknown username returns `None`.
- Over-limit password does not produce `500`.

`PayrollRecordService`:
- Existing record returns correct response.
- Missing record returns `None` or raises the expected not-found domain error.

`get_current_user`:
- Missing cookie.
- Invalid/tampered cookie.
- Expired session.
- Revoked session.
- Missing user.
- Valid session.

**Required Milestone 5 integration tests:**

1. Full employee authentication journey — register, login, cookie flags, payroll access, logout, post-logout `401`.
2. Remote device eviction — Device A revokes Device B; B gets `401`; A remains `200`.
3. IDOR prevention — Bob cannot revoke Charlie's session (`404`); Charlie remains active.
4. Cookie tampering and hash-at-rest defense — tampered cookie gets `401`; SQLite contains only 64-character SHA-256 hashes; raw token appears nowhere.
5. UTC expiration enforcement — manually expire session; request gets `401`.
6. Mass revocation with active-device preservation — three sessions, revoke-all returns `2`, caller remains active.

**Acceptance criteria:**

- All six integration scenarios pass.
- Unit tests cover the previously untested service and dependency behavior.
- No test depends on test execution order.

---

### FIX-21 — Fix test configuration and isolation

**Severity:** 🟡 Medium  
**Files:** `src/test/conftest.py`, `pyproject.toml`, `src/test/test_api_integration.py`

**Problems:**

- `get_db` uses the global engine, so integration tests can write to the real `DATABASE_URL` unless the dependency is overridden.
- The suite emits a `pytest-asyncio` deprecation warning about an unset `asyncio_default_fixture_loop_scope`.
- `TestClient` emits a Starlette/httpx deprecation warning in this environment.
- The Definition of Done requires tests to pass without warnings.

**Required change:**

- Override `get_db` in integration tests with the test session factory.
- Ensure every test uses the isolated in-memory database.
- Configure `asyncio_default_fixture_loop_scope` explicitly in `pyproject.toml`.
- Prefer `httpx.AsyncClient` with `ASGITransport` as required by the milestone.
- Ensure tables are created/dropped through fixtures, not import-time app initialization.

**Acceptance criteria:**

- Tests never touch the real database file.
- `pytest` reports zero warnings.
- Integration tests work with async fixtures and `ASGITransport`.

---

### FIX-22 — Replace import-time `create_tables()` and unify imports

**Severity:** 🟡 Medium  
**Files:** `src/app.py`, `src/payshield/model.py`, import statements across the project

**Problems:**

- `create_tables()` runs at import time, violating the Alembic migration invariant.
- It can create tables in the configured `DATABASE_URL` during tests or unrelated imports.
- The project mixes `src.payshield.*` and `payshield.*` imports, which can load two separate model/metadata copies in one process.

**Required change:**

- Remove `create_tables()` from `app.py`.
- Use Alembic (`alembic upgrade head`) to manage schema creation and evolution.
- If a startup check is needed, use a lifespan handler that verifies migrations rather than creating tables ad hoc.
- Pick one import root. Recommended: use `payshield.*` and run the app with `src` on the Python path (for example `uvicorn --app-dir src payshield...`).
- Do not mix `src.payshield` and `payshield` in the same process.

**Acceptance criteria:**

- Importing the app has no database side effects.
- Tests and production use the same module identities.
- Schema is managed by Alembic.
- The app starts cleanly with documented commands.

---

### FIX-23 — Align revocation count semantics

**Severity:** 🟡 Medium  
**Files:** `src/payshield/repository.py` (`delete_all_session`), `src/payshield/service.py`

**Problem:** `revoke_all_sessions()` counts every deleted row for the user, including already-expired sessions. The milestone test expects the count of *other active sessions*.

**Required change:**

- Decide and document whether `revoked_count` means:
  - all rows deleted, or
  - active sessions revoked.
- If active sessions are intended, filter by `expires_at > now` in the delete query.
- Keep the current-session exclusion behavior.

**Acceptance criteria:**

- `revoke-all` returns `2` when three active sessions exist and the current one is preserved.
- Behavior is covered by a test.

---

## 🟢 Optional Hardening

### FIX-24 — Optional security hardening

**Severity:** 🟢 Low  
**Files:** Depending on implementation

Consider these only after the milestone requirements are complete:

- Add login rate limiting and account lockout/backoff.
- Add CSRF tokens for state-changing requests as defense in depth beyond `SameSite=Lax`.
- Add security headers (`Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, etc.).
- Add audit logging for login, logout, and revocation events.
- Record and compare session `ip_address`/`user_agent` changes if the threat model requires it.
- Add session fingerprinting if appropriate for the deployment.
- Add a maximum number of concurrent sessions per user.
- Add periodic expired-session cleanup as a background job.

**Acceptance criteria:**

- Hardening does not break the required Milestone 4/5 behavior.
- New controls are covered by tests or documented as out of scope.

---

## ✅ Suggested Fix Order

1. `FIX-01` → `FIX-04`: fix service-layer correctness blockers.
2. `FIX-05`: implement the authentication dependency.
3. `FIX-06` → `FIX-08`: implement and mount the routers.
4. `FIX-09` → `FIX-12`: tighten revocation, token handling, and error behavior.
5. `FIX-13` → `FIX-16`: validation, auth hardening, async safety, cleanup.
6. `FIX-17` → `FIX-23`: robustness, test isolation, and app/migration cleanup.
7. `FIX-20` and `FIX-21`: finish the unit and integration test suites.
8. Run the full verification suite and confirm the Definition of Done.

---

## Verification Commands

```bash
# Apply migrations
uv run alembic upgrade head

# Run the full suite
uv run python -m pytest -v

# Run only Milestone 5 integration tests
uv run python -m pytest src/test/test_api_integration.py -v

# Start the application (adjust import path once FIX-22 is resolved)
uv run uvicorn --app-dir src payshield.app:app --reload
```

> Note: `uv run pytest` may be blocked by an Application Control policy in some Windows environments. If that happens, use `uv run python -m pytest`.

---

## Definition of Done Mapping

| Milestone requirement | Covered by |
|---|---|
| User repository/service create and authenticate correctly | FIX-01, FIX-02, FIX-03, FIX-13, FIX-14 |
| `get_current_user` protects secured endpoints with standard `401`s | FIX-05, FIX-20 |
| Cookies include `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=1800` | FIX-06, FIX-18 |
| Routes registered under `/api/v1` | FIX-08, FIX-22 |
| Six integration/security tests pass | FIX-20, FIX-21 |
| Full regression suite passes without warnings | FIX-19, FIX-21, FIX-22 |
| Schema managed through Alembic | FIX-22 |
| No plaintext session tokens in the database | FIX-10, FIX-12 |
| IDOR prevention | FIX-09 |
| Payroll least-privilege access | FIX-04, FIX-07 |
