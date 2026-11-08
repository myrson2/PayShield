import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from payshield.model import get_db
from app import app

async def _register_user(client: AsyncClient, username: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.test",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _login_user(
    client: AsyncClient,
    username: str,
    user_agent: str,
) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": "correct-horse-battery-staple",
        },
        headers={"user-agent": user_agent},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest_asyncio.fixture
async def isolated_database(db_session):
    def override_get_db():
        yield db_session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


@pytest.fixture
def client_factory(isolated_database):
    def create_client():
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )
    return create_client


@pytest.mark.asyncio
async def test_client_overrides_database_dependency(isolated_database):
    assert get_db in app.dependency_overrides


def _seed_payroll(db_session, user_id: int) -> None:
    from payshield.model import PayrollRecordModel

    db_session.add(
        PayrollRecordModel(
            user_id=user_id,
            salary_cents=1234567,
            currency="USD",
            bonus_cents=0,
        )
    )
    db_session.commit()


@pytest.mark.asyncio
async def test_authentication_journey(client_factory, db_session):
    from payshield.model import UserModel

    async with client_factory() as client:
        registration = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice_hr",
                "email": "alice@example.test",
                "password": "correct-horse-battery-staple",
            },
        )
        assert registration.status_code == 201, (
            registration.text
        )
        user = db_session.query(UserModel).filter_by(username="alice_hr").one()
        _seed_payroll(db_session, user.id)

        login = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "alice_hr",
                "password": "correct-horse-battery-staple",
            },
        )
        assert login.status_code == 200
        set_cookie = login.headers["set-cookie"]
        assert "session_id=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert "Path=/" in set_cookie
        assert "Max-Age=1800" in set_cookie
        assert "raw_token" not in login.text

        payroll = await client.get("/api/v1/payroll/me")
        assert payroll.status_code == 200
        assert payroll.json()["salary_cents"] == 1234567

        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 200
        assert "Max-Age=0" in logout.headers["set-cookie"]

        after_logout = await client.get("/api/v1/payroll/me")
        assert after_logout.status_code == 401


@pytest.mark.asyncio
async def test_remote_device_revocation(client_factory, db_session):
    from payshield.model import UserModel

    async with client_factory() as device_a, client_factory() as device_b:
        await _register_user(device_a, "alice_hr")
        alice = db_session.query(UserModel).filter_by(username="alice_hr").one()
        _seed_payroll(db_session, alice.id)
        await _login_user(device_a, "alice_hr", "Desktop")
        await _login_user(device_b, "alice_hr", "Mobile")

        sessions = await device_a.get("/api/v1/auth/sessions")
        assert sessions.status_code == 200, sessions.text
        device_b_session = next(
            session for session in sessions.json()
            if session["user_agent"] == "Mobile"
        )
        revoked = await device_a.post(
            f"/api/v1/auth/sessions/revoke/{device_b_session['id']}"
        )
        assert revoked.status_code == 200, revoked.text
        assert (await device_b.get("/api/v1/payroll/me")).status_code == 401
        assert (await device_a.get("/api/v1/payroll/me")).status_code == 200


@pytest.mark.asyncio
async def test_idor_cannot_revoke_another_users_session(client_factory, db_session):
    from payshield.model import UserModel

    async with client_factory() as bob_client, client_factory() as charlie_client:
        await _register_user(bob_client, "bob_employee")
        bob_session = await _login_user(bob_client, "bob_employee", "Bob's device")
        await _register_user(charlie_client, "charlie_employee")
        charlie = db_session.query(UserModel).filter_by(
            username="charlie_employee"
        ).one()
        _seed_payroll(db_session, charlie.id)
        charlie_session = await _login_user(
            charlie_client,
            "charlie_employee",
            "Charlie's device",
        )

        response = await bob_client.post(
            f"/api/v1/auth/sessions/revoke/{charlie_session['id']}"
        )
        assert response.status_code in (403, 404), response.text
        assert (await charlie_client.get("/api/v1/payroll/me")).status_code == 200
        assert bob_session["user_id"] != charlie_session["user_id"]


@pytest.mark.asyncio
async def test_cookie_tampering_and_hashed_token_storage(client_factory, db_session):
    import re

    from payshield.model import SessionModel, UserModel

    async with client_factory() as client:
        await _register_user(client, "dana_employee")
        dana = db_session.query(UserModel).filter_by(
            username="dana_employee"
        ).one()
        _seed_payroll(db_session, dana.id)
        await _login_user(client, "dana_employee", "Dana's browser")
        raw_token = client.cookies.get("session_id")
        assert raw_token

        replacement = "A" if raw_token[-1] != "A" else "B"
        tampered_response = await client.get(
            "/api/v1/payroll/me",
                headers={"Cookie": f"session_id={raw_token[:-1] + replacement}"},        )
        assert tampered_response.status_code == 401

        stored_sessions = db_session.query(SessionModel).all()
        assert stored_sessions
        for session in stored_sessions:
            assert re.fullmatch(r"[a-f0-9]{64}", session.session_token)
            for column in SessionModel.__table__.columns:
                assert getattr(session, column.key) != raw_token


@pytest.mark.asyncio
async def test_session_expiration_is_unauthorized(client_factory, db_session):
    from datetime import datetime, timedelta, timezone

    from payshield.model import SessionModel, UserModel

    async with client_factory() as client:
        await _register_user(client, "erin_employee")
        erin = db_session.query(UserModel).filter_by(
            username="erin_employee"
        ).one()
        _seed_payroll(db_session, erin.id)
        session_response = await _login_user(
            client,
            "erin_employee",
            "Erin's browser",
        )

        session = db_session.get(SessionModel, session_response["id"])
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db_session.commit()

        response = await client.get("/api/v1/payroll/me")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_mass_revocation_preserves_caller_session(client_factory, db_session):
    from payshield.model import UserModel

    async with (
        client_factory() as device_a,
        client_factory() as device_b,
        client_factory() as device_c,
    ):
        await _register_user(device_a, "frank_employee")
        frank = db_session.query(UserModel).filter_by(
            username="frank_employee"
        ).one()
        _seed_payroll(db_session, frank.id)
        await _login_user(device_a, "frank_employee", "Device A")
        await _login_user(device_b, "frank_employee", "Device B")
        await _login_user(device_c, "frank_employee", "Device C")

        response = await device_c.post("/api/v1/auth/sessions/revoke-all")
        assert response.status_code == 200, response.text
        assert response.json()["revoked_count"] == 2
        assert (await device_c.get("/api/v1/payroll/me")).status_code == 200
        assert (await device_a.get("/api/v1/payroll/me")).status_code == 401
        assert (await device_b.get("/api/v1/payroll/me")).status_code == 401
