#!/bin/bash
set -e

CONFIG="$(dirname "$0")/config.ini"

# Simple INI parser
get_config() {
    local section="$1" key="$2"
    sed -n "/^\[$section\]/,/^\[/p" "$CONFIG" | grep "^${key}\s*=" | head -1 | cut -d'=' -f2- | xargs
}

WG_IFACE=$(get_config wireguard interface)
WG_PORT=$(get_config wireguard port)
WG_ADDR=$(get_config wireguard server_address)
DOCKER_NET=$(get_config general docker_network)
DOCKER_SUBNET=$(get_config general docker_subnet)
STATE_DIR=$(get_config paths state_dir)
WG_DIR=$(get_config paths wireguard_dir)

echo "=== PwnBox CTF Host Setup ==="
echo "WireGuard interface: $WG_IFACE"
echo "WireGuard port:      $WG_PORT"
echo "Docker network:      $DOCKER_NET ($DOCKER_SUBNET)"
echo ""

# 1. WireGuard
echo "[1/6] Installing WireGuard..."
if ! command -v wg &>/dev/null; then
    apt-get update
    apt-get install -y wireguard wireguard-tools
else
    echo "  Already installed."
fi

# 2. Enable IP forwarding
echo "[2/6] Enabling IP forwarding..."
if ! sysctl net.ipv4.ip_forward | grep -q "= 1"; then
    echo "net.ipv4.ip_forward = 1" > /etc/sysctl.d/99-pwnbox.conf
    sysctl -p /etc/sysctl.d/99-pwnbox.conf
else
    echo "  Already enabled."
fi

# 3. Generate WireGuard server keys
echo "[3/6] Generating WireGuard keys..."
mkdir -p "$WG_DIR"
if [ ! -f "$WG_DIR/server_private.key" ]; then
    umask 077
    wg genkey | tee "$WG_DIR/server_private.key" | wg pubkey > "$WG_DIR/server_public.key"
    echo "  Keys generated."
else
    echo "  Keys already exist."
fi

SERVER_PRIVKEY=$(cat "$WG_DIR/server_private.key")
SERVER_PUBKEY=$(cat "$WG_DIR/server_public.key")

# 4. Create WireGuard config
echo "[4/6] Creating WireGuard config..."
if [ ! -f "$WG_DIR/$WG_IFACE.conf" ]; then
    cat > "$WG_DIR/$WG_IFACE.conf" << EOF
[Interface]
PrivateKey = $SERVER_PRIVKEY
Address = $WG_ADDR
ListenPort = $WG_PORT

# Allow forwarding between VPN and Docker network
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT

# Peers are managed by pwnbox-manager.py (appended below)
EOF
    chmod 600 "$WG_DIR/$WG_IFACE.conf"
    echo "  Config created."
else
    echo "  Config already exists, skipping."
fi

# 5. Create Docker network
echo "[5/6] Creating Docker network..."
if ! docker network inspect "$DOCKER_NET" &>/dev/null; then
    docker network create --subnet="$DOCKER_SUBNET" "$DOCKER_NET"
    echo "  Network created."
else
    echo "  Network already exists."
fi

# 6. Create state directory
echo "[6/6] Setting up state directory..."
mkdir -p "$STATE_DIR"
if [ ! -f "$STATE_DIR/instances.json" ]; then
    echo "{}" > "$STATE_DIR/instances.json"
fi

# Build the Docker image
echo ""
echo "=== Building PwnBox Docker image ==="
PWNBOX_DIR="$(dirname "$0")/.."
docker build -t "$(get_config general image_name)" "$PWNBOX_DIR"

# Start WireGuard
echo ""
echo "=== Starting WireGuard ==="
systemctl enable "wg-quick@$WG_IFACE"
systemctl start "wg-quick@$WG_IFACE" 2>/dev/null || systemctl restart "wg-quick@$WG_IFACE"

echo ""
echo "=== Setup Complete ==="
echo "Server public key: $SERVER_PUBKEY"
echo ""
echo "IMPORTANT: Edit config.ini and set 'endpoint' to your public IP/domain."
echo ""
echo "Next steps:"
echo "  1. Edit infra/config.ini → set endpoint = YOUR_PUBLIC_IP"
echo "  2. Open UDP port $WG_PORT in your firewall"
echo "  3. (Optional) Install systemd timer: cp infra/systemd/* /etc/systemd/system/ && systemctl enable --now pwnbox-cleanup.timer"
echo "  4. Start the portal: python3 infra/portal.py"
echo "  5. Or use CLI: python3 infra/pwnbox-manager.py create <team-name>"
