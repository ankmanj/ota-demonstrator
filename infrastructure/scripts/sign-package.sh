#!/bin/bash
#
# Sign Package Script for OTA Updates
# Signs a .swu package with RSA private key
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_DIR="${KEY_DIR:-$SCRIPT_DIR/keys}"
PRIVATE_KEY="$KEY_DIR/swupdate-priv.pem"
TEMP_DIR="/tmp/swu-sign-$$"

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
    echo "Usage: $0 <package.swu> [output.swu]"
    echo ""
    echo "Arguments:"
    echo "  package.swu   The unsigned .swu package to sign"
    echo "  output.swu    Output filename (optional, defaults to *-signed.swu)"
    exit 1
fi

INPUT_SWU="$1"
OUTPUT_SWU="${2:-${INPUT_SWU%.swu}-signed.swu}"

# Validate input
if [ ! -f "$INPUT_SWU" ]; then
    print_error "Input package not found: $INPUT_SWU"
    exit 1
fi

if [ ! -f "$PRIVATE_KEY" ]; then
    print_error "Private key not found: $PRIVATE_KEY"
    echo "Run ./generate-keys.sh first to create signing keys."
    exit 1
fi

# Create temp directory
mkdir -p "$TEMP_DIR"
#trap "rm -rf $TEMP_DIR" EXIT

# Step 1: Extract the .swu package
print_info "Extracting package..."
cd "$TEMP_DIR"
cpio -idv < "$INPUT_SWU"

# Verify sw-description exists
if [ ! -f "sw-description" ]; then
    print_error "Invalid .swu package: sw-description not found"
    exit 1
fi

# Step 2: Sign the sw-description
print_info "Signing sw-description..."
openssl dgst -sha256 -sign "$PRIVATE_KEY" -out sw-description.sig sw-description

# Verify signature was created
if [ ! -f "sw-description.sig" ]; then
    print_error "Failed to create signature"
    exit 1
fi

# Step 3: Rebuild the .swu with signature
print_info "Rebuilding signed package..."

# Order matters: sw-description, then signature, then other files
{
    echo "sw-description"
    echo "sw-description.sig"
    # Add all other files (excluding the ones we already listed)
    find . -type f ! -name "sw-description" ! -name "sw-description.sig" -printf "%f\n"
} | cpio -ov -H crc > "$OUTPUT_SWU"

# Step 4: Verify the signed package
print_info "Verifying signature..."
cd "$SCRIPT_DIR"
openssl dgst -sha256 -verify "$KEY_DIR/swupdate-pub.pem" \
    -signature <(cd "$TEMP_DIR" && cat sw-description.sig) \
    <(cd "$TEMP_DIR" && cat sw-description)

# Summary
echo ""
echo "=========================================="
print_info "Package signed successfully!"
echo "=========================================="
echo ""
echo "Signed package: $OUTPUT_SWU"
echo "Size: $(du -h "$OUTPUT_SWU" | cut -f1)"
echo ""
echo "Next step:"
echo "  Upload to MinIO: ./upload-to-minio.sh $OUTPUT_SWU"
