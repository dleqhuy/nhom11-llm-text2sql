import asyncio
import logging

from fastapi import HTTPException

from app.models import Prompt
from app.services.errors import upstream
from app.services.runtime import RunningTurn, Runtime, get_turn

logger = logging.getLogger(__name__)


async def start_turn(thread_id: str, body: Prompt, rt: Runtime):
    async with rt.locks[thread_id]:
        await rt.known_thread(thread_id)
        if thread_id in rt.active:
            raise HTTPException(409, "Thread đang có turn chạy.")
        try:
            thread = await rt.resume(thread_id)
            # Check persisted runtime state too, including turns from another client.
            snapshot = await thread.read()
            status = snapshot.thread.status
            status = status.model_dump(mode="json", by_alias=True)
            if status.get("type") == "active":
                raise HTTPException(409, "Thread đang có turn chạy.")
            handle = await thread.turn(body.prompt)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Cannot start turn")
            raise upstream(exc) from exc
        state = RunningTurn(thread_id, handle)
        # Retain recent finished handles; older turns remain readable in Codex.
        if len(rt.turns) >= 1000:
            for key, old in list(rt.turns.items()):
                if old.task and old.task.done():
                    del rt.turns[key]
                    if len(rt.turns) < 1000:
                        break
        rt.turns[(thread_id, handle.id)] = state
        rt.active[thread_id] = state
        event_cursor = f"{rt.bus.epoch}:{rt.bus.sequence}"
        await rt.bus.publish(
            thread_id, handle.id, "backend/turnStarted", {"status": "inProgress"}
        )
        state.task = asyncio.create_task(rt.consume(state))
        return {
            "threadId": thread_id,
            "turnId": handle.id,
            "status": "inProgress",
            "eventCursor": event_cursor,
        }


async def steer_turn(thread_id: str, turn_id: str, body: Prompt, rt: Runtime):
    async with rt.locks[thread_id]:
        state = await get_turn(rt, thread_id, turn_id)
        if state.status != "inProgress" or state.interrupt_requested:
            raise HTTPException(409, "Turn không còn nhận steer.")
        try:
            await state.handle.steer(body.prompt)
        except Exception as exc:
            raise upstream(exc) from exc
        return {"threadId": thread_id, "turnId": turn_id, "status": "accepted"}


async def interrupt_turn(thread_id: str, turn_id: str, rt: Runtime):
    async with rt.locks[thread_id]:
        state = await get_turn(rt, thread_id, turn_id)
        if state.status == "inProgress" and not state.interrupt_requested:
            try:
                await state.handle.interrupt()
            except Exception as exc:
                raise upstream(exc) from exc
            state.interrupt_requested = True
        return {
            "threadId": thread_id,
            "turnId": turn_id,
            "status": "interruptRequested"
            if state.status == "inProgress"
            else state.status,
        }
