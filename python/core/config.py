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

# PATH 3 (multi-word anchor match, see cue_matcher.py) compares spoken text
# against the target line's TEXT TRUNCATED to the same word count. With too
# few recognized words, that truncated target collapses to almost nothing
# (e.g. 1 word), which a stray ASR fragment (breath noise, room echo, a
# mis-heard sound right after a stream reset) can trivially score 100%
# against by chance if it happens to match a line's first word or two. This
# is the minimum number of actually-recognized words required before this
# path is attempted at all, so a 1-2 word fragment can never anchor-match a
# longer line on its own.
MIN_WORDS_FOR_ANCHOR_MATCH = 3

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

# Web Server Settings
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", 8000))

# ElevenLabs Voice Cloning + Dubbing
# ------------------------------------------------------------------------
# Each actor's own recorded lines (python/voice/original/) accumulate until
# VOICE_CLONE_THRESHOLD_SECONDS is reached, at which point an Instant Voice
# Clone is created automatically and used for all of that actor's later
# translated lines. Until then (and for actors with no premade fallback
# listed below), DEFAULT_VOICE_ID is used.
#
#   - ACTOR_VOICE_IDS: optional per-actor premade ElevenLabs voice_id to use
#     as that actor's fallback instead of DEFAULT_VOICE_ID, e.g.:
#         ACTOR_VOICE_IDS = {"ALADDIN": "ErXwobaYiN019PkySvjV"}
#   - DEFAULT_VOICE_ID: shared fallback for any actor not listed above (or
#     with no premade voice picked yet).
#   - VOICE_CLONE_THRESHOLD_SECONDS: seconds of an actor's own audio needed
#     before an Instant Voice Clone is created for them.
#   - ELEVENLABS_TTS_MODEL_ID: ElevenLabs model used to synthesize
#     translated lines (multilingual, needed for Spanish/Chinese output).
ACTOR_VOICE_IDS = {}
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "TX3LPaxmHKxFdv7VOQHJ")
VOICE_CLONE_THRESHOLD_SECONDS = 10.0
ELEVENLABS_TTS_MODEL_ID = "eleven_multilingual_v2"

# Dubbed/translated line audio output (served to the audience web UI)
VOICE_TRANSLATED_DIR = VOICE_DIR / "translated"