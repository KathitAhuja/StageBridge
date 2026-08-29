"""
===============================================================================
MODULE: speech_to_text.py
ROLE  : Speech-to-Text Worker Thread (Mic Capture + ASR Decode Loop)
===============================================================================

FUNCTIONAL OVERVIEW:
1. Owns the full life cycle of the microphone audio stream and the Sherpa-ONNX
   decode loop, previously the "main execution loop" of the application.
2. Designed to run entirely on a background worker thread so that the main
   thread is free to run the audience caption web server (see web/server.py).
3. Exits cleanly when signalled via a threading.Event, so the process can shut
   down gracefully when the web server (main thread) stops.
"""

import queue
import sounddevice as sd

from core.config import SAMPLE_RATE, BLOCK_SIZE
from core.asr_engine import find_mic_device


def run_speech_to_text(matcher, recognizer, stream, stop_event):
    """
    Thread entry point: captures live microphone audio, decodes it via the
    Sherpa-ONNX streaming recognizer, and forwards recognized text into the
    CueMatcher for cue triggering.

    Args:
        matcher (CueMatcher): Fuzzy-matching engine evaluating live text.
        recognizer (sherpa_onnx.OnlineRecognizer): Configured ASR engine.
        stream: Recognizer stream object created via recognizer.create_stream().
        stop_event (threading.Event): Signals this worker thread to shut down.
    """
    # Queue to pass audio blocks safely between sounddevice callback and this thread
    audio_queue = queue.Queue()

    # Locate hardware USB microphone device index
    mic_index = find_mic_device()

    def audio_callback(indata, frames, time, status):
        """
        Hardware Audio Callback: Executed by sounddevice whenever new PCM audio arrives.
        """
        if status and not status.input_overflow:
            print(f"\n[AUDIO WARNING]: {status}", flush=True)
        # Append fresh copy of raw audio frame block into processing queue
        audio_queue.put(indata.copy())

    print("\n" + "=" * 65, flush=True)
    print(f"  STAGEBRIDGE CUE ENGINE ONLINE (MIC INDEX {mic_index})", flush=True)
    print("  Speak your stage lines now!", flush=True)
    print("=" * 65 + "\n", flush=True)

    # Open continuous non-blocking microphone audio stream for the lifetime
    # of this worker thread.
    with sd.InputStream(
        device=mic_index,
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='float32',
        callback=audio_callback,
        blocksize=BLOCK_SIZE
    ):
        last_text = ""
        while not stop_event.is_set():
            try:
                # Block briefly for new audio; re-check stop_event periodically
                # so shutdown doesn't hang waiting on a queue that never fills.
                samples = audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if samples is None:  # Shutdown sentinel
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

    print("\n[STT] Speech-to-text worker thread stopped.", flush=True)
