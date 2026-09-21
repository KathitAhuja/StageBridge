"""
===============================================================================
MODULE: config.py
ROLE  : High-Speed Configuration Parameters for StageBridge
===============================================================================
"""

import os
from pathlib import Path

# Model Definition
MODEL_NAME = "sherpa-onnx-streaming-zipformer-en-2023-06-21"
SCRIPT_FILE_NAME = "aladdin_scene_dialogue.json"

# Path Definitions
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models" / MODEL_NAME
SCRIPT_PATH = BASE_DIR / "scripts" / SCRIPT_FILE_NAME

# Explicit Model File Paths
TOKENS_PATH = str(MODEL_DIR / "tokens.txt")
ENCODER_PATH = str(MODEL_DIR / "encoder-epoch-99-avg-1.int8.onnx")
DECODER_PATH = str(MODEL_DIR / "decoder-epoch-99-avg-1.int8.onnx")
JOINER_PATH = str(MODEL_DIR / "joiner-epoch-99-avg-1.int8.onnx")

# Audio Parameters
SAMPLE_RATE = 16000
BLOCK_SIZE = 800         # 50ms frame chunks
CHANNELS = 1
NUM_THREADS = 2

# Matching Thresholds
SHORT_MATCH_THRESHOLD = 85.0
MID_SENTENCE_THRESHOLD = 70.0
LOOKAHEAD_WINDOW = 3

# Voice Recording Output (matched actor lines saved here as MP3)
VOICE_DIR = BASE_DIR / "voice"
VOICE_ORIGINAL_DIR = VOICE_DIR / "original"

# Cue matching often confirms a line before the actor finishes speaking it
# (e.g. a prefix or short-target match). These control the "tail recording"
# that keeps capturing raw mic audio past the match point, so the saved MP3
# holds the WHOLE spoken line rather than just the audio up to the match:
#   - TRAILING_SILENCE_RMS_THRESHOLD: a block's raw amplitude below this is
#     treated as silence. Raise it if room/mic noise floor is being read as
#     speech (recording never ends until the length cap); lower it if the
#     actor's natural pauses aren't being detected as silence.
#   - TRAILING_SILENCE_SECONDS: how much continuous silence means "the line
#     is over" and the tail recording should be finalized and saved.
#   - MAX_LINE_RECORD_SECONDS: hard safety cap per line, in case silence is
#     never detected (loud background noise, mic issue, etc.).
TRAILING_SILENCE_RMS_THRESHOLD = 0.02
TRAILING_SILENCE_SECONDS = 2.0
MAX_LINE_RECORD_SECONDS = 15.0

# While a tail recording is open, its audio is independently re-decoded and
# compared against the FULL matched script line (same technique CueMatcher
# uses). Once the decoded tail text accounts for the whole line at this
# fuzzy-match score or higher, the recording is finalized immediately --
# before any off-script ad-lib/aside tacked on right after the line gets
# captured too. This is the primary cutoff; silence/next-match/length-cap
# above remain as fallbacks for when a clean content match never lands
# (misrecognition, mumbled ending, etc.).
CONTENT_COMPLETE_FUZZY_THRESHOLD = 90.0

# Web Server Settings
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", 8000))