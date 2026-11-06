"""HQ backend.

One job for stage 3: sit between the kiosk browser and Home Assistant.

- Holds the HA long-lived token (the browser never sees it).
- Keeps a live cache of entity states via HA's WebSocket API.
- Serves the static front-end.
- Exposes one WebSocket (/ws) to browsers: pushes the full state on
  connect, pushes every state change as it happens, and accepts
  service calls (light.toggle, climate.set_temperature, ...) to forward.

Everything else (calendar, chores, meals, AI) is added to this app later,
one feature at a time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("hq")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

HA_URL = os.environ.get("HA_URL", "http://homeassistant.local:8123").rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
HA_WS_URL = HA_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"

STATIC_DIR = Path(__file__).parent / "static"


class HomeAssistant:
    """Persistent WebSocket connection to HA with a state cache and fan-out to browsers."""

    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}
        self.connected = False
        self._ws: websockets.ClientConnection | None = None
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._browsers: set[WebSocket] = set()
        self._task: asyncio.Task | None = None

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()

    async def _run_forever(self) -> None:
        backoff = 1
        while True:
            try:
                await self._session()
                backoff = 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("HA connection lost: %s (retry in %ss)", exc, backoff)
            self.connected = False
            await self._broadcast({"type": "ha_connected", "connected": False})
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _session(self) -> None:
        async with websockets.connect(HA_WS_URL, max_size=16 * 1024 * 1024) as ws:
            self._ws = ws
            hello = json.loads(await ws.recv())
            if hello.get("type") != "auth_required":
                raise RuntimeError(f"unexpected hello: {hello}")
            await ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                raise RuntimeError(f"HA auth failed: {auth}")
            log.info("connected to HA %s", auth.get("ha_version"))
            self.connected = True

            # Full state snapshot, then live updates.
            states = await self._request({"type": "get_states"})
            self.states = {s["entity_id"]: s for s in states}
            await self._request({"type": "subscribe_events", "event_type": "state_changed"})
            await self._broadcast({"type": "ha_connected", "connected": True})
            await self._broadcast({"type": "states", "states": list(self.states.values())})

            async for raw in ws:
                msg = json.loads(raw)
                mid = msg.get("id")
                if msg.get("type") == "result" and mid in self._pending:
                    fut = self._pending.pop(mid)
                    if msg.get("success"):
                        fut.set_result(msg.get("result"))
                    else:
                        fut.set_exception(RuntimeError(str(msg.get("error"))))
                elif msg.get("type") == "event":
                    data = msg["event"].get("data", {})
                    new = data.get("new_state")
                    if new:
                        self.states[new["entity_id"]] = new
                        await self._broadcast({"type": "state", "state": new})

    # ---- HA requests -----------------------------------------------------

    async def _request(self, payload: dict[str, Any]) -> Any:
        if not self._ws:
            raise RuntimeError("not connected to HA")
        self._msg_id += 1
        payload["id"] = self._msg_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[self._msg_id] = fut
        await self._ws.send(json.dumps(payload))
        return await asyncio.wait_for(fut, timeout=10)

    async def call_service(self, domain: str, service: str, data: dict[str, Any] | None = None) -> None:
        await self._request({
            "type": "call_service",
            "domain": domain,
            "service": service,
            "service_data": data or {},
        })

    # ---- browsers --------------------------------------------------------

    async def add_browser(self, ws: WebSocket) -> None:
        self._browsers.add(ws)
        await ws.send_json({"type": "ha_connected", "connected": self.connected})
        await ws.send_json({"type": "states", "states": list(self.states.values())})

    def remove_browser(self, ws: WebSocket) -> None:
        self._browsers.discard(ws)

    async def _broadcast(self, msg: dict[str, Any]) -> None:
        dead = []
        for b in list(self._browsers):
            try:
                await b.send_json(msg)
            except Exception:  # noqa: BLE001
                dead.append(b)
        for b in dead:
            self._browsers.discard(b)


ha = HomeAssistant()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not HA_TOKEN:
        log.error("HA_TOKEN is not set - the app will serve the page but cannot talk to HA")
    ha.start()
    yield
    await ha.stop()


app = FastAPI(title="HQ", lifespan=lifespan)


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "ha_connected": ha.connected, "entities": len(ha.states)})


@app.websocket("/ws")
async def browser_ws(ws: WebSocket) -> None:
    await ws.accept()
    await ha.add_browser(ws)
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "call_service":
                try:
                    await ha.call_service(msg["domain"], msg["service"], msg.get("data"))
                except Exception as exc:  # noqa: BLE001
                    await ws.send_json({"type": "error", "message": str(exc), "ref": msg.get("ref")})
            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        ha.remove_browser(ws)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
