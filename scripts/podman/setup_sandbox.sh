#!/bin/bash
# Setup Laney's Podman sandbox on rei
#
# Usage: bash setup_sandbox.sh [command]
#   setup   - Install Podman, build image, start container (default)
#   rebuild - Rebuild image and restart container
#   reset   - Stop, remove, and restart container (fresh workspace)
#   stop    - Stop the container
#   start   - Start the container
#   status  - Show container status
#   shell   - Open interactive shell in container
#   logs    - Show container logs

set -e

CONTAINER_NAME="laney-sandbox"
IMAGE_NAME="laney-sandbox"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="$SCRIPT_DIR/Dockerfile.laney-sandbox"
WORKSPACE_DIR="$HOME/.holocene/sandbox"  # Shared directory for file I/O

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

check_podman() {
    if ! command -v podman &> /dev/null; then
        warn "Podman not found. Installing..."
        sudo apt-get update
        sudo apt-get install -y podman
    fi
    info "Podman version: $(sudo podman --version)"
}

build_image() {
    info "Building $IMAGE_NAME image..."
    sudo podman build -t "$IMAGE_NAME" -f "$DOCKERFILE" "$SCRIPT_DIR"
    info "Image built successfully"
}

start_container() {
    # Ensure workspace directory exists
    mkdir -p "$WORKSPACE_DIR"

    # Check if container exists
    if sudo podman container exists "$CONTAINER_NAME" 2>/dev/null; then
        if sudo podman ps -q -f "name=$CONTAINER_NAME" | grep -q .; then
            info "Container $CONTAINER_NAME is already running"
        else
            info "Starting existing container $CONTAINER_NAME..."
            sudo podman start "$CONTAINER_NAME"
        fi
    else
        info "Creating and starting container $CONTAINER_NAME..."
        sudo podman run -d \
            --name "$CONTAINER_NAME" \
            --restart unless-stopped \
            -v "$WORKSPACE_DIR:/workspace:Z" \
            "$IMAGE_NAME"
    fi
    info "Container is running"
    info "Workspace: $WORKSPACE_DIR (mounted at /workspace in container)"
}

stop_container() {
    if sudo podman container exists "$CONTAINER_NAME" 2>/dev/null; then
        info "Stopping container $CONTAINER_NAME..."
        sudo podman stop "$CONTAINER_NAME" 2>/dev/null || true
    else
        warn "Container $CONTAINER_NAME does not exist"
    fi
}

remove_container() {
    if sudo podman container exists "$CONTAINER_NAME" 2>/dev/null; then
        info "Removing container $CONTAINER_NAME..."
        sudo podman rm -f "$CONTAINER_NAME" 2>/dev/null || true
    fi
}

show_status() {
    echo ""
    echo "=== Laney Sandbox Status ==="
    if sudo podman container exists "$CONTAINER_NAME" 2>/dev/null; then
        sudo podman ps -a -f "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Created}}"
        echo ""
        echo "Test command:"
        echo "  sudo podman exec $CONTAINER_NAME python3 -c \"import numpy; print(f'NumPy {numpy.__version__}')\""
    else
        warn "Container $CONTAINER_NAME does not exist"
        echo "Run: bash setup_sandbox.sh setup"
    fi
    echo ""
}

case "${1:-setup}" in
    setup)
        info "Setting up Laney sandbox..."
        check_podman
        build_image
        start_container
        show_status
        ;;
    rebuild)
        info "Rebuilding Laney sandbox..."
        stop_container
        remove_container
        build_image
        start_container
        show_status
        ;;
    reset)
        info "Resetting Laney sandbox (fresh workspace)..."
        stop_container
        remove_container
        start_container
        show_status
        ;;
    stop)
        stop_container
        ;;
    start)
        start_container
        ;;
    status)
        show_status
        ;;
    shell)
        info "Opening shell in $CONTAINER_NAME..."
        sudo podman exec -it "$CONTAINER_NAME" /bin/bash
        ;;
    logs)
        sudo podman logs "$CONTAINER_NAME"
        ;;
    *)
        echo "Usage: $0 {setup|rebuild|reset|stop|start|status|shell|logs}"
        exit 1
        ;;
esac
