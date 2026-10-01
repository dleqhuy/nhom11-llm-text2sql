import tomllib
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app import crud
from app.core.config import Settings
from app.main import app


class AppTests(unittest.IsolatedAsyncioTestCase):
    def test_entrypoint_routes_and_store_location(self):
        from main import app as compatibility_app

        self.assertIs(app, compatibility_app)
        paths = app.openapi()["paths"]
        self.assertEqual(len([p for p in paths if p.startswith("/v1/")]), 7)
        self.assertEqual(set(paths["/v1/threads"]), {"get", "post"})
        self.assertIn("/health", paths)
        self.assertFalse(
            any(
                "legacy" in operation.get("tags", [])
                for methods in paths.values()
                for operation in methods.values()
            )
        )
        for removed in ("/threads", "/threads/{thread_id}", "/chat", "/chat/stream"):
            self.assertNotIn(removed, paths)
        self.assertEqual(
            crud.STORE_PATH,
            Path(__file__).resolve().parents[1] / "data" / "threads.json",
        )

    def test_settings_environment(self):
        with patch.dict("os.environ", {"MCP_URL": "http://localhost:7777/mcp"}):
            self.assertEqual(
                Settings(_env_file=None).MCP_URL, "http://localhost:7777/mcp"
            )

    async def test_lifespan_initializes_and_closes_shared_client(self):
        context = AsyncMock()
        with patch("app.core.lifespan.AsyncCodex", return_value=context) as factory:
            async with app.router.lifespan_context(app):
                self.assertIs(app.state.codex, context.__aenter__.return_value)
                self.assertIs(app.state.runtime.codex, app.state.codex)
                config = factory.call_args.kwargs["config"]
                mcp = tomllib.loads("\n".join(config.config_overrides))["mcp_servers"][
                    "text2sql"
                ]
                self.assertTrue(mcp["required"])
                context.__aexit__.assert_not_awaited()
            context.__aexit__.assert_awaited_once()
            self.assertFalse(hasattr(app.state, "runtime"))
            self.assertFalse(hasattr(app.state, "codex"))
