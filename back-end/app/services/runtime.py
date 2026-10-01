import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException
from openai_codex import AsyncThread
from openai_codex.models import UnknownNotification

from app.crud import list_threads
from app.services.errors import upstream
from app.services.events import EventBus

logger = logging.getLogger(__name__)


@dataclass
class RunningTurn:
    thread_id: str
    handle: object
    status: str = "inProgress"
    task: asyncio.Task | None = None
    interrupt_requested: bool = False


class Runtime:
    def __init__(self, codex):
        self.codex = codex
        self.bus = EventBus()
        self.threads = {}
        self.locks = defaultdict(asyncio.Lock)
        self.turns = {}
        self.active = {}

    async def known_thread(self, thread_id):
        records = await asyncio.to_thread(list_threads)
        record = next((r for r in records if r["thread_id"] == thread_id), None)
        if record is None:
            raise HTTPException(404, "Không tìm thấy thread.")
        return record

    async def resume(self, thread_id):
        await self.known_thread(thread_id)
        if thread_id not in self.threads:
            self.threads[thread_id] = await self.codex.thread_resume(thread_id)
        return self.threads[thread_id]

    async def consume(self, state):
        stream = state.handle.stream()
        try:
            async for event in stream:
                payload = (
                    event.payload.params
                    if isinstance(event.payload, UnknownNotification)
                    else event.payload.model_dump(mode="json", by_alias=True)
                )
                if event.method == "turn/completed":
                    state.status = payload["turn"]["status"]
                await self.bus.publish(
                    state.thread_id, state.handle.id, event.method, payload
                )
            if state.status == "inProgress":
                raise RuntimeError("Codex stream ended without turn/completed")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Turn stream failed")
            state.status = "failed"
            await self.bus.publish(
                state.thread_id,
                state.handle.id,
                "backend/error",
                {
                    "message": "Luồng Codex bị lỗi; tải lại lịch sử thread.",
                },
            )
            try:
                await state.handle.interrupt()
            except Exception:
                logger.exception("Cannot stop failed stream")
        finally:
            await stream.aclose()
            self.active.pop(state.thread_id, None)

    async def close(self):
        running = [s for s in self.turns.values() if s.task and not s.task.done()]

        async def stop(state):
            try:
                await asyncio.wait_for(state.handle.interrupt(), timeout=5)
            except Exception:
                logger.exception("Cannot interrupt turn during shutdown")

        await asyncio.gather(*(stop(s) for s in running))
        for state in running:
            state.task.cancel()
        await asyncio.gather(*(s.task for s in running), return_exceptions=True)
        async with self.bus.condition:
            self.bus.closed = True
            self.bus.condition.notify_all()


async def get_turn(rt, thread_id, turn_id):
    await rt.known_thread(thread_id)
    state = rt.turns.get((thread_id, turn_id))
    if state is None:
        # A finished persisted turn can still be interrupted idempotently after restart.
        try:
            snapshot = await AsyncThread(rt.codex, thread_id).read(include_turns=True)
        except Exception as exc:
            raise upstream(exc) from exc
        turn = next((t for t in snapshot.thread.turns if t.id == turn_id), None)
        if turn is None:
            raise HTTPException(404, "Không tìm thấy turn.")
        if turn.status.value == "inProgress":
            raise HTTPException(409, "Turn không được quản lý bởi server hiện tại.")
        return RunningTurn(thread_id, None, status=turn.status.value)
    return state
