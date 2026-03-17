"""
verifier.py - Package signature verification for .swu OTA packages.

A .swu file is a CPIO archive (newc format) where:
  - The FIRST entry must be "sw-description"  (the package manifest)
  - The SECOND entry must be "sw-description.sig" (raw RSA-4096 PKCS1v15/SHA-256 signature)

This matches the output of sign-package.sh:
  openssl dgst -sha256 -sign <private.pem> -out sw-description.sig sw-description

Verification:
  public_key.verify(sig_bytes, sw_desc_bytes, PKCS1v15(), SHA256())
"""

import logging
import struct
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

from config import AgentConfig

logger = logging.getLogger(__name__)

# CPIO newc magic numbers
_CPIO_NEWC_MAGIC = b"070701"
_CPIO_CRC_MAGIC = b"070702"
_CPIO_TRAILER = "TRAILER!!!"


class VerificationError(Exception):
    pass


class PackageVerifier:
    def __init__(self, config: AgentConfig) -> None:
        key_path = Path(config.public_key_path)
        logger.info("Loading RSA public key from %s", key_path)
        with open(key_path, "rb") as f:
            self._public_key = serialization.load_pem_public_key(f.read())
        logger.info("RSA public key loaded successfully")

    def verify(self, swu_path: Path) -> dict:
        """
        Verify .swu package signature. Returns parsed sw-description metadata.

        Raises VerificationError on any problem.
        """
        logger.info("Extracting sw-description and signature from %s", swu_path.name)
        sw_desc_bytes, sig_bytes = self._extract_from_cpio(swu_path)

        logger.info("Verifying RSA-4096 signature (%d bytes)...", len(sig_bytes))
        self._verify_rsa_signature(sw_desc_bytes, sig_bytes)
        logger.info("RSA-4096 signature VALID")

        metadata = self._parse_sw_description(sw_desc_bytes)
        return metadata

    def check_hardware_compatibility(self, hw_list: list, device_hw_id: str) -> bool:
        """Return True if device is compatible (empty list = accept all)."""
        if not hw_list:
            return True
        compatible = device_hw_id in hw_list
        if not compatible:
            logger.warning(
                "Hardware mismatch: device is '%s', package supports %s",
                device_hw_id, hw_list,
            )
        return compatible

    # ------------------------------------------------------------------
    # CPIO parsing (newc format, stdlib only)
    # ------------------------------------------------------------------

    def _extract_from_cpio(self, swu_path: Path) -> tuple[bytes, bytes]:
        """
        Parse the CPIO archive and return (sw-description bytes, signature bytes).

        CPIO newc header format (110 bytes, all ASCII hex):
          magic[6] ino[8] mode[8] uid[8] gid[8] nlink[8] mtime[8]
          filesize[8] devmajor[8] devminor[8] rdevmajor[8] rdevminor[8]
          namesize[8] check[8]
        Followed by: filename (namesize bytes, null-terminated)
        Padded to 4-byte boundary, then file data, padded to 4-byte boundary.
        """
        sw_description: Optional[bytes] = None
        sw_sig: Optional[bytes] = None

        with open(swu_path, "rb") as f:
            while True:
                header = f.read(110)
                if len(header) < 110:
                    break

                magic = header[:6]
                if magic not in (_CPIO_NEWC_MAGIC, _CPIO_CRC_MAGIC):
                    raise VerificationError(
                        f"Invalid CPIO magic: {magic!r}. Expected 070701 or 070702."
                    )

                namesize = int(header[94:102], 16)
                filesize = int(header[54:62], 16)

                # Read filename (namesize includes null terminator)
                name_raw = f.read(namesize)
                name = name_raw.rstrip(b"\x00").decode("ascii", errors="replace")

                # Align to 4-byte boundary after (110 + namesize)
                _skip_padding(f, (110 + namesize) % 4)

                if name == _CPIO_TRAILER:
                    break

                # Read file data
                data = f.read(filesize)
                _skip_padding(f, filesize % 4)

                if name == "sw-description":
                    sw_description = data
                    logger.debug("Found sw-description (%d bytes)", len(data))
                elif name == "sw-description.sig":
                    sw_sig = data
                    logger.debug("Found sw-description.sig (%d bytes)", len(data))

                if sw_description is not None and sw_sig is not None:
                    break  # Got what we need

        if sw_description is None:
            raise VerificationError(
                "sw-description not found in CPIO archive. "
                "Is this a valid .swu package?"
            )
        if sw_sig is None:
            raise VerificationError(
                "sw-description.sig not found in CPIO archive. "
                "Package has not been signed. Run sign-package.sh first."
            )

        return sw_description, sw_sig

    # ------------------------------------------------------------------
    # RSA signature verification
    # ------------------------------------------------------------------

    def _verify_rsa_signature(self, message: bytes, signature: bytes) -> None:
        try:
            self._public_key.verify(
                signature,
                message,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature as e:
            raise VerificationError(
                "RSA signature verification FAILED. "
                "Package may be tampered or signed with a different key."
            ) from e

    # ------------------------------------------------------------------
    # sw-description parsing (libconfig format, minimal parser)
    # ------------------------------------------------------------------

    def _parse_sw_description(self, sw_desc_bytes: bytes) -> dict:
        """
        Extract version and hardware-compatibility from sw-description.
        sw-description is in libconfig format. We do a simple key search
        rather than a full parser since this is a demonstrator.
        """
        text = sw_desc_bytes.decode("utf-8", errors="replace")
        metadata: dict = {
            "version": _extract_libconfig_string(text, "version"),
            "hardware_compatibility": _extract_libconfig_list(text, "hardware-compatibility"),
            "raw": text,
        }
        logger.info(
            "Package metadata: version=%s, hardware=%s",
            metadata["version"],
            metadata["hardware_compatibility"],
        )
        return metadata


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _skip_padding(f, remainder: int) -> None:
    if remainder != 0:
        f.read(4 - remainder)


def _extract_libconfig_string(text: str, key: str) -> Optional[str]:
    """Find 'key = "value"' in libconfig text."""
    import re
    pattern = rf'{re.escape(key)}\s*=\s*"([^"]*)"'
    m = re.search(pattern, text)
    return m.group(1) if m else None


def _extract_libconfig_list(text: str, key: str) -> list:
    """Find 'key = ["a", "b"]' in libconfig text."""
    import re
    pattern = rf'{re.escape(key)}\s*=\s*\[([^\]]*)\]'
    m = re.search(pattern, text)
    if not m:
        return []
    items = re.findall(r'"([^"]*)"', m.group(1))
    return items
