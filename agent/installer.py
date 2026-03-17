"""
installer.py - Real OTA package installer for Raspberry Pi A/B partition updates.

Replaces swupdate_sim.py when simulation_mode = false in config.yaml.

What it does (for real, not simulated):
  1. Detects active/inactive partition from /proc/cmdline
  2. Mounts inactive partition at /mnt/ota-update
  3. Extracts rootfs.tar.gz from the .swu CPIO archive into inactive partition
  4. Writes version marker
  5. Unmounts inactive partition
  6. Updates /boot/firmware/cmdline.txt to point to inactive partition
  7. Reboots

Requirements on Raspberry Pi:
  - Agent must run as root (sudo python3 agent.py)
  - OR configure passwordless sudo for specific commands in /etc/sudoers:
      ankith0073 ALL=(ALL) NOPASSWD: /bin/mount, /bin/umount, /bin/tar, /sbin/reboot, /bin/sed

Partitions expected:
  - mmcblk0p1 : /boot/firmware (FAT32)
  - mmcblk0p2 : rootfs-A      (ext4, PARTUUID suffix -02)
  - mmcblk0p3 : rootfs-B      (ext4, PARTUUID suffix -03)
"""

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from config import AgentConfig

logger = logging.getLogger(__name__)

_MOUNT_POINT    = "/mnt/ota-update"
_CMDLINE_PATH   = "/boot/firmware/cmdline.txt"
_PART_A_DEV     = "/dev/mmcblk0p2"
_PART_B_DEV     = "/dev/mmcblk0p3"
_PART_A_SUFFIX  = "02"
_PART_B_SUFFIX  = "03"


class InstallError(Exception):
    pass


def detect_inactive_partition() -> tuple:
    """
    Module-level helper: read /proc/cmdline to find the active PARTUUID and
    derive the inactive partition.

    Returns (active_dev, inactive_dev, active_partuuid, inactive_partuuid).
    Raises InstallError if the partition layout is not as expected.

    Used by both RealInstaller and the streaming install strategies in agent.py.
    """
    try:
        cmdline = Path("/proc/cmdline").read_text()
    except OSError as e:
        raise InstallError(f"Cannot read /proc/cmdline: {e}")

    m = re.search(r"root=PARTUUID=([\w-]+)", cmdline)
    if not m:
        raise InstallError(
            "Cannot find root=PARTUUID= in /proc/cmdline. "
            "Is this a Raspberry Pi with A/B partitions?"
        )

    active_partuuid = m.group(1)
    parts = active_partuuid.rsplit("-", 1)
    if len(parts) != 2:
        raise InstallError(f"Unexpected PARTUUID format: {active_partuuid}")

    base, suffix = parts
    if suffix == _PART_A_SUFFIX:
        active_dev      = _PART_A_DEV
        inactive_dev    = _PART_B_DEV
        inactive_suffix = _PART_B_SUFFIX
        active_label    = "A"
        inactive_label  = "B"
    elif suffix == _PART_B_SUFFIX:
        active_dev      = _PART_B_DEV
        inactive_dev    = _PART_A_DEV
        inactive_suffix = _PART_A_SUFFIX
        active_label    = "B"
        inactive_label  = "A"
    else:
        raise InstallError(
            f"Unexpected PARTUUID suffix '{suffix}'. "
            f"Expected '{_PART_A_SUFFIX}' (partition A) or '{_PART_B_SUFFIX}' (partition B)."
        )

    inactive_partuuid = f"{base}-{inactive_suffix}"

    logger.info("Partition detection:")
    logger.info("  Active   : partition %s (%s, PARTUUID=%s)",
                active_label, active_dev, active_partuuid)
    logger.info("  Inactive : partition %s (%s, PARTUUID=%s) ← UPDATE TARGET",
                inactive_label, inactive_dev, inactive_partuuid)

    return active_dev, inactive_dev, active_partuuid, inactive_partuuid


class RealInstaller:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def run(
        self,
        swu_path: Path,
        sw_description: dict,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        Perform a real OTA installation onto the inactive partition.
        Returns True on success. Raises InstallError on failure.
        """
        version = sw_description.get("version", "unknown")

        logger.info("=" * 60)
        logger.info("RealInstaller: Starting REAL installation of version %s", version)
        logger.info("=" * 60)

        _, inactive_dev, active_partuuid, inactive_partuuid = \
            self._detect_partitions()

        self._mount_inactive(inactive_dev)
        try:
            self._extract_rootfs(swu_path, progress_cb)
            self._write_version_marker(version)
        finally:
            # Always unmount, even if extraction failed
            self._unmount()

        self._switch_boot_partition(active_partuuid, inactive_partuuid)
        self._reboot(version, inactive_dev)
        return True

    # ------------------------------------------------------------------
    # Step 1: Detect partitions
    # ------------------------------------------------------------------

    def _detect_partitions(self) -> tuple:
        """Delegates to module-level detect_inactive_partition()."""
        return detect_inactive_partition()

    # ------------------------------------------------------------------
    # Step 2: Mount inactive partition
    # ------------------------------------------------------------------

    def _mount_inactive(self, device: str) -> None:
        mount_point = Path(_MOUNT_POINT)
        mount_point.mkdir(parents=True, exist_ok=True)

        # Unmount first if already mounted (leftover from previous failed attempt)
        if self._is_mounted(_MOUNT_POINT):
            logger.warning("Mount point %s already in use, unmounting first...", _MOUNT_POINT)
            self._run(["umount", _MOUNT_POINT])

        logger.info("Mounting %s at %s ...", device, _MOUNT_POINT)
        self._run(["mount", device, _MOUNT_POINT])
        logger.info("Mounted successfully")

        # Check available disk space
        stat = os.statvfs(_MOUNT_POINT)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        logger.info("Disk space available on inactive partition: %.1f GB", free_gb)
        if free_gb < 1.0:
            raise InstallError(
                f"Not enough disk space on inactive partition: {free_gb:.1f} GB free, need at least 1 GB"
            )

    # ------------------------------------------------------------------
    # Step 3: Extract rootfs from .swu
    # ------------------------------------------------------------------

    def _extract_rootfs(
        self,
        swu_path: Path,
        progress_cb: Optional[Callable],
    ) -> None:
        """
        Extract rootfs from inside the .swu CPIO archive, then untar it into
        the inactive partition mount point.

        Supports both single-file and chunked packages:
        - Single: contains 'rootfs.tar.gz'
        - Chunked: contains 'rootfs.tar.gz.part-aaa', 'rootfs.tar.gz.part-aab', ...
          (created by build-real-package.sh when rootfs > 3.9 GB to avoid the
          CPIO newc 4 GB per-file size limit)
        """
        logger.info("Extracting rootfs from %s ...", swu_path.name)

        # Detect whether this is a chunked package
        all_names = self._list_cpio_files(swu_path)
        chunk_names = sorted(n for n in all_names if n.startswith("rootfs.tar.gz.part-"))

        rootfs_tar = Path(_MOUNT_POINT) / ".ota_rootfs.tar.gz"

        if chunk_names:
            # --- Chunked package ---
            logger.info(
                "Step 1/2: Chunked package detected (%d parts). Extracting and reassembling...",
                len(chunk_names),
            )
            with open(rootfs_tar, "wb") as out:
                for i, cname in enumerate(chunk_names):
                    logger.info("  Extracting chunk %d/%d: %s", i + 1, len(chunk_names), cname)
                    self._extract_from_cpio(swu_path, cname, out)
            logger.info(
                "  Reassembled rootfs.tar.gz: %.1f MB", rootfs_tar.stat().st_size / (1024 ** 2)
            )
        else:
            # --- Single-file package ---
            logger.info("Step 1/2: Extracting rootfs.tar.gz from CPIO archive...")
            with open(rootfs_tar, "wb") as out:
                self._extract_from_cpio(swu_path, "rootfs.tar.gz", out)
            logger.info(
                "  rootfs.tar.gz extracted: %.1f MB", rootfs_tar.stat().st_size / (1024 ** 2)
            )

        # Wipe the inactive partition contents before writing
        logger.info("Step 2/2: Clearing inactive partition...")
        self._run(["find", _MOUNT_POINT, "-mindepth", "1",
                   "-not", "-name", ".ota_rootfs.tar.gz", "-delete"])

        # Extract the rootfs tarball into the mount point
        logger.info("Step 2/2: Extracting rootfs into %s ...", _MOUNT_POINT)
        logger.info("  This may take several minutes for a full rootfs...")

        self._run([
            "tar", "-xzf", str(rootfs_tar),
            "-C", _MOUNT_POINT,
            "--numeric-owner",      # preserve original uid/gid numbers
        ])

        # Clean up the temp tar file
        rootfs_tar.unlink(missing_ok=True)
        logger.info("Rootfs extracted successfully")

        if progress_cb:
            progress_cb(1, 1)

    def _list_cpio_files(self, swu_path: Path) -> list[str]:
        """Return a list of all filenames present in the CPIO archive."""
        _NEWC_MAGIC = b"070701"
        _CRC_MAGIC  = b"070702"
        _TRAILER    = "TRAILER!!!"

        names: list[str] = []
        with open(swu_path, "rb") as src:
            while True:
                header = src.read(110)
                if len(header) < 110:
                    break

                magic = header[:6]
                if magic not in (_NEWC_MAGIC, _CRC_MAGIC):
                    break  # Not a valid CPIO entry — stop scanning

                namesize = int(header[94:102], 16)
                filesize = int(header[54:62], 16)

                name_raw = src.read(namesize)
                name = name_raw.rstrip(b"\x00").decode("ascii", errors="replace")

                pad = (110 + namesize) % 4
                if pad:
                    src.read(4 - pad)

                if name == _TRAILER:
                    break

                names.append(name)

                # Skip file data
                src.seek(filesize, 1)
                pad = filesize % 4
                if pad:
                    src.seek(4 - pad, 1)

        return names

    def _extract_from_cpio(self, swu_path: Path, target_name: str, out) -> None:
        """
        Extract a single named file from a CPIO archive, writing its bytes into
        the already-open file object 'out'.  Parses CPIO newc headers manually.
        """
        _NEWC_MAGIC = b"070701"
        _CRC_MAGIC  = b"070702"
        _TRAILER    = "TRAILER!!!"

        with open(swu_path, "rb") as src:
            while True:
                header = src.read(110)
                if len(header) < 110:
                    break

                magic = header[:6]
                if magic not in (_NEWC_MAGIC, _CRC_MAGIC):
                    raise InstallError(f"Invalid CPIO magic: {magic!r}")

                namesize = int(header[94:102], 16)
                filesize = int(header[54:62], 16)

                name_raw = src.read(namesize)
                name = name_raw.rstrip(b"\x00").decode("ascii", errors="replace")

                # Align to 4-byte boundary after (110 + namesize)
                pad = (110 + namesize) % 4
                if pad:
                    src.read(4 - pad)

                if name == _TRAILER:
                    break

                if name == target_name:
                    remaining = filesize
                    while remaining > 0:
                        chunk = src.read(min(65536, remaining))
                        if not chunk:
                            break
                        out.write(chunk)
                        remaining -= len(chunk)
                    return  # Found and extracted, done

                # Skip this file's data
                src.seek(filesize, 1)
                pad = filesize % 4
                if pad:
                    src.seek(4 - pad, 1)

        raise InstallError(
            f"'{target_name}' not found in CPIO archive. "
            "Was this package built with build-real-package.sh?"
        )

    # ------------------------------------------------------------------
    # Step 4: Write version marker
    # ------------------------------------------------------------------

    def _write_version_marker(self, version: str) -> None:
        marker_dir = Path(_MOUNT_POINT) / "etc" / "ota-demo"
        marker_dir.mkdir(parents=True, exist_ok=True)

        marker = marker_dir / "version.txt"
        marker.write_text(f"{version}\n")
        logger.info("Version marker written: %s → %s", marker, version)

        rootfs_version = Path(_MOUNT_POINT) / "etc" / "rootfs-version"
        rootfs_version.write_text(f"{version}\n")
        logger.info("Rootfs version written: %s → %s", rootfs_version, version)

    # ------------------------------------------------------------------
    # Step 5: Unmount
    # ------------------------------------------------------------------

    def _unmount(self) -> None:
        logger.info("Syncing filesystem writes...")
        self._run(["sync"])
        logger.info("Unmounting %s ...", _MOUNT_POINT)
        self._run(["umount", _MOUNT_POINT])
        logger.info("Unmounted successfully")

    # ------------------------------------------------------------------
    # Step 6: Switch boot partition
    # ------------------------------------------------------------------

    def _switch_boot_partition(
        self, active_partuuid: str, inactive_partuuid: str
    ) -> None:
        cmdline_path = Path(_CMDLINE_PATH)
        if not cmdline_path.exists():
            raise InstallError(f"cmdline.txt not found at {_CMDLINE_PATH}")

        original = cmdline_path.read_text().strip()
        if active_partuuid not in original:
            raise InstallError(
                f"Active PARTUUID {active_partuuid} not found in cmdline.txt. "
                f"Current content: {original}"
            )

        updated = original.replace(active_partuuid, inactive_partuuid)

        # Backup current cmdline.txt before modifying
        backup = cmdline_path.with_suffix(".txt.bak")
        backup.write_text(original)
        logger.info("Backed up cmdline.txt → %s", backup)

        # Write new cmdline.txt
        cmdline_path.write_text(updated + "\n")
        self._run(["sync"])

        logger.info("cmdline.txt updated:")
        logger.info("  Before : %s", original)
        logger.info("  After  : %s", updated)
        logger.info("  Backup : %s", backup)

    # ------------------------------------------------------------------
    # Step 7: Reboot
    # ------------------------------------------------------------------

    def _reboot(self, version: str, inactive_dev: str) -> None:
        logger.info("=" * 60)
        logger.info("Installation complete. Rebooting in 5 seconds...")
        logger.info("  New version    : %s", version)
        logger.info("  Will boot from : %s", inactive_dev)
        logger.info("  Boot sequence  :")
        logger.info("    1. GPU firmware reads /boot/firmware/cmdline.txt")
        logger.info("    2. Kernel mounts %s as root /", inactive_dev)
        logger.info("    3. systemd starts from new partition")
        logger.info("    4. OTA agent starts, reports SUCCESS via MQTT")
        logger.info("=" * 60)

        time.sleep(5)
        self._run(["reboot"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess:
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise InstallError(
                f"Command failed: {' '.join(cmd)}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
        return result

    def _is_mounted(self, path: str) -> bool:
        result = subprocess.run(["mountpoint", "-q", path])
        return result.returncode == 0
