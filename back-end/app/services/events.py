import asyncio
import json
import uuid
from collections import deque

from fastapi import HTTPException


class EventBus:
    def __init__(self, capacity=2000):
        self.epoch = uuid.uuid4().hex
        self.sequence = 0
        self.buffer = deque(maxlen=capacity)
        self.condition = asyncio.Condition()
        self.closed = False

    async def publish(self, thread_id, turn_id, event_type, data):
        async with self.condition:
            self.sequence += 1
            event = {
                "id": f"{self.epoch}:{self.sequence}",
                "threadId": thread_id,
                "turnId": turn_id,
                "type": event_type,
                "data": data,
            }
            self.buffer.append((self.sequence, event))
            self.condition.notify_all()

    def cursor(self, value):
        if value is None:
            return self.sequence
        try:
            epoch, number = value.split(":")
            number = int(number)
        except (ValueError, AttributeError):
            raise HTTPException(422, "Last-Event-ID không hợp lệ.")
        if epoch != self.epoch:
            raise HTTPException(409, "Server đã restart; tải lại lịch sử thread.")
        self.validate(number)
        return number

    def validate(self, number):
        oldest = self.buffer[0][0] if self.buffer else self.sequence + 1
        if number < oldest - 1 or number > self.sequence:
            raise HTTPException(409, "Event cursor hết hạn; tải lại lịch sử thread.")

    async def events(self, cursor, thread_id=None, turn_id=None):
        while not self.closed:
            reset = False
            async with self.condition:
                try:
                    self.validate(cursor)
                except HTTPException:
                    reset = True
                batch = [(seq, event) for seq, event in self.buffer if seq > cursor]
                if not batch and not reset:
                    try:
                        await asyncio.wait_for(self.condition.wait(), timeout=15)
                    except TimeoutError:
                        pass
                    # Recheck retention on the next iteration, before delivering.
                    if self.sequence > cursor:
                        continue
            if reset:
                yield 'event: reset\ndata: {"message":"Tải lại lịch sử thread."}\n\n'
                return
            if not batch:
                yield ": heartbeat\n\n"
            for seq, event in batch:
                cursor = seq
                if thread_id is not None and event["threadId"] != thread_id:
                    continue
                if turn_id is not None and event["turnId"] != turn_id:
                    continue
                yield (
                    f"id: {event['id']}\nevent: codex\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )
