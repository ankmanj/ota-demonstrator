#!/bin/bash
#
# Key Generation Script for OTA Update Package Signing
# Generates RSA key pair for signing .swu update packages
#

set -e

# Configuration
KEY_DIR="${KEY_DIR:-./keys}"
KEY_SIZE="${KEY_SIZE:-4096}"
PRIVATE_KEY="$KEY_DIR/swupdate-priv.pem"
PUBLIC_KEY="$KEY_DIR/swupdate-pub.pem"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if openssl is installed
if ! command -v openssl &> /dev/null; then
    print_error "OpenSSL is not installed. Please install it first."
    echo "  Ubuntu/Debian: sudo apt-get install openssl"
    echo "  Fedora/RHEL:   sudo dnf install openssl"
    exit 1
fi

# Create keys directory
if [ ! -d "$KEY_DIR" ]; then
    print_info "Creating keys directory: $KEY_DIR"
    mkdir -p "$KEY_DIR"
fi

# Check if keys already exist
if [ -f "$PRIVATE_KEY" ] || [ -f "$PUBLIC_KEY" ]; then
    print_warn "Keys already exist in $KEY_DIR"
    read -p "Do you want to overwrite them? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Keeping existing keys."
        exit 0
    fi
    print_warn "Overwriting existing keys..."
fi

# Generate RSA private key
print_info "Generating $KEY_SIZE-bit RSA private key..."
openssl genrsa -out "$PRIVATE_KEY" "$KEY_SIZE"
# openssl ecparam -genkey -name prime256v1 -out swupdate-priv.pem
# openssl genpkey -algorithm Ed25519 -out swupdate-priv.pem

# Set restrictive permissions on private key
chmod 600 "$PRIVATE_KEY"

# Extract public key from private key
print_info "Extracting public key..."
openssl rsa -in "$PRIVATE_KEY" -outform PEM -pubout -out "$PUBLIC_KEY"
# openssl ec -in swupdate-priv.pem -pubout -out swupdate-pub.pem
# openssl pkey -in swupdate-priv.pem -pubout -out swupdate-pub.pem

# Set permissions on public key (readable)
chmod 644 "$PUBLIC_KEY"

# Display summary
echo ""
echo "=========================================="
print_info "Key generation complete!"
echo "=========================================="
echo ""
echo "Keys generated:"
echo "  Private key: $PRIVATE_KEY (KEEP THIS SECRET!)"
echo "  Public key:  $PUBLIC_KEY"
echo ""
echo "Key details:"
openssl rsa -in "$PRIVATE_KEY" -text -noout | head -1
echo ""
echo "Next steps:"
echo "  1. Keep the private key secure (never commit to git!)"
echo "  2. Copy the public key to your Raspberry Pi for verification"
echo "  3. Use the private key to sign your .swu packages"
echo ""
print_warn "Remember: Add 'keys/' to your .gitignore!"
