"""API v1 package — aggregates the versioned routers."""

from fastapi import APIRouter

from app.api.v1 import auth, conversations, rag, tools, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(conversations.router)
api_router.include_router(rag.router)
api_router.include_router(tools.router)

__all__ = ["api_router"]

