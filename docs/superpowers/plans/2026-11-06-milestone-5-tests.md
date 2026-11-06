# Milestone 5 Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the six Milestone 5 integration/security scenarios in `src/test/test_api_integration.py` against an isolated SQLite database.

**Architecture:** Exercise the mounted FastAPI application with `httpx.AsyncClient` and `ASGITransport`. Override the app's `get_db` dependency to use the existing function-scoped test session and reset overrides after each test; ensure app imports cannot create tables in the configured project database.

**Tech Stack:** Python 3.14+, pytest, pytest-asyncio, httpx `AsyncClient`/`ASGITransport`, FastAPI, SQLAlchemy, SQLite.

**Spec:** `MILESTONE_4_AND_5_REQUIREMENTS.md`, section 3.

## Global Constraints

- Implement tests only; do not modify Milestone 4 application behavior.
- Keep all integration data isolated from `DATABASE_URL` and roll it back after each test.
- Use server-side sessions; never expect a stateless JWT.
- Assert that session tokens in SQLite are SHA-256 hex digests and raw cookie tokens are absent from stored session columns.
- Verify ownership boundaries and cookie attributes defined in the requirements.

## Review Focus

- The test app may import `create_tables()` against the configured database; pin the test database to in-memory SQLite before app imports.
- Each client must retain its own cookie to model distinct devices and prevent cross-device cookie replacement.
- Payroll records must be explicitly seeded because registration does not initialize them.
- SQLite may return naive datetimes after persisting UTC values; expiration assertions must exercise the actual request path.
- Revocation behavior must be checked both through the response and by proving affected/retained cookies' access outcomes.

---

### Task 1: Isolate the integration test application and database

**Files:**
- Modify: `src/test/conftest.py`
- Create: `src/test/test_api_integration.py`

**Interfaces:**
- Consume: Existing `engine` and `db_session` fixtures; `get_db` from the same module referenced by the app's repository dependencies.
- Produce: An async client fixture using `ASGITransport`, a dependency override that yields the isolated `db_session`, and test helpers to register users, log in, and seed payroll records.

- [ ] **Step 1: Write a failing isolation check**

Add a test fixture setup assertion that the app's requests use the in-memory test session, and that `app.dependency_overrides` is empty again after the test.

- [ ] **Step 2: Run the targeted check**

Run: `uv run python -m pytest src/test/test_api_integration.py -q`
Expected: It fails until the app dependency is overridden with the test database.

- [ ] **Step 3: Implement test isolation**

Set `DATABASE_URL` to in-memory SQLite before importing the application/model modules in test collection. Override the exact `get_db` dependency used by the app's providers with the existing test session fixture, and clear the override during teardown.

- [ ] **Step 4: Verify the isolation check**

Run: `uv run python -m pytest src/test/test_api_integration.py -q`
Expected: The isolation check passes, and no integration setup touches the configured project database.

### Task 2: Verify the employee login, payroll, and logout journey

**Files:**
- Modify: `src/test/test_api_integration.py`

**Interfaces:**
- Consume: Task 1 async client and helper fixtures.
- Produce: An integration test for `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/payroll/me`, and `POST /api/v1/auth/logout`.

- [ ] **Step 1: Add the journey test**

Assert registration returns `201`; login returns `200` and sets `session_id` with `HttpOnly`, `SameSite=lax`, and `Path=/`; payroll access returns the seeded salary; logout returns a cookie with `Max-Age=0`; and payroll access using the logged-out client's cookie returns `401`.

- [ ] **Step 2: Run the journey test and confirm it exposes any mismatch**

Run: `uv run python -m pytest src/test/test_api_integration.py -k authentication_journey -q`
Expected: The test passes only if the existing implementation satisfies each assertion; report application failures without changing app code.

### Task 3: Verify device revocation and IDOR protection

**Files:**
- Modify: `src/test/test_api_integration.py`

**Interfaces:**
- Consume: Task 1 client/helper fixtures.
- Produce: Tests for remote revocation of a second device and cross-user revocation denial.

- [ ] **Step 1: Add the remote device eviction test**

Log in as one employee using separate clients for Device A and Device B; identify Device B's session from the session list by its `user_agent`; revoke it from Device A; assert B's payroll request returns `401` while A's returns `200`.

- [ ] **Step 2: Add the IDOR test**

Log in as Bob and Charlie using separate clients; have Bob revoke Charlie's session; assert the response is `404` or `403`, then verify Charlie's payroll request remains `200`.

- [ ] **Step 3: Run both tests**

Run: `uv run python -m pytest src/test/test_api_integration.py -k "remote_device or idor" -q`
Expected: Both tests pass and demonstrate that one user's request cannot revoke another user's session.

### Task 4: Verify cookie tampering, hash-at-rest, and expiry

**Files:**
- Modify: `src/test/test_api_integration.py`

**Interfaces:**
- Consume: Task 1 app/client and isolated database fixtures.
- Produce: Tests for invalid cookie tampering, SHA-256 token storage, raw-token absence, and UTC expiry enforcement.

- [ ] **Step 1: Add the tampering and storage test**

Tamper with a logged-in cookie and assert payroll returns `401`. Query stored `SessionModel` rows, assert every token is 64 lowercase hexadecimal characters, and assert the raw cookie value is absent from every persisted session column.

- [ ] **Step 2: Add the expiration test**

Set the logged-in session's `expires_at` to `datetime.now(timezone.utc) - timedelta(minutes=5)` in the test database; assert the protected payroll request returns `401`.

- [ ] **Step 3: Run both tests**

Run: `uv run python -m pytest src/test/test_api_integration.py -k "tampering or expiration" -q`
Expected: Both tests pass through the HTTP dependency/authentication path.

### Task 5: Verify mass revocation preserves the caller session

**Files:**
- Modify: `src/test/test_api_integration.py`

**Interfaces:**
- Consume: Task 1 app/client helpers and test database.
- Produce: A test covering three simultaneous user sessions, revoke-all count, and access for all three devices.

- [ ] **Step 1: Add the mass-revocation test**

Create three sessions for one employee with separate clients; call revoke-all from the caller client; assert `revoked_count == 2`, caller payroll remains `200`, and the other two clients receive `401`.

- [ ] **Step 2: Run the mass-revocation test**

Run: `uv run python -m pytest src/test/test_api_integration.py -k mass_revocation -q`
Expected: The caller session remains active and both other sessions are revoked.

### Task 6: Run Milestone 5 and regression suites

**Files:**
- Verify: `src/test/test_api_integration.py` and the existing `src/test/` suite.

- [ ] **Step 1: Run all six integration scenarios**

Run: `uv run python -m pytest src/test/test_api_integration.py -v`
Expected: All six scenarios pass without warnings.

- [ ] **Step 2: Run the complete test suite**

Run: `uv run python -m pytest -v`
Expected: The full suite passes without warnings; distinguish existing application failures from test harness failures in the handoff.
