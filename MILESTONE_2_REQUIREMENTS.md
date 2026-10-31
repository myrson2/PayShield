# 🔐 Milestone 2: Cryptographic Security Utilities

**Target Module:** `src/payshield/security.py`  
**Test Suite:** `src/test/test_security.py`  
**Status:** In Progress (Requirements Defined)  

---

## 1. Objective & Security Rationale

Milestone 2 establishes the cryptographic foundation required for secure session management and authentication in PayShield.

### A. SHA-256 for Opaque Session Tokens
* **The Vulnerability:** Storing raw session cookies in database tables exposes all logged-in accounts if an internal database backup or SQL dump is leaked.
* **The Solution:** The server generates random, opaque UUIDv4 strings for the client's cookie, but hashes the token using **SHA-256** prior to database insertion or query lookup.
* **Why SHA-256?** SHA-256 is collision-resistant, deterministic, fast ($O(1)$ database index lookups), and produces a standardized 64-character hex digest that fits `String(64)` in the database schema.

### B. Worker-Thread Bcrypt (Preventing Event-Loop Starvation)
* **The Vulnerability:** `bcrypt` is intentionally computationally expensive (salting + key stretching) to deter brute-force attacks. Hashing or verifying a password takes ~100–300ms of synchronous CPU time.
* **The Solution:** Running `bcrypt.hashpw` or `bcrypt.checkpw` directly on FastAPI's main async event loop halts all other concurrent requests. We offload these CPU-bound tasks to worker threads using `asyncio.to_thread`.

---

## 2. Technical Specifications (`src/payshield/security.py`)

### 2.1 Token Hashing
```python
def hash_token_sha256(token: str) -> str:
    """
    Compute a SHA-256 hex digest of an opaque session token.
    
    Args:
        token: The raw session token string (e.g., UUIDv4 string).
        
    Returns:
        A 64-character lowercase hexadecimal string digest.
    """
```
**Requirements:**
- Must encode the input `str` to UTF-8 `bytes`.
- Must compute the digest via standard library `hashlib.sha256()`.
- Must return `hexdigest()` (guaranteed 64 lowercase hex characters).
- Must be strictly deterministic (identical input produces identical output).

---

### 2.2 Synchronous Password Hashing & Verification
```python
def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt with a generated salt.
    
    Args:
        password: Raw user password string.
        
    Returns:
        Salted bcrypt hash decoded as a UTF-8 string.
    """

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    
    Args:
        plain_password: The plaintext candidate password.
        hashed_password: The stored bcrypt hash string.
        
    Returns:
        True if the password matches the hash, False otherwise.
    """
```
**Requirements:**
- `hash_password`:
  - Encode `password` to UTF-8 `bytes`.
  - Generate salt via `bcrypt.gensalt()`.
  - Hash via `bcrypt.hashpw(password_bytes, salt)`.
  - Return the resulting bytes decoded as a UTF-8 string (`.decode("utf-8")`) for database storage.
- `verify_password`:
  - Encode `plain_password` and `hashed_password` to `bytes`.
  - Return `bcrypt.checkpw(plain_bytes, hashed_bytes)`.
  - Must return `False` on mismatched passwords without throwing unhandled exceptions.

---

### 2.3 Non-Blocking Asynchronous Wrappers
```python
async def async_hash_password(password: str) -> str:
    """
    Asynchronously hash a password offloaded to a worker thread.
    """

async def async_verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Asynchronously verify a password offloaded to a worker thread.
    """
```
**Requirements:**
- Use `await asyncio.to_thread(hash_password, password)`.
- Use `await asyncio.to_thread(verify_password, plain_password, hashed_password)`.
- Must be awaitable coroutines so FastAPI route handlers can process requests without blocking the event loop.

---

## 3. Implementation Guardrails & Edge Cases

1. **Bcrypt Type Safety (`bytes` vs `str`)**:
   - `bcrypt.hashpw` and `bcrypt.checkpw` accept only `bytes`. Passing strings raises `TypeError`.
   - Ensure explicit `.encode("utf-8")` before passing to bcrypt, and `.decode("utf-8")` when returning to callers.
2. **72-Byte Truncation Limit**:
   - Standard bcrypt truncates input passwords longer than 72 bytes. Keep this in mind when designing registration validations in future milestones.
3. **Empty Strings**:
   - Verify behavior when an empty string `""` is passed to `hash_token_sha256` (must return the standard SHA-256 digest of empty bytes, `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).
4. **Salt Uniqueness**:
   - Calling `hash_password("password123")` twice must produce two completely distinct hashes due to random salting, yet both must return `True` when checked with `verify_password`.

---

## 4. Test Specifications (`src/test/test_security.py`)

Create unit tests covering the following scenarios:

- [ ] **SHA-256 Digest Length**: Assert `len(hash_token_sha256(token)) == 64`.
- [ ] **SHA-256 Determinism**: Assert `hash_token_sha256("token-abc") == hash_token_sha256("token-abc")`.
- [ ] **SHA-256 Collision Resistance**: Assert `hash_token_sha256("token-1") != hash_token_sha256("token-2")`.
- [ ] **Password Hashing Non-Reversibility**: Assert `hash_password("secret") != "secret"`.
- [ ] **Password Hash Structure**: Assert `hash_password("secret").startswith("$2b$")`.
- [ ] **Password Verification Success**: Assert `verify_password("correct_pw", hash_password("correct_pw")) is True`.
- [ ] **Password Verification Failure**: Assert `verify_password("wrong_pw", hash_password("correct_pw")) is False`.
- [ ] **Async Hashing & Verification**: Test `async_hash_password` and `async_verify_password` inside `@pytest.mark.asyncio` test cases.

---

## 5. Verification Command

Run the test suite once implemented:
```bash
pytest src/test/test_security.py -v
```
