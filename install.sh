#!/usr/bin/env bash
# Snipe — self-hosted install script
# Clones Snipe and its shared library (circuitforge-core) into a workspace,
# then starts the Docker stack.
#
# Usage:
#   bash install.sh                    # installs to ~/snipe
#   bash install.sh /opt/snipe         # custom install directory
#
# Requirements: Docker with Compose plugin, Git

set -euo pipefail

INSTALL_DIR="${1:-$HOME/snipe}"
FORGEJO="https://git.opensourcesolarpunk.com/Circuit-Forge"

info()  { echo "  [snipe] $*"; }
ok()    { echo "✓ $*"; }
fail()  { echo "✗ $*" >&2; exit 1; }

echo ""
echo "  Snipe — self-hosted installer"
echo "  Install directory: $INSTALL_DIR"
echo ""

# ── Pre-flight checks ────────────────────────────────────────────────────────

command -v docker  >/dev/null 2>&1 || fail "Docker is required. Install from https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is required (docker compose, not docker-compose)."
command -v git     >/dev/null 2>&1 || fail "Git is required."
ok "Docker $(docker --version | awk '{print $3}' | tr -d ,) and Git found."

# ── Clone repos ──────────────────────────────────────────────────────────────

# compose.yml builds with context: .. so both repos must be siblings.
SNIPE_DIR="$INSTALL_DIR/snipe"
CORE_DIR="$INSTALL_DIR/circuitforge-core"

if [[ -d "$SNIPE_DIR" ]]; then
    info "Snipe already exists at $SNIPE_DIR — pulling latest..."
    git -C "$SNIPE_DIR" pull --ff-only
else
    info "Cloning Snipe..."
    mkdir -p "$INSTALL_DIR"
    git clone "$FORGEJO/snipe.git" "$SNIPE_DIR"
fi
ok "Snipe cloned to $SNIPE_DIR"

if [[ -d "$CORE_DIR" ]]; then
    info "circuitforge-core already exists — pulling latest..."
    git -C "$CORE_DIR" pull --ff-only
else
    info "Cloning circuitforge-core (shared library)..."
    git clone "$FORGEJO/circuitforge-core.git" "$CORE_DIR"
fi
ok "circuitforge-core cloned to $CORE_DIR"

# ── Configure environment ────────────────────────────────────────────────────

ENV_FILE="$SNIPE_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$SNIPE_DIR/.env.example" "$ENV_FILE"
    ok ".env created from .env.example"
    echo ""
    echo "  ┌────────────────────────────────────────────────────────┐"
    echo "  │  Next step: edit $ENV_FILE            │"
    echo "  │                                                        │"
    echo "  │  Snipe works out of the box with no API keys.         │"
    echo "  │  Add EBAY_APP_ID / EBAY_CERT_ID for faster searches   │"
    echo "  │  and full seller account age data (optional).          │"
    echo "  └────────────────────────────────────────────────────────┘"
    echo ""
else
    info ".env already exists — skipping (delete it to reset)"
fi

# ── Build and start ──────────────────────────────────────────────────────────

info "Building Docker images (first run downloads ~1 GB of dependencies)..."
cd "$SNIPE_DIR"
docker compose build

info "Starting Snipe..."
docker compose up -d

echo ""
ok "Snipe is running!"
echo ""
echo "  Web UI:  http://localhost:8509"
echo "  API:     http://localhost:8510/docs"
echo ""
echo "  Manage:  cd $SNIPE_DIR && ./manage.sh {start|stop|restart|logs|test}"
echo ""
