import asyncio
import json
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from openai_codex.generated.v2_all import ThreadStatus, TurnStatus
from openai_codex.models import Notification, UnknownNotification

from app import crud as thread_store
from app import main
from app.services.events import EventBus
from app.services.runtime import Runtime


async def call(method, path, body=None, query="", headers=()):
    output = []

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(body).encode(),
            "more_body": False,
        }

    async def send(event):
        output.append(event)

    await main.app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "headers": [(b"content-type", b"application/json"), *headers],
            "client": ("127.0.0.1", 1),
            "server": ("localhost", 8000),
        },
        receive,
        send,
    )
    payload = b"".join(e.get("body", b"") for e in output[1:])
    return output[0]["status"], json.loads(payload) if payload else None


class V1Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.store_patch = patch.object(
            thread_store, "STORE_PATH", Path(self.directory.name) / "threads.json"
        )
        self.store_patch.start()
        thread_store.save_thread("thread", "Initial prompt")
        self.queue = asyncio.Queue()

        async def stream():
            while True:
                event = await self.queue.get()
                yield event
                if event.method == "turn/completed":
                    return

        self.handle = SimpleNamespace(
            id="turn", stream=stream, steer=AsyncMock(), interrupt=AsyncMock()
        )
        self.snapshot = SimpleNamespace(
            thread=SimpleNamespace(
                status=ThreadStatus.model_validate({"type": "idle"}), turns=[]
            )
        )
        self.thread = SimpleNamespace(
            id="thread",
            turn=AsyncMock(return_value=self.handle),
            read=AsyncMock(return_value=self.snapshot),
        )
        self.codex = SimpleNamespace(thread_resume=AsyncMock(return_value=self.thread))
        self.rt = Runtime(self.codex)
        main.app.state.runtime = self.rt
        main.app.state.codex = self.codex

    async def asyncTearDown(self):
        await self.rt.close()
        del main.app.state.runtime
        del main.app.state.codex
        self.store_patch.stop()
        self.directory.cleanup()

    async def start(self):
        return await call("POST", "/v1/threads/thread/turns", {"prompt": "Hello"})

    async def test_delete_thread_removes_registry_and_runtime(self):
        thread_store.save_thread("other", "Keep this thread")
        self.codex._client = SimpleNamespace(request=AsyncMock())
        self.rt.threads["thread"] = self.thread
        with patch("app.services.threads.AsyncThread", return_value=self.thread):
            status, body = await call("DELETE", "/v1/threads/thread")
        self.assertEqual(status, 204)
        self.assertIsNone(body)
        self.codex._client.request.assert_awaited_once()
        self.assertEqual(
            self.codex._client.request.call_args.args,
            ("thread/delete", {"threadId": "thread"}),
        )
        self.assertEqual(
            [r["thread_id"] for r in thread_store.list_threads()], ["other"]
        )
        self.assertNotIn("thread", self.rt.threads)
        self.assertEqual((await call("GET", "/v1/threads/thread"))[0], 404)

    async def test_delete_rejects_active_and_preserves_on_upstream_failure(self):
        self.rt.active["thread"] = object()
        self.assertEqual((await call("DELETE", "/v1/threads/thread"))[0], 409)
        self.rt.active.clear()
        self.codex._client = SimpleNamespace(
            request=AsyncMock(side_effect=RuntimeError("Failure"))
        )
        with patch("app.services.threads.AsyncThread", return_value=self.thread):
            self.assertEqual((await call("DELETE", "/v1/threads/thread"))[0], 502)
        self.assertEqual(len(thread_store.list_threads()), 1)
        from openai_codex import MethodNotFoundError

        self.codex._client.request.side_effect = MethodNotFoundError(
            -32601, "Unsupported"
        )
        with patch("app.services.threads.AsyncThread", return_value=self.thread):
            self.assertEqual((await call("DELETE", "/v1/threads/thread"))[0], 501)
        self.assertEqual(len(thread_store.list_threads()), 1)
        self.assertEqual((await call("DELETE", "/v1/threads/missing"))[0], 404)

    async def test_removed_legacy_routes(self):
        for path in ("/chat", "/chat/stream"):
            status, _ = await call("POST", path, {"prompt": "Hello"})
            self.assertEqual(status, 404)
        for path in ("/threads", "/threads/thread"):
            status, _ = await call("GET", path)
            self.assertEqual(status, 404)

    async def test_create_and_list_pagination(self):
        async def prepare(body, request):
            thread_store.save_thread("new", body.prompt)
            return SimpleNamespace(id="new"), body.prompt

        with patch("app.api.routes.threads.prepare_thread", side_effect=prepare):
            status, body = await call("POST", "/v1/threads", {"prompt": "New question"})
        self.assertEqual(status, 201)
        self.assertEqual(body["name"], "New question")
        self.assertIn("new", self.rt.threads)
        status, page = await call("GET", "/v1/threads", query="limit=1")
        self.assertEqual(page["data"][0]["id"], "new")
        _, second = await call(
            "GET", "/v1/threads", query=f"limit=1&cursor={page['nextCursor']}"
        )
        self.assertEqual(second["data"][0]["id"], "thread")
        self.assertIsNone(second["nextCursor"])

    async def test_concurrent_start_auto_resume_and_conflict(self):
        results = await asyncio.gather(self.start(), self.start())
        self.assertEqual(sorted(r[0] for r in results), [202, 409])
        self.codex.thread_resume.assert_awaited_once_with("thread")
        self.thread.turn.assert_awaited_once_with("Hello")
        self.assertIn(
            "eventCursor", next(body for code, body in results if code == 202)
        )

    async def test_steer_interrupt_idempotence_and_completion(self):
        await self.start()
        path = "/v1/threads/thread/turns/turn"
        self.assertEqual(
            (await call("POST", path + "/steer", {"prompt": "Use EUR"}))[0], 200
        )
        self.handle.steer.assert_awaited_once_with("Use EUR")
        for _ in range(2):
            self.assertEqual((await call("POST", path + "/interrupt"))[0], 200)
        self.handle.interrupt.assert_awaited_once()
        self.assertEqual(
            (await call("POST", path + "/steer", {"prompt": "Again"}))[0], 409
        )
        await self.queue.put(
            Notification(
                "turn/completed",
                UnknownNotification({"turn": {"status": "interrupted"}}),
            )
        )
        await self.rt.turns[("thread", "turn")].task
        self.assertNotIn("thread", self.rt.active)
        _, response = await call("POST", path + "/interrupt")
        self.assertEqual(response["status"], "interrupted")

    async def test_missing_validation_and_resume(self):
        self.assertEqual((await call("POST", "/v1/threads/missing/resume"))[0], 404)
        self.assertEqual(
            (await call("POST", "/v1/threads/thread/turns", {"prompt": " "}))[0], 422
        )
        with patch("app.services.runtime.AsyncThread", return_value=self.thread):
            self.assertEqual(
                (await call("POST", "/v1/threads/thread/turns/missing/interrupt"))[0],
                404,
            )
        self.assertEqual((await call("POST", "/v1/threads/thread/resume"))[0], 200)
        self.assertEqual((await call("POST", "/v1/threads/thread/resume"))[0], 200)
        self.codex.thread_resume.assert_awaited_once()

    async def test_history_flag_and_persisted_turn_after_restart(self):
        snapshot = SimpleNamespace(
            model_dump=lambda **kwargs: {"thread": {"id": "thread", "turns": []}}
        )
        reader = SimpleNamespace(read=AsyncMock(return_value=snapshot))
        with (
            patch("app.services.threads.AsyncThread", return_value=reader),
            patch("app.services.runtime.AsyncThread", return_value=reader),
        ):
            self.assertEqual(
                (await call("GET", "/v1/threads/thread", query="includeTurns=true"))[0],
                200,
            )
            reader.read.assert_awaited_once_with(include_turns=True)
            reader.read.return_value = SimpleNamespace(
                thread=SimpleNamespace(
                    turns=[SimpleNamespace(id="old", status=TurnStatus.completed)]
                )
            )
            self.assertEqual(
                (await call("POST", "/v1/threads/thread/turns/old/interrupt"))[0], 200
            )
            self.assertEqual(
                (
                    await call(
                        "POST", "/v1/threads/thread/turns/old/steer", {"prompt": "Hi"}
                    )
                )[0],
                409,
            )

    async def test_sse_filter_replay_disconnect_and_stale_cursor(self):
        _, result = await self.start()
        cursor = self.rt.bus.cursor(result["eventCursor"])
        stream = self.rt.bus.events(cursor, "thread", "turn")
        chunk = await anext(stream)
        self.assertIn("backend/turnStarted", chunk)
        await stream.aclose()
        self.handle.interrupt.assert_not_awaited()
        await self.queue.put(
            Notification(
                "item/agentMessage/delta",
                UnknownNotification({"delta": "Hello\nworld"}),
            )
        )
        await self.queue.put(
            Notification(
                "turn/completed", UnknownNotification({"turn": {"status": "completed"}})
            )
        )
        await self.rt.turns[("thread", "turn")].task
        self.assertEqual(self.rt.turns[("thread", "turn")].status, "completed")
        bus = EventBus(capacity=2)
        await bus.publish("other", "other-turn", "delta", {})
        await bus.publish("thread", "turn", "delta", {"text": "Hello"})
        replay = bus.events(0, "thread", "turn")
        self.assertIn('"text": "Hello"', await anext(replay))
        await replay.aclose()
        await bus.publish("thread", "turn", "done", {})
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as expired:
            bus.cursor(f"{bus.epoch}:0")
        self.assertEqual(expired.exception.status_code, 409)
        with self.assertRaises(HTTPException):
            bus.cursor("old-epoch:1")

    async def test_external_active_turn_and_upstream_error(self):
        self.snapshot.thread.status = ThreadStatus.model_validate(
            {"type": "active", "activeFlags": []}
        )
        self.assertEqual((await self.start())[0], 409)
        self.thread.turn.assert_not_awaited()
        self.snapshot.thread.status = ThreadStatus.model_validate({"type": "idle"})
        self.thread.turn.side_effect = RuntimeError("Unavailable")
        self.assertEqual((await self.start())[0], 502)

    async def test_stream_failure_releases_thread_and_emits_error(self):
        async def failed_stream():
            raise RuntimeError("Transport disconnected")
            yield

        self.handle.stream = failed_stream
        await self.start()
        state = self.rt.turns[("thread", "turn")]
        await state.task
        self.assertEqual(state.status, "failed")
        self.assertNotIn("thread", self.rt.active)
        self.handle.interrupt.assert_awaited_once()
        self.assertEqual(self.rt.bus.buffer[-1][1]["type"], "backend/error")


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
