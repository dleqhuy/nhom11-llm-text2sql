import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from openai_codex import AsyncCodex, CodexConfig

from app.core.config import settings
from app.services.runtime import Runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_url = settings.MCP_URL
    config = CodexConfig(
        config_overrides=(
            f"mcp_servers.text2sql.url={json.dumps(mcp_url)}",
            "mcp_servers.text2sql.enabled=true",
            "mcp_servers.text2sql.required=true",
            'mcp_servers.text2sql.enabled_tools=["search_objects", "execute_sql"]',
        )
    )
    async with AsyncCodex(config=config) as codex:
        app.state.codex = codex
        app.state.runtime = Runtime(codex)
        try:
            yield
        finally:
            await app.state.runtime.close()
            del app.state.runtime
            del app.state.codex
