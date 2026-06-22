from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.api.dependencies import get_session, get_settings_dep, get_user_db
from dharmiq.auth.manager import UserManager, current_active_user, get_user_manager
from dharmiq.config.settings import Settings
from dharmiq.db.models.users import User
from dharmiq.schemas.account import AccountDeleteRequest
from dharmiq.services.account_delete import delete_user_account
from dharmiq.services.account_export import build_account_export, export_filename

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/export")
async def export_account(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    payload = await build_account_export(user, db)
    filename = export_filename(payload.exported_at)
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: AccountDeleteRequest,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_session),
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
    user_manager: UserManager = Depends(get_user_manager),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    if body.email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email does not match",
        )

    credentials = OAuth2PasswordRequestForm(
        username=body.email,
        password=body.password,
        scope="",
    )
    authenticated = await user_manager.authenticate(credentials)
    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if authenticated.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email does not match",
        )

    await delete_user_account(
        current_user,
        db=db,
        user_db=user_db,
        settings=settings,
    )
