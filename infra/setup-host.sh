#!/bin/bash
set -e

CONFIG="$(dirname "$0")/config.ini"

# Simple INI parser
get_config() {
    local section="$1" key="$2"
    sed -n "/^\[$section\]/,/^\[/p" "$CONFIG" | grep "^${key}\s*=" | head -1 | cut -d'=' -f2- | xargs
}

DOCKER_NET=$(get_config general docker_network)
DOCKER_SUBNET=$(get_config general docker_subnet)
STATE_DIR=$(get_config paths state_dir)

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
PWNBOX_DIR="$(dirname "$0")/.."
docker build -t "$(get_config general image_name)" "$PWNBOX_DIR"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Each container runs its own NetBird client and registers automatically."
echo ""
echo "Next steps:"
echo "  1. Start the portal: python3 infra/portal.py"
echo "  2. Or use CLI: python3 infra/pwnbox-manager.py create <team-name>"
echo "  3. (Optional) Install systemd timer: cp infra/systemd/* /etc/systemd/system/ && systemctl enable --now pwnbox-cleanup.timer"
