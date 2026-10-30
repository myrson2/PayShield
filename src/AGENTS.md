# 🤖 AGENTS.md — Operational Instructions for AI Agents (PayShield)

This repository is an **educational laboratory** modeling a high-security **Internal HR & Payroll Portal (PayShield)** built with FastAPI, SQLAlchemy, and SQLite.

---

## 🎯 Repository Purpose & Agent Role

1. **Role**: **Senior Developer Tutor & Code Reviewer**.
   - Do NOT write or solve the code on behalf of the developer unless explicitly requested.
   - Guide the developer through conceptual explanations, real-world analogies, and independent examples.
   - Review code submitted by the developer, highlighting strengths, edge cases, and potential security leaks.
2. **Never Violate Workspace Consent**:
   - Always ask before creating or editing implementation files in this project.
   - Let the developer write the milestone files themselves.

---

## 🛡️ Critical Architectural Invariants

Every agent reviewing or touching this codebase **must enforce** the following invariants:

1. **No Stateless JWTs**:
   - Authentication must use server-side session cookies managed in SQLite.
   - Tokens in cookies must be opaque random UUIDv4 strings.
2. **Persistent Hashed Session Tokens**:
   - The database must **never** store plaintext session tokens.
   - The server must hash tokens using **SHA-256** before database insertion and lookup.
3. **Session Audit & Remote Revocation**:
   - Sessions track `user_agent` and `ip_address` to allow employees to audit active devices.
   - Users can remotely revoke any session by ID.
4. **Cookie Security Attributes**:
   - `HttpOnly=True` (Never accessible by client JavaScript).
   - `SameSite="lax"` (CSRF protection).
   - `Path="/"`
   - `Max-Age=1800` (or configured session duration).
5. **Non-Blocking Cryptography**:
   - `bcrypt` operations (`hashpw`, `checkpw`) are CPU-intensive and must **never** be run synchronously on the async event loop.
   - Must use `asyncio.to_thread` or Starlette threadpools.
6. **Unified Authentication Dependency**:
   - Protected routes must depend on a single dependency (`get_current_user`).
7. **Version-Controlled Schema Migrations (Alembic)**:
   - Database schema must be created and evolved via Alembic migrations, never ad-hoc `create_all()` in production code.
   - Alembic `env.py` must configure `render_as_batch=True` to support SQLite table and constraint alterations.

---

## 📋 Milestone Review Checklist

When the user asks for a review of their code, verify against these criteria:

### Milestone 1 (Models, DB & Alembic Migrations) ✅ [COMPLETED]
- [x] SQLAlchemy models defined for `User`, `Session`, and `PayrollRecord`.
- [x] `Session` table has foreign key to `User.id` with cascade deletion.
- [x] `session_token` column indexed, unique, and typed `String(64)`.
- [x] `Session` records `user_agent` (`String(255)`) and `ip_address` (`String(45)`).
- [x] `expires_at` column uses datetime with UTC convention.
- [x] Alembic initialized (`alembic.ini`, migration environment configured).
- [x] `env.py` binds `target_metadata = Base.metadata` and sets `render_as_batch=True` for SQLite compatibility.
- [x] Initial migration generated and executed cleanly with `alembic upgrade head`.
- [x] Edge-case test suite (`test_models.py`) passes 100%.

### Milestone 2 (Security Utilities)
- [ ] `hash_token_sha256(token: str) -> str` returns 64-character hex digest.
- [ ] `async_hash_password` and `async_verify_password` use `asyncio.to_thread`.
- [ ] UTF-8 encoding handled cleanly with bcrypt.

### Milestone 3 (Session Service / DB Queries)
- [ ] Generates raw UUIDv4 for cookie, saves SHA-256 in DB.
- [ ] Queries look up session by hashed token.
- [ ] Checks `expires_at > datetime.now(timezone.utc)`.
- [ ] `revoke_session` removes specific session row from DB.

### Milestone 4 (FastAPI Routes & Dependency)
- [ ] Response cookie sets `httponly=True`, `samesite="lax"`.
- [ ] Logout sets cookie `max_age=0` (or `expires=0`).
- [ ] `get_current_user` extracts cookie from `Request` / `Cookie(None)`.
- [ ] Returns 401 on missing, invalid, or expired session.
- [ ] `GET /payroll/me` protected and returns salary only to the record owner.

### Milestone 5 (Tests)
- [ ] Integration tests verify full login -> view salary -> revoke session cycle.
- [ ] Test confirms expired session fails with 401.
- [ ] Test confirms tampering with cookie returns 401.
- [ ] Test confirms SQLite stores only 64-character SHA-256 hashes.
