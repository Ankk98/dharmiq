from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings
from dharmiq.db.models.users import User


def user_uploads_dir(settings: Settings, user_id: uuid.UUID) -> Path:
    return settings.uploads.resolve_uploads_dir(settings.repo_root) / str(user_id)


async def delete_user_account(
    user: User,
    *,
    db: AsyncSession,
    user_db: SQLAlchemyUserDatabase,
    settings: Settings,
) -> None:
    uploads_dir = user_uploads_dir(settings, user.id)
    if uploads_dir.exists():
        shutil.rmtree(uploads_dir, ignore_errors=True)

    await user_db.delete(user)
    await db.commit()
