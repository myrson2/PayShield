# Milestone 1: Database Setup, Domain Models & Migrations

**Date**: 2026-10-31

## 💡 Core Concept
Relational data modeling in asynchronous/threaded environments requires explicit foreign key enforcement, declarative cascade lifecycles, and batch-enabled migration engines to guarantee schema evolution safety in SQLite.

## 📝 Short Description
Milestone 1 establishes the persistent domain model and migration foundation for PayShield using SQLAlchemy 2.0 and Alembic. It introduces standard naming conventions for database constraints, enforces SQLite foreign keys via engine event listeners, configures cascade deletion to prevent orphaned session and payroll records, and enables batch migration mode to overcome SQLite's architectural limitations when modifying existing tables.

## 🛠️ Body

### Use Case
In PayShield, sensitive employee data, confidential salary records, and active device sessions must remain strictly bound to their parent user. When an employee is offboarded, deleting the user must atomically purge all associated sessions and payroll records. Additionally, running unit tests and applying migrations across environments requires an isolated database layer with deterministic schema versioning.

### Code
From [`src/payshield/model.py`](file:///C:/Users/merss/OneDrive/Documents/Side%20Projects/PayShield/src/payshield/model.py):

```python
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

engine = create_engine(
    database,
    connect_args={"check_same_thread": False}
)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if engine.url.drivername.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    session_token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False
    )
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

### Line-by-Line Explanation
- `convention = { ... }`: Explicitly defines standardized naming patterns for indexes (`ix`), unique constraints (`uq`), check constraints (`ck`), foreign keys (`fk`), and primary keys (`pk`), enabling Alembic to identify and alter named constraints reliably.
- `connect_args={"check_same_thread": False}`: Allows SQLite database connections to be shared across multiple threads in multi-threaded web servers like FastAPI/Uvicorn without throwing `ProgrammingError`.
- `@event.listens_for(Engine, "connect")`: Registers a SQLAlchemy event hook that intercepts every low-level SQLite database connection at creation time.
- `cursor.execute("PRAGMA foreign_keys=ON")`: Enables foreign key constraint enforcement in SQLite, which is disabled by default for backwards compatibility.
- `user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), ...)`: Defines a database-level cascading delete rule ensuring child session rows are deleted automatically when the parent user record is removed.
- `session_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, ...)`: Allocates an exact 64-character indexed column sized specifically for SHA-256 hex digests with unique enforcement to guarantee $O(1)$ lookup performance and prevent collisions.

---

## 🎯 Common Interview Questions (Socratic Method)

1. **Why does SQLite require an explicit `PRAGMA foreign_keys=ON` event listener in SQLAlchemy?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   SQLite was originally designed with backwards compatibility for legacy applications that did not implement relational constraints. As a result, foreign key constraint enforcement is disabled by default in the underlying C library. Without explicitly sending `PRAGMA foreign_keys = ON` upon opening each connection, foreign key constraints are silently ignored, allowing orphaned records and broken relational integrity.
   </details>

2. **Why is `render_as_batch=True` mandatory in Alembic's `env.py` when using SQLite?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   Standard relational engines (PostgreSQL, MySQL) support direct `ALTER TABLE DROP COLUMN` or `ALTER TABLE ALTER COLUMN`. SQLite has severely limited `ALTER TABLE` capabilities and cannot drop or alter constraints or non-trivial columns directly. Alembic's batch mode works around this by creating a new temporary table with the desired schema, copying all data over, dropping the old table, and renaming the temporary table to the original table name.
   </details>

3. **What is the difference between SQLAlchemy ORM-level `cascade="all, delete-orphan"` and database-level `ondelete="CASCADE"`?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   `cascade="all, delete-orphan"` operates in Python application memory: when you delete an ORM object or remove it from a parent's collection, SQLAlchemy issues individual `DELETE` statements for the children during `session.commit()`. Conversely, `ondelete="CASCADE"` is enforced by the database engine itself via DDL: if a parent row is deleted directly (such as via raw SQL or an administrative tool), the database automatically purges child rows in a single atomic transaction without requiring Python to load or track child objects.
   </details>

4. **Why must `check_same_thread=False` be used with SQLite in FastAPI/SQLAlchemy applications?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   By default, Python's `sqlite3` driver restricts connection usage to the exact operating system thread that created it to prevent concurrent access issues. In FastAPI, request handlers and dependency injectors (`get_db`) execute across worker threads and async event loop boundaries. Setting `check_same_thread=False` allows connections to cross thread contexts safely while SQLAlchemy's connection pool coordinates synchronization.
   </details>

5. **Why do we define an explicit naming convention dictionary on `MetaData`?**
   <details>
   <summary>💡 View Answer & Engineering Rationale</summary>

   SQL databases require names for indexes and constraints. If constraints are created anonymously (unnamed), the database engine assigns an internal, vendor-specific random identifier (e.g., `sqlite_autoindex_users_1`). When Alembic later attempts to drop or alter that constraint in a future migration, it cannot reference the constraint deterministically. Explicit naming conventions guarantee repeatable, platform-agnostic constraint identifiers across all migration environments.
   </details>
