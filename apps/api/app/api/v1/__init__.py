"""API v1 package — aggregates the versioned routers."""

from fastapi import APIRouter

from app.api.v1 import auth, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)

__all__ = ["api_router"]

