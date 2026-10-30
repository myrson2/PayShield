from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.exc import IntegrityError

from payshield.model import User, Session, PayrollRecord

def test_cascade_delete_user_removes_sessions_and_payroll(db_session):
    """Edge Case 1: Deleting a User must cascade delete all associated Sessions

    and PayrollRecord rows, while deleting a Session must keep the User intact.
    """
    user = User(
        username="carol_hr",
        email="carol@payshield.com",
        hashed_password="hashed_secret_pw",
        role="hr_admin"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    session_1 = Session(
        user_id=user.id,
        session_token="a" * 64,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        ip_address="192.168.1.100",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    session_2 = Session(
        user_id=user.id,
        session_token="b" * 64,
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        ip_address="10.0.0.1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    payroll = PayrollRecord(
        user_id=user.id,
        salary_cents=12000000,
        currency="USD",
        bonus_cents=1500000
    )
    db_session.add_all([session_1, session_2, payroll])
    db_session.commit()

    # Verify entities are linked
    assert len(db_session.query(Session).filter_by(user_id=user.id).all()) == 2
    assert db_session.query(PayrollRecord).filter_by(user_id=user.id).first() is not None

    # Deleting a child session should NOT delete the user
    db_session.delete(session_2)
    db_session.commit()
    assert db_session.query(User).filter_by(id=user.id).first() is not None
    assert len(db_session.query(Session).filter_by(user_id=user.id).all()) == 1

    # Deleting the user MUST cascade and delete remaining session and payroll record
    db_session.delete(user)
    db_session.commit()

    assert db_session.query(Session).filter_by(user_id=user.id).all() == []
    assert db_session.query(PayrollRecord).filter_by(user_id=user.id).first() is None


def test_user_unique_constraints(db_session):
    """Edge Case 2: Duplicate usernames or emails must raise an IntegrityError."""
    user1 = User(
        username="unique_alice",
        email="alice@payshield.com",
        hashed_password="hashed_pw_1"
    )
    db_session.add(user1)
    db_session.commit()

    # Attempt duplicate username inside a savepoint so user1 remains committed
    duplicate_username = User(
        username="unique_alice",
        email="different_email@payshield.com",
        hashed_password="hashed_pw_2"
    )
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate_username)

    # Attempt duplicate email inside a savepoint
    duplicate_email = User(
        username="different_alice",
        email="alice@payshield.com",
        hashed_password="hashed_pw_3"
    )
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate_email)


def test_session_token_unique_constraint(db_session):
    """Edge Case 3: Two distinct sessions cannot share the same SHA-256 session_token."""
    user1 = User(username="user_one", email="one@payshield.com", hashed_password="pw")
    user2 = User(username="user_two", email="two@payshield.com", hashed_password="pw")
    db_session.add_all([user1, user2])
    db_session.commit()

    token_hash = "c" * 64
    session1 = Session(
        user_id=user1.id,
        session_token=token_hash,
        user_agent="Firefox",
        ip_address="127.0.0.1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    db_session.add(session1)
    db_session.commit()

    # Attempt collision on session_token
    session2 = Session(
        user_id=user2.id,
        session_token=token_hash,
        user_agent="Chrome",
        ip_address="127.0.0.2",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(session2)


def test_payroll_record_unique_user_id_constraint(db_session):
    """Edge Case 4: A User can only have a single active PayrollRecord (1-to-1)."""
    user = User(username="dan_dev", email="dan@payshield.com", hashed_password="pw")
    db_session.add(user)
    db_session.commit()

    payroll1 = PayrollRecord(
        user_id=user.id,
        salary_cents=8000000,
        currency="USD",
        bonus_cents=500000
    )
    db_session.add(payroll1)
    db_session.commit()

    # Attempt second payroll record for the same user
    payroll2 = PayrollRecord(
        user_id=user.id,
        salary_cents=9000000,
        currency="USD",
        bonus_cents=0
    )
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(payroll2)


def test_model_default_values_and_utc_timestamps(db_session):
    """Edge Case 5: Models must correctly populate defaults upon flush/commit."""
    user = User(
        username="eva_eng",
        email="eva@payshield.com",
        hashed_password="pw"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # User defaults verified post-commit
    assert user.role == "employee"
    assert user.created_at is not None
    assert isinstance(user.created_at, datetime)

    payroll = PayrollRecord(
        user_id=user.id,
        salary_cents=9500000
    )
    db_session.add(payroll)
    db_session.commit()
    db_session.refresh(payroll)

    # Payroll defaults verified post-commit
    assert payroll.currency == "USD"
    assert payroll.bonus_cents == 0
    assert payroll.updated_at is not None
    assert isinstance(payroll.updated_at, datetime)
