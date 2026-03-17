#!/bin/bash
#
# build-image-package.sh - Build a .swu OTA package from a raw partition image.
#
# The resulting .swu contains:
#   1. sw-description       — libconfig manifest with per-chunk sha256 + byte offset
#   2. sw-description.sig   — added later by sign-package.sh
#   3. rootfs.img           — raw image  (single file, if < 3.9 GiB)
#      OR
#      rootfs.img.part-aaa  — chunk 0   (if image >= 3.9 GiB)
#      rootfs.img.part-aab  — chunk 1
#      ...
#
# The OTA agent streams each chunk directly to the inactive partition at the
# recorded byte offset — no temporary files anywhere.
#
# How to create rootfs.img on the Raspberry Pi:
#
#   Option A — full partition dump (simple, size = full partition):
#     sudo dd if=/dev/mmcblk0p3 bs=4M status=progress of=/tmp/rootfs.img
#
#   Option B — used-blocks-only sparse image (smaller on disk):
#     sudo e2image -rap /dev/mmcblk0p3 /tmp/rootfs.img
#
#   Option C — shrink first, then dump (smallest possible):
#     sudo e2fsck -f /dev/mmcblk0p3
#     sudo resize2fs -M /dev/mmcblk0p3
#     sudo dd if=/dev/mmcblk0p3 bs=4M status=progress of=/tmp/rootfs.img
#     # grow the partition back after dumping
#
#   Transfer to build host:
#     rsync -avz --progress pi@<ip>:/tmp/rootfs.img ./
#
# Usage:
#   ./build-image-package.sh <path-to-rootfs.img> [version]
#
# Example:
#   ./build-image-package.sh /tmp/rootfs.img 2.0.0
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/output}"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build-image}"

# CPIO newc filesize field is 32-bit (max 0xFFFFFFFF ≈ 4.29 GiB).
# Use 3.9 GiB chunks to stay safely under the limit.
CHUNK_SIZE_BYTES=$(( 3900 * 1024 * 1024 ))
CHUNK_SIZE_ARG="3900m"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
print_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
IMAGE_FILE="${1:-}"
VERSION="${2:-2.0.0}"
PACKAGE_NAME="ota-rootfs-image"

if [[ -z "$IMAGE_FILE" ]]; then
    print_error "Usage: $0 <path-to-rootfs.img> [version]"
    print_error "Example: $0 /tmp/rootfs.img 2.0.0"
    echo ""
    echo "Create rootfs.img on the Raspberry Pi with:"
    echo "  sudo dd if=/dev/mmcblk0p3 bs=4M status=progress of=/tmp/rootfs.img"
    echo "  sudo e2image -rap /dev/mmcblk0p3 /tmp/rootfs.img   # sparse, smaller"
    exit 1
fi

if [[ ! -f "$IMAGE_FILE" ]]; then
    print_error "Image file not found: $IMAGE_FILE"
    exit 1
fi

IMAGE_FILE="$(realpath "$IMAGE_FILE")"
IMAGE_BYTES=$(stat -c%s "$IMAGE_FILE")

print_info "Building raw-image OTA package"
print_info "  Image file  : $IMAGE_FILE"
print_info "  Image size  : $(numfmt --to=iec-i --suffix=B "$IMAGE_BYTES")"
print_info "  Version     : $VERSION"
print_info "  Output dir  : $OUTPUT_DIR"

# ---------------------------------------------------------------------------
# Prepare build directory
# ---------------------------------------------------------------------------
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
mkdir -p "$OUTPUT_DIR"

# ---------------------------------------------------------------------------
# Decide: single file or chunked
# ---------------------------------------------------------------------------
if [[ "$IMAGE_BYTES" -ge "$CHUNK_SIZE_BYTES" ]]; then
    CHUNKED=true
    print_warn "Image >= 3.9 GiB — splitting into ${CHUNK_SIZE_ARG} chunks to stay under CPIO 4 GiB limit"
else
    CHUNKED=false
    print_info "Image fits in one CPIO entry — no chunking needed"
fi

# ---------------------------------------------------------------------------
# CHUNKED PATH
# ---------------------------------------------------------------------------
if [[ "$CHUNKED" == "true" ]]; then

    print_info "Splitting rootfs.img into chunks..."
    split --bytes="$CHUNK_SIZE_ARG" --suffix-length=3 \
          "$IMAGE_FILE" "$BUILD_DIR/rootfs.img.part-"

    mapfile -t CHUNK_NAMES < <(ls "$BUILD_DIR"/rootfs.img.part-* | xargs -n1 basename | sort)
    NUM_CHUNKS="${#CHUNK_NAMES[@]}"
    print_info "  Created $NUM_CHUNKS chunks"

    # Build images list: each chunk needs its sha256 AND its byte offset in the
    # original image so the agent can seek to the right position before writing.
    IMAGES_LIBCONFIG=""
    OFFSET=0
    for i in "${!CHUNK_NAMES[@]}"; do
        CNAME="${CHUNK_NAMES[$i]}"
        CPATH="$BUILD_DIR/$CNAME"
        CSHA=$(sha256sum "$CPATH" | cut -d' ' -f1)
        CSIZE=$(stat -c%s "$CPATH")
        print_info "    [$i] $CNAME  $(numfmt --to=iec-i --suffix=B "$CSIZE")  offset=$OFFSET  sha256=$CSHA"

        if [[ "$i" -gt 0 ]]; then
            IMAGES_LIBCONFIG+=","$'\n'
        fi
        IMAGES_LIBCONFIG+="        {
            filename = \"${CNAME}\";
            type = \"rawimage-chunk\";
            chunk_index = ${i};
            offset = ${OFFSET};
            sha256 = \"${CSHA}\";
        }"

        OFFSET=$(( OFFSET + CSIZE ))
    done

    print_info "Creating sw-description (chunked)..."
    cat > "$BUILD_DIR/sw-description" <<EOF
software =
{
    version = "$VERSION";
    description = "Raspberry Pi raw rootfs image OTA update (chunked, $NUM_CHUNKS parts)";
    hardware-compatibility = ["raspberrypi"];

    images: (
${IMAGES_LIBCONFIG}
    );
}
EOF

    CPIO_FILE_LIST="sw-description"
    for CNAME in "${CHUNK_NAMES[@]}"; do
        CPIO_FILE_LIST+=$'\n'"$CNAME"
    done

# ---------------------------------------------------------------------------
# SINGLE-FILE PATH
# ---------------------------------------------------------------------------
else

    ln -s "$IMAGE_FILE" "$BUILD_DIR/rootfs.img"

    print_info "Computing SHA-256..."
    IMAGE_SHA256=$(sha256sum "$IMAGE_FILE" | cut -d' ' -f1)
    print_info "  sha256 = $IMAGE_SHA256"

    print_info "Creating sw-description..."
    cat > "$BUILD_DIR/sw-description" <<EOF
software =
{
    version = "$VERSION";
    description = "Raspberry Pi raw rootfs image OTA update";
    hardware-compatibility = ["raspberrypi"];

    images: (
        {
            filename = "rootfs.img";
            type = "rawimage";
            chunk_index = 0;
            offset = 0;
            sha256 = "$IMAGE_SHA256";
        }
    );
}
EOF

    CPIO_FILE_LIST="sw-description"$'\n'"rootfs.img"

fi

# ---------------------------------------------------------------------------
# Show sw-description
# ---------------------------------------------------------------------------
print_info "sw-description:"
cat "$BUILD_DIR/sw-description"
echo ""

# ---------------------------------------------------------------------------
# Build CPIO archive — sw-description MUST be the first entry
# ---------------------------------------------------------------------------
print_info "Building .swu CPIO archive..."
OUTPUT_FILE="$OUTPUT_DIR/${PACKAGE_NAME}-${VERSION}.swu"

cd "$BUILD_DIR"
echo "$CPIO_FILE_LIST" | cpio -ov -H crc > "$OUTPUT_FILE"
cd "$SCRIPT_DIR"

PACKAGE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
PACKAGE_SHA256=$(sha256sum "$OUTPUT_FILE" | cut -d' ' -f1)

echo ""
echo "=========================================="
print_info "OTA image package built successfully!"
echo "=========================================="
echo ""
echo "  Package   : $OUTPUT_FILE"
echo "  Size      : $PACKAGE_SIZE"
echo "  SHA-256   : $PACKAGE_SHA256"
if [[ "$CHUNKED" == "true" ]]; then
    echo "  Chunked   : YES ($NUM_CHUNKS parts of up to ${CHUNK_SIZE_ARG})"
fi
echo ""
echo "Next steps:"
echo "  1. Sign   : ./sign-package.sh $OUTPUT_FILE"
echo "  2. Upload : ./upload-to-minio.sh ${OUTPUT_FILE%.swu}-signed.swu"
echo ""
print_warn "To reduce package size, shrink the ext4 filesystem first:"
print_warn "  sudo e2fsck -f /dev/mmcblk0p3 && sudo resize2fs -M /dev/mmcblk0p3"
print_warn "  Then re-dump with dd and rebuild."
