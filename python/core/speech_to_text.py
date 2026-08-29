"""
===============================================================================
MODULE: speech_to_text.py
ROLE  : High-Speed Real-Time Audio Streaming & STT Processing Loop
===============================================================================
"""

import os
import sys
import queue
import threading
import sounddevice as sd
import sherpa_onnx

from core.config import (
    TOKENS_PATH,
    ENCODER_PATH,
    DECODER_PATH,
    JOINER_PATH,
    SAMPLE_RATE,
    BLOCK_SIZE,
    NUM_THREADS,
)
from core.cue_matcher import CueMatcher


def find_mic_device():
    """Scans host audio input devices for dedicated USB hardware microphones."""
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0 and (
                "TONOR" in dev.get("name", "") or "USB" in dev.get("name", "")
            ):
                return idx
    except Exception:
        pass
    return None


def create_recognizer() -> sherpa_onnx.OnlineRecognizer:
    """
    Instantiates Sherpa-ONNX transducer recognizer using greedy search
    for ultra-low latency processing.
    """
    return sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=TOKENS_PATH,
        encoder=ENCODER_PATH,
        decoder=DECODER_PATH,
        joiner=JOINER_PATH,
        decoding_method="greedy_search",
        num_threads=getattr(sys.modules[__name__], "NUM_THREADS", 4),
        sample_rate=SAMPLE_RATE,
        feature_dim=80,
        provider="cpu",
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=2.4,
        rule2_min_trailing_silence=1.2,
        rule3_min_utterance_length=20.0,
    )


def start_speech_recognition(matcher: CueMatcher, stop_event: threading.Event = None):
    print("[STT] Initializing Sherpa-ONNX High-Speed Recognizer (greedy_search)...", flush=True)
    recognizer = create_recognizer()
    stream = recognizer.create_stream()

    mic_index = find_mic_device()
    audio_queue = queue.Queue(maxsize=50)

    def audio_callback(indata, frames, time_info, status):
        if status and not status.input_overflow:
            print(f"\n[AUDIO WARNING]: {status}", file=sys.stderr, flush=True)
        try:
            audio_queue.put_nowait(indata.copy())
        except queue.Full:
            pass

    print(
        f"[STT] Hardware Audio Stream Online (Mic Index: {mic_index}, {SAMPLE_RATE} Hz)",
        flush=True,
    )
    print("[STT] System ready. Speak your script lines...\n", flush=True)

    last_text = ""

    try:
        with sd.InputStream(
            device=mic_index,
            channels=1,
            dtype="float32",
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            callback=audio_callback,
        ):
            while stop_event is None or not stop_event.is_set():
                try:
                    samples = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if samples is None:
                    break

                # Accept waveform chunk into active stream
                stream.accept_waveform(SAMPLE_RATE, samples.reshape(-1))

                while recognizer.is_ready(stream):
                    recognizer.decode_stream(stream)

                text = recognizer.get_result(stream).strip()

                if text and text != last_text:
                    cue_triggered = matcher.evaluate(text)
                    last_text = text

                    # Reset stream state instantly when a cue is matched
                    if cue_triggered:
                        recognizer.reset(stream)
                        last_text = ""
                        continue

                if recognizer.is_endpoint(stream):
                    recognizer.reset(stream)
                    last_text = ""

                audio_queue.task_done()

    except Exception as e:
        print(
            f"\n[STT ERROR]: Unexpected error in speech recognition loop: {e}",
            file=sys.stderr,
            flush=True,
        )
    finally:
        recognizer.reset(stream)
        print("[STT] Speech-to-text worker thread stopped.", flush=True)


# Backwards compatibility alias
run_speech_to_text = start_speech_recognition