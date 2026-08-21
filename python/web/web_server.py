"""
===============================================================================
MODULE: web_server.py
ROLE  : Audience Caption Streaming Web Server (Stub / Preparation)
===============================================================================

FUNCTIONAL OVERVIEW:
1. Provides thread entry point for web server hosting audience pages.
2. Exposes subscriber function registered with EventBus to broadcast live cue
   updates to browser clients via WebSockets or Server-Sent Events (SSE).
"""

import json

def start_caption_server(host="0.0.0.0", port=8080):
    """
    Target function for background thread running web server.
    
    Args:
        host (str): Interface binding address (0.0.0.0 binds all interfaces).
        port (int): Port for HTTP connection.
    """
    print(f"[WEB SERVER] Caption endpoint ready at http://{host}:{port}", flush=True)


def web_broadcast_subscriber(payload: dict):
    """
    EventBus Subscriber Callback: Prepares cue dictionary for web output.
    
    Args:
        payload (dict): Triggered cue payload from CueMatcher.
    """
    # Serialize payload dictionary to JSON string format for streaming
    json_data = json.dumps(payload)
    
    # Placeholder: Broadcast json_data across active HTTP SSE or WebSocket connections
    pass