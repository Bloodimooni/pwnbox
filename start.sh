#!/bin/bash
set -e

# NetBird setup — only runs if netbird is installed and env vars are set
if command -v netbird &>/dev/null; then
    # Try to create /dev/net/tun if missing (not required — NetBird works without it)
    if [ ! -e /dev/net/tun ]; then
        mkdir -p /dev/net
        mknod /dev/net/tun c 10 200 2>/dev/null && chmod 666 /dev/net/tun || true
    fi

    netbird service install 2>/dev/null || true
    netbird service start 2>/dev/null || true

    if [ -n "$NETBIRD_SETUP_KEY" ] && [ -n "$NETBIRD_MGMT_URL" ]; then
        netbird up --setup-key "$NETBIRD_SETUP_KEY" --management-url "$NETBIRD_MGMT_URL" --hostname "${HOSTNAME:-pwnbox}" &
        sleep 3
    fi
fi

# Run the original entrypoint
exec python entrypoint.py
