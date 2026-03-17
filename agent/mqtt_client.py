"""
mqtt_client.py - MQTT connection management and topic dispatch.

Subscribes to:
  ota/devices/{device_id}/update/notify  - Device-specific update notifications
  ota/devices/broadcast/update/notify    - Broadcast updates for all devices

Publishes via publish().
"""

import json
import logging
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from config import AgentConfig

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(
        self,
        config: AgentConfig,
        on_update_notify: Callable[[dict], None],
    ) -> None:
        self._config = config
        self._on_update_notify = on_update_notify
        self._client = mqtt.Client(
            client_id=f"ota-agent-{config.device_id}",
            protocol=mqtt.MQTTv311,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(
            min_delay=config.mqtt_reconnect_delay_min,
            max_delay=config.mqtt_reconnect_delay_max,
        )
        self._connected = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:
        host = self._config.mqtt_broker_host
        port = self._config.mqtt_broker_port
        logger.info("Connecting to MQTT broker %s:%d ...", host, port)
        self._client.connect(host, port, keepalive=self._config.mqtt_keepalive)
        self._client.loop_start()

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("Disconnected from MQTT broker")

    def publish(
        self,
        topic: str,
        payload: dict,
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        msg = json.dumps(payload)
        result = self._client.publish(topic, msg, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("Failed to publish to %s (rc=%d)", topic, result.rc)
        else:
            logger.debug("Published to %s: %s", topic, msg)

    # ------------------------------------------------------------------
    # paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            logger.error("MQTT connection failed: rc=%d", rc)
            return

        logger.info("Connected to MQTT broker (rc=%d)", rc)
        self._connected = True

        device_id = self._config.device_id
        qos = self._config.mqtt_qos

        # Subscribe to device-specific and broadcast topics
        topics = [
            (f"ota/devices/{device_id}/update/notify", qos),
            ("ota/devices/broadcast/update/notify", qos),
        ]
        client.subscribe(topics)
        for topic, _ in topics:
            logger.info("Subscribed to %s (QoS %d)", topic, qos)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        if rc == 0:
            logger.info("MQTT disconnected cleanly")
        else:
            logger.warning("MQTT disconnected unexpectedly (rc=%d), will reconnect", rc)

    def _on_message(self, client, userdata, msg) -> None:
        logger.info("Message received on %s", msg.topic)
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Failed to parse MQTT message: %s", e)
            return

        required = {"message_id", "version", "package_url", "package_sha256"}
        missing = required - payload.keys()
        if missing:
            logger.error("Update notification missing required fields: %s", missing)
            return

        self._on_update_notify(payload)
