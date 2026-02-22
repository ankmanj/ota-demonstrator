#!/bin/bash
#
# Build Package Script for OTA Updates
# Creates a .swu update package for SWUpdate
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/build}"
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/output}"
VERSION="${VERSION:-1.0.0}"
PACKAGE_NAME="${PACKAGE_NAME:-ota-demo-update}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Clean previous build
print_info "Cleaning previous build..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/rootfs"
mkdir -p "$OUTPUT_DIR"

# Step 1: Create the rootfs structure
print_info "Creating rootfs structure..."

# Create version file
mkdir -p "$BUILD_DIR/rootfs/etc/ota-demo"
cat > "$BUILD_DIR/rootfs/etc/ota-demo/version.txt" << EOF
OTA Demo Version: $VERSION
Build Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Build Host: $(hostname)
EOF

# Create hello.sh script
mkdir -p "$BUILD_DIR/rootfs/usr/local/bin"
cat > "$BUILD_DIR/rootfs/usr/local/bin/hello.sh" << 'EOF'
#!/bin/bash
# OTA Demo Hello Script
echo "Hello from OTA Update!"
echo "Version: $(cat /etc/ota-demo/version.txt 2>/dev/null || echo 'unknown')"
echo "Running on: $(hostname)"
echo "Date: $(date)"
EOF
chmod +x "$BUILD_DIR/rootfs/usr/local/bin/hello.sh"

# Step 2: Create rootfs tarball
print_info "Creating rootfs tarball..."
cd "$BUILD_DIR/rootfs"
tar -czvf "$BUILD_DIR/rootfs.tar.gz" .
cd "$SCRIPT_DIR"

# Step 3: Create sw-description
print_info "Creating sw-description..."
cat > "$BUILD_DIR/sw-description" << EOF
software =
{
    version = "$VERSION";
    description = "OTA Demo Update Package";
    hardware-compatibility = ["raspberrypi"];

    scripts: (
        {
            filename = "rootfs.tar.gz";
            type = "archive";
            path = "/";
            sha256 = "$(sha256sum "$BUILD_DIR/rootfs.tar.gz" | cut -d' ' -f1)";
        }
    );
}
EOF

# Step 4: Build the .swu package (CPIO archive)
print_info "Building .swu package..."
cd "$BUILD_DIR"

# Create the CPIO archive (order matters: sw-description must be first!)
echo "sw-description" > "$BUILD_DIR/swu-files.txt"
echo "rootfs.tar.gz" >> "$BUILD_DIR/swu-files.txt"

# Build unsigned .swu
cat "$BUILD_DIR/swu-files.txt" | cpio -ov -H crc > "$OUTPUT_DIR/${PACKAGE_NAME}-${VERSION}.swu"

cd "$SCRIPT_DIR"

# Summary
echo ""
echo "=========================================="
print_info "Package build complete!"
echo "=========================================="
echo ""
echo "Package: $OUTPUT_DIR/${PACKAGE_NAME}-${VERSION}.swu"
echo "Size: $(du -h "$OUTPUT_DIR/${PACKAGE_NAME}-${VERSION}.swu" | cut -f1)"
echo ""
echo "Contents:"
echo "  - /etc/ota-demo/version.txt"
echo "  - /usr/local/bin/hello.sh"
echo ""
echo "Next steps:"
echo "  1. Sign the package: ./sign-package.sh $OUTPUT_DIR/${PACKAGE_NAME}-${VERSION}.swu"
echo "  2. Upload to MinIO:  ./upload-to-minio.sh $OUTPUT_DIR/${PACKAGE_NAME}-${VERSION}.swu"
