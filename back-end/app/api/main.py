from fastapi import APIRouter

from app.api.routes import events, threads, turns

api_router = APIRouter()
api_router.include_router(threads.router)
api_router.include_router(turns.router)
api_router.include_router(events.router)
