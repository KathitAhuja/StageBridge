"""
===============================================================================
MODULE: server.py
ROLE  : Audience Caption Streaming Web Server (FastAPI)
===============================================================================

FUNCTIONAL OVERVIEW:
1. Serves the audience-facing single-page caption UI (static/index.html) and
   its assets (CSS, JS, actor images, cue-line voice clips).
2. Exposes a Server-Sent Events (SSE) endpoint that streams cue payloads to
   each connected browser LIVE, as they are triggered by CueMatcher on the
   Speech-to-Text worker thread -- translated into the client's chosen
   language.
3. This module owns no threads or event loops of its own: it is designed to
   be run by Uvicorn on the application's MAIN thread (see main.py), while
   speech recognition runs on a separate background thread.
"""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from web.broadcaster import web_broadcaster

app = FastAPI(title="Stage Bridge Audience Caption Server", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Maps an audience member's language selection to the cue payload field
# CueMatcher already populates for that language.
LANG_FIELD_MAP = {
    "spanish": "spanish_translation",
    "es": "spanish_translation",
    "chinese": "chinese_translation",
    "zh": "chinese_translation",
    "english": "english",
    "en": "english",
}


@app.get("/")
async def serve_index():
    """Serves the audience caption single-page UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/v1/stream")
async def stream_theater_lines(lang: str = Query(...)):
    """
    Server-Sent Events endpoint: streams cue payloads to the browser live,
    as they are triggered on stage, translated to the requested language.

    Args:
        lang (str): Requested audience language ("spanish"/"es", "chinese"/"zh").
    """
    normalized_lang = lang.lower()
    if normalized_lang not in LANG_FIELD_MAP:
        raise HTTPException(status_code=400, detail="Unsupported language selected.")

    target_field = LANG_FIELD_MAP[normalized_lang]

    async def event_generator():
        # Register this client on the *current* request's running event loop
        # (the same loop Uvicorn is driving on the main thread) so the
        # WebBroadcaster can safely deliver cues published from the
        # STT thread.
        event_loop = asyncio.get_running_loop()
        client_queue = web_broadcaster.register(event_loop)
        try:
            while True:
                payload = await client_queue.get()
                out = {
                    "line_id": payload.get("line_id"),
                    "scene_id": payload.get("scene_id"),
                    "actor": payload.get("actor"),
                    "text": payload.get(target_field) or payload.get("english"),
                }
                # SSE framing format requires standard `data: <string>\n\n` syntax
                yield f"data: {json.dumps(out, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            # Client disconnected; let cleanup below run and re-raise.
            raise
        finally:
            web_broadcaster.unregister(client_queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
