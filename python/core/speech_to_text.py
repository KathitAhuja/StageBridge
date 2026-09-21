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
import numpy as np
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
    TRAILING_SILENCE_RMS_THRESHOLD,
    TRAILING_SILENCE_SECONDS,
    MAX_LINE_RECORD_SECONDS,
)
from core.cue_matcher import CueMatcher
from core.audio_recorder import save_utterance_audio


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

    block_duration = BLOCK_SIZE / SAMPLE_RATE
    trailing_silence_chunks = max(1, round(TRAILING_SILENCE_SECONDS / block_duration))
    max_chunks_per_recording = max(1, round(MAX_LINE_RECORD_SECONDS / block_duration))

    last_text = ""
    # Raw audio chunks for the utterance currently being decoded/matched
    # (since the last stream reset). The instant it's confirmed as a cue
    # match -- which can happen on a prefix/short-target match, i.e. before
    # the actor has finished speaking the whole line -- these chunks are
    # handed off to a tail recording (below) rather than saved immediately,
    # and this buffer restarts empty for the next line right away.
    utterance_chunks = []

    # Tail recordings in progress: one entry per matched cue that is still
    # capturing audio past its match point, waiting for the line to end.
    # Each entry:
    #   chunks      -- audio collected for this line so far
    #   payload     -- the matched cue payload (for filename/actor/line_id)
    #   silent_run  -- consecutive near-silent chunks seen since the match
    # Finalized (saved) on whichever comes first:
    #   1. The NEXT cue matches -- the strongest signal, since a new line
    #      being confirmed means this one is definitely over even if the
    #      next actor started with zero gap (overlapping/rapid dialogue).
    #   2. Trailing silence (TRAILING_SILENCE_SECONDS) -- covers lines with
    #      no immediate next line (end of scene, blackout, ad-lib).
    #   3. MAX_LINE_RECORD_SECONDS safety cap.
    # Runs independently of ASR matching/reset, so it never delays
    # detecting the next cue.
    tail_recordings = []

    def _finalize_tail_recordings(recordings):
        """Saves every still-open tail recording (used on shutdown)."""
        for rec in recordings:
            if rec["chunks"]:
                save_utterance_audio(np.concatenate(rec["chunks"]), rec["payload"])

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

                flat_samples = samples.reshape(-1)
                chunk_copy = flat_samples.copy()
                utterance_chunks.append(chunk_copy)

                # Feed this same chunk to any lines still finishing their
                # tail recording, and check whether each has now hit real
                # trailing silence (or the safety length cap).
                if tail_recordings:
                    chunk_rms = float(np.sqrt(np.mean(np.square(flat_samples))))
                    still_open = []
                    for rec in tail_recordings:
                        rec["chunks"].append(chunk_copy)
                        if chunk_rms < TRAILING_SILENCE_RMS_THRESHOLD:
                            rec["silent_run"] += 1
                        else:
                            rec["silent_run"] = 0

                        finished = (
                            rec["silent_run"] >= trailing_silence_chunks
                            or len(rec["chunks"]) >= max_chunks_per_recording
                        )
                        if finished:
                            save_utterance_audio(
                                np.concatenate(rec["chunks"]), rec["payload"]
                            )
                        else:
                            still_open.append(rec)
                    tail_recordings = still_open

                # Accept waveform chunk into active stream
                stream.accept_waveform(SAMPLE_RATE, flat_samples)

                while recognizer.is_ready(stream):
                    recognizer.decode_stream(stream)

                text = recognizer.get_result(stream).strip()

                if text and text != last_text:
                    cue_triggered = matcher.evaluate(text)
                    last_text = text

                    # Reset stream state instantly when a cue is matched --
                    # captions/matching for the next line must not wait on
                    # this line's audio finishing.
                    if cue_triggered:
                        # This new match is proof the previous line is over,
                        # even if the next actor came in with no audible gap
                        # (silence detection alone would miss that). Save
                        # whatever's been captured for it now.
                        if tail_recordings:
                            _finalize_tail_recordings(tail_recordings)
                            tail_recordings = []

                        # The audio captured so far (start of line through
                        # the match point) moves into a tail recording that
                        # keeps listening for the rest of the sentence.
                        if utterance_chunks:
                            tail_recordings.append(
                                {
                                    "chunks": utterance_chunks,
                                    "payload": matcher.last_payload,
                                    "silent_run": 0,
                                }
                            )
                        utterance_chunks = []
                        recognizer.reset(stream)
                        last_text = ""
                        continue

                if recognizer.is_endpoint(stream):
                    # Endpoint reached with no cue match -- off-script or
                    # misrecognized speech, discard the buffered audio.
                    utterance_chunks = []
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
        _finalize_tail_recordings(tail_recordings)
        recognizer.reset(stream)
        print("[STT] Speech-to-text worker thread stopped.", flush=True)


# Backwards compatibility alias
run_speech_to_text = start_speech_recognition