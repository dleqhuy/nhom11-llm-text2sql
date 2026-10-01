from fastapi import APIRouter

from app.api.deps import RuntimeDep
from app.models import Prompt
from app.services import turns as service

router = APIRouter(prefix="/threads/{thread_id}/turns", tags=["turns"])


@router.post("", status_code=202)
async def start_turn(thread_id: str, body: Prompt, rt: RuntimeDep):
    return await service.start_turn(thread_id, body, rt)


@router.post("/{turn_id}/steer")
async def steer_turn(thread_id: str, turn_id: str, body: Prompt, rt: RuntimeDep):
    return await service.steer_turn(thread_id, turn_id, body, rt)


@router.post("/{turn_id}/interrupt")
async def interrupt_turn(thread_id: str, turn_id: str, rt: RuntimeDep):
    return await service.interrupt_turn(thread_id, turn_id, rt)
