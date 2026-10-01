import asyncio
import logging

from fastapi import HTTPException
from openai_codex import ApprovalMode, AsyncCodex, Sandbox

from app.crud import save_thread
from app.models import CreateThread

logger = logging.getLogger(__name__)


async def prepare_thread(body: CreateThread, codex: AsyncCodex):
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Prompt không được để trống.")
    name = " ".join((body.name if body.name is not None else prompt).split())[:100]
    if not name:
        raise HTTPException(status_code=422, detail="Tên không được để trống.")

    try:
        thread = await codex.thread_start(
            developer_instructions=(
                "For database questions, use the text2sql MCP tools. "
                "Discover schemas and tables with search_objects before writing SQL. "
                "Use execute_sql for read-only queries. Do not invent database results."
            ),
            sandbox=Sandbox.read_only,
            approval_mode=ApprovalMode.auto_review,
            ephemeral=False,
        )
        try:
            await asyncio.to_thread(save_thread, thread.id, name)
        except Exception as exc:
            logger.exception("Cannot save thread %s", thread.id)
            raise HTTPException(
                status_code=500, detail="Không thể lưu thread."
            ) from exc
        await thread.set_name(name)
        return thread, prompt
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Cannot prepare Codex thread")
        raise HTTPException(
            status_code=502, detail="Không thể tạo thread Codex."
        ) from exc
