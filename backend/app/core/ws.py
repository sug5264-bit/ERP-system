"""In-process WebSocket broadcast manager.

PoC-grade: holds connections in memory. For multi-process production,
replace with Redis pub/sub or a dedicated message broker.
"""
import asyncio
import json
from typing import Any

from fastapi import WebSocket


class WSManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(ws)

    async def disconnect(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.get(user_id, set()).discard(ws)
            if not self._connections.get(user_id):
                self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))
        text = json.dumps(payload, default=str)
        for ws in sockets:
            try:
                await ws.send_text(text)
            except Exception:
                await self.disconnect(user_id, ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            all_sockets = [(uid, s) for uid, conns in self._connections.items() for s in conns]
        text = json.dumps(payload, default=str)
        for uid, ws in all_sockets:
            try:
                await ws.send_text(text)
            except Exception:
                await self.disconnect(uid, ws)

    def emit(self, user_id: int | None, payload: dict[str, Any]) -> None:
        """Schedule a send from sync code onto the main event loop."""
        coro = self.send_to_user(user_id, payload) if user_id else self.broadcast(payload)
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return  # no loop yet (tests/seed) — drop the message
        try:
            running = asyncio.get_running_loop()
            if running is loop:
                loop.create_task(coro)
                return
        except RuntimeError:
            pass
        asyncio.run_coroutine_threadsafe(coro, loop)


manager = WSManager()
