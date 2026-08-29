"""
===============================================================================
MODULE: event_bus.py
ROLE  : Decoupled Publish-Subscribe Event Dispatcher (Observer Pattern)
===============================================================================

FUNCTIONAL OVERVIEW:
1. Receives matched cue payloads from the recognition engine.
2. Fan-outs cue events to all registered listeners (Terminal, Web, MCU)
   without coupling recognition logic to delivery mechanisms.
3. Isolates subscriber execution errors so one failing output channel
   does not crash the rest of the application.

ADDING A NEW OUTPUT CHANNEL:
EventBus doesn't know or care what a subscriber does with a cue -- it just
calls it with the payload dict. To add a new delivery channel (e.g. an LCD
screen), write a plain function taking one dict argument and register it:

    def lcd_subscriber(payload: dict):
        lcd.write(payload["english"][:16])

    event_bus.subscribe(lcd_subscriber)

See console_logger() below for a working example, and web/broadcaster.py's
WebBroadcaster.publish() for a subscriber that bridges into another
thread/event loop (needed for web browser delivery specifically -- most
subscribers, like an LCD, don't need anything that involved).
"""

class EventBus:
    def __init__(self):
        # Internal registry storing active callback functions
        self._subscribers = []

    def subscribe(self, callback_func):
        """
        Registers a new function listener to receive live cue events.
        
        Args:
            callback_func (callable): Function taking a single 'dict' payload.
        """
        self._subscribers.append(callback_func)

    def emit_cue(self, cue_payload: dict):
        """
        Iterates over all registered listeners and delivers the cue payload.
        
        Args:
            cue_payload (dict): Standardized dictionary containing line ID,
                                spoken text, match type, and translations.
        """
        for callback in self._subscribers:
            try:
                # Dispatch payload to subscriber execution context
                callback(cue_payload)
            except Exception as err:
                # Prevent subscriber crashes from interrupting other output streams
                print(f"[EVENT_BUS ERROR] Listener '{callback.__name__}' failed: {err}", flush=True)


# Global singleton instance used throughout the app life cycle
event_bus = EventBus()


# =============================================================================
# DEFAULT SUBSCRIBER: CONSOLE PRINT LOGGING
# =============================================================================
def console_logger(payload: dict):
    """
    Subscriber Callback: Formats and prints triggered cue data to standard output.
    """
    print(f"\n\n{'='*65}", flush=True)
    print(f"  [CUE TRIGGERED - {payload['match_type']}] -> Line #{payload['line_id']} ({payload['scene_id']})", flush=True)
    print(f"  Actor       : {payload['actor']}", flush=True)
    print(f"  English     : {payload['english']}", flush=True)
    
    if payload.get("spanish_translation"):
        print(f"  Spanish     : {payload['spanish_translation']}", flush=True)
    if payload.get("chinese_translation"):
        print(f"  Chinese     : {payload['chinese_translation']}", flush=True)
        
    print(f"{'='*65}\n", flush=True)


# Automatically attach the console logging subscriber when module loads
event_bus.subscribe(console_logger)