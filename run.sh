#!/bin/bash
# PwnBox unified run script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="pwnbox-ctf"
DOCKERFILE="$SCRIPT_DIR/docker/Dockerfile"
COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.yml"
PORTAL="$SCRIPT_DIR/infra/portal.py"

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; BOLD='\033[1m'; RST='\033[0m'

info()    { echo -e "${BLU}[*]${RST} $*"; }
success() { echo -e "${GRN}[+]${RST} $*"; }
warn()    { echo -e "${YLW}[!]${RST} $*"; }
error()   { echo -e "${RED}[x]${RST} $*" >&2; exit 1; }

# ── helpers ────────────────────────────────────────────────────────────────────

image_exists() {
    docker image inspect "$IMAGE" &>/dev/null
}

image_outdated() {
    # Compare image creation time against Dockerfile + requirements.txt mtimes
    local img_epoch
    img_epoch=$(docker image inspect "$IMAGE" --format '{{.Created}}' 2>/dev/null \
        | xargs -I{} date -d {} +%s 2>/dev/null || echo 0)

    local newest_src=0
    for f in "$DOCKERFILE" "$SCRIPT_DIR/requirements.txt" \
              "$SCRIPT_DIR/entrypoint.py"; do
        [[ -f "$f" ]] || continue
        local t
        t=$(stat -c %Y "$f")
        (( t > newest_src )) && newest_src=$t
    done

    (( newest_src > img_epoch ))
}

build_image() {
    local force="${1:-false}"
    local netbird="${2:-false}"

    if ! image_exists; then
        info "Image '$IMAGE' not found — building..."
    elif [[ "$force" == "true" ]]; then
        info "Force rebuild requested..."
    elif image_outdated; then
        warn "Source files are newer than the image — rebuilding..."
    else
        success "Image '$IMAGE' is up to date."
        return 0
    fi

    local build_args=("--build-arg" "INSTALL_NETBIRD=$netbird")
    info "Building from docker/Dockerfile (context: project root)..."
    docker build "${build_args[@]}" -f "$DOCKERFILE" -t "$IMAGE" "$SCRIPT_DIR"
    success "Build complete."
}

# ── commands ───────────────────────────────────────────────────────────────────

cmd_build() {
    local force=false netbird=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force|-f)   force=true   ;;
            --netbird)    netbird=true ;;
            *) warn "Unknown build option: $1" ;;
        esac
        shift
    done
    build_image "$force" "$netbird"
}

cmd_app() {
    local netbird=false force=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --netbird)    netbird=true ;;
            --force|-f)   force=true   ;;
            *) warn "Unknown app option: $1" ;;
        esac
        shift
    done

    build_image "$force" "$netbird"

    info "Starting CorpChat app container..."
    info "  App:  http://localhost:8080"
    info "  SSH:  ssh svc_backup@localhost -p 2222"
    echo ""

    docker run --rm -it \
        --name corpchat-dev \
        --cap-add NET_ADMIN \
        -p 8080:8080 \
        -p 2222:22 \
        -v corpchat_data:/data \
        -e FLASK_CONFIG=config.ProductionConfig \
        -e SECRET_KEY=corpchat-dev-secret \
        -e DATABASE_DIR=/data \
        -e UPLOAD_FOLDER=/data/uploads \
        -e LOG_DIR=/data/logs \
        "$IMAGE"
}

cmd_portal() {
    info "Starting CTF portal..."
    info "  Portal: http://localhost:8888"
    echo ""

    # Portal instances require NetBird
    local force=false
    if image_exists; then
        if ! docker run --rm --entrypoint /bin/sh "$IMAGE" -c "command -v netbird" &>/dev/null 2>&1; then
            warn "Image '$IMAGE' exists but NetBird is not installed — forcing rebuild with NetBird..."
            force=true
        fi
    fi
    build_image "$force" "true"

    if ! python3 -c "import flask, bcrypt, filelock" 2>/dev/null; then
        warn "Missing Python deps — running: pip install flask bcrypt filelock"
        pip3 install flask bcrypt filelock
    fi

    cd "$SCRIPT_DIR/infra"
    exec python3 portal.py
}

cmd_scale() {
    info "  Starting PwnBox Scaler..."
    echo ""

    # Autoscaler instances require NetBird
    local force=false
    if image_exists; then
        if ! docker run --rm --entrypoint /bin/sh "$IMAGE" -c "command -v netbird" &>/dev/null 2>&1; then
            warn "Image '$IMAGE' exists but NetBird is not installed — forcing rebuild with NetBird..."
            force=true
        fi
    fi
    build_image "$force" "true"

    if ! python3 -c "import flask, filelock" 2>/dev/null; then
        warn "Missing Python deps — running: pip install flask filelock"
        pip3 install flask filelock
    fi

    cd "$SCRIPT_DIR/infra"
    exec python3 scaler.py
}

cmd_compose() {
    local action="${1:-up}"
    shift || true

    case "$action" in
        up)
            info "Starting via Docker Compose..."
            info "  App:  http://localhost:8080"
            info "  SSH:  ssh svc_backup@localhost -p 2222"
            echo ""
            docker compose -f "$COMPOSE_FILE" up --build "$@"
            ;;
        down)
            info "Stopping Docker Compose stack..."
            docker compose -f "$COMPOSE_FILE" down "$@"
            ;;
        logs)
            docker compose -f "$COMPOSE_FILE" logs -f "$@"
            ;;
        *)
            # Pass anything else straight through
            docker compose -f "$COMPOSE_FILE" "$action" "$@"
            ;;
    esac
}

cmd_help() {
    echo -e ""
    echo -e "${BOLD}${CYN}PwnBox — CTF Platform Runner${RST}"
    echo -e ""
    echo -e "${BOLD}USAGE${RST}"
    echo -e "  ./run.sh <command> [options]"
    echo -e ""
    echo -e "${BOLD}COMMANDS${RST}"
    echo -e "  ${GRN}app${RST}              Build (if needed) and run the CorpChat app in Docker"
    echo -e "  ${GRN}portal${RST}           Start the CTF self-service portal on the host"
    echo -e "  ${GRN}scale${RST}            Start the operator scaler (token-auth, no team system)"
    echo -e "  ${GRN}compose${RST} [action] Docker Compose wrapper (default action: up)"
    echo -e "                     Actions: up | down | logs | <any compose sub-command>"
    echo -e "  ${GRN}build${RST}            Build or rebuild the Docker image"
    echo -e "  ${GRN}help${RST}             Show this help"
    echo -e ""
    echo -e "${BOLD}OPTIONS${RST}"
    echo -e "  ${YLW}--force, -f${RST}      Force rebuild even if image is up to date  (app, build)"
    echo -e "  ${YLW}--netbird${RST}        Include NetBird VPN in the image            (app, build)"
    echo -e ""
    echo -e "${BOLD}EXAMPLES${RST}"
    echo -e "  ./run.sh app                   # Dev run, auto-build if stale"
    echo -e "  ./run.sh app --netbird         # Same, with NetBird baked in"
    echo -e "  ./run.sh app --force           # Force rebuild then run"
    echo -e "  ./run.sh portal                # Launch the CTF portal (host process)"
    echo -e "  ./run.sh compose               # docker compose up --build"
    echo -e "  ./run.sh compose down          # docker compose down"
    echo -e "  ./run.sh compose logs          # Follow compose logs"
    echo -e "  ./run.sh build --netbird       # Build with NetBird, no run"
    echo -e ""
    echo -e "${BOLD}FILES${RST}"
    echo -e "  docker/Dockerfile              Container image definition"
    echo -e "  docker/docker-compose.yml      Compose stack for single-instance dev"
    echo -e "  infra/portal.py                CTF management portal"
    echo -e "  infra/config.ini               All portal + infra configuration"
    echo -e ""
}

# ── entrypoint ─────────────────────────────────────────────────────────────────

CMD="${1:-help}"
shift 2>/dev/null || true

case "$CMD" in
    app)          cmd_app       "$@" ;;
    portal)       cmd_portal    "$@" ;;
    scale|scaler) cmd_scale     "$@" ;;
    compose)      cmd_compose   "$@" ;;
    build)        cmd_build     "$@" ;;
    help|--help|-h) cmd_help  ;;
    *)
        error "Unknown command: '$CMD'  (try ./run.sh --help)"
        ;;
esac
