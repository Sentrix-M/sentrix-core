"""User entity.

A plain Pydantic model representing a registered Sentrix user. This entity is
persistence-agnostic (no ORM dependency) so it can be produced by the
in-memory repository or a future PostgreSQL implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.role import get_role_permissions


class User(BaseModel):
    """A registered platform user."""

    model_config = ConfigDict(
        # Keep the model frozen in application code; create copies for changes.
        frozen=True,
        # Do not accidentally serialise the password hash.
        json_encoders={},
    )

    id: str = Field(description="Stable UUID for the user.")
    email: EmailStr = Field(description="Verified email address.")
    full_name: str = Field(min_length=1, description="Display name.")
    password_hash: str = Field(exclude=True, description="Argon2id password hash.")
    role: str = Field(description="RBAC role name from the enterprise catalog.")
    org_id: str = Field(description="Tenant/organization the user belongs to.")
    is_active: bool = True
    mfa_enabled: bool = False
    created_at: datetime
    updated_at: datetime

    @property
    def permissions(self) -> list[str]:
        """Compute the permission list from the role catalog."""
        return get_role_permissions(self.role)

    def to_claims_payload(self) -> dict[str, Any]:
        """Return the claim-relevant subset for JWT encoding."""
        return {
            "id": self.id,
            "email": str(self.email),
            "full_name": self.full_name,
            "role": self.role,
            "org_id": self.org_id,
            "is_active": self.is_active,
            "mfa_enabled": self.mfa_enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def now_utc(cls) -> datetime:
        """Return the current UTC timestamp with timezone info."""
        return datetime.now(timezone.utc)

