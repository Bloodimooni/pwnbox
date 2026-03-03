#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/infra/config.ini"
INFRA_DIR="$SCRIPT_DIR/infra"

# Simple INI parser — resolves relative paths against the infra/ directory
get_config() {
    local section="$1" key="$2"
    sed -n "/^\[$section\]/,/^\[/p" "$CONFIG" | grep "^${key}\s*=" | head -1 | cut -d'=' -f2- | xargs
}

get_config_path() {
    local val
    val=$(get_config "$1" "$2")
    # Resolve relative paths against infra/ (where config.ini lives)
    case "$val" in
        /*) echo "$val" ;;
        *)  echo "$INFRA_DIR/$val" ;;
    esac
}

DOCKER_NET=$(get_config general docker_network)
DOCKER_SUBNET=$(get_config general docker_subnet)
STATE_DIR=$(get_config_path paths state_dir)

echo "=== PwnBox CTF Host Setup ==="
echo "Docker network: $DOCKER_NET ($DOCKER_SUBNET)"
echo ""

# 1. Enable IP forwarding
echo "[1/3] Enabling IP forwarding..."
if ! sysctl net.ipv4.ip_forward | grep -q "= 1"; then
    echo "net.ipv4.ip_forward = 1" > /etc/sysctl.d/99-pwnbox.conf
    sysctl -p /etc/sysctl.d/99-pwnbox.conf
else
    echo "  Already enabled."
fi

# 2. Create Docker network
echo "[2/3] Creating Docker network..."
if ! docker network inspect "$DOCKER_NET" &>/dev/null; then
    docker network create --subnet="$DOCKER_SUBNET" "$DOCKER_NET"
    echo "  Network created."
else
    echo "  Network already exists."
fi

# 3. Create state directory
echo "[3/3] Setting up state directory..."
mkdir -p "$STATE_DIR"
if [ ! -f "$STATE_DIR/instances.json" ]; then
    echo "{}" > "$STATE_DIR/instances.json"
fi

# Build the Docker image
echo ""
echo "=== Building PwnBox Docker image ==="
docker build -f "$SCRIPT_DIR/docker/Dockerfile" -t "$(get_config general image_name)" "$SCRIPT_DIR"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Each container runs its own NetBird client and registers automatically."
echo ""
echo "Next steps:"
echo "  1. Start the portal:  ./run.sh portal"
echo "  2. Start the scaler:  ./run.sh scale"
echo "  3. Or use CLI:        python3 infra/pwnbox-manager.py create <name>"
