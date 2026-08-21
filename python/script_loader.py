"""
===============================================================================
MODULE: script_loader.py
ROLE  : Script Parsing & Dynamic Hotword Extraction
===============================================================================

FUNCTIONAL OVERVIEW:
1. Loads dialogue JSON data into memory.
2. Scans script nodes for actor names, distinct terms, and 2-word key phrases.
3. Generates formatted `hotwords.txt` file to boost acoustic likelihood of
   uncommon script terms during ASR search tree decoding.
"""

import json
import os
import sys
from core.config import SCRIPT_PATH, HOTWORDS_PATH, HOTWORD_SCORE

def load_script():
    """
    Reads and parses script JSON file.
    
    Returns:
        list: Parsed JSON array containing dialogue dictionaries.
    """
    if not os.path.exists(SCRIPT_PATH):
        print(f"[ERROR] Script file not found at {SCRIPT_PATH}", flush=True)
        sys.exit(1)

    print(f"[INIT] Loading script JSON: {SCRIPT_PATH}...", flush=True)
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_hotwords(script_nodes: list):
    """
    Extracts high-priority terms from script and builds hotwords.txt file.
    
    Args:
        script_nodes (list): Script dialogue nodes from load_script().
    """
    # Common words excluded from acoustic boosting
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by", "is", "it", "we", "were"}
    hotwords = set()

    # Step 1: Parse script nodes
    for node in script_nodes:
        # Boost actor character names
        if "actor" in node:
            hotwords.add(node["actor"])

        # Clean punctuation from dialogue lines
        text = node.get("english", "")
        words = [w.strip(".,!?'\"").replace("’", "") for w in text.split()]

        # Step 2: Extract 2-word key phrases (e.g., "CAVE OF")
        for i in range(len(words) - 1):
            w1, w2 = words[i].lower(), words[i+1].lower()
            if w1 not in stopwords and w2 not in stopwords and len(w1) > 2 and len(w2) > 2:
                hotwords.add(f"{words[i]} {words[i+1]}")

        # Step 3: Extract distinct single words (length >= 4)
        for w in words:
            if len(w) >= 4 and w.lower() not in stopwords:
                hotwords.add(w)

    # Step 4: Write formatted terms into hotwords.txt file ("TERM : SCORE")
    with open(HOTWORDS_PATH, "w", encoding="utf-8") as f:
        for hw in hotwords:
            f.write(f"{hw} : {HOTWORD_SCORE}\n")

    print(f"[INIT] Dynamic hotwords generated: {len(hotwords)} terms -> {HOTWORDS_PATH}", flush=True)