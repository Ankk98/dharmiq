from __future__ import annotations

from dharmiq.auth.manager import fastapi_users
from dharmiq.core.security import auth_backend
from dharmiq.schemas.users import UserCreate, UserRead, UserUpdate

router = fastapi_users.get_auth_router(auth_backend)
register_router = fastapi_users.get_register_router(UserRead, UserCreate)
users_router = fastapi_users.get_users_router(UserRead, UserUpdate)
