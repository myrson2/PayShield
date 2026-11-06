from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, HTTPException, status

from dependencies import (
    get_current_user,
    get_session_service,
    get_user_service,
)
from payshield.schema import (
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    UserResponse,
)
from payshield.model import UserModel
from payshield.service import SessionService, UserService

router = APIRouter()


@router.post("/register", status_code=201, response_model=UserResponse)
async def register(
        payload: RegisterRequest,
        user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
   return await user_service.register_user(username=payload.username,
            password=payload.password,
            email=payload.email)

@router.post("/login", response_model=SessionResponse)
async def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        user_service: Annotated[UserService, Depends(get_user_service)],
        session_service: Annotated[SessionService, Depends(get_session_service)],
) -> SessionResponse:
    user_agent = request.headers.get("user-agent", "unknown")
    ip_address = request.client.host if request.client else "unknown"

    authenticate_user = await user_service.authenticate_user(username=payload.username, password=payload.password)
    if authenticate_user is None:
        raise HTTPException(status_code=404, detail="Invalid Credentials")

    session = session_service.create_session(
        user_id=authenticate_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    response.set_cookie(
        key="session_id",
        value=session.raw_token,
        httponly=True,
        samesite="lax",
        max_age=1800,
        path="/",
    )
    return session.session


@router.post("/logout")
async def logout(
        request: Request,
        response: Response,
        current_user: Annotated[UserModel, Depends(get_current_user)],
        session_service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, str]:
    raw_token = request.cookies.get("session_id")

    if raw_token is None:
        raise HTTPException(status_code=401, detail="Invalid Credentials")

    session = session_service.validate_session(raw_token)
    if session:
        session_service.revoke_session(
            user_id=current_user.id,
            session_id=session.id
        )
    # 3. Clear the cookie from the client browser
    response.delete_cookie(
        key="session_id",
        path="/",
        httponly=True,
        samesite="lax",
    )
    # 4. Return success message
    return {"message": "Logged out successfully"}

@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
        current_user: Annotated[UserModel, Depends(get_current_user)],
        session_service: Annotated[SessionService, Depends(get_session_service)],
) -> list[SessionResponse]:
    return session_service.list_user_sessions(current_user.id)


@router.post("/sessions/revoke/{session_id}")
async def revoke_session(
        session_id: int,
        current_user: Annotated[UserModel, Depends(get_current_user)],
        session_service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, str]:
    """Revoke a specific session by ID, enforcing user ownership."""
    success = session_service.revoke_session(
        session_id=session_id,
        user_id=current_user.id
    )

    if not success:
        # Return 404 for both nonexistent and other-user sessions to prevent IDOR/enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found or unauthorized"
        )

    return {"message": "Session revoked successfully"}


@router.post("/sessions/revoke-all")
async def revoke_all_sessions(
        request: Request,
        current_user: Annotated[UserModel, Depends(get_current_user)],
        session_service: Annotated[SessionService, Depends(get_session_service)],
) -> dict[str, str | int]:
    """Revoke all sessions except the currently active one."""
    raw_token = request.cookies.get("session_id")
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    # Resolve session using the raw token cookie
    current_session = session_service.validate_session(raw_token)
    if not current_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )

    # Revoke all other sessions belonging to this user, keeping the current one active
    revoked_count = session_service.revoke_all_sessions(
        user_id=current_user.id,
        keep_session_id=current_session.id
    )

    return {
        "revoked_count": revoked_count,
        "message": "All other sessions revoked"
    }
