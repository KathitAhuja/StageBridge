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

from core.config import VOICE_TRANSLATED_DIR
from web.broadcaster import web_broadcaster

app = FastAPI(title="Stage Bridge Audience Caption Server", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Dubbed/translated line clips (core/voice_pipeline.py writes here as
# python/voice/translated/<lang>/<line_id>.mp3), served to the audience UI
# for playback as each AUDIO_READY event arrives.
VOICE_TRANSLATED_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/audio/translated", StaticFiles(directory=str(VOICE_TRANSLATED_DIR)), name="translated_audio"
)

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

# Maps the same language selection to the short code core/voice_pipeline.py
# tags each AUDIO_READY event with. English has no dubbed clip (the
# actor's own voice already IS the original-language audio), so it maps to
# None -- an English-language client simply never receives audio events.
LANG_AUDIO_CODE_MAP = {
    "spanish": "es",
    "es": "es",
    "chinese": "zh",
    "zh": "zh",
    "english": None,
    "en": None,
}


def _audio_url(audio_path: str) -> "str | None":
    """Converts an absolute path under VOICE_TRANSLATED_DIR into the URL
    the browser can fetch it from via the static mount above."""
    try:
        rel = Path(audio_path).resolve().relative_to(VOICE_TRANSLATED_DIR.resolve())
    except Exception:
        return None
    return f"/audio/translated/{rel.as_posix()}"


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
    target_audio_lang = LANG_AUDIO_CODE_MAP.get(normalized_lang)

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

                if payload.get("event") == "AUDIO_READY":
                    # Dubbed audio arrives later than its line's text (real
                    # ElevenLabs generation time) and is per-language, just
                    # like the text -- only forward it to a client whose
                    # selected language matches this clip's language.
                    if payload.get("language") != target_audio_lang:
                        continue
                    audio_url = _audio_url(payload.get("audio_path"))
                    if not audio_url:
                        continue
                    out = {
                        "line_id": payload.get("line_id"),
                        "scene_id": payload.get("scene_id"),
                        "actor": payload.get("actor"),
                        "audio_url": audio_url,
                    }
                    # Named SSE event so the client can tell this apart from
                    # the default (text) message below.
                    yield f"event: audio\ndata: {json.dumps(out, ensure_ascii=False)}\n\n"
                    continue

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