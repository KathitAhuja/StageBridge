"""
===============================================================================
MODULE: dev_server.py
ROLE  : Developer Entry Point -- Web Server ONLY (no mic, no ASR model)
===============================================================================

FUNCTIONAL OVERVIEW:
1. Runs the exact same FastAPI app as production (web/server.py) so the
   audience UI, static assets, and SSE stream are all tested for real.
2. Skips create_recognizer() / the Speech-to-Text worker thread entirely --
   no Sherpa-ONNX model download or microphone required. This is what lets
   you run and test the web server in PyCharm on a laptop, separate from the
   Arduino Uno Q hardware path (main.py).
3. Loads the script JSON and auto-emits one cue payload per line, on a fixed
   interval, via event_bus.emit_cue() -- the SAME call CueMatcher makes in
   production. This drives the console logger AND the web broadcaster off a
   single call, exactly like the real app, just without real speech input.

USAGE (e.g. as a PyCharm Run Configuration):
    Script path : python/dev_server.py
    Working dir : python/
    Run it, open http://localhost:8080, pick a language, and watch the
    script play out automatically.

NOTE: main.py (the production/Arduino entry point) never imports this file.
"""

import threading
import time

import uvicorn

from core.config import WEB_HOST, WEB_PORT
from core.event_bus import event_bus
from script_loader import load_script
from web.server import app
from web.broadcaster import web_broadcaster

# Seconds to wait between auto-emitted lines.
LINE_INTERVAL_SECONDS = 2.0

# Load the script once at startup -- this is the only "data" dev_server needs.
script_data = load_script()

# Wire the web browser broadcaster up to the EventBus, exactly like main.py does.
event_bus.subscribe(web_broadcaster.publish)


def auto_play_script():
    """
    Background thread: walks the script from the top and emits each line's
    cue payload through the EventBus on a fixed interval, standing in for
    CueMatcher's real-time triggering.
    """
    time.sleep(1.0)  # brief pause so the server is fully up before the first cue
    for idx, node in enumerate(script_data):
        payload = {
            "event": "CUE_TRIGGERED",
            "line_id": node.get("line_id"),
            "scene_id": node.get("scene_id"),
            "actor": node.get("actor"),
            "english": node.get("english"),
            "spanish_translation": node.get("spanish_translation", ""),
            "chinese_translation": node.get("chinese_translation", ""),
            "match_type": "DEV_AUTO_PLAY",
            "line_index": idx,
        }
        event_bus.emit_cue(payload)
        time.sleep(LINE_INTERVAL_SECONDS)


if __name__ == "__main__":
    print("\n" + "=" * 65, flush=True)
    print(f"  STAGEBRIDGE DEV WEB SERVER (NO MIC / NO ASR MODEL)", flush=True)
    print(f"  Audience UI : http://localhost:{WEB_PORT}", flush=True)
    print(f"  Auto-playing {len(script_data)} lines, one every {LINE_INTERVAL_SECONDS}s", flush=True)
    print("=" * 65 + "\n", flush=True)

    threading.Thread(target=auto_play_script, daemon=True).start()
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT, log_level="info")
