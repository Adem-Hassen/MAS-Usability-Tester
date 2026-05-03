import threading
from typing import Callable, Optional

class EventBus:
    """Thread-safe event emission for pipeline → SSE bridge."""
    _instance: Optional["EventBus"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._handlers: list[Callable] = []
    
    @classmethod
    def get(cls) -> "EventBus":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    def subscribe(self, handler: Callable[[str, dict], None]):
        self._handlers.append(handler)
    
    def unsubscribe_all(self):
        self._handlers.clear()

    def emit(self, event_type: str, **payload):
        for handler in self._handlers:
            try:
                handler(event_type, payload)
            except Exception:
                pass
