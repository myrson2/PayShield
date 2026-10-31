import pytest
from payshield import (
    hash_token_256,
    hash_password,
    verify_password,
    async_hash_password,
    async_verify_password,
)


def test_hash_token_256_output_format_and_length():
    """Verify SHA-256 token hashing produces a 64-character lowercase hex string."""
    raw_token = "9f8a3c4e-1234-5678-abcd-ef0123456789"
    digest = hash_token_256(raw_token)

    assert isinstance(digest, str)
    assert len(digest) == 64
    # Ensure all characters are lowercase hex digits
    assert all(c in "0123456789abcdef" for c in digest)


def test_hash_token_256_is_deterministic():
    """Verify identical input tokens always produce identical SHA-256 digests."""
    raw_token = "session-fixed-uuid-12345"
    assert hash_token_256(raw_token) == hash_token_256(raw_token)


def test_hash_token_256_collision_resistance():
    """Verify distinct tokens produce distinct SHA-256 digests."""
    token_1 = "session-device-laptop-1"
    token_2 = "session-device-phone-2"
    assert hash_token_256(token_1) != hash_token_256(token_2)


def test_hash_token_256_empty_string():
    """Verify empty string produces the standard known SHA-256 digest."""
    expected_empty_digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert hash_token_256("") == expected_empty_digest


def test_sync_password_hashing_and_verification():
    """Verify synchronous password hashing and verification."""
    plain_password = "SuperSecurePayrollPassword!2026"
    hashed = hash_password(plain_password)

    # Must be non-reversible string
    assert isinstance(hashed, str)
    assert hashed != plain_password
    # Standard bcrypt prefix
    assert hashed.startswith("$2b$")

    # Correct password succeeds
    assert verify_password(plain_password, hashed) is True
    # Incorrect password fails
    assert verify_password("WrongPassword!", hashed) is False


def test_sync_password_salting_uniqueness():
    """Verify that hashing the same password twice yields unique hashes due to random salting."""
    plain = "same_secret_password"
    hash_1 = hash_password(plain)
    hash_2 = hash_password(plain)

    assert hash_1 != hash_2
    assert verify_password(plain, hash_1) is True
    assert verify_password(plain, hash_2) is True


@pytest.mark.asyncio
async def test_async_password_hashing_and_verification():
    """Verify asynchronous threadpool password hashing and verification."""
    plain_password = "AsyncPayrollPassword#2026"
    hashed = await async_hash_password(plain_password)

    assert isinstance(hashed, str)
    assert hashed.startswith("$2b$")
    assert await async_verify_password(plain_password, hashed) is True
    assert await async_verify_password("IncorrectPassword", hashed) is False


@pytest.mark.asyncio
async def test_async_password_salting_uniqueness():
    """Verify async password hashing produces distinct salts on each call."""
    plain = "async_same_secret"
    hash_1 = await async_hash_password(plain)
    hash_2 = await async_hash_password(plain)

    assert hash_1 != hash_2
    assert await async_verify_password(plain, hash_1) is True
    assert await async_verify_password(plain, hash_2) is True
