#!/usr/bin/env python3
"""
trigger-update.py - Send an OTA update notification to the agent via MQTT.

Usage:
    python trigger-update.py --url <package_url> --sha256 <sha256> --version <version>

Examples:
    # Stream-to-partition update
    python trigger-update.py \
        --url http://192.168.178.10:9000/updates/v2.0/rootfs.img \
        --sha256 abc123... \
        --version 2.0.0

    # Broadcast to all devices
    python trigger-update.py --broadcast \
        --url http://192.168.178.10:9000/updates/v2.0/rootfs.img \
        --sha256 abc123... \
        --version 2.0.0

    # Override broker and device ID
    python trigger-update.py \
        --broker 192.168.178.10 \
        --device-id rpi-002 \
        --url http://... --sha256 ... --version 2.0.0
"""

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Defaults — mirror config.yaml
# ---------------------------------------------------------------------------
DEFAULT_BROKER      = "localhost"
DEFAULT_PORT        = 1883
DEFAULT_DEVICE_ID   = "rpi-001"
DEFAULT_HW_COMPAT   = []   # empty = accept all hardware


def compute_sha256(path: str) -> str:
    """Compute SHA-256 of a local file (convenience helper, not used in publish)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def publish_notification(
    broker: str,
    port: int,
    topic: str,
    payload: dict,
) -> None:
    connected = False
    published = False
    error = None

    def on_connect(client, userdata, flags, rc, properties=None):
        nonlocal connected
        if rc == 0:
            connected = True
        else:
            nonlocal error
            error = f"MQTT connect failed with code {rc}"

    def on_publish(client, userdata, mid, *args):
        nonlocal published
        published = True

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_publish  = on_publish

    print(f"Connecting to MQTT broker {broker}:{port} ...")
    try:
        client.connect(broker, port, keepalive=10)
    except Exception as e:
        print(f"ERROR: Cannot connect to broker: {e}", file=sys.stderr)
        sys.exit(1)

    client.loop_start()

    # Wait for connection
    import time
    for _ in range(50):
        if connected or error:
            break
        time.sleep(0.1)

    if error or not connected:
        print(f"ERROR: {error or 'timeout connecting to broker'}", file=sys.stderr)
        client.loop_stop()
        sys.exit(1)

    message = json.dumps(payload)
    result = client.publish(topic, message, qos=1)
    result.wait_for_publish(timeout=5)

    client.loop_stop()
    client.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description="Send an OTA update notification to the agent via MQTT.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Required
    parser.add_argument("--url",     required=True, help="Package URL (MinIO/S3 URL the agent will download from)")
    parser.add_argument("--sha256",  required=True, help="SHA-256 hex digest of the package file")
    parser.add_argument("--version", required=True, help="Version string (e.g. 2.0.0)")

    # Optional
    parser.add_argument("--broker",    default=DEFAULT_BROKER,    help=f"MQTT broker hostname (default: {DEFAULT_BROKER})")
    parser.add_argument("--port",      default=DEFAULT_PORT, type=int, help=f"MQTT broker port (default: {DEFAULT_PORT})")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help=f"Target device ID (default: {DEFAULT_DEVICE_ID})")
    parser.add_argument("--broadcast", action="store_true",        help="Send to broadcast topic (all devices)")
    parser.add_argument("--hw",        nargs="*", default=[],      help="Hardware compatibility list (e.g. --hw raspberrypi rpi4)")
    parser.add_argument("--message-id", default=None,             help="Custom message ID (default: random UUID)")

    # Convenience: compute sha256 from a local file instead of typing it
    parser.add_argument("--file",    default=None, help="Local file to compute SHA-256 from (overrides --sha256)")

    args = parser.parse_args()

    # Compute sha256 from local file if provided
    if args.file:
        if not Path(args.file).exists():
            print(f"ERROR: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        print(f"Computing SHA-256 of {args.file} ...")
        sha256 = compute_sha256(args.file)
        print(f"  SHA-256: {sha256}")
    else:
        sha256 = args.sha256

    message_id = args.message_id or str(uuid.uuid4())

    # Build topic
    if args.broadcast:
        topic = "ota/devices/broadcast/update/notify"
    else:
        topic = f"ota/devices/{args.device_id}/update/notify"

    # Build payload — must match what agent._on_update_notify() expects
    payload = {
        "message_id":             message_id,
        "version":                args.version,
        "package_url":            args.url,
        "package_sha256":         sha256,
        "hardware_compatibility": args.hw,
    }

    # Print summary
    print()
    print("=" * 60)
    print("OTA Update Notification")
    print("=" * 60)
    print(f"  Broker     : {args.broker}:{args.port}")
    print(f"  Topic      : {topic}")
    print(f"  Message ID : {message_id}")
    print(f"  Version    : {args.version}")
    print(f"  URL        : {args.url}")
    print(f"  SHA-256    : {sha256}")
    print(f"  HW compat  : {args.hw or '(any)'}")
    print()

    publish_notification(args.broker, args.port, topic, payload)

    print(f"Published to {topic}")
    print()
    print("Watch the agent logs on the device for:")
    print(f"  Update notification received: version={args.version}")


if __name__ == "__main__":
    main()
