import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from payshield.model import Base

# Ensure both 'backend' and 'backend/src' are in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir / "src") not in sys.path:
    sys.path.insert(0, str(backend_dir / "src"))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


# Isolated in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

# Enable SQLite foreign key enforcement for tests
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

@pytest.fixture(scope="session")
def engine():
    """Create an in-memory SQLite engine and create all tables for the test session."""
    test_engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(scope="function")
def db_session(engine):
    """Provide a transactional database session rolled back after every test."""
    connection = engine.connect()
    transaction = connection.begin()

    testing_session_local = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False
    )
    session = testing_session_local()

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
