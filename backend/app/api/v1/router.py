from fastapi import APIRouter

from app.api.v1.routes import chat, health, tools

api_router = APIRouter()
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
