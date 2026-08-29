"""
===============================================================================
MODULE: broadcaster.py
ROLE  : Thread-Safe Bridge Between EventBus (STT Thread) and Web Browser
        SSE Clients (Main Thread's asyncio Event Loop)
===============================================================================

WHY THIS MODULE EXISTS:
EventBus (see core/event_bus.py) is a plain synchronous pub/sub dispatcher --
it fans a cue payload out to whatever subscribers are registered, with no
opinion on what those subscribers do with it (print to console, drive an
LCD, etc.). WebBroadcaster is simply ONE such subscriber, dedicated
to the web audience: it turns each cue into Server-Sent Events for every
connected browser tab.

It exists as its own module (rather than living inside EventBus or the web
server) because of a threading wrinkle specific to browsers:
1. CueMatcher fires cues on the background Speech-to-Text thread via the
   synchronous EventBus.
2. FastAPI/Uvicorn -- and the asyncio event loop each browser's SSE
   connection depends on -- runs on the main thread.
3. asyncio.Queue is NOT thread-safe to write to from a different thread than
   the one running its event loop. WebBroadcaster.publish() is the
   one place that safely crosses that boundary, via
   event_loop.call_soon_threadsafe().

FUNCTIONAL OVERVIEW:
1. Each connected browser client registers its own asyncio.Queue (see
   register()). publish() is safe to call from ANY thread and enqueues the
   cue payload onto every registered client's queue.
2. Keeps a short replay history so an audience member who connects mid-scene
   immediately catches up on cues already triggered, instead of seeing a
   blank screen until the next line.
"""

import asyncio
import threading


class WebBroadcaster:
    def __init__(self):
        # Each entry: (asyncio.Queue, the asyncio event loop that queue's
        # owning SSE connection is running on)
        self._clients = []
        # Guards _clients / _history against concurrent access from the STT
        # thread (publish) and the web server's request-handling coroutines
        # (register/unregister), which may run on different threads.
        self._lock = threading.Lock()
        # Cues broadcast so far this session, replayed to newly joined clients
        self._history = []

    def register(self, event_loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        """
        Registers a new SSE client on the given event loop and replays any
        cues already triggered so far, so latecomers catch up immediately.

        Args:
            event_loop (asyncio.AbstractEventLoop): The running loop handling
                this client's request (obtained via asyncio.get_running_loop()
                inside the SSE endpoint, one per connected browser tab).

        Returns:
            asyncio.Queue: Queue that will receive future cue payloads.
        """
        client_queue = asyncio.Queue()
        with self._lock:
            self._clients.append((client_queue, event_loop))
            backlog = list(self._history)
        for payload in backlog:
            client_queue.put_nowait(payload)
        return client_queue

    def unregister(self, client_queue: asyncio.Queue):
        """Removes a disconnected client's queue from the broadcast list."""
        with self._lock:
            self._clients = [
                (q, event_loop) for q, event_loop in self._clients if q is not client_queue
            ]

    def publish(self, payload: dict):
        """
        EventBus subscriber callback -- register this with event_bus.subscribe()
        to have every triggered cue reach connected browsers. Safe to call
        from any thread (in production this is invoked on the Speech-to-Text
        worker thread whenever a cue fires).

        Args:
            payload (dict): Standardized cue payload from CueMatcher.
        """
        with self._lock:
            self._history.append(payload)
            clients = list(self._clients)

        for client_queue, event_loop in clients:
            # Hand off to each client's own event loop instead of touching
            # the asyncio.Queue directly from this (non-event-loop) thread.
            event_loop.call_soon_threadsafe(client_queue.put_nowait, payload)


# Global singleton instance shared between main.py/dev_server.py (subscribes
# it to the EventBus) and web/server.py (registers/reads from it per SSE
# connection).
web_broadcaster = WebBroadcaster()
