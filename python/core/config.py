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

# Web Server Settings
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", 8000))