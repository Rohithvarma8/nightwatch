"""Local web app: smart-display page + JSON API. Run with `make sim` (http://localhost:8765)."""

import base64
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from nightwatch_sim.engine import Engine
from nightwatch_sim.settings import Settings
from nightwatch_sim.tts import Speaker

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("nightwatch_sim")
state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    state["settings"] = settings
    state["engine"] = Engine(settings)
    state["speaker"] = Speaker(settings.region, settings.voice_id)
    yield
    state["engine"].close()


app = FastAPI(title="Night Watch simulated Alexa+ client (unofficial)", lifespan=lifespan)


class TurnIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=500)
    speak: bool = True


class SessionIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def status() -> dict[str, Any]:
    settings: Settings = state["settings"]
    engine: Engine = state["engine"]
    return {
        "mcp_host": urlparse(settings.mcp_url).hostname,
        "model": settings.primary_model,
        "fallback_model": settings.fallback_model,
        "voice": settings.voice_id,
        "tools": [t.tool_name for t in engine.tools],
    }


@app.post("/api/turn")
def turn(body: TurnIn) -> dict[str, Any]:
    engine: Engine = state["engine"]
    result = engine.turn(body.session_id, body.text.strip())
    out = result.to_json()
    out["audio"] = None
    if body.speak and result.reply:
        try:
            audio, tts_ms = state["speaker"].synthesize(result.reply)
            out["audio"] = base64.b64encode(audio).decode()
            out["tts_ms"] = tts_ms
        except Exception as exc:  # the text reply still stands without audio
            log.warning("polly failed: %r", exc)
            out["tts_error"] = repr(exc)
    return out


@app.post("/api/reset")
def reset(body: SessionIn) -> dict[str, bool]:
    state["engine"].reset(body.session_id)
    return {"ok": True}


@app.get("/api/resource")
def resource(uri: str) -> dict[str, Any]:
    if not uri.startswith("ui://"):
        raise HTTPException(400, "only ui:// resources")
    try:
        return state["engine"].read_resource(uri)
    except Exception as exc:
        raise HTTPException(502, f"resources/read failed: {exc!r}") from exc
