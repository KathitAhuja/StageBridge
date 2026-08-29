"""
===============================================================================
MODULE: script_loader.py
ROLE  : Script Parsing & Fast Loader
===============================================================================
"""

import json
import os
import sys
from core.config import SCRIPT_PATH

def load_script():
    """Reads and parses script JSON file."""
    if not os.path.exists(SCRIPT_PATH):
        print(f"[ERROR] Script file not found at {SCRIPT_PATH}", flush=True)
        sys.exit(1)

    print(f"[INIT] Loading script JSON: {SCRIPT_PATH}...", flush=True)
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_hotwords(script_nodes: list):
    """Bypassed for high-speed greedy decoding."""
    pass