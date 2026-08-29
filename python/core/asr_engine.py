"""
===============================================================================
MODULE: asr_engine.py
ROLE  : Sherpa-ONNX Speech Recognizer & Hardware Microphone Setup
===============================================================================

FUNCTIONAL OVERVIEW:
1. Queries system audio interfaces to locate external USB hardware microphones.
2. Instantiates Sherpa-ONNX online transducer model with parameters optimized
   for low latency and low CPU utilization on ARM processors.
3. Loads hotwords.txt for vocabulary boosting and configures endpointing rules.
"""

import os
import sys
import sherpa_onnx
import sounddevice as sd
from core.config import (
    MODEL_DIR, 
    ENCODER_PARAM, 
    DECODER_PARAM, 
    JOINER_PARAM, 
    TOKENS_PARAM, 
    HOTWORDS_PATH, 
    HOTWORD_SCORE, 
    SAMPLE_RATE,
    NUM_THREADS
)

def find_mic_device():
    """
    Scans host audio input devices for dedicated USB hardware microphones.
    
    Returns:
        int or None: Index of matched device, or None to fall back to default input.
    """
    for idx, dev in enumerate(sd.query_devices()):
        # Check for input channel capability and matching hardware keywords
        if dev['max_input_channels'] > 0 and ('TONOR' in dev['name'] or 'USB' in dev['name']):
            return idx
    return None


def create_recognizer():
    """
    Builds and configures the streaming Zipformer neural ASR engine instance.
    
    Returns:
        sherpa_onnx.OnlineRecognizer: Fully configured recognizer instance.
    """
    # Verify model directory exists before attempting native library load
    if not os.path.exists(MODEL_DIR):
        print(f"[ERROR] Model directory missing at {MODEL_DIR}", flush=True)
        sys.exit(1)

    print(f"[INIT] Loading Zipformer int8 model from {MODEL_DIR}...", flush=True)
    
    return sherpa_onnx.OnlineRecognizer.from_transducer(
        # Explicit model path definitions using int8 quantized weights
        tokens=TOKENS_PARAM,
        encoder=ENCODER_PARAM,
        decoder=DECODER_PARAM,
        joiner=JOINER_PARAM,
        
        # Search strategy configuration
        decoding_method="modified_beam_search",  # Required for hotwords biasing
        max_active_paths=4,                      # Keeps search tree small to preserve CPU
        
        # Hotword biasing configuration
        hotwords_file=HOTWORDS_PATH if os.path.exists(HOTWORDS_PATH) else "",
        hotwords_score=HOTWORD_SCORE,
        
        # Audio stream and runtime parameters (Utilizes all 4 CPU cores)
        num_threads=NUM_THREADS,
        sample_rate=SAMPLE_RATE,
        feature_dim=80,
        provider="cpu",
        
        # Speech silence boundary (endpointing) rules tuned for responsive cueing
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=1.2,  # Silence duration to split long sentences
        rule2_min_trailing_silence=0.6,  # Silence duration to split short utterances
        rule3_min_utterance_length=20.0, # Maximum utterance length cap
    )