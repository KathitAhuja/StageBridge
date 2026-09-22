"""
===============================================================================
MODULE: voice_pipeline.py
ROLE  : Per-Actor Voice Cloning + Translated-Line Dubbing via ElevenLabs
===============================================================================

FUNCTIONAL OVERVIEW:
1. Every actor gets a DynamicVoiceManager. Each time that actor's matched
   line audio is saved locally (core/audio_recorder.py), it's registered
   here. Once an actor's own accumulated audio reaches
   VOICE_CLONE_THRESHOLD_SECONDS, an ElevenLabs Instant Voice Clone (IVC) is
   created automatically from those clips and used for all of that actor's
   FUTURE translated lines. Until then, a fallback voice_id is used
   (ACTOR_VOICE_IDS[actor] if configured, else DEFAULT_VOICE_ID).
2. For each translation on the matched cue (spanish_translation,
   chinese_translation), the translated text is synthesized in the actor's
   current voice via ElevenLabs TTS -- so the audience hears the line as if
   the actual actor were delivering it in that language -- saved under
   python/voice/translated/<lang>/<line_id>.mp3, and an AUDIO_READY event is
   emitted on the event bus once that clip is done.
3. ElevenLabs is a network API: cloning and TTS calls run on a small
   background thread pool, never on the real-time STT thread. A slow or
   failed API call must never drop mic audio or delay cue matching.

WHY AUDIO_READY IS A SEPARATE, LATER EVENT FROM CUE_TRIGGERED:
CueMatcher already broadcasts a line's TEXT the instant it's confirmed
(often mid-sentence, well before the tail recording even finishes -- see
core/speech_to_text.py). The dubbed AUDIO for that same line can only exist
after: the full line's original audio is saved, the actor's active voice_id
is resolved (and possibly just-cloned), and ElevenLabs has generated the
translated clip. That's real, sometimes multi-second, network latency --
so AUDIO_READY is always a later, independent event, matched back to its
caption on the web client by line_id.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

from core.config import (
    SAMPLE_RATE,
    ACTOR_VOICE_IDS,
    DEFAULT_VOICE_ID,
    VOICE_CLONE_THRESHOLD_SECONDS,
    VOICE_TRANSLATED_DIR,
    ELEVENLABS_TTS_MODEL_ID,
)
from core.event_bus import event_bus

load_dotenv()

# Payload fields holding translated text, mapped to the short language code
# used for filenames / SSE events / the audience language selector.
TRANSLATION_FIELDS = {
    "spanish_translation": "es",
    "chinese_translation": "zh",
}

_client = None
_client_lock = threading.Lock()


def _get_client() -> ElevenLabs:
    """Lazily creates the shared ElevenLabs client (reads
    ELEVENLABS_API_KEY from the environment/.env, same as the reference
    script)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
    return _client


class DynamicVoiceManager:
    """
    Accumulates one actor's own recorded lines and auto-triggers an
    ElevenLabs Instant Voice Clone once enough audio
    (VOICE_CLONE_THRESHOLD_SECONDS) has been collected. Uses a fallback
    voice_id until the clone exists.
    """

    def __init__(self, actor_name: str, fallback_voice_id: str):
        self.actor_name = actor_name
        self.fallback_voice_id = fallback_voice_id
        self.cloned_voice_id = None
        self.audio_samples = []
        self.total_duration = 0.0
        # Set once a clone attempt fails, so a persistent problem (e.g. the
        # ElevenLabs account's plan not including Instant Voice Cloning)
        # doesn't retry -- and fail, and log -- on every single subsequent
        # line for the rest of the run. Restarting the app resets this, so
        # fixing the account and restarting is enough to try again.
        self.clone_attempt_failed = False
        # Guards state across concurrent background-thread-pool workers
        # (two lines for the same actor could finish saving close together).
        self._lock = threading.Lock()

    def add_sample_and_check_clone(self, audio_file_path: str, duration_seconds: float) -> str:
        """
        Registers a newly-saved original-audio clip for this actor. If this
        pushes total accumulated duration past the clone threshold and no
        clone exists yet, creates one now.

        Args:
            audio_file_path (str): Path to the actor's saved original-line
                MP3 (core.audio_recorder.save_utterance_audio's output).
            duration_seconds (float): Exact duration of that clip -- known
                directly from the sample count already captured, so no
                file-parsing/estimation is needed.

        Returns:
            str: The voice_id to use for this actor's NEXT translated line
                 (the new/existing clone if ready, fallback otherwise).
        """
        with self._lock:
            if self.cloned_voice_id or self.clone_attempt_failed:
                return self.cloned_voice_id or self.fallback_voice_id

            self.audio_samples.append(audio_file_path)
            self.total_duration += duration_seconds
            print(
                f"[VOICE] [{self.actor_name}] +{duration_seconds:.1f}s of "
                f"original audio (total {self.total_duration:.1f}s / "
                f"{VOICE_CLONE_THRESHOLD_SECONDS:.0f}s needed)",
                flush=True,
            )

            if self.total_duration >= VOICE_CLONE_THRESHOLD_SECONDS:
                print(
                    f"[VOICE] {self.actor_name}: threshold reached -- "
                    "creating Instant Voice Clone...",
                    flush=True,
                )
                try:
                    self.cloned_voice_id = self._create_clone()
                    print(
                        f"[VOICE] {self.actor_name}: clone ready -> "
                        f"{self.cloned_voice_id}",
                        flush=True,
                    )
                except Exception as err:
                    self.clone_attempt_failed = True
                    print(
                        f"[VOICE ERROR] {self.actor_name}: clone failed "
                        f"({err}); staying on fallback voice for the rest "
                        "of this run.",
                        flush=True,
                    )

            return self.cloned_voice_id or self.fallback_voice_id

    def _create_clone(self) -> str:
        # Open each audio sample file in binary read mode ('rb').
        # HTTPX / ElevenLabs SDK requires file-like objects (or bytes). Passing
        # raw file path strings causes HTTPX to treat the path string itself as the
        # file content, resulting in ElevenLabs rejecting it as 'File is corrupted'.
        file_handles = []
        try:
            for path in self.audio_samples:
                if os.path.isfile(path):
                    file_handles.append(open(path, "rb"))

            if not file_handles:
                raise ValueError("No valid audio sample files found to create voice clone.")

            # Explicitly pass labels={} because omitting it causes the Fern-generated
            # SDK to serialize OMIT to "null" in the multipart request body, triggering
            # ElevenLabs API error: "Labels must be serialized dictionary object."
            voice = _get_client().voices.ivc.create(
                name=f"AutoClone_{self.actor_name}",
                description=f"Automated voice clone for {self.actor_name}",
                files=file_handles,
                labels={},
            )
            return voice.voice_id
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    def get_active_voice_id(self) -> str:
        """Returns the cloned voice ID if available, otherwise the fallback."""
        return self.cloned_voice_id or self.fallback_voice_id


_voice_managers = {}
_voice_managers_lock = threading.Lock()


def _get_voice_manager(actor_name: str) -> DynamicVoiceManager:
    with _voice_managers_lock:
        manager = _voice_managers.get(actor_name)
        if manager is None:
            fallback_voice_id = ACTOR_VOICE_IDS.get(actor_name, DEFAULT_VOICE_ID)
            manager = DynamicVoiceManager(actor_name, fallback_voice_id)
            _voice_managers[actor_name] = manager
        return manager


def _dub_line(text: str, voice_id: str, payload: dict, lang_code: str):
    """Synthesizes one translated line in the actor's current voice and
    emits an AUDIO_READY event once the file is written."""
    if not text:
        return

    line_id = str(payload.get("line_id", "unknown"))
    lang_dir = VOICE_TRANSLATED_DIR / lang_code
    lang_dir.mkdir(parents=True, exist_ok=True)
    output_path = lang_dir / f"{line_id}.mp3"

    try:
        audio_generator = _get_client().text_to_speech.convert(
            text=text, voice_id=voice_id, model_id=ELEVENLABS_TTS_MODEL_ID
        )
        with open(output_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)

        print(f"[VOICE] Dubbed [{lang_code}] line {line_id} -> {output_path}", flush=True)

        event_bus.emit_audio_ready(
            {
                "event": "AUDIO_READY",
                "line_id": payload.get("line_id"),
                "scene_id": payload.get("scene_id"),
                "actor": payload.get("actor"),
                "language": lang_code,
                "audio_path": str(output_path),
            }
        )
    except Exception as err:
        print(
            f"[VOICE ERROR] Dubbing failed for line {line_id} [{lang_code}]: {err}",
            flush=True,
        )


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voice-pipeline")


def process_matched_line(samples, payload: dict, original_audio_path: str):
    """
    Entry point called from the STT loop once a matched line's full
    original audio has been saved locally. Submits the actual voice
    cloning + dubbing work to a background thread -- this call itself
    returns immediately and never blocks real-time mic capture.

    Args:
        samples (np.ndarray): The exact float32 samples that were saved,
            used only to compute duration precisely (len(samples)/SAMPLE_RATE)
            -- no need to re-parse/estimate from the encoded MP3 file.
        payload (dict): The matched cue payload (actor, line_id, scene_id,
            spanish_translation, chinese_translation, ...).
        original_audio_path (str): Path to the actor's own saved audio for
            this line (core.audio_recorder.save_utterance_audio's return
            value). If falsy, cloning progress isn't updated for this line
            (e.g. the save failed) but dubbing still proceeds on whatever
            voice is currently active.
    """
    duration_seconds = (len(samples) / float(SAMPLE_RATE)) if samples is not None else 0.0
    _executor.submit(
        _process_matched_line_sync, duration_seconds, payload, original_audio_path
    )


def _process_matched_line_sync(duration_seconds: float, payload: dict, original_audio_path: str):
    actor = payload.get("actor") or "UNKNOWN"
    manager = _get_voice_manager(actor)

    if original_audio_path:
        voice_id = manager.add_sample_and_check_clone(original_audio_path, duration_seconds)
    else:
        voice_id = manager.get_active_voice_id()

    for field, lang_code in TRANSLATION_FIELDS.items():
        _dub_line(payload.get(field, ""), voice_id, payload, lang_code)