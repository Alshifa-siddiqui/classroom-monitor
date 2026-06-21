import asyncio
import json
import logging
from typing import List

from fastapi import WebSocket, WebSocketDisconnect

from ..security import ws_authenticate, ws_limiter

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> bool:
        ip = websocket.client.host if websocket.client else "unknown"
        if ws_authenticate(websocket) is None:
            await websocket.close(code=4401, reason="Authentication failed")
            return False
        if not ws_limiter.try_acquire(ip):
            await websocket.close(code=4429, reason="Too many connections")
            return False
        await websocket.accept()
        async with self._lock:
            self.connections.append(websocket)
        websocket.state.client_ip = ip
        return True

    async def disconnect(self, websocket: WebSocket) -> None:
        ip = getattr(websocket.state, "client_ip", "unknown")
        ws_limiter.release(ip)
        async with self._lock:
            if websocket in self.connections:
                self.connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        if not self.connections:
            return
        payload = json.dumps(message)
        dead: List[WebSocket] = []
        async with self._lock:
            targets = list(self.connections)
        for ws in targets:
            try:
                # a frozen/slow client must not stall the pipeline for everyone
                await asyncio.wait_for(ws.send_text(payload), timeout=2.0)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
            try:
                await ws.close(code=1011, reason="send timeout")
            except Exception:
                pass


    async def shutdown(self) -> None:
        """Close all client connections during graceful shutdown."""
        async with self._lock:
            targets = list(self.connections)
            self.connections.clear()
        for ws in targets:
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                pass


manager = ConnectionManager()


async def live_endpoint(websocket: WebSocket) -> None:
    if not await manager.connect(websocket):
        return
    try:
        while True:
            # client messages are ignored; receive() keeps the socket alive
            # and lets us observe disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
