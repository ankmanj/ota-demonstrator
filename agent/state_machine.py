"""
state_machine.py - OTA agent state management.

Valid state transitions:
  IDLE → DOWNLOADING → VERIFYING → INSTALLING → REBOOTING → SUCCESS → IDLE
  Any state → ERROR → IDLE
"""

import enum
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class UpdateState(enum.Enum):
    IDLE = "IDLE"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    INSTALLING = "INSTALLING"
    REBOOTING = "REBOOTING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


# Which transitions are legal
_ALLOWED_TRANSITIONS: dict[UpdateState, set[UpdateState]] = {
    UpdateState.IDLE: {UpdateState.DOWNLOADING},
    UpdateState.DOWNLOADING: {UpdateState.VERIFYING, UpdateState.ERROR},
    UpdateState.VERIFYING: {UpdateState.INSTALLING, UpdateState.ERROR},
    UpdateState.INSTALLING: {UpdateState.REBOOTING, UpdateState.ERROR},
    UpdateState.REBOOTING: {UpdateState.SUCCESS, UpdateState.ERROR},
    UpdateState.SUCCESS: {UpdateState.IDLE},
    UpdateState.ERROR: {UpdateState.IDLE},
}


class StateMachine:
    def __init__(self) -> None:
        self._state = UpdateState.IDLE
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []
        self.active_message_id: Optional[str] = None
        self.target_version: Optional[str] = None

    @property
    def current_state(self) -> UpdateState:
        return self._state

    def is_busy(self) -> bool:
        """Return True when an update is in progress (not IDLE or ERROR)."""
        return self._state not in (UpdateState.IDLE, UpdateState.ERROR)

    def on_transition(self, callback: Callable[[UpdateState, UpdateState, dict], None]) -> None:
        """Register a listener called on every state change."""
        self._callbacks.append(callback)

    def transition(self, new_state: UpdateState, **context) -> None:
        """
        Transition to new_state. Raises ValueError for illegal transitions.
        context kwargs are passed to registered callbacks.
        """
        with self._lock:
            old_state = self._state
            allowed = _ALLOWED_TRANSITIONS.get(old_state, set())
            if new_state not in allowed:
                raise ValueError(
                    f"Illegal state transition: {old_state.value} → {new_state.value}. "
                    f"Allowed: {[s.value for s in allowed]}"
                )
            self._state = new_state
            logger.info("State: %s → %s", old_state.value, new_state.value)

        for cb in self._callbacks:
            try:
                cb(old_state, new_state, context)
            except Exception:
                logger.exception("Error in state transition callback")
