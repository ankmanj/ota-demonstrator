#!/usr/bin/env python3
"""
build-merkle-manifest.py - Generate a Merkle hash tree manifest for an OTA image.

Run this on your dev machine after creating a raw rootfs image, before uploading
to MinIO.  The agent's MerkleStrategy fetches this manifest first, verifies the
RSA signature on the root hash, then downloads and verifies each block before
writing it to the inactive partition.

Usage:
    python build-merkle-manifest.py <image_file> <private_key.pem>
    python build-merkle-manifest.py <image_file> <private_key.pem> --block-size 4096
    python build-merkle-manifest.py <image_file> <private_key.pem> --output /tmp/manifest.json

Output:
    <image_file>.manifest.json  (or path from --output)

    {
      "version": 1,
      "block_size": 4096,
      "block_count": 12345,
      "image_size_bytes": 50593792,
      "root_hash": "abcdef...",
      "root_hash_sig": "hex-encoded RSA-4096 PKCS1v15/SHA-256 signature",
      "blocks": [
        {"index": 0, "sha256": "..."},
        {"index": 1, "sha256": "..."},
        ...
      ]
    }

Upload both files to MinIO together:
    mc cp rootfs.img     minio/ota-packages/v2.0/rootfs.img
    mc cp manifest.json  minio/ota-packages/v2.0/manifest.json

The agent derives the manifest URL automatically from the image URL
(same directory, filename = manifest.json).

Merkle tree construction:
    - Leaf nodes  : SHA-256 of each block (last block is zero-padded to block_size)
    - Parent nodes: SHA-256( hex(left) + hex(right) )
    - Padding rule: if a level has an odd number of nodes, the last is duplicated
    - Root hash   : single node remaining after all levels are reduced
    This matches _build_merkle_root() in agent/strategies.py exactly.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def hash_blocks(image_path: Path, block_size: int) -> list:
    """
    Read the image in fixed-size blocks and compute SHA-256 for each.
    The last block is zero-padded to block_size if it is smaller.

    Returns a list of dicts: [{"index": 0, "sha256": "..."}, ...]
    """
    blocks = []
    image_size = image_path.stat().st_size
    total_blocks = (image_size + block_size - 1) // block_size

    with open(image_path, "rb") as f:
        idx = 0
        while True:
            data = f.read(block_size)
            if not data:
                break
            # Pad last block so every block is exactly block_size bytes.
            # The agent must apply the same padding when it fetches the last block.
            if len(data) < block_size:
                data = data + b"\x00" * (block_size - len(data))
            blocks.append({"index": idx, "sha256": hashlib.sha256(data).hexdigest()})
            idx += 1

            if idx % 2048 == 0:
                pct = idx / total_blocks * 100
                print(f"  Hashing blocks: {idx}/{total_blocks} ({pct:.0f}%)...", end="\r", flush=True)

    print(f"  Hashed {len(blocks)} blocks.                          ")
    return blocks


def build_merkle_root(leaf_hashes: list) -> str:
    """
    Build a Merkle tree bottom-up from a flat list of hex-encoded SHA-256 hashes.
    Returns the root hash as a hex string.

    Padding rule: when a level has an odd number of nodes, the last node is
    duplicated before pairing.  This must match _build_merkle_root() in
    agent/strategies.py exactly — any deviation will cause root hash mismatches.
    """
    if not leaf_hashes:
        raise ValueError("Cannot build Merkle tree from empty leaf list")

    level = list(leaf_hashes)
    depth = 0
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])   # duplicate last node
        next_level = []
        for i in range(0, len(level), 2):
            combined = (level[i] + level[i + 1]).encode()
            next_level.append(hashlib.sha256(combined).hexdigest())
        level = next_level
        depth += 1

    return level[0]


def sign_root_hash(root_hash: str, key_path: Path) -> str:
    """
    Sign the root_hash string with RSA private key using PKCS1v15 + SHA-256.
    Returns the signature as a lowercase hex string.

    This matches the verification in MerkleStrategy._verify_root_sig():
        public_key.verify(bytes.fromhex(sig_hex), root_hash.encode(),
                          PKCS1v15(), SHA256())
    """
    with open(key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    sig_bytes = private_key.sign(
        root_hash.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return sig_bytes.hex()


def whole_file_sha256(image_path: Path) -> str:
    """Compute SHA-256 of the entire image file (for the MQTT package_sha256 field)."""
    hasher = hashlib.sha256()
    with open(image_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build a Merkle hash tree manifest for an OTA raw image.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("image",       help="Raw image file (e.g. rootfs.img)")
    parser.add_argument("private_key", help="PEM private key used to sign the root hash")
    parser.add_argument(
        "--block-size", type=int, default=4096,
        help="Block size in bytes (default: 4096 — must match agent config)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output path for manifest.json (default: <image>.manifest.json)",
    )
    args = parser.parse_args()

    image_path   = Path(args.image)
    key_path     = Path(args.private_key)
    output_path  = Path(args.output) if args.output else image_path.with_suffix(".manifest.json")

    # --- Validate inputs ---
    if not image_path.exists():
        print(f"ERROR: image not found: {image_path}", file=sys.stderr)
        sys.exit(1)
    if not key_path.exists():
        print(f"ERROR: private key not found: {key_path}", file=sys.stderr)
        sys.exit(1)

    image_size   = image_path.stat().st_size
    total_blocks = (image_size + args.block_size - 1) // args.block_size

    print("=" * 60)
    print("OTA Merkle Manifest Builder")
    print("=" * 60)
    print(f"  Image      : {image_path}  ({image_size / (1024**2):.1f} MB)")
    print(f"  Block size : {args.block_size} bytes")
    print(f"  Blocks     : {total_blocks}")
    print(f"  Key        : {key_path}")
    print(f"  Output     : {output_path}")
    print()

    t0 = time.monotonic()

    # Step 1: Hash every block
    print("Step 1/4: Hashing blocks...")
    blocks = hash_blocks(image_path, args.block_size)

    # Step 2: Build Merkle tree
    print("Step 2/4: Building Merkle tree...")
    leaf_hashes = [b["sha256"] for b in blocks]
    root_hash   = build_merkle_root(leaf_hashes)
    print(f"  Root hash  : {root_hash}")

    # Step 3: Sign root hash
    print("Step 3/4: Signing root hash with RSA private key...")
    sig_hex = sign_root_hash(root_hash, key_path)
    print(f"  Signature  : {sig_hex[:48]}…")

    # Step 4: Compute whole-file SHA-256 (used in the MQTT notification message)
    print("Step 4/4: Computing whole-file SHA-256 (for MQTT package_sha256)...")
    file_sha256 = whole_file_sha256(image_path)
    print(f"  File SHA-256: {file_sha256}")

    # Assemble manifest
    manifest = {
        "version":          1,
        "block_size":       args.block_size,
        "block_count":      len(blocks),
        "image_size_bytes": image_size,
        "root_hash":        root_hash,
        "root_hash_sig":    sig_hex,
        "file_sha256":      file_sha256,   # convenience — put this in MQTT package_sha256
        "blocks":           blocks,
    }

    with open(output_path, "w") as f:
        json.dump(manifest, f, separators=(",", ":"))   # compact, no indentation for large files

    elapsed = time.monotonic() - t0
    manifest_size_kb = output_path.stat().st_size / 1024

    print()
    print("=" * 60)
    print("Done!")
    print(f"  Manifest   : {output_path}  ({manifest_size_kb:.0f} KB)")
    print(f"  Elapsed    : {elapsed:.1f}s")
    print()
    print("Next steps:")
    print(f"  1. Upload image    : mc cp {image_path} minio/ota-packages/<version>/rootfs.img")
    print(f"  2. Upload manifest : mc cp {output_path} minio/ota-packages/<version>/manifest.json")
    print( "  3. In config.yaml  : set install_strategy: merkle")
    print(f"  4. In MQTT notify  : set package_sha256 to {file_sha256}")
    print("=" * 60)


if __name__ == "__main__":
    main()
