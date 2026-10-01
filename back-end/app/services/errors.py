from fastapi import HTTPException
from openai_codex import ServerBusyError


def upstream(exc):
    return HTTPException(
        status_code=503 if isinstance(exc, ServerBusyError) else 502,
        detail="Không thể xử lý yêu cầu Codex.",
    )
