"""
===============================================================================
MODULE: audio_recorder.py
ROLE  : Persists the Raw Microphone Audio Behind a Matched Cue as MP3
===============================================================================

FUNCTIONAL OVERVIEW:
1. The STT loop (core/speech_to_text.py) accumulates every raw audio chunk
   belonging to the CURRENT utterance (i.e. since the recognizer stream was
   last reset).
2. The instant CueMatcher confirms that utterance matched a script line,
   the STT loop hands the concatenated float32 samples + the matched cue's
   payload to save_utterance_audio() here.
3. This module encodes those samples directly to MP3 using `lameenc` -- a
   pip-only wrapper around libmp3lame. No WAV intermediate, no system
   `ffmpeg` binary required (unlike pydub), so `pip install -r
   requirements.txt` is the only setup step needed on any machine.

OUTPUT LOCATION: python/voice/original/ (see core/config.VOICE_ORIGINAL_DIR)
FILENAME FORMAT : <line_id>_<ACTOR>_<scene_id>_<timestamp>.mp3
"""

import re
import time

import numpy as np
import lameenc

from core.config import SAMPLE_RATE, VOICE_ORIGINAL_DIR

MP3_BITRATE_KBPS = 128
MP3_CHANNELS = 1
# 0 = highest quality/slowest, 7 = fastest/lowest quality (lameenc scale)
MP3_QUALITY = 2


def _safe_slug(value: str, fallback: str = "unknown") -> str:
    """Turns an arbitrary label (actor name, scene id, ...) into a
    filesystem-safe slug, e.g. 'Cave Voice' -> 'Cave_Voice'."""
    value = (value or "").strip()
    if not value:
        return fallback
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or fallback


def _build_filename(payload: dict) -> str:
    line_id = _safe_slug(str(payload.get("line_id", "")), fallback="line")
    actor = _safe_slug(payload.get("actor"), fallback="actor")
    scene_id = _safe_slug(payload.get("scene_id"), fallback="scene")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{line_id}_{actor}_{scene_id}_{timestamp}"


def _encode_mp3(samples: np.ndarray) -> bytes:
    """Encodes mono float32 samples (range ~[-1, 1]) at SAMPLE_RATE to MP3
    bytes using lameenc -- no external ffmpeg/system binary needed."""
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(MP3_BITRATE_KBPS)
    encoder.set_in_sample_rate(SAMPLE_RATE)
    encoder.set_channels(MP3_CHANNELS)
    encoder.set_quality(MP3_QUALITY)

    # lameenc expects 16-bit PCM bytes, not float32.
    clipped = np.clip(samples, -1.0, 1.0)
    pcm16_bytes = (clipped * 32767.0).astype(np.int16).tobytes()

    mp3_data = encoder.encode(pcm16_bytes)
    mp3_data += encoder.flush()
    return mp3_data


def save_utterance_audio(samples: np.ndarray, payload: dict) -> "str | None":
    """
    Encodes the raw mono float32 samples for a just-matched utterance to
    python/voice/original/<...>.mp3.

    Args:
        samples (np.ndarray): 1-D float32 array of the utterance's audio,
            captured at core.config.SAMPLE_RATE.
        payload (dict): The matched cue payload from CueMatcher.trigger_cue
            (line_id, actor, scene_id, english, ...), used to name the file.

    Returns:
        str or None: Path to the saved MP3 file, or None if nothing was
        written (e.g. an empty buffer, or encoding failed).
    """
    if samples is None or len(samples) == 0:
        return None

    VOICE_ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)

    base_name = _build_filename(payload or {})
    mp3_path = VOICE_ORIGINAL_DIR / f"{base_name}.mp3"

    try:
        mp3_data = _encode_mp3(samples)
        with open(mp3_path, "wb") as f:
            f.write(mp3_data)

        print(f"[AUDIO] Saved actor line audio -> {mp3_path}", flush=True)
        return str(mp3_path)
    except Exception as err:
        print(f"[AUDIO ERROR] Failed to save utterance audio: {err}", flush=True)
        return None