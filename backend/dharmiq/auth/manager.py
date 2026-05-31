from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase

from dharmiq.api.dependencies import get_user_db
from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.logging import get_logger
from dharmiq.core.security import auth_backend
from dharmiq.db.models.users import User

logger = get_logger(__name__)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = ""
    verification_token_secret = ""

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        logger.info("user_registered", user_id=str(user.id), email=user.email)


def _configure_user_manager_secrets(settings: Settings) -> None:
    secret = settings.auth.jwt_secret.get_secret_value()
    UserManager.reset_password_token_secret = secret
    UserManager.verification_token_secret = secret


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[UserManager, None]:
    _configure_user_manager_secrets(settings)
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
