#!/bin/bash
#
# Upload to MinIO Script
# Uploads signed .swu packages to MinIO storage
#

set -e

# Configuration
MINIO_ALIAS="${MINIO_ALIAS:-ota-minio}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin123}"
BUCKET_NAME="${BUCKET_NAME:-updates}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <package.swu> [destination-name]"
    echo ""
    echo "Arguments:"
    echo "  package.swu       The .swu package to upload"
    echo "  destination-name  Name in bucket (optional, defaults to filename)"
    echo ""
    echo "Environment variables:"
    echo "  MINIO_ENDPOINT    MinIO server URL (default: http://localhost:9000)"
    echo "  MINIO_ACCESS_KEY  Access key (default: minioadmin)"
    echo "  MINIO_SECRET_KEY  Secret key (default: minioadmin)"
    echo "  BUCKET_NAME       Target bucket (default: updates)"
    exit 1
fi

PACKAGE_FILE="$1"
DEST_NAME="${2:-$(basename "$PACKAGE_FILE")}"

# Validate input
if [ ! -f "$PACKAGE_FILE" ]; then
    print_error "Package file not found: $PACKAGE_FILE"
    exit 1
fi

# Check if mc (MinIO client) is installed
if ! command -v mc &> /dev/null; then
    print_error "MinIO client (mc) is not installed."
    echo ""
    echo "Install it with:"
    echo "  curl -O https://dl.min.io/client/mc/release/linux-amd64/mc"
    echo "  chmod +x mc"
    echo "  sudo mv mc /usr/local/bin/"
    echo ""
    echo "Or use Docker:"
    echo "  docker run --rm -v \$(pwd):/data minio/mc ..."
    exit 1
fi

# Step 1: Configure MinIO alias
print_info "Configuring MinIO connection..."
mc alias set "$MINIO_ALIAS" "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api S3v4

# Step 2: Check if bucket exists, create if not
print_info "Checking bucket: $BUCKET_NAME"
if ! mc ls "$MINIO_ALIAS/$BUCKET_NAME" &> /dev/null; then
    print_warn "Bucket '$BUCKET_NAME' not found, creating..."
    mc mb "$MINIO_ALIAS/$BUCKET_NAME"
fi

# Step 3: Upload the package with SHA-256 integrity check
# --checksum SHA256 sends a SHA-256 checksum as a trailing header.
# MinIO computes SHA-256 of received data and compares it against the header.
# If they don't match, MinIO rejects the upload with an error.
print_info "Uploading package (with SHA-256 integrity check)..."
mc cp --checksum SHA256 "$PACKAGE_FILE" "$MINIO_ALIAS/$BUCKET_NAME/$DEST_NAME"
print_info "Upload integrity verified via SHA-256 checksum"

# Step 5: Generate download URL
DOWNLOAD_URL="$MINIO_ENDPOINT/$BUCKET_NAME/$DEST_NAME"

# Summary
echo ""
echo "=========================================="
print_info "Upload complete!"
echo "=========================================="
echo ""
echo "Package: $DEST_NAME"
echo "Bucket:  $BUCKET_NAME"
echo "Size:    $(du -h "$PACKAGE_FILE" | cut -f1)"
echo ""
echo "Download URL:"
echo "  $DOWNLOAD_URL"
echo ""
echo "List bucket contents:"
echo "  mc ls $MINIO_ALIAS/$BUCKET_NAME"
echo ""
echo "MinIO Console:"
echo "  http://localhost:9001 (login: minioadmin/minioadmin)"
