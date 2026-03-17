"""
reporter.py - Publishes device status and heartbeat messages back to MQTT.

Topics:
  ota/devices/{device_id}/status      - State transitions and progress
  ota/devices/{device_id}/update/ack  - Acknowledge a received notification
  ota/devices/{device_id}/heartbeat   - Periodic liveness signal
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from state_machine import UpdateState

logger = logging.getLogger(__name__)


class StatusReporter:
    def __init__(self, mqtt_client, device_id: str, current_version: str) -> None:
        self._mqtt = mqtt_client
        self._device_id = device_id
        self._current_version = current_version
        self._heartbeat_timer: Optional[threading.Timer] = None
        self._active_partition = self._detect_active_partition()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish_status(
        self,
        old_state: UpdateState,
        new_state: UpdateState,
        context: dict,
    ) -> None:
        """Called by StateMachine on every transition."""
        payload = {
            "device_id": self._device_id,
            "timestamp": _now(),
            "state": new_state.value,
            "progress_percent": context.get("progress_percent", 0),
            "current_version": self._current_version,
            "target_version": context.get("target_version"),
            "details": context.get("details", ""),
            "error": context.get("error"),
        }
        topic = f"ota/devices/{self._device_id}/status"
        self._mqtt.publish(topic, payload, qos=1)

    def publish_ack(self, message_id: str, action: str, reason: Optional[str] = None) -> None:
        """Acknowledge receipt of an update notification."""
        payload = {
            "message_id": message_id,
            "device_id": self._device_id,
            "acknowledged_at": _now(),
            "action": action,  # "accepted" or "rejected"
        }
        if reason:
            payload["reason"] = reason
        topic = f"ota/devices/{self._device_id}/update/ack"
        self._mqtt.publish(topic, payload, qos=1)

    def publish_heartbeat(self) -> None:
        payload = {
            "device_id": self._device_id,
            "timestamp": _now(),
            "current_version": self._current_version,
            "active_partition": self._active_partition,
            "uptime_seconds": int(time.monotonic()),
        }
        topic = f"ota/devices/{self._device_id}/heartbeat"
        self._mqtt.publish(topic, payload, qos=0)

    def update_current_version(self, version: str) -> None:
        self._current_version = version

    def start_heartbeat_loop(self, interval_seconds: int) -> None:
        self._heartbeat_interval = interval_seconds
        self._schedule_heartbeat()

    def stop_heartbeat_loop(self) -> None:
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _schedule_heartbeat(self) -> None:
        self.publish_heartbeat()
        self._heartbeat_timer = threading.Timer(
            self._heartbeat_interval, self._schedule_heartbeat
        )
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    def _detect_active_partition(self) -> str:
        """Read /proc/cmdline to determine whether we're on partition A or B."""
        try:
            cmdline = open("/proc/cmdline").read()
            if "PARTUUID=" in cmdline:
                for token in cmdline.split():
                    if token.startswith("root=PARTUUID="):
                        partuuid = token.split("=", 2)[2]
                        suffix = partuuid.split("-")[-1]
                        return "A" if suffix == "02" else "B"
        except Exception:
            pass
        return "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
