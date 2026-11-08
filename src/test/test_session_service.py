from datetime import datetime, timezone, timedelta
import pytest

from payshield import SessionModel, UserModel, hash_token_256
from payshield.repository import SessionRepository
from payshield.service import SessionService


@pytest.fixture
def test_user(db_session):
    user = UserModel(
        username="test_employee",
        email="employee@payshield.com",
        hashed_password="hashed_pw_dummy",
        role="employee"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def another_user(db_session):
    user = UserModel(
        username="another_employee",
        email="another@payshield.com",
        hashed_password="hashed_pw_dummy_2",
        role="employee"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def session_service(db_session):
    repository = SessionRepository(db_session)
    return SessionService(repository)


def test_creation_and_hash_verification(session_service, test_user, db_session):
    """create_session returns a raw token, while DB stores 64-character SHA-256 hash."""
    result = session_service.create_session(
        user_id=test_user.id,
        user_agent="Mozilla/5.0 Test Browser",
        ip_address="192.168.1.50",
        duration_minutes=30
    )

    raw_token = result.raw_token
    session_response = result.session

    assert raw_token is not None
    assert isinstance(raw_token, str)
    assert session_response.user_id == test_user.id

    # Verify database persistence and SHA-256 hash
    expected_hash = hash_token_256(raw_token)
    assert len(expected_hash) == 64

    db_record = db_session.query(SessionModel).filter_by(id=session_response.id).first()
    assert db_record is not None
    assert db_record.session_token == expected_hash
    assert db_record.session_token != raw_token


def test_validate_session_success(session_service, test_user):
    """validate_session with a valid raw_token returns the active session."""
    created = session_service.create_session(
        user_id=test_user.id,
        user_agent="Mozilla/5.0 Test Browser",
        ip_address="192.168.1.50",
        duration_minutes=30
    )

    validated = session_service.validate_session(created.raw_token)
    assert validated is not None
    assert validated.id == created.session.id
    assert validated.user_id == test_user.id


def test_validate_session_non_existent_token(session_service):
    """validate_session with an unknown token returns None."""
    assert session_service.validate_session("non-existent-token-12345") is None
    assert session_service.validate_session("") is None


def test_validate_session_expired(session_service, test_user, db_session):
    """validate_session with an expired session returns None."""
    created = session_service.create_session(
        user_id=test_user.id,
        user_agent="Mozilla/5.0",
        ip_address="127.0.0.1",
        duration_minutes=30
    )

    # Manually expire the session in the DB
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.query(SessionModel).filter_by(id=created.session.id).update(
        {"expires_at": past_time}
    )
    db_session.commit()

    validated = session_service.validate_session(created.raw_token)
    assert validated is None


def test_list_user_sessions_ordering_and_active(session_service, test_user, db_session):
    """list_user_sessions returns user sessions ordered newest first and excludes expired."""
    s1 = session_service.create_session(
        user_id=test_user.id,
        user_agent="Browser A",
        ip_address="10.0.0.1",
        duration_minutes=30
    )
    s2 = session_service.create_session(
        user_id=test_user.id,
        user_agent="Browser B",
        ip_address="10.0.0.2",
        duration_minutes=30
    )

    # Add an already expired session directly
    expired_session = SessionModel(
        user_id=test_user.id,
        session_token="expired" + "0" * 57,
        user_agent="Old Browser",
        ip_address="10.0.0.3",
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    db_session.add(expired_session)
    db_session.commit()

    active_sessions = session_service.list_user_sessions(user_id=test_user.id)
    assert len(active_sessions) == 2
    # Check descending order by created_at
    assert active_sessions[0].created_at >= active_sessions[1].created_at
    ids = [s.id for s in active_sessions]
    assert s2.session.id == ids[0]
    assert s1.session.id == ids[1]
    assert expired_session.id not in ids


def test_revoke_session_success(session_service, test_user):
    """Calling revoke_session deletes the session; subsequent validation returns None."""
    created = session_service.create_session(
        user_id=test_user.id,
        user_agent="Mozilla/5.0",
        ip_address="127.0.0.1",
        duration_minutes=30
    )

    revoked = session_service.revoke_session(
        session_id=created.session.id,
        user_id=test_user.id
    )
    assert revoked is True

    # Validate fails after revocation
    assert session_service.validate_session(created.raw_token) is None


def test_revoke_session_idor_protection(session_service, test_user, another_user, db_session):
    """Revoking another user's session returns False and leaves it active."""
    created = session_service.create_session(
        user_id=test_user.id,
        user_agent="Mozilla/5.0",
        ip_address="127.0.0.1",
        duration_minutes=30
    )

    # another_user tries to revoke test_user's session
    revoked = session_service.revoke_session(
        session_id=created.session.id,
        user_id=another_user.id
    )
    assert revoked is False

    # Session must still be active and intact
    validated = session_service.validate_session(created.raw_token)
    assert validated is not None
    assert validated.id == created.session.id


def test_revoke_all_sessions(session_service, test_user):
    """revoke_all_sessions removes all sessions or spares keep_session_id."""
    s1 = session_service.create_session(user_id=test_user.id, user_agent="Device 1", ip_address="1.1.1.1")
    s2 = session_service.create_session(user_id=test_user.id, user_agent="Device 2", ip_address="1.1.1.2")
    s3 = session_service.create_session(user_id=test_user.id, user_agent="Device 3", ip_address="1.1.1.3")

    # Revoke all except s3 (current active session)
    deleted_count = session_service.revoke_all_sessions(
        user_id=test_user.id,
        keep_session_id=s3.session.id
    )
    assert deleted_count == 2

    # s1 and s2 should be revoked
    assert session_service.validate_session(s1.raw_token) is None
    assert session_service.validate_session(s2.raw_token) is None

    # s3 should remain valid
    assert session_service.validate_session(s3.raw_token) is not None

    final_deleted = session_service.revoke_all_sessions(user_id=test_user.id)
    assert final_deleted == 1
    assert session_service.validate_session(s3.raw_token) is None
