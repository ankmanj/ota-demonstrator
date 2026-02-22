#!/bin/bash
#
# Benchmark Verification Times
# Compares signature verification performance across algorithms
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_header() { echo -e "${CYAN}$1${NC}"; }

# Usage
usage() {
    echo "Usage: $0 <algorithm> [iterations]"
    echo ""
    echo "Algorithms:"
    echo "  rsa-sha256      RSA-4096 + SHA-256"
    echo "  rsa-sha384      RSA-4096 + SHA-384"
    echo "  rsa-sha512      RSA-4096 + SHA-512"
    echo "  ecdsa-sha256    ECDSA P-256 + SHA-256"
    echo "  ecdsa-sha384    ECDSA P-384 + SHA-384"
    echo "  ecdsa-sha512    ECDSA P-521 + SHA-512"
    echo "  ed25519         Ed25519"
    echo "  all             Run all algorithms"
    echo ""
    echo "Arguments:"
    echo "  iterations      Number of verification runs (default: 20)"
    echo ""
    echo "Examples:"
    echo "  $0 rsa-sha256"
    echo "  $0 ed25519 50"
    echo "  $0 all 20"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

ALGORITHM="$1"
ITERATIONS="${2:-20}"

# Temp directory for benchmark files
BENCH_DIR=$(mktemp -d)
trap "rm -rf $BENCH_DIR" EXIT

# Create dummy 1MB package payload
print_info "Creating 1MB dummy package payload..."
dd if=/dev/urandom of="$BENCH_DIR/rootfs.img" bs=1M count=1 2>/dev/null

# Create sw-description with SHA-256 checksum of the payload
PAYLOAD_HASH=$(sha256sum "$BENCH_DIR/rootfs.img" | awk '{print $1}')
cat > "$BENCH_DIR/sw-description" << EOF
software = {
    version = "1.0.0";
    hardware-compatibility: ["revA"];
    images: ({
        filename = "rootfs.img";
        type = "raw";
        sha256 = "$PAYLOAD_HASH";
    });
}
EOF

print_info "sw-description created ($(stat -c%s "$BENCH_DIR/sw-description") bytes)"
echo ""

# Function to run benchmark for a single algorithm
run_benchmark() {
    local algo_name="$1"
    local key_gen_cmd="$2"
    local sign_cmd="$3"
    local verify_cmd="$4"

    print_header "=========================================="
    print_header "  Algorithm: $algo_name"
    print_header "  Iterations: $ITERATIONS"
    print_header "=========================================="
    echo ""

    # Generate keys
    print_info "Generating keys..."
    eval "$key_gen_cmd"
    echo ""

    # Sign sw-description
    print_info "Signing sw-description..."
    eval "$sign_cmd"
    echo ""

    # Run verification iterations
    print_info "Running $ITERATIONS verification iterations..."
    echo ""
    printf "%-12s %s\n" "Iteration" "Time (seconds)"
    printf "%-12s %s\n" "---------" "--------------"

    local total_time=0

    for i in $(seq 1 "$ITERATIONS"); do
        # Measure verification time using date with nanoseconds
        local start=$(date +%s%N)
        eval "$verify_cmd" > /dev/null 2>&1
        local end=$(date +%s%N)

        # Calculate elapsed time in seconds (nanosecond precision)
        local elapsed=$(echo "scale=6; ($end - $start) / 1000000000" | bc)
        total_time=$(echo "scale=6; $total_time + $elapsed" | bc)

        printf "%-12s %s\n" "$i" "${elapsed}s"
    done

    local avg_time=$(echo "scale=6; $total_time / $ITERATIONS" | bc)

    echo ""
    echo "-------------------------------------------"
    printf "Total time:   %ss\n" "$total_time"
    printf "Average time: %ss\n" "$avg_time"
    echo "-------------------------------------------"
    echo ""
}

# Define algorithms
run_rsa_sha256() {
    run_benchmark "RSA-4096 + SHA-256" \
        "openssl genrsa -out $BENCH_DIR/priv.pem 4096 2>/dev/null && openssl rsa -in $BENCH_DIR/priv.pem -pubout -out $BENCH_DIR/pub.pem 2>/dev/null" \
        "openssl dgst -sha256 -sign $BENCH_DIR/priv.pem -out $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description" \
        "openssl dgst -sha256 -verify $BENCH_DIR/pub.pem -signature $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description"
}

run_rsa_sha384() {
    run_benchmark "RSA-4096 + SHA-384" \
        "openssl genrsa -out $BENCH_DIR/priv.pem 4096 2>/dev/null && openssl rsa -in $BENCH_DIR/priv.pem -pubout -out $BENCH_DIR/pub.pem 2>/dev/null" \
        "openssl dgst -sha384 -sign $BENCH_DIR/priv.pem -out $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description" \
        "openssl dgst -sha384 -verify $BENCH_DIR/pub.pem -signature $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description"
}

run_rsa_sha512() {
    run_benchmark "RSA-4096 + SHA-512" \
        "openssl genrsa -out $BENCH_DIR/priv.pem 4096 2>/dev/null && openssl rsa -in $BENCH_DIR/priv.pem -pubout -out $BENCH_DIR/pub.pem 2>/dev/null" \
        "openssl dgst -sha512 -sign $BENCH_DIR/priv.pem -out $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description" \
        "openssl dgst -sha512 -verify $BENCH_DIR/pub.pem -signature $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description"
}

run_ecdsa_sha256() {
    run_benchmark "ECDSA P-256 + SHA-256" \
        "openssl ecparam -genkey -name prime256v1 -out $BENCH_DIR/priv.pem 2>/dev/null && openssl ec -in $BENCH_DIR/priv.pem -pubout -out $BENCH_DIR/pub.pem 2>/dev/null" \
        "openssl dgst -sha256 -sign $BENCH_DIR/priv.pem -out $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description" \
        "openssl dgst -sha256 -verify $BENCH_DIR/pub.pem -signature $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description"
}

run_ecdsa_sha384() {
    run_benchmark "ECDSA P-384 + SHA-384" \
        "openssl ecparam -genkey -name secp384r1 -out $BENCH_DIR/priv.pem 2>/dev/null && openssl ec -in $BENCH_DIR/priv.pem -pubout -out $BENCH_DIR/pub.pem 2>/dev/null" \
        "openssl dgst -sha384 -sign $BENCH_DIR/priv.pem -out $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description" \
        "openssl dgst -sha384 -verify $BENCH_DIR/pub.pem -signature $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description"
}

run_ecdsa_sha512() {
    run_benchmark "ECDSA P-521 + SHA-512" \
        "openssl ecparam -genkey -name secp521r1 -out $BENCH_DIR/priv.pem 2>/dev/null && openssl ec -in $BENCH_DIR/priv.pem -pubout -out $BENCH_DIR/pub.pem 2>/dev/null" \
        "openssl dgst -sha512 -sign $BENCH_DIR/priv.pem -out $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description" \
        "openssl dgst -sha512 -verify $BENCH_DIR/pub.pem -signature $BENCH_DIR/sw-description.sig $BENCH_DIR/sw-description"
}

run_ed25519() {
    run_benchmark "Ed25519" \
        "openssl genpkey -algorithm Ed25519 -out $BENCH_DIR/priv.pem 2>/dev/null && openssl pkey -in $BENCH_DIR/priv.pem -pubout -out $BENCH_DIR/pub.pem 2>/dev/null" \
        "openssl pkeyutl -sign -inkey $BENCH_DIR/priv.pem -out $BENCH_DIR/sw-description.sig -rawin -in $BENCH_DIR/sw-description" \
        "openssl pkeyutl -verify -pubin -inkey $BENCH_DIR/pub.pem -sigfile $BENCH_DIR/sw-description.sig -rawin -in $BENCH_DIR/sw-description"
}

# Run selected algorithm
case "$ALGORITHM" in
    rsa-sha256)   run_rsa_sha256 ;;
    rsa-sha384)   run_rsa_sha384 ;;
    rsa-sha512)   run_rsa_sha512 ;;
    ecdsa-sha256) run_ecdsa_sha256 ;;
    ecdsa-sha384) run_ecdsa_sha384 ;;
    ecdsa-sha512) run_ecdsa_sha512 ;;
    ed25519)      run_ed25519 ;;
    all)
        run_rsa_sha256
        run_rsa_sha384
        run_rsa_sha512
        run_ecdsa_sha256
        run_ecdsa_sha384
        run_ecdsa_sha512
        run_ed25519
        ;;
    *)
        echo "Unknown algorithm: $ALGORITHM"
        echo ""
        usage
        ;;
esac
