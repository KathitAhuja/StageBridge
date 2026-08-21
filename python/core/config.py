"""
===============================================================================
MODULE: config.py
ROLE  : Central Configuration & Environmental Constants
===============================================================================

FUNCTIONAL OVERVIEW:
1. Dynamically constructs absolute paths across local directories so the app
   runs cleanly whether launched via CLI, systemd, or Arduino App Lab.
2. Defines hardware audio streaming parameters for the microphone pipeline.
3. Sets tuning parameters for neural ASR biasing and fuzzy matching paths.
"""

import os

# =============================================================================
# SECTION 1: DIRECTORY & PATH CALCULATIONS
# =============================================================================
# BASE_DIR resolves to: /home/arduino/ArduinoApps/stagebridge/python
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# APP_ROOT resolves to: /home/arduino/ArduinoApps/stagebridge
APP_ROOT = os.path.dirname(BASE_DIR)

# Path to the source theater script JSON file containing line IDs and translations
SCRIPT_PATH = os.path.join(BASE_DIR, "scripts", "aladdin_scene_dialogue.json")

# Path where dynamically generated hotword boosts will be saved for Sherpa-ONNX
HOTWORDS_PATH = os.path.join(BASE_DIR, "hotwords.txt")

# Locates the Zipformer model directory by checking app root before script folder
ROOT_MODEL = os.path.join(APP_ROOT, "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17")
SCRIPT_MODEL = os.path.join(BASE_DIR, "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17")
MODEL_DIR = ROOT_MODEL if os.path.exists(ROOT_MODEL) else SCRIPT_MODEL

# =============================================================================
# SECTION 2: AUDIO STREAMING & NEURAL ENGINE PARAMETERS
# =============================================================================
# Sampling rate required by Sherpa-ONNX Zipformer acoustic models (16,000 Hz)
SAMPLE_RATE = 16000

# Audio frame chunk size: 3200 samples = exactly 200 milliseconds per block
BLOCK_SIZE = 3200

# Acoustic weight multiplier assigned to script vocabulary in hotwords.txt
HOTWORD_SCORE = 2.5

# =============================================================================
# SECTION 3: FUZZY CUE-MATCHING ENGINE THRESHOLDS
# =============================================================================
# Minimum similarity ratio (%) required to trigger short target lines ("Yes", "No")
SHORT_MATCH_THRESHOLD = 85

# Minimum similarity ratio (%) required for mid-sentence anchor triggers (3+ words)
MID_SENTENCE_THRESHOLD = 72

# Maximum number of upcoming script lines to evaluate simultaneously from pointer
LOOKAHEAD_WINDOW = 3