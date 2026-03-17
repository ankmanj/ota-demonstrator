"""
agent.py - OTA Update Agent entry point.

Usage:
    python agent.py [--config config.yaml] [--device-id rpi-001] [--broker localhost]

Environment variable overrides (highest priority):
    OTA_DEVICE_ID, OTA_MQTT_BROKER_HOST, OTA_LOG_LEVEL, ...  (see config.py)

MQTT topics:
    Subscribe: ota/devices/{device_id}/update/notify
    Subscribe: ota/devices/broadcast/update/notify
    Publish:   ota/devices/{device_id}/status
    Publish:   ota/devices/{device_id}/update/ack
    Publish:   ota/devices/{device_id}/heartbeat
"""

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

from config import AgentConfig, ConfigError, InstallStrategy, load_config
from mqtt_client import MQTTClient
from reporter import StatusReporter
from state_machine import StateMachine, UpdateState
from installer import InstallError, RealInstaller, detect_inactive_partition
from verifier import PackageVerifier
from strategies import MerkleStrategy, StrategyError, StreamToPartitionStrategy


def setup_logging(config: AgentConfig) -> None:
    level = getattr(logging, config.log_level, logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if config.log_file:
        try:
            handlers.append(logging.FileHandler(config.log_file))
        except OSError as e:
            print(f"WARNING: Cannot open log file {config.log_file}: {e}", file=sys.stderr)
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


logger = logging.getLogger(__name__)


class OTAAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._state_machine = StateMachine()
        self._reporter: Optional[StatusReporter] = None
        self._mqtt: Optional[MQTTClient] = None
        self._verifier = PackageVerifier(config)
        self._installer = RealInstaller(config)
        self._strategy = self._build_strategy(config)
        self._shutdown_event = threading.Event()

    def _build_strategy(self, config: AgentConfig):
        if config.install_strategy == InstallStrategy.MERKLE:
            logger.info("Install strategy: Merkle (block-level verify before write)")
            return MerkleStrategy(self._verifier._public_key, config)
        logger.info("Install strategy: StreamToPartition (CPIO-aware, RSA sig + SHA-256 from sw-description)")
        return StreamToPartitionStrategy(self._verifier._public_key, config)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        cfg = self._config
        logger.info("=" * 60)
        logger.info("OTA Agent starting")
        logger.info("  Device ID    : %s", cfg.device_id)
        logger.info("  Hardware ID  : %s", cfg.hardware_id)
        logger.info("  Version      : %s", cfg.current_version)
        logger.info("  MQTT broker  : %s:%d", cfg.mqtt_broker_host, cfg.mqtt_broker_port)
        logger.info("  MinIO        : %s/%s", cfg.minio_base_url, cfg.minio_bucket)
        logger.info("  Public key   : %s", Path(cfg.public_key_path).resolve())
        logger.info("  Mode         : %s", "SIMULATION" if cfg.simulation_mode else "REAL (will write to partition + reboot)")
        logger.info("  Strategy     : %s", cfg.install_strategy.value)
        if cfg.install_strategy.value != "temp_file":
            logger.info("  Target part  : %s", cfg.target_partition)
        logger.info("=" * 60)

        # Wire up MQTT client
        self._mqtt = MQTTClient(cfg, on_update_notify=self._on_update_notify)

        # Wire up status reporter
        self._reporter = StatusReporter(self._mqtt, cfg.device_id, cfg.current_version)

        # Register state transition → publish status
        self._state_machine.on_transition(self._reporter.publish_status)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        # Connect and start MQTT loop in background thread
        self._mqtt.connect()

        # Start periodic heartbeat
        self._reporter.start_heartbeat_loop(cfg.heartbeat_interval_seconds)

        logger.info("OTA Agent running. Waiting for update notifications...")
        logger.info("Send a test notification with:")
        logger.info(
            "  mosquitto_pub -h %s -p %d -t 'ota/devices/%s/update/notify' -m '<json>'",
            cfg.mqtt_broker_host, cfg.mqtt_broker_port, cfg.device_id,
        )

        # Block main thread until shutdown signal
        self._shutdown_event.wait()

    def shutdown(self) -> None:
        logger.info("Shutting down OTA agent...")
        if self._reporter:
            self._reporter.stop_heartbeat_loop()
        if self._mqtt:
            self._mqtt.disconnect()
        self._shutdown_event.set()

    def _handle_signal(self, signum, frame) -> None:
        logger.info("Received signal %d, shutting down...", signum)
        self.shutdown()

    # ------------------------------------------------------------------
    # Update pipeline
    # ------------------------------------------------------------------

    def _on_update_notify(self, message: dict) -> None:
        """Called by MQTTClient when an update notification arrives."""
        msg_id = message.get("message_id", "unknown")
        version = message.get("version", "unknown")
        logger.info("Update notification received: version=%s, message_id=%s", version, msg_id)

        if self._state_machine.is_busy():
            logger.warning("Update in progress, rejecting new notification (message_id=%s)", msg_id)
            self._reporter.publish_ack(msg_id, "rejected", reason="update_in_progress")
            return

        hw_compat = message.get("hardware_compatibility", [])
        if hw_compat and self._config.hardware_id not in hw_compat:
            logger.warning(
                "Hardware mismatch: device='%s', package supports %s",
                self._config.hardware_id, hw_compat,
            )
            self._reporter.publish_ack(msg_id, "rejected", reason="hardware_incompatible")
            return

        if version == self._config.current_version:
            logger.info("Already on version %s, skipping update", version)
            self._reporter.publish_ack(msg_id, "rejected", reason="already_up_to_date")
            return

        self._reporter.publish_ack(msg_id, "accepted")
        self._state_machine.active_message_id = msg_id
        self._state_machine.target_version = version

        # Run the update in a daemon thread to not block MQTT callbacks
        t = threading.Thread(
            target=self._run_update,
            args=(message,),
            daemon=True,
            name=f"ota-update-{msg_id}",
        )
        t.start()

    def _run_update(self, message: dict) -> None:
        """
        Streaming pipeline: download + write directly to the inactive partition.
        Used by both StreamToPartitionStrategy and MerkleStrategy.

        After the strategy writes the image, we switch the boot partition and
        reboot — same final steps as the temp-file path.

        In simulation_mode the partition write and reboot are skipped (the
        strategy still runs, but target_partition should be set to a safe path
        like /tmp/ota-sim-partition in config.yaml).
        """
        version          = message["version"]
        url              = message["package_url"]
        expected_sha256  = message["package_sha256"]

        try:
            self._state_machine.transition(
                UpdateState.DOWNLOADING,
                target_version=version,
                details=f"Streaming to inactive partition from {url}",
            )

            if self._config.simulation_mode:
                target_partition = self._config.target_partition
                logger.info(
                    "SIMULATION: strategy.execute() target=%s (no real device write)",
                    target_partition,
                )
            else:
                _, inactive_dev, active_partuuid, inactive_partuuid = \
                    detect_inactive_partition()
                target_partition = inactive_dev

            self._strategy.execute(
                url,
                expected_sha256,
                target_partition,
                progress_cb=lambda done, total: self._on_download_progress(done, total, version),
            )

            self._state_machine.transition(
                UpdateState.INSTALLING,
                target_version=version,
                details="Image written; switching boot partition",
            )

            if not self._config.simulation_mode:
                self._installer._switch_boot_partition(active_partuuid, inactive_partuuid)
                self._installer._reboot(version, inactive_dev)
                # Real mode: reboot() does not return
            else:
                logger.info("SIMULATION: would switch boot to %s and reboot", target_partition)

            self._state_machine.transition(
                UpdateState.SUCCESS,
                target_version=version,
                details=f"Successfully installed version {version}",
            )
            if self._reporter:
                self._reporter.update_current_version(version)
            self._config.current_version = version

        except StrategyError as e:
            logger.error("Strategy failed: %s", e)
            self._transition_error(version, "STRATEGY_FAILED", str(e))

        except InstallError as e:
            logger.error("Partition switch failed: %s", e)
            self._transition_error(version, "INSTALL_FAILED", str(e))

        except Exception as e:
            logger.exception("Unexpected error during streaming update")
            self._transition_error(version, "UNEXPECTED_ERROR", str(e))

        finally:
            try:
                self._state_machine.transition(UpdateState.IDLE)
            except ValueError:
                pass
            self._state_machine.active_message_id = None
            self._state_machine.target_version = None

    def _transition_error(self, version: str, code: str, message: str) -> None:
        try:
            self._state_machine.transition(
                UpdateState.ERROR,
                target_version=version,
                error={"code": code, "message": message},
            )
        except ValueError:
            logger.warning("Could not transition to ERROR from %s", self._state_machine.current_state)

    def _on_download_progress(self, downloaded: int, total: int, version: str) -> None:
        pct = int(downloaded / total * 100) if total else 0
        # Only publish at 0%, 25%, 50%, 75%, 100% to avoid flooding MQTT
        if pct % 25 == 0 or downloaded == total:
            if self._reporter:
                self._reporter.publish_status(
                    UpdateState.DOWNLOADING, UpdateState.DOWNLOADING,
                    {"target_version": version, "progress_percent": pct,
                     "details": f"Downloaded {downloaded:,} / {total:,} bytes"},
                )



# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OTA Update Agent - listens for MQTT update notifications and installs packages"
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--device-id", help="Override device ID from config")
    parser.add_argument("--broker", help="Override MQTT broker hostname")
    parser.add_argument("--version", help="Override current device version")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Apply CLI overrides
    if args.device_id:
        config.device_id = args.device_id
    if args.broker:
        config.mqtt_broker_host = args.broker
    if args.version:
        config.current_version = args.version

    setup_logging(config)

    agent = OTAAgent(config)
    agent.start()


if __name__ == "__main__":
    main()
