# CLAUDE.md — OTA Demonstrator

## What this project is

An OTA (Over-The-Air) update demonstrator for embedded Linux devices using an A/B partition scheme.
The primary target is a Raspberry Pi, but the agent is portable to any Linux device with two root partitions.

### Key components

| Component | Location | Purpose |
|---|---|---|
| OTA Agent | `agent/` | Python daemon that runs on the device, listens for MQTT update notifications, downloads and writes firmware |
| Build scripts | `infrastructure/scripts/` | Package creation, signing, upload |
| Infrastructure | `infrastructure/infrastructure/docker/` | Docker Compose stack (MQTT, MinIO, hawkBit, etc.) |

---

## Architecture

### A/B partition flow

```
Build server                    MQTT broker              Device (Raspberry Pi)
─────────────────               ────────────             ───────────────────────
1. dd if=/dev/mmcblk0p3         4. trigger-update.py     5. agent.py receives
   of=rootfs.img                   publishes notify          MQTT notification
2. build-image-package.sh       ──────────────────►      6. verify RSA sig on
   → .swu CPIO archive                                       sw-description
3. sign-package.sh                                       7. stream image chunks
   → -signed.swu                                            → inactive partition
4. upload-to-minio.sh                                    8. switch boot partition
   → MinIO storage                                       9. reboot into new image
```

### MQTT topics

| Topic | Direction | Purpose |
|---|---|---|
| `ota/devices/{id}/update/notify` | server → device | trigger update |
| `ota/devices/broadcast/update/notify` | server → all | broadcast update |
| `ota/devices/{id}/update/ack` | device → server | accepted / rejected |
| `ota/devices/{id}/status` | device → server | state transitions |
| `ota/devices/{id}/heartbeat` | device → server | periodic heartbeat |

### Update payload (MQTT message)

```json
{
  "message_id": "<uuid>",
  "version": "2.0.0",
  "package_url": "http://192.168.178.46:9000/updates/ota-rootfs-image-2.0.0-signed.swu",
  "package_sha256": "<sha256 of whole .swu>",
  "hardware_compatibility": ["raspberrypi"]
}
```

---

## .swu package format

A `.swu` is a CPIO archive (newc/crc format). Entry order matters:

```
[sw-description]        ← libconfig manifest, must be first
[sw-description.sig]    ← RSA-4096 PKCS1v15/SHA-256 signature of sw-description
[rootfs.img]            ← raw partition image (single file, < 3.9 GiB)
   OR
[rootfs.img.part-aaa]   ← chunk 0 (≥ 3.9 GiB images are split)
[rootfs.img.part-aab]   ← chunk 1
...
```

`sw-description` libconfig format (single image):
```
software = {
    version = "2.0.0";
    hardware-compatibility = ["raspberrypi"];
    images: ({
        filename = "rootfs.img";
        type = "rawimage";
        chunk_index = 0;
        offset = 0;
        sha256 = "<sha256 of rootfs.img>";
    });
}
```

Chunked packages include `offset = <byte offset in original image>` per chunk so the agent can seek before writing each one.

---

## Agent internals

### Install strategies

**`StreamToPartitionStrategy`** (default, `install_strategy: stream_to_partition`):
- Streams the `.swu` HTTP response and parses CPIO on-the-fly — no temp files
- Reads `sw-description` → extracts image filename + sha256 per chunk
- Reads `sw-description.sig` → verifies RSA-4096 signature **before** any write
- For each image chunk: `dev.seek(offset)`, stream bytes to block device, verify sha256
- Both single-image and chunked packages are handled transparently

**`MerkleStrategy`** (`install_strategy: merkle`):
- Fetches `manifest.json` (built by `build-merkle-manifest.py`) from same URL directory
- Verifies RSA signature on the Merkle root hash
- Downloads each 4 KB block via HTTP Range requests, verifies leaf hash before writing
- Strongest integrity guarantee: trust is established before anything lands on disk

### State machine

`IDLE → DOWNLOADING → INSTALLING → SUCCESS` (or `ERROR` on any failure, then back to `IDLE`)

### Simulation mode

Set `simulation_mode: true` in `config.yaml`. The strategy still runs (writes to `target_partition`) but the boot partition switch and reboot are skipped. For safe simulation set:
```yaml
agent:
  simulation_mode: true
  target_partition: /tmp/ota-sim-partition
```
Create the sim target with: `truncate -s 500M /tmp/ota-sim-partition`

---

## Infrastructure services (Docker Compose)

```
docker compose -f infrastructure/infrastructure/docker/docker-compose.yml up -d
```

| Service | Port | Purpose |
|---|---|---|
| Mosquitto (MQTT) | 1883 | Device communication |
| MinIO | 9000 / 9001 | Package storage (S3-compatible) |
| hawkBit | 8080 | Update campaign management UI |
| PostgreSQL | 5432 | hawkBit backend DB |
| RabbitMQ | 5672 / 15672 | hawkBit message bus |
| Redis | 6379 | Session cache |

Default credentials in `.env.example` — copy to `.env` before first run.

---

## Key files

| File | Purpose |
|---|---|
| `agent/agent.py` | Entry point, wires MQTT → state machine → strategy |
| `agent/strategies.py` | `StreamToPartitionStrategy`, `MerkleStrategy`, CPIO stream parser |
| `agent/verifier.py` | `PackageVerifier` — CPIO parser for file-based verification |
| `agent/installer.py` | `detect_inactive_partition()`, boot partition switch, reboot |
| `agent/config.py` | `AgentConfig` dataclass, YAML + env var loading |
| `agent/config.yaml` | Device configuration (broker, keys, strategy, target partition) |
| `infrastructure/scripts/build-image-package.sh` | Build `.swu` from raw partition image (chunks if ≥ 3.9 GiB) |
| `infrastructure/scripts/build-real-package.sh` | Legacy: build `.swu` from rootfs tarball |
| `infrastructure/scripts/sign-package.sh` | Add `sw-description.sig` to a `.swu` |
| `infrastructure/scripts/upload-to-minio.sh` | Upload signed package to MinIO |
| `infrastructure/scripts/trigger-update.py` | Send MQTT update notification from host |
| `infrastructure/scripts/generate-keys.sh` | Generate RSA-4096 key pair |

---

## Running the agent

```bash
cd agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# On Raspberry Pi (real partition write requires root):
sudo .venv/bin/python agent.py
```

Config can be overridden via environment variables (`OTA_DEVICE_ID`, `OTA_MQTT_BROKER_HOST`, `OTA_INSTALL_STRATEGY`, `OTA_TARGET_PARTITION`, etc.) — see `agent/config.py` for the full list.

---

## Triggering an update from the host

```bash
cd infrastructure/scripts
python trigger-update.py \
  --broker 192.168.178.46 \
  --url http://192.168.178.46:9000/updates/ota-rootfs-image-2.0.0-signed.swu \
  --sha256 <sha256> \
  --version 2.0.0
```

---

## Building a package (end-to-end)

```bash
# 1. On the Pi — dump the inactive partition to a raw image
sudo dd if=/dev/mmcblk0p3 bs=4M status=progress of=/tmp/rootfs.img

# 2. On build host — transfer
rsync -avz --progress pi@<ip>:/tmp/rootfs.img ./

# 3. Build .swu (auto-chunks if ≥ 3.9 GiB)
./infrastructure/scripts/build-image-package.sh rootfs.img 2.0.0

# 4. Sign
./infrastructure/scripts/sign-package.sh output/ota-rootfs-image-2.0.0.swu

# 5. Upload
./infrastructure/scripts/upload-to-minio.sh output/ota-rootfs-image-2.0.0-signed.swu

# 6. Trigger
python infrastructure/scripts/trigger-update.py \
  --url http://localhost:9000/updates/ota-rootfs-image-2.0.0-signed.swu \
  --sha256 <sha256> \
  --version 2.0.0
```

---

## Security model

- RSA-4096 key pair generated by `generate-keys.sh`; private key stays on build host, public key is deployed to device at `security.public_key_path` in `config.yaml`
- `sw-description` is RSA-signed (PKCS1v15 / SHA-256); the agent verifies the signature before writing a single byte to the inactive partition
- Per-chunk SHA-256 is verified after each chunk write; a mismatch aborts immediately — the partition is dirty but still inactive, so a retry is safe
- Hardware compatibility is checked before accepting any update notification

---

## Raspberry Pi A/B partition layout (reference)

```
/dev/mmcblk0p1  boot firmware  (FAT32)
/dev/mmcblk0p2  rootfs A       ← active (current boot)
/dev/mmcblk0p3  rootfs B       ← inactive (OTA writes here)
```

`detect_inactive_partition()` in `installer.py` reads `/proc/cmdline` to find the active PARTUUID and derives the inactive one automatically.
