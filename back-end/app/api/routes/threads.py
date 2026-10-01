from fastapi import APIRouter, Query, Response

from app.api.deps import CodexDep, RuntimeDep
from app.models import CreateThread
from app.services import threads as service
from app.services.thread_creation import prepare_thread

router = APIRouter(prefix="/threads", tags=["threads"])


@router.post("", status_code=201)
async def create_thread(body: CreateThread, codex: CodexDep, rt: RuntimeDep):
    thread, _ = await prepare_thread(body, codex)
    rt.threads[thread.id] = thread
    record = await rt.known_thread(thread.id)
    return {"id": thread.id, "name": record["name"], "createdAt": record["created_at"]}


@router.get("")
async def list_threads(limit: int = Query(20, ge=1, le=100), cursor: str | None = None):
    return await service.list_thread_page(limit, cursor)


@router.get("/{thread_id}")
async def read_thread(thread_id: str, rt: RuntimeDep, includeTurns: bool = False):
    return await service.read_thread(thread_id, rt, includeTurns)


@router.post("/{thread_id}/resume")
async def resume_thread(thread_id: str, rt: RuntimeDep):
    return await service.resume_thread(thread_id, rt)


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(thread_id: str, rt: RuntimeDep):
    await service.delete_thread(thread_id, rt)
    return Response(status_code=204)
