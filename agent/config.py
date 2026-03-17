"""
config.py - Configuration loading for the OTA update agent.

Priority (highest to lowest):
  1. OTA_* environment variables
  2. config.yaml values
  3. Hardcoded defaults
"""

import enum
import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class InstallStrategy(enum.Enum):
    STREAM_TO_PARTITION  = "stream_to_partition"   # stream directly to inactive partition, SHA-256 at end
    MERKLE               = "merkle"                # Merkle hash tree, block-level verify before write


@dataclass
class AgentConfig:
    # Device identity
    device_id: str = "rpi-001"
    hardware_id: str = "raspberrypi"
    current_version: str = "0.0.0"

    # MQTT broker
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_keepalive: int = 60
    mqtt_reconnect_delay_min: int = 1
    mqtt_reconnect_delay_max: int = 60
    mqtt_qos: int = 1

    # MinIO / package storage
    minio_base_url: str = "http://localhost:9000"
    minio_bucket: str = "updates"

    # Security
    public_key_path: str = "../infrastructure/scripts/keys/swupdate-pub.pem"

    # Agent behaviour
    heartbeat_interval_seconds: int = 30
    simulation_mode: bool = True

    # Install strategy (stream_to_partition | merkle)
    install_strategy: InstallStrategy = InstallStrategy.STREAM_TO_PARTITION
    # Block device written to by the active strategy
    target_partition: str = "/dev/mmcblk0p2"

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None


def load_config(config_path: str = "config.yaml") -> AgentConfig:
    """Load configuration from YAML file, then overlay OTA_* environment variables."""
    cfg = AgentConfig()

    # --- Load YAML ---
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        _apply_yaml(cfg, raw)
        logger.debug("Loaded config from %s", path)
    else:
        logger.warning("Config file %s not found, using defaults", path)

    # --- Overlay environment variables ---
    _apply_env(cfg)

    # --- Validate ---
    _validate(cfg)

    return cfg


def _apply_yaml(cfg: AgentConfig, raw: dict) -> None:
    device = raw.get("device", {})
    cfg.device_id = device.get("id", cfg.device_id)
    cfg.hardware_id = device.get("hardware_id", cfg.hardware_id)
    cfg.current_version = device.get("current_version", cfg.current_version)

    mqtt = raw.get("mqtt", {})
    cfg.mqtt_broker_host = mqtt.get("broker_host", cfg.mqtt_broker_host)
    cfg.mqtt_broker_port = int(mqtt.get("broker_port", cfg.mqtt_broker_port))
    cfg.mqtt_keepalive = int(mqtt.get("keepalive", cfg.mqtt_keepalive))
    cfg.mqtt_reconnect_delay_min = int(mqtt.get("reconnect_delay_min", cfg.mqtt_reconnect_delay_min))
    cfg.mqtt_reconnect_delay_max = int(mqtt.get("reconnect_delay_max", cfg.mqtt_reconnect_delay_max))
    cfg.mqtt_qos = int(mqtt.get("qos", cfg.mqtt_qos))

    minio = raw.get("minio", {})
    cfg.minio_base_url = minio.get("base_url", cfg.minio_base_url).rstrip("/")
    cfg.minio_bucket = minio.get("bucket", cfg.minio_bucket)

    security = raw.get("security", {})
    cfg.public_key_path = security.get("public_key_path", cfg.public_key_path)

    agent = raw.get("agent", {})
    cfg.heartbeat_interval_seconds = int(agent.get("heartbeat_interval_seconds", cfg.heartbeat_interval_seconds))
    cfg.simulation_mode = bool(agent.get("simulation_mode", cfg.simulation_mode))
    raw_strategy = agent.get("install_strategy", cfg.install_strategy.value)
    try:
        cfg.install_strategy = InstallStrategy(raw_strategy)
    except ValueError:
        raise ConfigError(
            f"Unknown install_strategy '{raw_strategy}'. "
            f"Valid values: {[s.value for s in InstallStrategy]}"
        )
    cfg.target_partition = agent.get("target_partition", cfg.target_partition)

    logging_cfg = raw.get("logging", {})
    cfg.log_level = logging_cfg.get("level", cfg.log_level).upper()
    cfg.log_file = logging_cfg.get("file", cfg.log_file)


def _apply_env(cfg: AgentConfig) -> None:
    """Override config values from OTA_* environment variables."""
    env_map = {
        "OTA_DEVICE_ID": ("device_id", str),
        "OTA_HARDWARE_ID": ("hardware_id", str),
        "OTA_CURRENT_VERSION": ("current_version", str),
        "OTA_MQTT_BROKER_HOST": ("mqtt_broker_host", str),
        "OTA_MQTT_BROKER_PORT": ("mqtt_broker_port", int),
        "OTA_MINIO_BASE_URL": ("minio_base_url", str),
        "OTA_MINIO_BUCKET": ("minio_bucket", str),
        "OTA_PUBLIC_KEY_PATH": ("public_key_path", str),
        "OTA_LOG_LEVEL": ("log_level", str),
        "OTA_LOG_FILE": ("log_file", str),
        "OTA_TARGET_PARTITION": ("target_partition", str),
    }
    strategy_env = os.environ.get("OTA_INSTALL_STRATEGY")
    if strategy_env is not None:
        try:
            cfg.install_strategy = InstallStrategy(strategy_env)
        except ValueError:
            raise ConfigError(
                f"OTA_INSTALL_STRATEGY='{strategy_env}' is invalid. "
                f"Valid values: {[s.value for s in InstallStrategy]}"
            )
    for env_key, (attr, cast) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            setattr(cfg, attr, cast(val))
            logger.debug("Config override from env: %s=%s", env_key, val)


def _validate(cfg: AgentConfig) -> None:
    if not cfg.device_id:
        raise ConfigError("device_id must not be empty")
    if not (1 <= cfg.mqtt_broker_port <= 65535):
        raise ConfigError(f"Invalid MQTT port: {cfg.mqtt_broker_port}")
    key_path = Path(cfg.public_key_path)
    if not key_path.exists():
        raise ConfigError(
            f"Public key not found at '{key_path.resolve()}'. "
            "Run infrastructure/scripts/generate-keys.sh first."
        )
