"""
===============================================================================
MODULE: cue_matcher.py
ROLE  : Precision Fuzzy Text Alignment Engine with Robust Interjection Support
===============================================================================
"""

import re
from rapidfuzz import fuzz
from core.config import SHORT_MATCH_THRESHOLD, MID_SENTENCE_THRESHOLD, LOOKAHEAD_WINDOW
from core.event_bus import event_bus


class CueMatcher:
    def __init__(self, script_data: list):
        self.script_data = script_data
        self.current_line_idx = 0
        # Payload dict from the most recently triggered cue (None until the
        # first match). The STT loop reads this right after evaluate()
        # returns True to know which line/actor the just-recorded audio
        # buffer belongs to, for saving it under voice/original.
        self.last_payload = None

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.upper()
        text = text.replace("-", " ")
        text = re.sub(r"[^\w\s]", " ", text)
        return " ".join(text.split())

    def trigger_cue(self, target_node: dict, matched_idx: int, match_type: str):
        payload = {
            "event": "CUE_TRIGGERED",
            "line_id": target_node.get("line_id"),
            "scene_id": target_node.get("scene_id"),
            "actor": target_node.get("actor"),
            "english": target_node.get("english"),
            "spanish_translation": target_node.get("spanish_translation", ""),
            "chinese_translation": target_node.get("chinese_translation", ""),
            "match_type": match_type,
            "line_index": matched_idx,
        }

        self.last_payload = payload
        event_bus.emit_cue(payload)
        self.current_line_idx = matched_idx + 1

    def evaluate(self, live_text: str) -> bool:
        if self.current_line_idx >= len(self.script_data):
            return False

        live_clean = self._clean_text(live_text)
        words = live_clean.split()
        if not words:
            return False

        remaining_lines = len(self.script_data) - self.current_line_idx
        window_size = min(LOOKAHEAD_WINDOW, remaining_lines)

        for window_offset in range(window_size):
            eval_idx = self.current_line_idx + window_offset
            target_node = self.script_data[eval_idx]
            target_clean = self._clean_text(target_node.get("english", ""))
            target_words = target_clean.split()

            if not target_words:
                continue

            # -----------------------------------------------------------------
            # PATH 1: EXACT MATCH CHECK (100% Match for Short Lines / Interjections)
            # Handles "UH OH" == "UH OH", "NO" == "NO", etc.
            # -----------------------------------------------------------------
            if live_clean == target_clean:
                self.trigger_cue(target_node, eval_idx, "EXACT PHRASE MATCH")
                return True

            # If spoken text is trailing words of live stream (e.g., "ALADDIN SAID UH OH")
            if len(words) >= len(target_words):
                spoken_tail = " ".join(words[-len(target_words):])
                if spoken_tail == target_clean:
                    self.trigger_cue(target_node, eval_idx, "TRAILING EXACT MATCH")
                    return True

            # -----------------------------------------------------------------
            # PATH 2: SHORT TARGET LINES (1-2 words in script)
            # -----------------------------------------------------------------
            if len(target_words) <= 2:
                ratio_score = fuzz.ratio(live_clean, target_clean)
                token_score = fuzz.token_sort_ratio(live_clean, target_clean)
                if max(ratio_score, token_score) >= 70.0:
                    self.trigger_cue(target_node, eval_idx, "SHORT TARGET FUZZY MATCH")
                    return True
                continue

            # -----------------------------------------------------------------
            # PATH 3: MULTI-WORD TARGET LINES (3+ words in script)
            # Spoken phrase must align with the prefix or order of the line
            # -----------------------------------------------------------------
            # Compare spoken text directly against the prefix of the target line
            target_prefix = " ".join(target_words[:len(words)])
            prefix_score = fuzz.ratio(live_clean, target_prefix)

            # Sequence alignment score
            token_sort_score = fuzz.token_sort_ratio(live_clean, target_clean)

            # Allow match if prefix matches closely OR full line similarity is high
            if prefix_score >= 75.0 or token_sort_score >= MID_SENTENCE_THRESHOLD:
                self.trigger_cue(target_node, eval_idx, "MULTI-WORD ANCHOR MATCH")
                return True

        return False