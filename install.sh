#!/usr/bin/env bash
# Snipe — self-hosted install script
#
# Supports two install paths:
#   Docker (recommended) — everything in containers, no system Python deps required
#   No-Docker            — conda or venv + direct uvicorn, for machines without Docker
#
# Usage:
#   bash install.sh                    # installs to ~/snipe
#   bash install.sh /opt/snipe         # custom install directory
#   bash install.sh ~/snipe --no-docker  # force no-Docker path even if Docker present
#
# Requirements (Docker path):   Docker with Compose plugin, Git
# Requirements (no-Docker path): Python 3.11+, Node.js 20+, Git, xvfb (system)

set -euo pipefail

INSTALL_DIR="${1:-$HOME/snipe}"
FORCE_NO_DOCKER="${2:-}"
FORGEJO="https://git.opensourcesolarpunk.com/Circuit-Forge"
CONDA_ENV="cf"

info()  { echo "  [snipe] $*"; }
ok()    { echo "✓ $*"; }
warn()  { echo "! $*"; }
fail()  { echo "✗ $*" >&2; exit 1; }
hr()    { echo "────────────────────────────────────────────────────────"; }

echo ""
echo "  Snipe — self-hosted installer"
echo "  Install directory: $INSTALL_DIR"
echo ""

# ── Detect capabilities ──────────────────────────────────────────────────────

HAS_DOCKER=false
HAS_CONDA=false
HAS_PYTHON=false
HAS_NODE=false

docker compose version >/dev/null 2>&1 && HAS_DOCKER=true
conda --version >/dev/null 2>&1 && HAS_CONDA=true
python3 --version >/dev/null 2>&1 && HAS_PYTHON=true
node --version >/dev/null 2>&1 && HAS_NODE=true
command -v git >/dev/null 2>&1 || fail "Git is required. Install with: sudo apt-get install git"

# Honour --no-docker flag
[[ "$FORCE_NO_DOCKER" == "--no-docker" ]] && HAS_DOCKER=false

if $HAS_DOCKER; then
    INSTALL_PATH="docker"
    ok "Docker found — using Docker install path (recommended)"
elif $HAS_PYTHON; then
    INSTALL_PATH="python"
    warn "Docker not found — using no-Docker path (conda or venv)"
else
    fail "Docker or Python 3.11+ is required. Install Docker: https://docs.docker.com/get-docker/"
fi

# ── Clone repos ──────────────────────────────────────────────────────────────

# compose.yml and the Dockerfile both use context: .. (parent directory), so
# snipe/ and circuitforge-core/ must be siblings inside INSTALL_DIR.
SNIPE_DIR="$INSTALL_DIR/snipe"
CORE_DIR="$INSTALL_DIR/circuitforge-core"

if [[ -d "$SNIPE_DIR" ]]; then
    info "Snipe already cloned — pulling latest..."
    git -C "$SNIPE_DIR" pull --ff-only
else
    info "Cloning Snipe..."
    mkdir -p "$INSTALL_DIR"
    git clone "$FORGEJO/snipe.git" "$SNIPE_DIR"
fi
ok "Snipe → $SNIPE_DIR"

if [[ -d "$CORE_DIR" ]]; then
    info "circuitforge-core already cloned — pulling latest..."
    git -C "$CORE_DIR" pull --ff-only
else
    info "Cloning circuitforge-core (shared library)..."
    git clone "$FORGEJO/circuitforge-core.git" "$CORE_DIR"
fi
ok "circuitforge-core → $CORE_DIR"

# ── Configure environment ────────────────────────────────────────────────────

ENV_FILE="$SNIPE_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$SNIPE_DIR/.env.example" "$ENV_FILE"
    # Safe defaults for local installs — no eBay registration, no Heimdall
    sed -i 's/^EBAY_WEBHOOK_VERIFY_SIGNATURES=true/EBAY_WEBHOOK_VERIFY_SIGNATURES=false/' "$ENV_FILE"
    ok ".env created from .env.example"
    echo ""
    info "Snipe works out of the box with no API keys."
    info "Add EBAY_APP_ID / EBAY_CERT_ID later for faster searches (optional)."
    echo ""
else
    info ".env already exists — skipping (delete it to reset)"
fi

cd "$SNIPE_DIR"

# ── Docker install path ───────────────────────────────────────────────────────

if [[ "$INSTALL_PATH" == "docker" ]]; then
    info "Building Docker images (~1 GB download on first run)..."
    docker compose build

    info "Starting Snipe..."
    docker compose up -d

    echo ""
    ok "Snipe is running!"
    hr
    echo "  Web UI:  http://localhost:8509"
    echo "  API:     http://localhost:8510/docs"
    echo ""
    echo "  Manage:  cd $SNIPE_DIR && ./manage.sh {start|stop|restart|logs|test}"
    hr
    echo ""
    exit 0
fi

# ── No-Docker install path ───────────────────────────────────────────────────

# System deps: Xvfb is required for Playwright (Kasada bypass via headed Chromium)
if ! command -v Xvfb >/dev/null 2>&1; then
    info "Installing Xvfb (required for eBay scraper)..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y --no-install-recommends xvfb
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y xorg-x11-server-Xvfb
    elif command -v brew >/dev/null 2>&1; then
        warn "macOS: Xvfb not available. The scraper fallback may fail."
        warn "Add eBay API credentials to .env to use the API adapter instead."
    else
        warn "Could not install Xvfb automatically. Install it with your package manager."
    fi
fi

# ── Python environment setup ─────────────────────────────────────────────────

if $HAS_CONDA; then
    info "Setting up conda environment '$CONDA_ENV'..."
    if conda env list | grep -q "^$CONDA_ENV "; then
        info "Conda env '$CONDA_ENV' already exists — updating..."
        conda run -n "$CONDA_ENV" pip install --quiet -e "$CORE_DIR"
        conda run -n "$CONDA_ENV" pip install --quiet -e "$SNIPE_DIR"
    else
        conda create -n "$CONDA_ENV" python=3.11 -y
        conda run -n "$CONDA_ENV" pip install --quiet -e "$CORE_DIR"
        conda run -n "$CONDA_ENV" pip install --quiet -e "$SNIPE_DIR"
    fi
    conda run -n "$CONDA_ENV" playwright install chromium
    conda run -n "$CONDA_ENV" playwright install-deps chromium
    PYTHON_RUN="conda run -n $CONDA_ENV"
    ok "Conda environment '$CONDA_ENV' ready"
else
    info "Setting up Python venv at $SNIPE_DIR/.venv ..."
    python3 -m venv "$SNIPE_DIR/.venv"
    "$SNIPE_DIR/.venv/bin/pip" install --quiet -e "$CORE_DIR"
    "$SNIPE_DIR/.venv/bin/pip" install --quiet -e "$SNIPE_DIR"
    "$SNIPE_DIR/.venv/bin/playwright" install chromium
    "$SNIPE_DIR/.venv/bin/playwright" install-deps chromium
    PYTHON_RUN="$SNIPE_DIR/.venv/bin"
    ok "Python venv ready at $SNIPE_DIR/.venv"
fi

# ── Frontend ─────────────────────────────────────────────────────────────────

if $HAS_NODE; then
    info "Building Vue frontend..."
    cd "$SNIPE_DIR/web"
    npm ci --prefer-offline --silent
    npm run build
    cd "$SNIPE_DIR"
    ok "Frontend built → web/dist/"
else
    warn "Node.js not found — skipping frontend build."
    warn "Install Node.js 20+ from https://nodejs.org and re-run install.sh to build the UI."
    warn "Until then, you can access the API directly at http://localhost:8510/docs"
fi

# ── Write start/stop scripts ─────────────────────────────────────────────────

cat > "$SNIPE_DIR/start-local.sh" << 'STARTSCRIPT'
#!/usr/bin/env bash
# Start Snipe without Docker (API only — run from the snipe/ directory)
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .venv/bin/uvicorn ]]; then
    UVICORN=".venv/bin/uvicorn"
elif command -v conda >/dev/null 2>&1 && conda env list | grep -q "^cf "; then
    UVICORN="conda run -n cf uvicorn"
else
    echo "No Python env found. Run install.sh first." >&2; exit 1
fi

mkdir -p data
echo "Starting Snipe API on http://localhost:8510 ..."
$UVICORN api.main:app --host 0.0.0.0 --port 8510 "${@}"
STARTSCRIPT
chmod +x "$SNIPE_DIR/start-local.sh"

# Frontend serving (if built)
cat > "$SNIPE_DIR/serve-ui.sh" << 'UISCRIPT'
#!/usr/bin/env bash
# Serve the pre-built Vue frontend on port 8509 (dev only — use nginx for production)
cd "$(dirname "$0")/web/dist"
python3 -m http.server 8509
UISCRIPT
chmod +x "$SNIPE_DIR/serve-ui.sh"

echo ""
ok "Snipe installed (no-Docker mode)"
hr
echo "  Start API:     cd $SNIPE_DIR && ./start-local.sh"
echo "  Serve UI:      cd $SNIPE_DIR && ./serve-ui.sh  (separate terminal)"
echo "  API docs:      http://localhost:8510/docs"
echo "  Web UI:        http://localhost:8509  (after ./serve-ui.sh)"
echo ""
echo "  For production, point nginx at web/dist/ and proxy /api/ to localhost:8510"
hr
echo ""
