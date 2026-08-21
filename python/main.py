"""
===============================================================================
MODULE: main.py
ROLE  : Master Application Orchestrator & Execution Thread Controller
===============================================================================

FUNCTIONAL OVERVIEW:
1. Loads script JSON and triggers hotwords vocabulary generation.
2. Initializes audio processing queue, ASR engine, and CueMatcher instance.
3. Connects subscribers (Web Server stub) to EventBus.
4. Spawns asynchronous worker threads for web hosting and ASR audio decoding.
5. Captures real-time microphone stream via sounddevice callback loop.
"""

import queue
import threading
import sounddevice as sd

# Core architecture imports
from core.config import SAMPLE_RATE, BLOCK_SIZE
from core.cue_matcher import CueMatcher
from core.asr_engine import find_mic_device, create_recognizer
from core.event_bus import event_bus

# Support imports
from script_loader import load_script, generate_hotwords
from web.web_server import start_caption_server, web_broadcast_subscriber

# =============================================================================
# STEP 1: SYSTEM INITIALIZATION & DATA LOADING
# =============================================================================
# Parse script dialogue JSON file
script_data = load_script()

# Build dynamic hotwords.txt file from script vocabulary
generate_hotwords(script_data)

# Register web server subscriber function to receive EventBus cue events
event_bus.subscribe(web_broadcast_subscriber)

# Instantiate matcher engine and ASR recognizer objects
matcher = CueMatcher(script_data)
recognizer = create_recognizer()
stream = recognizer.create_stream()

# Queue to pass audio blocks safely between sounddevice callback and worker thread
audio_queue = queue.Queue()

# Locate hardware USB microphone device index
mic_index = find_mic_device()

# Start background web caption server thread
threading.Thread(target=start_caption_server, daemon=True).start()


# =============================================================================
# STEP 2: AUDIO STREAMING & DECODING WORKER THREADS
# =============================================================================
def audio_callback(indata, frames, time, status):
    """
    Hardware Audio Callback: Executed by sounddevice whenever new PCM audio arrives.
    """
    if status and not status.input_overflow:
        print(f"\n[AUDIO WARNING]: {status}", flush=True)
    # Append fresh copy of raw audio frame block into processing queue
    audio_queue.put(indata.copy())


def process_audio():
    """
    ASR Worker Thread: Pulls raw audio frames from queue, passes them into Zipformer
    stream, decodes text, and forwards updates to CueMatcher.
    """
    last_text = ""
    while True:
        # Block until new audio chunk is available in queue
        samples = audio_queue.get()
        if samples is None:  # Shutdown signal received
            break

        # Pass 16kHz float32 audio samples into Sherpa-ONNX stream buffer
        stream.accept_waveform(SAMPLE_RATE, samples[:, 0])

        # Run model inference while audio data is ready for decoding
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)

        # Check silence/pause status and extract current text string
        is_endpoint = recognizer.is_endpoint(stream)
        text = recognizer.get_result(stream).strip()

        # Evaluate text against script lines whenever recognized text updates
        if text and text != last_text:
            matcher.evaluate(text)
            last_text = text

        # Clear stream context buffer upon detected speech pause
        if is_endpoint:
            recognizer.reset(stream)
            last_text = ""

        audio_queue.task_done()


# Spawn audio decoding loop as background daemon thread
threading.Thread(target=process_audio, daemon=True).start()


# =============================================================================
# STEP 3: MAIN EXECUTION LOOP
# =============================================================================
print("\n" + "=" * 65, flush=True)
print(f"  STAGEBRIDGE CUE ENGINE ONLINE (MIC INDEX {mic_index})", flush=True)
print("  Speak your stage lines now!", flush=True)
print("=" * 65 + "\n", flush=True)

# Open continuous non-blocking microphone audio stream
with sd.InputStream(
    device=mic_index,
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype='float32',
    callback=audio_callback,
    blocksize=BLOCK_SIZE
):
    try:
        # Keep main thread alive while background threads process audio
        while True:
            sd.sleep(100)
    except KeyboardInterrupt:
        print("\n\nStopping StageBridge engine...", flush=True)
        # Send sentinel signal to stop audio processing worker thread
        audio_queue.put(None)