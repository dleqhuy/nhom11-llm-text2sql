from typing import Annotated

from fastapi import Depends, Request
from openai_codex import AsyncCodex

from app.services.runtime import Runtime


def get_codex(request: Request) -> AsyncCodex:
    return request.app.state.codex


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


CodexDep = Annotated[AsyncCodex, Depends(get_codex)]
RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
