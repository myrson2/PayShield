# Milestone 2: Cryptographic Security Utilities & Threadpool Offloading

**Date**: 2026-10-31

## 💡 Core Concept
Separating cryptographic hashing by computational profile—using ultra-fast single-pass hashing (SHA-256) for frequent token lookups and offloading intentionally slow, CPU-bound key-stretching algorithms (Bcrypt) to thread pools—prevents event-loop starvation while ensuring defense-in-depth data security.

## 📝 Short Description
Milestone 2 implements the cryptographic engine of PayShield. It addresses two critical security and performance requirements: preventing database leaks by storing only SHA-256 digests of session cookies, and avoiding web server freezes by executing CPU-intensive bcrypt password hashing and verification off the main async event loop via Python's `asyncio.to_thread`.

## 🛠️ Body

### Use Case
On high-traffic occasions like payday morning, hundreds of employees authenticate concurrently while others check their confidential salary records. Running bcrypt directly on FastAPI's single-threaded async event loop halts all incoming requests for 200–300ms per login attempt. By delegating bcrypt to worker threads, the async event loop remains free to serve other requests in parallel. Concurrently, session tokens in transit (cookies) are separated from session tokens at rest (database) using fast SHA-256 hashing to protect active sessions against database backup compromises.

### Code
From [`src/payshield/security.py`](file:///C:/Users/merss/OneDrive/Documents/Side%20Projects/PayShield/src/payshield/security.py):

```python
import hashlib
import bcrypt
import asyncio

def hash_token_256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)

async def async_hash_password(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)

async def async_verify_password(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)
```

### Line-by-Line Explanation
- `hash_token_256(token: str) -> str`: Encodes the raw session token string into UTF-8 bytes and calculates the standard SHA-256 64-character lowercase hexadecimal digest.
- `pwd_bytes = password.encode('utf-8')`: Converts string inputs to raw bytes because the C/Rust backend of `bcrypt` operates strictly on byte sequences, throwing `TypeError` if passed strings.
- `salt = bcrypt.gensalt()`: Generates a cryptographically secure, randomized 128-bit salt with default cost factor ($2^{12} = 4096$ rounds) to defend against precomputed rainbow table attacks.
- `hashed = bcrypt.hashpw(pwd_bytes, salt)`: Executes key stretching to produce a salted bcrypt hash containing the algorithm identifier, cost factor, salt, and hash.
- `return hashed.decode('utf-8')`: Decodes the resulting hash bytes back into a standard UTF-8 string for safe storage in the database's `hashed_password` text column.
- `bcrypt.checkpw(pwd_bytes, hashed_bytes)`: Extracts the embedded salt and cost factor from `hashed_bytes`, hashes `pwd_bytes`, and executes a constant-time comparison to prevent timing attacks.
- `await asyncio.to_thread(hash_password, password)`: Dispatches the CPU-bound synchronous hashing function to Python's background `ThreadPoolExecutor`, immediately yielding control back to the async event loop so other concurrent requests proceed unimpeded.

---

## 🎯 Common Interview Questions (Socratic Method)

1. **Why does decorating a CPU-intensive function with `async def` without `await asyncio.to_thread` fail to prevent event-loop freezing?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   `async def` merely indicates that a function is a Python coroutine; it does not automatically introduce multi-threading or parallel execution. If an `async def` function executes synchronous CPU-bound operations (such as `bcrypt.hashpw`) without yielding execution via `await`, it monopolizes the single OS thread running the async event loop. The loop cannot execute any other pending tasks, timers, or I/O callbacks until that CPU calculation completes.
   </details>

2. **Why is `hash_token_256` kept synchronous instead of being wrapped in `asyncio.to_thread`?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   SHA-256 is an ultra-fast algorithm taking approximately ~1 microsecond (0.001ms) of CPU time. The overhead of scheduling work onto Python's thread pool and performing an operating system thread context switch takes roughly 10 to 50 microseconds. Offloading SHA-256 to a thread would actually make the operation 10 to 50 times slower. Offloading is only advantageous when task duration significantly exceeds thread scheduling overhead (e.g., bcrypt taking 100–300ms).
   </details>

3. **Why do we store SHA-256 hashes of session tokens in SQLite rather than plaintext tokens or raw UUIDs?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   This implements defense-in-depth. If an attacker gains read access to the database (through an SQL injection vulnerability, compromised backup files, or internal data leakage), plaintext tokens would immediately allow them to hijack all active user sessions. Because SHA-256 is a one-way cryptographic function, attackers cannot reverse the stored hashes to recover the raw cookie tokens needed to authenticate against the server.
   </details>

4. **Why is bcrypt preferred for passwords while SHA-256 is preferred for session tokens?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   Passwords typically have low entropy (human-chosen words or short phrases) and must be protected against offline brute-force cracking using intentionally slow, salted, memory/CPU-heavy key-stretching functions like bcrypt. In contrast, session tokens are high-entropy, 128-bit cryptographically random UUIDs ($2^{128}$ possibilities), making brute-force unfeasible. Session verification occurs on every HTTP request and requires fast, deterministic $O(1)$ lookups, making SHA-256 the optimal choice.
   </details>

5. **How does `bcrypt.checkpw` protect against side-channel timing attacks?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   Standard string equality comparison (`str1 == str2`) terminates early at the first mismatched byte, leaking information about how many leading characters matched based on how quickly the comparison returns. `bcrypt.checkpw` implements a constant-time comparison algorithm (similar to `hmac.compare_digest`), ensuring that verification takes the exact same number of clock cycles regardless of whether the password matches completely, partially, or not at all.
   </details>
