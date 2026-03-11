#!/bin/bash
# bundle.sh — Create a distributable zip for the PWNBOX CorpChat CTF challenge.
#
# Usage:
#   ./bundle.sh              # produces pwnbox-ctf.zip in the current directory
#
# Steps performed:
#   1. Generates the static/challenge git repo (via ctfrepo.sh) if not present
#   2. Packages all files needed for `docker compose up --build`
#   3. Excludes dev tooling, git history, pre-compiled binaries, and secrets

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$REPO_ROOT/pwnbox-ctf.zip"

echo "[*] Preparing bundle..."

# ── Step 1: Ensure static/challenge exists ────────────────────────────────────
if [ ! -d "$REPO_ROOT/static/challenge/.git" ]; then
    echo "[*] static/challenge/.git not found — running ctfrepo.sh..."
    bash "$REPO_ROOT/ctfrepo.sh"
else
    echo "[*] static/challenge already present — skipping ctfrepo.sh"
fi

# ── Step 2: Remove old zip ────────────────────────────────────────────────────
rm -f "$OUT"

# ── Step 3: Create zip ────────────────────────────────────────────────────────
cd "$REPO_ROOT"

zip -r "$OUT" . \
    --exclude "*.git/*" \
    --exclude "*/.git/*" \
    --exclude "__pycache__/*" \
    --exclude "*/__pycache__/*" \
    --exclude "*.pyc" \
    --exclude "*.pyo" \
    --exclude "data/*" \
    --exclude "*.db" \
    --exclude ".env" \
    --exclude ".claude/*" \
    --exclude "documentation/*" \
    --exclude "infra/*" \
    --exclude "CTF_Info.pdf" \
    --exclude "*.csv" \
    --exclude "*.pdf" \
    --exclude "*.log" \
    --exclude "reversing-challenge/xor_encode.c" \
    --exclude "reversing-challenge/corpchat-admin" \
    --exclude "bot/node_modules/*" \
    --exclude "bot/package-lock.json" \
    --exclude "bundle.sh" \
    --exclude "pwnbox-ctf.zip" \
    --exclude "run.sh" \
    --exclude "setup-host.sh"

echo ""
echo "[+] Bundle created: $OUT"
echo "[+] Size: $(du -sh "$OUT" | cut -f1)"
echo ""
echo "Distribute pwnbox-ctf.zip to players/organizers."
echo ""
echo "Setup instructions:"
echo "  1. unzip pwnbox-ctf.zip"
echo "  2. cd pwnbox-ctf"
echo "  3. docker compose -f docker/docker-compose.yml up --build"
echo "  App: http://localhost:8080   SSH: localhost:2222"
