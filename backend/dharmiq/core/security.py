from __future__ import annotations

from fastapi_users import models
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy

from dharmiq.config.settings import get_settings

bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    settings = get_settings()
    return JWTStrategy(
        secret=settings.auth.jwt_secret.get_secret_value(),
        lifetime_seconds=settings.auth.jwt_lifetime_seconds,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)
