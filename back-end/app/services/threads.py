import asyncio
import logging

from fastapi import HTTPException
from openai_codex import AsyncThread, MethodNotFoundError
from pydantic import BaseModel

from app.crud import delete_thread as delete_thread_record
from app.crud import list_threads
from app.services.errors import upstream
from app.services.runtime import Runtime

logger = logging.getLogger(__name__)


class EmptyRpcResponse(BaseModel):
    pass


async def delete_thread(thread_id: str, rt: Runtime):
    async with rt.locks[thread_id]:
        await rt.known_thread(thread_id)
        if thread_id in rt.active:
            raise HTTPException(409, "Dừng turn đang chạy trước khi xóa thread.")
        try:
            snapshot = await AsyncThread(rt.codex, thread_id).read()
            if snapshot.thread.status.model_dump(mode="json").get("type") == "active":
                raise HTTPException(409, "Dừng turn đang chạy trước khi xóa thread.")
            # SDK 0.159.3 has no high-level delete method; isolate the RPC adapter here.
            await rt.codex._client.request(
                "thread/delete",
                {"threadId": thread_id},
                response_model=EmptyRpcResponse,
            )
        except HTTPException:
            raise
        except MethodNotFoundError as exc:
            raise HTTPException(
                501, "Codex runtime chưa hỗ trợ xóa thread; cần nâng cấp."
            ) from exc
        except Exception as exc:
            logger.exception("Cannot delete Codex thread %s", thread_id)
            raise upstream(exc) from exc
        try:
            await asyncio.to_thread(delete_thread_record, thread_id)
        except Exception as exc:
            logger.exception("Codex thread deleted but registry cleanup failed")
            raise HTTPException(
                500, "Thread đã xóa trên Codex nhưng chưa cập nhật được danh sách."
            ) from exc
        rt.threads.pop(thread_id, None)
        for key in list(rt.turns):
            if key[0] == thread_id:
                rt.turns.pop(key)
        async with rt.bus.condition:
            retained = [
                entry for entry in rt.bus.buffer if entry[1]["threadId"] != thread_id
            ]
            rt.bus.buffer.clear()
            rt.bus.buffer.extend(retained)
        await rt.bus.publish(thread_id, None, "thread/deleted", {"threadId": thread_id})


async def list_thread_page(limit: int, cursor: str | None):
    try:
        records = await asyncio.to_thread(list_threads)
    except Exception as exc:
        logger.exception("Cannot list thread store")
        raise HTTPException(500, "Không thể đọc danh sách thread.") from exc
    offset = 0
    if cursor is not None:
        index = next(
            (i for i, r in enumerate(records) if r["thread_id"] == cursor), None
        )
        if index is None:
            raise HTTPException(422, "Cursor không hợp lệ.")
        offset = index + 1
    page = records[offset : offset + limit]
    return {
        "data": [
            {"id": r["thread_id"], "name": r["name"], "createdAt": r["created_at"]}
            for r in page
        ],
        "nextCursor": page[-1]["thread_id"]
        if offset + len(page) < len(records)
        else None,
    }


async def read_thread(thread_id: str, rt: Runtime, includeTurns: bool = False):
    await rt.known_thread(thread_id)
    try:
        result = await AsyncThread(rt.codex, thread_id).read(include_turns=includeTurns)
        return result.model_dump(mode="json", by_alias=True)
    except Exception as exc:
        logger.exception("Cannot read thread")
        raise upstream(exc) from exc


async def resume_thread(thread_id: str, rt: Runtime):
    async with rt.locks[thread_id]:
        try:
            await rt.resume(thread_id)
            return {"threadId": thread_id, "status": "loaded"}
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Cannot resume thread")
            raise upstream(exc) from exc
