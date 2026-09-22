"""
===============================================================================
MODULE: main.py
ROLE  : Master Application Orchestrator & Execution Thread Controller
===============================================================================
"""

import threading
import uvicorn

# Core architecture imports
from core.config import WEB_HOST, WEB_PORT
from core.cue_matcher import CueMatcher
from core.event_bus import event_bus
from core.speech_to_text import run_speech_to_text

# Support imports
from script_loader import load_script, generate_hotwords
from web.server import app
from web.broadcaster import web_broadcaster

# =============================================================================
# STEP 1: SYSTEM INITIALIZATION & DATA LOADING
# =============================================================================
# Parse script dialogue JSON file
script_data = load_script()

# Build dynamic hotwords.txt file from script vocabulary
generate_hotwords(script_data)

# Register web browser broadcaster as subscriber for SSE delivery
event_bus.subscribe(web_broadcaster.publish)
# Same broadcaster instance also relays dubbed/translated audio, which
# arrives later than that line's text (real ElevenLabs generation time).
event_bus.subscribe_audio(web_broadcaster.publish)

# Instantiate matcher engine
matcher = CueMatcher(script_data)

# =============================================================================
# STEP 2: SPEECH-TO-TEXT WORKER THREAD
# =============================================================================
stt_stop_event = threading.Event()

stt_thread = threading.Thread(
    target=run_speech_to_text,
    args=(matcher, stt_stop_event),
    daemon=True,
    name="StageBridge-STT",
)
stt_thread.start()

# =============================================================================
# STEP 3: AUDIENCE CAPTION WEB SERVER (MAIN THREAD)
# =============================================================================
print("\n" + "=" * 65, flush=True)
print(f"  STAGEBRIDGE CAPTION SERVER ONLINE  http://{WEB_HOST}:{WEB_PORT}", flush=True)
print("=" * 65 + "\n", flush=True)

try:
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT, log_level="info")
except KeyboardInterrupt:
    print("\n\nStopping StageBridge engine...", flush=True)
finally:
    stt_stop_event.set()
    stt_thread.join(timeout=5)