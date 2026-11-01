from datetime import datetime
from pydantic import BaseModel, ConfigDict


class UserSchema(BaseModel):
    username: str
    email: str
    role: str = "employee"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionSchema(BaseModel):
    user_id: int
    session_token: str
    user_agent: str
    ip_address: str
    expires_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SessionResponse(BaseModel):
    id: int
    user_id: int
    user_agent: str
    ip_address: str
    expires_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SessionAuthResult(BaseModel):
    session: SessionResponse  # The safe metadata
    raw_token: str  # The plaintext token for the cookie

class PayrollRecordSchema(BaseModel):
    user_id: int
    salary_cents: int
    currency: str = "USD"
    bonus_cents: int = 0
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PayrollRecordResponse(BaseModel):
    id: int
    user_id: int
    salary_cents: int
    currency: str = "USD"
    bonus_cents: int = 0
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
