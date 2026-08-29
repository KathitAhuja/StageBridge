"""
===============================================================================
MODULE: main.py
ROLE  : Master Application Orchestrator & Execution Thread Controller
===============================================================================

FUNCTIONAL OVERVIEW:
1. Loads script JSON and triggers hotwords vocabulary generation.
2. Initializes the ASR engine and CueMatcher instance.
3. Wires the audience caption web server (SSE Broadcaster) up to the EventBus.
4. Spawns the Speech-to-Text engine (mic capture + ASR decode loop) on a
   background worker thread.
5. Runs the audience caption web server (FastAPI/Uvicorn) on the MAIN thread.

THREADING MODEL:
    Main thread........ Uvicorn / FastAPI web server (audience captions)
    Background thread.. Speech-to-Text engine (mic capture + cue matching)
"""

import threading

import uvicorn

# Core architecture imports
from core.config import WEB_HOST, WEB_PORT
from core.cue_matcher import CueMatcher
from core.asr_engine import create_recognizer
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

# Register the web browser broadcaster as a subscriber so live cues reach
# connected audience browsers. web_broadcaster.publish() is thread-safe:
# CueMatcher fires it from the background Speech-to-Text thread, and it
# hands cues off to each browser's SSE connection running on the main
# thread's event loop.
event_bus.subscribe(web_broadcaster.publish)

# Instantiate matcher engine and ASR recognizer objects
matcher = CueMatcher(script_data)
recognizer = create_recognizer()
stream = recognizer.create_stream()

# =============================================================================
# STEP 2: SPEECH-TO-TEXT WORKER THREAD
# =============================================================================
# Signals the STT thread to shut down cleanly when the web server stops.
stt_stop_event = threading.Event()

stt_thread = threading.Thread(
    target=run_speech_to_text,
    args=(matcher, recognizer, stream, stt_stop_event),
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
    # Blocking call: this IS the main thread's execution loop from here on.
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT, log_level="info")
except KeyboardInterrupt:
    print("\n\nStopping StageBridge engine...", flush=True)
finally:
    # Signal the Speech-to-Text worker thread to stop and wait for it to exit.
    stt_stop_event.set()
    stt_thread.join(timeout=5)
