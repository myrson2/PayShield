# Validation & Test Plan: Authentication & Session Security

> **Feature Directory:** `specs/feature/auth-session-security-2026-10-30`  
> **Milestone:** Milestone 1 — The Working Code Dictionary (Phase 1)  
> **Status:** Approved for Implementation  
> **Last Updated:** 2026-10-30

---

## 1. Overview & Quality Gates

This document defines the validation strategy, test matrix, and verification procedures for Phase 1 (Authentication & Session Security). 

All tests must be executed with `pytest` using an asynchronous test client (`httpx.AsyncClient`) backed by an isolated in-memory SQLite database (`sqlite:///:memory:`) that enforces foreign key constraints via `PRAGMA foreign_keys=ON`.

---

## 2. Test Scenarios & Test Matrix

| ID | Test Case | Target Layer | Expected Result |
|---|---|---|---|
| **TC-AUTH-01** | User Registration Success | API (`POST /auth/session-user/register`) | HTTP `201 Created`, returns `UserResponse`, password is not exposed, user persisted. |
| **TC-AUTH-02** | Reject Duplicate Email/Username | API (`POST /auth/session-user/register`) | HTTP `409 Conflict` when registering with existing email or username. |
| **TC-AUTH-03** | Successful Login & Cookie Issuance | API (`POST /auth/session-user/login`) | HTTP `200 OK`, response header includes `Set-Cookie` with `session_id`, `HttpOnly=True`, `SameSite=lax`. |
| **TC-AUTH-04** | Invalid Credentials Rejection | API (`POST /auth/session-user/login`) | HTTP `401 Unauthorized` for incorrect password or non-existent username; no cookie issued. |
| **TC-AUTH-05** | Persistent Hashed Token Verification | Database (`Session` table) | The database row stores `sha256(raw_cookie_token)` in `session_token`. Raw token is never found in the DB. |
| **TC-AUTH-06** | Authenticated Access to Protected Route | API (`GET /auth/session-user/user`) | HTTP `200 OK` when presenting valid `session_id` cookie; returns authenticated user profile. |
| **TC-AUTH-07** | Rejection of Missing Cookie | API (`GET /auth/session-user/user`) | HTTP `401 Unauthorized` when request has no cookie. |
| **TC-AUTH-08** | Rejection of Forged/Tampered Cookie | API (`GET /auth/session-user/user`) | HTTP `401 Unauthorized` when cookie value does not match any hashed token in the DB. |
| **TC-AUTH-09** | Rejection of Expired Session | API / Database | HTTP `401 Unauthorized` when `expires_at < now()`; expired record is purged from the database. |
| **TC-AUTH-10** | Logout Invalidation | API (`POST /auth/session-user/logout`) | HTTP `204 No Content`, DB session record is deleted, response deletes cookie (`Max-Age=0`). Subsequent calls return `401`. |
| **TC-AUTH-11** | Non-blocking Cryptography Verification | Utilities (`async_hash_password`) | Confirms `bcrypt` hashing runs asynchronously in a worker thread and does not block the asyncio event loop. |
| **TC-AUTH-12** | Database Cascade on User Deletion | Database Integration | Deleting a `User` cascades to delete all associated `Session` records via `ondelete="CASCADE"`. |

---

## 3. Test Implementation Blueprint (`backend/tests/test_auth.py`)

Below is the test structure to validate this feature:

```python
import pytest
from httpx import AsyncClient, ASGITransport
import hashlib
from src.app import app
from src.model.models import User, Session

@pytest.mark.anyio
async def test_register_and_login_flow(db_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register
        reg_payload = {
            "username": "auth_tester",
            "email": "tester@example.com",
            "password": "ValidPassword123!"
        }
        reg_res = await client.post("/auth/session-user/register", json=reg_payload)
        assert reg_res.status_code == 201

        # 2. Login
        login_data = {
            "username": "auth_tester",
            "password": "ValidPassword123!"
        }
        login_res = await client.post(
            "/auth/session-user/login",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert login_res.status_code == 200
        assert "session_id" in login_res.cookies
        raw_cookie = login_res.cookies["session_id"]

        # 3. Verify Database Hashed Storage
        expected_hash = hashlib.sha256(raw_cookie.encode("utf-8")).hexdigest()
        db_record = db_session.query(Session).filter_by(session_token=expected_hash).first()
        assert db_record is not None
        assert db_record.session_token != raw_cookie

        # 4. Access Protected Route
        user_res = await client.get("/auth/session-user/user")
        assert user_res.status_code == 200
        assert user_res.json()["username"] == "auth_tester"

        # 5. Logout
        logout_res = await client.post("/auth/session-user/logout")
        assert logout_res.status_code == 204

        # 6. Verify Session is Invalidated
        stale_res = await client.get("/auth/session-user/user")
        assert stale_res.status_code == 401
```

---

## 4. Execution & Verification Commands

Run the test suite from `backend/`:

```bash
# Run all tests
uv run pytest

# Run specifically the authentication tests with verbose output
uv run pytest tests/test_auth.py -v
```

---

## 5. Acceptance Checklist

- [ ] All 12 test cases in the test matrix are implemented and pass.
- [ ] No regression in existing `test_models.py` tests.
- [ ] In-memory session dictionary (`temp_session`) is completely eliminated from the source code.
- [ ] Database session tokens match the SHA-256 digest of the cookie value.
