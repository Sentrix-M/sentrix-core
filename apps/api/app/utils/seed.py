"""Development seed helpers.

Seeds a default admin user into the in-memory repository so the platform is
usable immediately in local development. This is intentionally a no-op when a
durable (PostgreSQL) repository is enabled.
"""

from __future__ import annotations

from datetime import datetime, timezone

import uuid

from app.config.settings import Settings
from app.core.security import hash_password
from app.models.role import RoleName
from app.models.user import User
from app.repositories.user_repository import UserRepository


async def seed_admin_user(
    user_repository: UserRepository, settings: Settings
) -> User | None:
    """Create the default admin user if it does not already exist.

    Returns the seeded user, or ``None`` if a user with the admin email
    already exists.
    """
    existing = await user_repository.get_by_email(settings.admin_email)
    if existing is not None:
        return existing

    now = datetime.now(timezone.utc)
    admin = User(
        id=str(uuid.uuid4()),
        email=settings.admin_email,
        full_name=settings.admin_full_name,
        password_hash=hash_password(settings.admin_password),
        role=RoleName.ADMIN.value,
        org_id=settings.admin_org_id,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    await user_repository.create(admin)
    return admin

