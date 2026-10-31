# 💼 PayShield (Gatekeeper): HR & Payroll Session Security Portal

**PayShield** is an enterprise-grade learning project designed to solve a critical real-world business challenge: **protecting sensitive employee salary, compensation data, and payroll records against session hijacking, credential theft, and unauthorized access**.

---

## 🏢 The Business Problem: Why Session Security is Non-Negotiable

In corporate HR and payroll systems, security failures lead to direct compliance violations, confidential salary leaks, and identity theft.

### Common Real-World Failure Modes
1. **The Shared Workstation Risk**: An HR administrator checks payroll on an office workstation. If the system uses tokens stored in `localStorage`, client-side scripts, browser extensions, or XSS attacks can silently export the token.
2. **The Lost Device / Offboarding Dilemma**: An employee loses their laptop, or an HR staff member is offboarded. If the system uses stateless JWTs, that token remains valid until it expires, leaving a window of vulnerability. In PayShield, the employee or security officer can view all active sessions and **revoke any session remotely in real time**.
3. **Database Backup Leakage**: If an attacker gets an internal database backup, storing plaintext session tokens gives them instant backdoor access to every logged-in user. In PayShield, only cryptographic hashes (`SHA-256`) exist in the database.
4. **Payroll Rush Event-Loop Freeze**: On payday morning, hundreds of employees log in simultaneously. Running `bcrypt` on the main async event loop halts all other payroll and API requests. Offloading to worker threads prevents event-loop starvation.

---

## 🏛️ System Architecture

```
[ Employee Browser ]                             [ PayShield Backend (FastAPI) ]                       [ SQLite Database ]
         |                                                      |                                              |
         | --- 1. POST /auth/login (username, password) ------> |                                              |
         |                                                      | --- 2. Verify password (Worker Thread) ----> |
         |                                                      |                                              |
         |                                                      | --- 3. Generate raw_token (UUIDv4)           |
         |                                                      | --- 4. Compute sha256(raw_token)             |
         |                                                      | --- 5. Save Session (user_agent, ip, hash)-> | Stored: sha256(token)
         |                                                      |                                              |
         | <-- 6. Set-Cookie: session_id=<raw_token> ---------- |                                              |
         |        (HttpOnly; SameSite=Lax; Max-Age=1800)        |                                              |
         |                                                      |                                              |
         | --- 7. GET /payroll/my-salary (Cookie) ------------> |                                              |
         |                                                      | --- 8. Compute sha256(cookie) -------------> |
         |                                                      | --- 9. Validate active, unexpired session -> |
         | <-- 10. 200 OK (Confidential Salary Record) -------- |                                              |
         |                                                      |                                              |
         | --- 11. POST /auth/sessions/revoke/{session_id} ---> | --- 12. Delete target session row ---------> | Instant Revocation!
```

---

## 🗄️ Core Data Entities

### 1. `User` (Employees & HR Staff)
- `id`: Primary key
- `username`: Unique login handle (e.g., `alice_hr`)
- `email`: Corporate email address
- `hashed_password`: Secure bcrypt hash (salted)
- `role`: Role designation (`employee`, `hr_admin`)
- `created_at`: Account creation timestamp

### 2. `Session` (Active Devices & Audit Trail)
- `id`: Primary key
- `user_id`: Foreign key referencing `User.id` (`ondelete="CASCADE"`)
- `session_token`: **SHA-256 hash** of the raw token (`String(64)`, indexed, unique)
- `user_agent`: Device / browser identifier string (for the session audit log)
- `ip_address`: Client IP address
- `expires_at`: UTC timestamp (e.g., 30 minutes from creation/activity)
- `created_at`: Session start timestamp

### 3. `PayrollRecord` (Confidential Business Resource)
- `id`: Primary key
- `user_id`: Foreign key referencing `User.id`
- `salary_cents`: Integer (e.g. `9500000` = $95,000.00)
- `currency`: Default `"USD"`
- `bonus_cents`: Integer
- `updated_at`: Last payroll audit timestamp

---

## 🗺️ Incremental Learning Milestones

You will build this project step-by-step. After each milestone, your Senior Tutor will review your implementation, analyze design choices, and guide you to the next step.

### 📌 Milestone 1: Database Setup, Domain Models & Migrations (`database.py`, `models.py`, `alembic/`)
- Configure SQLite database engine with thread check disabled (`check_same_thread=False`).
- Write the SQLAlchemy models: `User`, `Session`, and `PayrollRecord`.
- Ensure proper relationships, cascade deletion, and indexing on `session_token`.
- Initialize Alembic (`alembic init`) and configure `env.py` to point to `Base.metadata`.
- Enable `render_as_batch=True` in Alembic for SQLite compatibility with constraint alterations.
- Generate and apply the initial migration (`alembic upgrade head`) to establish version-controlled DDL.

### 📌 Milestone 2: Cryptographic Security Utilities (`payshield/security.py`, `test_security.py`) ✅ [COMPLETED]
- [x] Implement `hash_token_256(token: str) -> str` returning 64-character lowercase SHA-256 hex digest.
- [x] Implement non-blocking password hashing and verification using `asyncio.to_thread(hash_password, ...)` and `asyncio.to_thread(verify_password, ...)`.
- [x] Handle UTF-8 encoding and decoding cleanly for `bcrypt` byte inputs and string storage.
- [x] Create comprehensive automated test suite (`test_security.py`) verifying determinism, collision resistance, salting uniqueness, and async threadpool offloading.

### 📌 Milestone 3: Session Service & Device Audit Management (`session_service.py`)
- `create_session`: Generate raw UUIDv4, hash it, store with `user_agent` and `ip_address`, return `raw_token`.
- `validate_session`: Hash incoming cookie, query database, check expiry.
- `list_user_sessions`: Retrieve active devices/sessions for the authenticated employee.
- `revoke_session`: Invalidate a specific session ID (or all sessions on a user logout).

### 📌 Milestone 4: FastAPI Web Application & Routes (`../main.py`)
- Auth endpoints:
  - `POST /auth/register`: Onboard an employee.
  - `POST /auth/login`: Authenticate and set `Set-Cookie: session_id=...` with `HttpOnly` and `SameSite=Lax`.
  - `POST /auth/logout`: Revoke active session and clear cookie (`Max-Age=0`).
  - `GET /auth/sessions`: View all active logged-in devices/sessions for the current user.
  - `POST /auth/sessions/revoke/{session_id}`: Remote revocation of a specific device session.
- Business endpoints:
  - `GET /payroll/me`: Return authenticated employee's confidential salary record.

### 📌 Milestone 5: Automated Testing & Security Verification (`tests/`)
- Test password hashing offload and timing.
- Test `HttpOnly` cookie presence in response headers.
- Test that revoking a session from device A immediately cuts off access.
- Test that SQL database stores only 64-character SHA-256 hashes, not raw UUIDs.
- Test database restart persistence.

---

## 🚀 Environment Setup

```bash
# Navigate to the project
cd src

# Create virtual environment
python -m venv venv

# Activate on Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Install dependencies:
pip install fastapi uvicorn[standard] sqlalchemy alembic bcrypt httpx pytest pytest-asyncio
```
