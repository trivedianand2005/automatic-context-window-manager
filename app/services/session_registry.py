"""Per-visitor service isolation for the public API.

Each browser session sends an opaque ``X-ACWM-Session`` id. Every id gets its own
``ACWMService`` (its own index store and run history), so one visitor can never see
or evict another visitor's indexed repositories. Sessions are kept in memory with an
LRU cap; the least recently used session is dropped when the cap is reached.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict

from app.core.config import Settings
from app.core.exceptions import ACWMError
from app.services.acwm_service import ACWMService

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class InvalidSessionError(ACWMError):
    code = "invalid_session"
    http_status = 400


class SessionRegistry:
    def __init__(self, settings: Settings, max_sessions: int = 200) -> None:
        self.settings = settings
        self.max_sessions = max_sessions
        self._services: OrderedDict[str, ACWMService] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, session_id: str) -> ACWMService:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise InvalidSessionError(
                "X-ACWM-Session must be 8-64 characters of letters, digits or '-'."
            )
        with self._lock:
            service = self._services.get(session_id)
            if service is None:
                service = ACWMService(self.settings)
                self._services[session_id] = service
            self._services.move_to_end(session_id)
            while len(self._services) > self.max_sessions:
                self._services.popitem(last=False)
            return service

    def __len__(self) -> int:
        with self._lock:
            return len(self._services)
