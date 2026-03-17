"""
swupdate_sim.py - Simulated SWUpdate and A/B partition switch.

Every step that real SWUpdate would perform is logged with a [SIMULATED] prefix
so the complete update flow is visible and educational without requiring SWUpdate
to be installed or a real Raspberry Pi.

On a real Raspberry Pi, this module would be replaced by:
  subprocess.run(["swupdate", "-i", str(swu_path), "-k", public_key_path])
"""

import logging
import re
import time
from pathlib import Path
from typing import Callable, Optional

from config import AgentConfig

logger = logging.getLogger(__name__)

# PARTUUID suffixes for A/B partitions (as set up during repartitioning)
_PARTITION_A_SUFFIX = "02"
_PARTITION_B_SUFFIX = "03"
_CMDLINE_PATH = "/boot/firmware/cmdline.txt"


class SWUpdateSimulator:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def run(
        self,
        swu_path: Path,
        sw_description: dict,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        Simulate a complete SWUpdate installation.

        Returns True on success.
        progress_cb(current_step, total_steps) is called between steps.
        """
        version = sw_description.get("version", "unknown")
        hw_compat = sw_description.get("hardware_compatibility", [])
        total_steps = 7
        step = 0

        def advance(n=1):
            nonlocal step
            step += n
            if progress_cb:
                progress_cb(step, total_steps)

        logger.info("=" * 60)
        logger.info("[SIMULATED] SWUpdate: Starting installation of version %s", version)
        logger.info("=" * 60)

        self._step_parse_sw_description(sw_description)
        advance()

        active, inactive, active_partuuid, inactive_partuuid = self._step_detect_partitions()
        advance()

        self._step_mount_inactive_partition(inactive, inactive_partuuid)
        advance()

        self._step_install_images(sw_description, swu_path, progress_cb=None)
        advance()

        self._step_update_version_marker(inactive, version)
        advance()

        self._step_unmount_partition(inactive)
        advance()

        self._step_switch_boot_partition(
            active, inactive, active_partuuid, inactive_partuuid
        )
        self._step_simulate_reboot(inactive, inactive_partuuid, version)
        advance()

        logger.info("=" * 60)
        logger.info("[SIMULATED] SWUpdate: Installation COMPLETE. New version: %s", version)
        logger.info("=" * 60)
        return True

    # ------------------------------------------------------------------
    # Individual simulation steps
    # ------------------------------------------------------------------

    def _step_parse_sw_description(self, sw_description: dict) -> None:
        version = sw_description.get("version", "unknown")
        hw_compat = sw_description.get("hardware_compatibility", [])
        raw = sw_description.get("raw", "")
        image_count = raw.count("images:")  # rough count

        logger.info("[SIMULATED] SWUpdate: Parsing sw-description")
        logger.info("[SIMULATED]   version              : %s", version)
        logger.info("[SIMULATED]   hardware-compatibility: %s", hw_compat)
        logger.info("[SIMULATED]   Manifest valid, proceeding with install")

    def _step_detect_partitions(self) -> tuple[str, str, str, str]:
        """
        Detect active/inactive partition. Returns (active, inactive, active_partuuid, inactive_partuuid).
        """
        partuuid_base = None
        active_suffix = None

        try:
            cmdline = Path("/proc/cmdline").read_text()
            m = re.search(r"root=PARTUUID=([\w-]+)", cmdline)
            if m:
                full_partuuid = m.group(1)
                parts = full_partuuid.rsplit("-", 1)
                if len(parts) == 2:
                    partuuid_base = parts[0]
                    active_suffix = parts[1]
        except OSError:
            pass

        if partuuid_base and active_suffix:
            if active_suffix == _PARTITION_A_SUFFIX:
                active, inactive = "A", "B"
                inactive_suffix = _PARTITION_B_SUFFIX
            else:
                active, inactive = "B", "A"
                inactive_suffix = _PARTITION_A_SUFFIX
            active_partuuid = f"{partuuid_base}-{active_suffix}"
            inactive_partuuid = f"{partuuid_base}-{inactive_suffix}"
            source = f"/proc/cmdline (PARTUUID={active_partuuid})"
        else:
            # Development machine - use mock values
            active, inactive = "A", "B"
            partuuid_base = "51fdec2f"
            active_partuuid = f"{partuuid_base}-{_PARTITION_A_SUFFIX}"
            inactive_partuuid = f"{partuuid_base}-{_PARTITION_B_SUFFIX}"
            source = "[DEV MODE] Not running on Raspberry Pi, using mock partition values"

        logger.info("[SIMULATED] SWUpdate: Detecting partitions")
        logger.info("[SIMULATED]   Source               : %s", source)
        logger.info("[SIMULATED]   Active partition      : %s (PARTUUID=%s)", active, active_partuuid)
        logger.info("[SIMULATED]   Inactive partition    : %s (PARTUUID=%s) ← UPDATE TARGET", inactive, inactive_partuuid)

        return active, inactive, active_partuuid, inactive_partuuid

    def _step_mount_inactive_partition(self, inactive: str, partuuid: str) -> None:
        dev = "/dev/mmcblk0p3" if inactive == "B" else "/dev/mmcblk0p2"
        mount_point = "/mnt/swupdate-target"

        logger.info("[SIMULATED] SWUpdate: Mounting inactive partition %s", inactive)
        logger.info("[SIMULATED]   Device               : %s (PARTUUID=%s)", dev, partuuid)
        logger.info("[SIMULATED]   Mount point          : %s", mount_point)
        logger.info("[SIMULATED]   Checking disk space  : ~2.1 GB available, ~0.5 GB needed")
        logger.info("[SIMULATED]   Command would be     : mount %s %s", dev, mount_point)
        logger.info("[SIMULATED]   (SKIPPED: running in simulation mode)")

    def _step_install_images(
        self,
        sw_description: dict,
        swu_path: Path,
        progress_cb: Optional[Callable],
    ) -> None:
        raw = sw_description.get("raw", "")
        version = sw_description.get("version", "unknown")

        # Extract image names from sw-description (simple regex approach)
        import re as _re
        filenames = _re.findall(r'filename\s*=\s*"([^"]+)"', raw)
        if not filenames:
            filenames = ["rootfs.tar.gz"]  # default fallback

        logger.info("[SIMULATED] SWUpdate: Installing %d image(s)", len(filenames))
        for i, filename in enumerate(filenames, 1):
            logger.info("[SIMULATED]   Image %d/%d: %s", i, len(filenames), filename)
            logger.info("[SIMULATED]     Extracting from .swu CPIO archive...")
            logger.info("[SIMULATED]     Verifying SHA-256 checksum...")
            logger.info("[SIMULATED]     SHA-256 OK")
            logger.info("[SIMULATED]     Writing to /mnt/swupdate-target/ ...")
            logger.info("[SIMULATED]     (SKIPPED: running in simulation mode)")
            if progress_cb:
                progress_cb(i, len(filenames))

    def _step_update_version_marker(self, inactive: str, version: str) -> None:
        logger.info("[SIMULATED] SWUpdate: Updating version markers on inactive partition")
        for marker_path in [
            "/mnt/swupdate-target/etc/rootfs-version",
            "/mnt/swupdate-target/etc/ota-demo/version.txt",
        ]:
            logger.info("[SIMULATED]   echo '%s' > %s", version, marker_path)
        logger.info("[SIMULATED]   (SKIPPED: running in simulation mode)")

    def _step_unmount_partition(self, inactive: str) -> None:
        logger.info("[SIMULATED] SWUpdate: Unmounting inactive partition %s", inactive)
        logger.info("[SIMULATED]   sync  # flush all pending writes to disk")
        logger.info("[SIMULATED]   umount /mnt/swupdate-target")
        logger.info("[SIMULATED]   (SKIPPED: running in simulation mode)")

    def _step_switch_boot_partition(
        self,
        active: str,
        inactive: str,
        active_partuuid: str,
        inactive_partuuid: str,
    ) -> None:
        logger.info("[SIMULATED] SWUpdate: *** PARTITION SWITCH ***")
        logger.info("[SIMULATED]   Switching boot from partition %s → %s", active, inactive)
        logger.info("[SIMULATED]   File to modify: %s", _CMDLINE_PATH)

        # Show current cmdline if on a real Pi
        try:
            current = Path("/proc/cmdline").read_text().strip()
            logger.info("[SIMULATED]   Current /proc/cmdline: %s", current)
        except OSError:
            logger.info("[SIMULATED]   Current /proc/cmdline: [not available in DEV MODE]")
            current = f"console=serial0,115200 root=PARTUUID={active_partuuid} rootfstype=ext4 rootwait"

        new_cmdline = current.replace(active_partuuid, inactive_partuuid)
        logger.info("[SIMULATED]   New cmdline would be  : %s", new_cmdline)
        logger.info(
            "[SIMULATED]   Command would be      : sed -i 's/PARTUUID=%s/PARTUUID=%s/' %s",
            active_partuuid, inactive_partuuid, _CMDLINE_PATH,
        )
        logger.info("[SIMULATED]   Syncing boot partition...")
        logger.info("[SIMULATED]   (SKIPPED: running in simulation mode)")

    def _step_simulate_reboot(self, inactive: str, inactive_partuuid: str, version: str) -> None:
        dev = "/dev/mmcblk0p3" if inactive == "B" else "/dev/mmcblk0p2"

        logger.info("[SIMULATED] *** REBOOT SEQUENCE ***")
        logger.info("[SIMULATED]   Scheduling reboot in 5 seconds...")
        logger.info("[SIMULATED]   (In real system: sudo shutdown -r +0)")
        logger.info("[SIMULATED]")
        logger.info("[SIMULATED]   Boot sequence after reboot would be:")
        logger.info("[SIMULATED]   1. GPU firmware reads /boot/firmware/config.txt")
        logger.info("[SIMULATED]      → Loads kernel8.img into memory")
        logger.info("[SIMULATED]   2. GPU firmware reads /boot/firmware/cmdline.txt")
        logger.info("[SIMULATED]      → Passes parameters to kernel")
        logger.info("[SIMULATED]      → root=PARTUUID=%s  ← NOW POINTS TO PARTITION %s", inactive_partuuid, inactive)
        logger.info("[SIMULATED]   3. Kernel initialises, scans for PARTUUID=%s", inactive_partuuid)
        logger.info("[SIMULATED]      → Found: %s", dev)
        logger.info("[SIMULATED]   4. Kernel mounts %s as root /", dev)
        logger.info("[SIMULATED]   5. systemd starts from new partition %s", inactive)
        logger.info("[SIMULATED]   6. OTA agent starts, reads /etc/rootfs-version → '%s'", version)
        logger.info("[SIMULATED]   7. Agent publishes SUCCESS status to MQTT")
        logger.info("[SIMULATED]")
        logger.info("[SIMULATED]   If boot fails 3 times → watchdog reverts cmdline.txt")
        logger.info("[SIMULATED]   (real watchdog not implemented in this demonstrator)")
        logger.info("[SIMULATED]")

        # Dramatic pause so the user can read the logs
        time.sleep(2)

        logger.info("[SIMULATED] *** Update complete. New version: %s ***", version)
