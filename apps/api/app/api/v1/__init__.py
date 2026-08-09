"""API v1 package — aggregates the versioned routers."""

from fastapi import APIRouter

from app.api.v1 import auth, conversations, memory, rag, tools, tts, users, voice

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(conversations.router)
api_router.include_router(rag.router)
api_router.include_router(tools.router)
api_router.include_router(memory.router)
api_router.include_router(voice.router)
api_router.include_router(tts.router)

__all__ = ["api_router"]

