"""
===============================================================================
MODULE: cue_matcher.py
ROLE  : Dual-Path Fuzzy Logic Text Alignment Engine
===============================================================================

FUNCTIONAL OVERVIEW:
1. Compares real-time ASR text against active target script lines.
2. Path 1 (Short Input / Short Target): Enforces strict ratio checks on 1-2 word
   utterances to prevent false positives against long dialogue lines.
3. Path 2 (Long Target / 3+ Words): Uses mid-sentence partial ratio matching
   to trigger cues instantly as soon as an actor starts speaking a line.
4. Advances the active line pointer upon successful match.
"""

from rapidfuzz import fuzz
from core.config import SHORT_MATCH_THRESHOLD, MID_SENTENCE_THRESHOLD, LOOKAHEAD_WINDOW
from core.event_bus import event_bus

class CueMatcher:
    def __init__(self, script_data: list):
        """
        Args:
            script_data (list): Parsed JSON list of dialogue nodes.
        """
        self.script_data = script_data
        # Self-advancing pointer tracking the index of the active script line
        self.current_line_idx = 0

    def trigger_cue(self, target_node: dict, matched_idx: int, match_type: str):
        """
        Packages matched line details into a payload dictionary, broadcasts it
        to the EventBus, and advances the pointer.
        """
        # Step 1: Construct JSON-serializable output payload
        payload = {
            "event": "CUE_TRIGGERED",
            "line_id": target_node.get("line_id"),
            "scene_id": target_node.get("scene_id"),
            "actor": target_node.get("actor"),
            "english": target_node.get("english"),
            "spanish_translation": target_node.get("spanish_translation", ""),
            "chinese_translation": target_node.get("chinese_translation", ""),
            "match_type": match_type,
            "line_index": matched_idx
        }

        # Step 2: Publish payload to all EventBus subscribers (CLI, Web, MCU)
        event_bus.emit_cue(payload)

        # Step 3: Advance active index past matched line to prevent re-triggering
        self.current_line_idx = matched_idx + 1

    def evaluate(self, live_text: str):
        """
        Evaluates incoming ASR text against upcoming script lines within lookahead window.
        
        Args:
            live_text (str): Live partial/final text output from Sherpa-ONNX.
        """
        # Stop processing if performance script has finished
        if self.current_line_idx >= len(self.script_data):
            return

        # Clean and split incoming live text
        live_upper = live_text.upper().strip()
        words = live_upper.split()
        if not words:
            return

        # Calculate dynamic lookahead window based on remaining script lines
        remaining_lines = len(self.script_data) - self.current_line_idx
        window_size = min(LOOKAHEAD_WINDOW, remaining_lines)

        # Iterate over lookahead window lines (Active Line, Active+1, Active+2)
        for window_offset in range(window_size):
            eval_idx = self.current_line_idx + window_offset
            target_node = self.script_data[eval_idx]
            
            target_english = target_node["english"].upper().strip()
            target_words = target_english.split()

            # Flag targets with 2 or fewer words ("Yes, my lord.", "Stop!")
            is_short_target = len(target_words) <= 2

            # =================================================================
            # PATH 1: EVALUATE SHORT TARGETS OR SHORT SPOKEN INPUT (< 3 WORDS)
            # =================================================================
            if is_short_target or len(words) < 3:
                # Calculate strict Levenshtein-based string ratio
                strict_score = fuzz.ratio(live_upper, target_english)
                
                # Check for strict threshold or exact word containment
                if strict_score >= SHORT_MATCH_THRESHOLD or (is_short_target and live_upper in target_english):
                    self.trigger_cue(target_node, eval_idx, "STRICT SHORT MATCH")
                    break

            # =================================================================
            # PATH 2: EVALUATE LONG TARGET LINES (3 OR MORE SPOKEN WORDS)
            # =================================================================
            else:
                # partial_ratio: Finds best matching sub-segment anywhere in target
                partial_score = fuzz.partial_ratio(live_upper, target_english)
                
                # token_set_ratio: Matches key words regardless of word order/extra words
                token_set_score = fuzz.token_set_ratio(live_upper, target_english)
                
                # Use maximum calculated score for robust alignment
                effective_score = max(partial_score, token_set_score)

                # Visual real-time score tracker printed on active console line
                print(f"\r[{target_node['actor']} CUE]: {live_text[-30:]} | Score: {int(effective_score)}%\x1b[K", end="", flush=True)

                # Trigger cue if score meets mid-sentence anchor threshold (72%)
                if effective_score >= MID_SENTENCE_THRESHOLD:
                    self.trigger_cue(target_node, eval_idx, "MID-SENTENCE ANCHOR (3+ Words)")
                    break