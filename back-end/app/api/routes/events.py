from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import RuntimeDep

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def events(
    request: Request,
    rt: RuntimeDep,
    threadId: str | None = None,
    turnId: str | None = None,
    after: str | None = None,
):
    if turnId and not threadId:
        raise HTTPException(422, "turnId cần đi cùng threadId.")
    if threadId:
        await rt.known_thread(threadId)
    cursor = rt.bus.cursor(request.headers.get("last-event-id") or after)
    return StreamingResponse(
        rt.bus.events(cursor, threadId, turnId),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
