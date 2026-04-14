#!/usr/bin/env bash
# Snipe — self-hosted installer
#
# Supports two install paths:
#   Docker (recommended) — everything in containers, no system Python deps required
#   Bare metal           — conda or pip venv + uvicorn, for machines without Docker
#
# Usage:
#   bash install.sh               # interactive (auto-detects Docker)
#   bash install.sh --docker      # Docker Compose setup only
#   bash install.sh --bare-metal  # conda or venv + uvicorn
#   bash install.sh --help
#
# No account or API key required. eBay credentials are optional (faster searches).

set -euo pipefail

# ── Terminal colours ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

info()   { echo -e "${BLUE}▶${NC} $*"; }
ok()     { echo -e "${GREEN}✓${NC} $*"; }
warn()   { echo -e "${YELLOW}⚠${NC}  $*"; }
error()  { echo -e "${RED}✗${NC} $*" >&2; }
header() { echo; echo -e "${BOLD}$*${NC}"; printf '%0.s─' {1..60}; echo; }
dim()    { echo -e "${DIM}$*${NC}"; }
ask()    { echo -e "${CYAN}?${NC} ${BOLD}$*${NC}"; }
fail()   { error "$*"; exit 1; }

# ── Paths ──────────────────────────────────────────────────────────────────────
SNIPE_CONFIG_DIR="${HOME}/.config/circuitforge"
SNIPE_ENV_FILE="${SNIPE_CONFIG_DIR}/snipe.env"
SNIPE_VENV_DIR="${SNIPE_CONFIG_DIR}/venv"
FORGEJO="https://git.opensourcesolarpunk.com/Circuit-Forge"

# Default install directory. Overridable:
#   SNIPE_DIR=/opt/snipe bash install.sh
SNIPE_INSTALL_DIR="${SNIPE_DIR:-${HOME}/snipe}"

# ── Argument parsing ───────────────────────────────────────────────────────────
MODE_FORCE=""
for arg in "$@"; do
    case "$arg" in
        --bare-metal) MODE_FORCE="bare-metal" ;;
        --docker)     MODE_FORCE="docker" ;;
        --help|-h)
            echo "Usage: bash install.sh [--docker|--bare-metal|--help]"
            echo
            echo "  --docker      Docker Compose install (recommended)"
            echo "  --bare-metal  conda or pip venv + uvicorn"
            echo "  --help        Show this message"
            echo
            echo "  Set SNIPE_DIR=/path to change the install directory (default: ~/snipe)"
            exit 0
            ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

# ── Banner ─────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}  🎯 Snipe — eBay listing intelligence${NC}"
echo -e "${DIM}  Bid with confidence. Privacy-first, no account required.${NC}"
echo -e "${DIM}  Part of the Circuit Forge LLC suite (BSL 1.1)${NC}"
echo

# ── System checks ──────────────────────────────────────────────────────────────
header "System checks"

HAS_DOCKER=false
HAS_CONDA=false
HAS_CONDA_CMD=""
HAS_PYTHON=false
HAS_NODE=false
HAS_CHROMIUM=false
HAS_XVFB=false

command -v git >/dev/null 2>&1 || fail "Git is required. Install: sudo apt-get install git"
ok "Git found"

docker compose version >/dev/null 2>&1 && HAS_DOCKER=true
if $HAS_DOCKER; then ok "Docker (Compose plugin) found"; fi

# Detect conda / mamba / micromamba in preference order
for _c in conda mamba micromamba; do
    if command -v "$_c" >/dev/null 2>&1; then
        HAS_CONDA=true
        HAS_CONDA_CMD="$_c"
        ok "Conda manager found: $_c"
        break
    fi
done

# Python 3.11+ check
if command -v python3 >/dev/null 2>&1; then
    _py_ok=$(python3 -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null || echo "False")
    if [[ "$_py_ok" == "True" ]]; then
        HAS_PYTHON=true
        ok "Python 3.11+ found ($(python3 --version))"
    else
        warn "Python found but version is below 3.11 ($(python3 --version)) — bare-metal path may fail"
    fi
fi

command -v node >/dev/null 2>&1 && HAS_NODE=true
if $HAS_NODE; then ok "Node.js found ($(node --version))"; fi

# Chromium / Google Chrome — needed for the Kasada-bypass scraper
for _chrome in google-chrome chromium-browser chromium; do
    if command -v "$_chrome" >/dev/null 2>&1; then
        HAS_CHROMIUM=true
        ok "Chromium/Chrome found: $_chrome"
        break
    fi
done
if ! $HAS_CHROMIUM; then
    warn "Chromium / Google Chrome not found."
    warn "Snipe uses headed Chromium + Xvfb to bypass eBay's Kasada anti-bot."
    warn "The installer will install Chromium via Playwright. If that fails,"
    warn "add eBay API credentials to .env to use the API adapter instead."
fi

# Xvfb — virtual framebuffer for headed Chromium on headless servers
command -v Xvfb >/dev/null 2>&1 && HAS_XVFB=true
if $HAS_XVFB; then ok "Xvfb found"; fi

# ── Mode selection ─────────────────────────────────────────────────────────────
header "Install mode"

INSTALL_MODE=""
if [[ -n "$MODE_FORCE" ]]; then
    INSTALL_MODE="$MODE_FORCE"
    info "Mode forced: $INSTALL_MODE"
elif $HAS_DOCKER; then
    INSTALL_MODE="docker"
    ok "Docker available — using Docker install (recommended)"
    dim "  Pass --bare-metal to override"
elif $HAS_PYTHON; then
    INSTALL_MODE="bare-metal"
    warn "Docker not found — using bare-metal install"
else
    fail "Docker or Python 3.11+ is required. Install Docker: https://docs.docker.com/get-docker/"
fi

# ── Clone repos ───────────────────────────────────────────────────────────────
header "Clone repositories"

# compose.yml and the Dockerfile both use context: .. (parent directory), so
# snipe/ and circuitforge-core/ must be siblings inside SNIPE_INSTALL_DIR.
REPO_DIR="$SNIPE_INSTALL_DIR"
SNIPE_DIR_ACTUAL="$REPO_DIR/snipe"
CORE_DIR="$REPO_DIR/circuitforge-core"

_clone_or_pull() {
    local label="$1" url="$2" dest="$3"
    if [[ -d "$dest/.git" ]]; then
        info "$label already cloned — pulling latest..."
        git -C "$dest" pull --ff-only
    else
        info "Cloning $label..."
        mkdir -p "$(dirname "$dest")"
        git clone "$url" "$dest"
    fi
    ok "$label → $dest"
}

_clone_or_pull "snipe" "$FORGEJO/snipe.git" "$SNIPE_DIR_ACTUAL"
_clone_or_pull "circuitforge-core" "$FORGEJO/circuitforge-core.git" "$CORE_DIR"

# ── Config file ────────────────────────────────────────────────────────────────
header "Configuration"

ENV_FILE="$SNIPE_DIR_ACTUAL/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$SNIPE_DIR_ACTUAL/.env.example" "$ENV_FILE"
    # Disable webhook signature verification for local installs
    # (no production eBay key yet — the endpoint won't be registered)
    sed -i 's/^EBAY_WEBHOOK_VERIFY_SIGNATURES=true/EBAY_WEBHOOK_VERIFY_SIGNATURES=false/' "$ENV_FILE"
    ok ".env created from .env.example"
    echo
    dim "  Snipe works out of the box with no API keys (scraper mode)."
    dim "  Add EBAY_APP_ID / EBAY_CERT_ID later for faster searches (optional)."
    dim "  Edit: $ENV_FILE"
    echo
else
    info ".env already exists — skipping (delete to reset defaults)"
fi

# ── License key (optional) ─────────────────────────────────────────────────────
header "CircuitForge license key (optional)"
dim "  Snipe is free to self-host. A Paid/Premium key unlocks cloud features"
dim "  (photo analysis, eBay OAuth). Skip this if you don't have one."
echo
ask "Enter your license key, or press Enter to skip:"
read -r _license_key || true

if [[ -n "${_license_key:-}" ]]; then
    _key_re='^CFG-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$'
    if echo "$_license_key" | grep -qP "$_key_re" 2>/dev/null || \
       echo "$_license_key" | grep -qE "$_key_re" 2>/dev/null; then
        # Append / uncomment Heimdall vars in .env
        if grep -q "^# HEIMDALL_URL=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s|^# HEIMDALL_URL=.*|HEIMDALL_URL=https://license.circuitforge.tech|" "$ENV_FILE"
        else
            echo "HEIMDALL_URL=https://license.circuitforge.tech" >> "$ENV_FILE"
        fi
        # Write or replace CF_LICENSE_KEY
        if grep -q "^CF_LICENSE_KEY=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s|^CF_LICENSE_KEY=.*|CF_LICENSE_KEY=${_license_key}|" "$ENV_FILE"
        else
            echo "CF_LICENSE_KEY=${_license_key}" >> "$ENV_FILE"
        fi
        ok "License key saved to .env"
    else
        warn "Key format not recognised (expected CFG-XXXX-XXXX-XXXX-XXXX) — skipping."
        warn "Edit $ENV_FILE to add it manually."
    fi
else
    info "No license key entered — self-hosted free tier."
fi

# ── Docker install ─────────────────────────────────────────────────────────────
_install_docker() {
    header "Docker install"

    cd "$SNIPE_DIR_ACTUAL"
    info "Building Docker images (~1 GB download on first run)..."
    docker compose build

    info "Starting Snipe..."
    docker compose up -d

    echo
    ok "Snipe is running!"
    printf '%0.s─' {1..60}; echo
    echo -e "  ${GREEN}Web UI:${NC}  http://localhost:8509"
    echo -e "  ${GREEN}API:${NC}     http://localhost:8510/docs"
    echo
    echo -e "  ${DIM}Manage:  cd $SNIPE_DIR_ACTUAL && ./manage.sh {start|stop|restart|logs|test}${NC}"
    printf '%0.s─' {1..60}; echo
    echo
}

# ── Bare-metal install ─────────────────────────────────────────────────────────
_install_xvfb() {
    if $HAS_XVFB; then return; fi
    info "Installing Xvfb (required for eBay scraper)..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y --no-install-recommends xvfb
        ok "Xvfb installed"
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y xorg-x11-server-Xvfb
        ok "Xvfb installed"
    elif command -v brew >/dev/null 2>&1; then
        warn "macOS: Xvfb not available via Homebrew."
        warn "The scraper (Kasada bypass) will not work on macOS."
        warn "Add eBay API credentials to .env to use the API adapter instead."
    else
        warn "Could not install Xvfb automatically. Install it with your system package manager."
        warn "  Debian/Ubuntu: sudo apt-get install xvfb"
        warn "  Fedora/RHEL:   sudo dnf install xorg-x11-server-Xvfb"
    fi
}

_setup_python_env() {
    if $HAS_CONDA; then
        info "Setting up conda environment (manager: $HAS_CONDA_CMD)..."
        _env_name="cf"
        if "$HAS_CONDA_CMD" env list 2>/dev/null | grep -q "^${_env_name} "; then
            info "Conda env '$_env_name' already exists — updating packages..."
        else
            "$HAS_CONDA_CMD" create -n "$_env_name" python=3.11 -y
        fi
        "$HAS_CONDA_CMD" run -n "$_env_name" pip install --quiet -e "$CORE_DIR"
        "$HAS_CONDA_CMD" run -n "$_env_name" pip install --quiet -e "$SNIPE_DIR_ACTUAL"
        "$HAS_CONDA_CMD" run -n "$_env_name" playwright install chromium
        "$HAS_CONDA_CMD" run -n "$_env_name" playwright install-deps chromium
        PYTHON_BIN="$HAS_CONDA_CMD run -n $_env_name"
        ok "Conda environment '$_env_name' ready"
    else
        info "Setting up pip venv at $SNIPE_VENV_DIR ..."
        mkdir -p "$SNIPE_CONFIG_DIR"
        python3 -m venv "$SNIPE_VENV_DIR"
        "$SNIPE_VENV_DIR/bin/pip" install --quiet -e "$CORE_DIR"
        "$SNIPE_VENV_DIR/bin/pip" install --quiet -e "$SNIPE_DIR_ACTUAL"
        "$SNIPE_VENV_DIR/bin/playwright" install chromium
        "$SNIPE_VENV_DIR/bin/playwright" install-deps chromium
        PYTHON_BIN="$SNIPE_VENV_DIR/bin"
        ok "Python venv ready at $SNIPE_VENV_DIR"
    fi
}

_build_frontend() {
    if ! $HAS_NODE; then
        warn "Node.js not found — skipping frontend build."
        warn "Install Node.js 20+ from https://nodejs.org and re-run install.sh."
        warn "Until then, access the API at http://localhost:8510/docs"
        return
    fi
    info "Building Vue frontend..."
    cd "$SNIPE_DIR_ACTUAL/web"
    npm ci --prefer-offline --silent
    npm run build
    cd "$SNIPE_DIR_ACTUAL"
    ok "Frontend built → web/dist/"
}

_write_start_scripts() {
    # start-local.sh — launches the FastAPI server
    cat > "$SNIPE_DIR_ACTUAL/start-local.sh" << 'STARTSCRIPT'
#!/usr/bin/env bash
# Start Snipe API (bare-metal / no-Docker mode)
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f "$HOME/.config/circuitforge/venv/bin/uvicorn" ]]; then
    UVICORN="$HOME/.config/circuitforge/venv/bin/uvicorn"
elif command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -q "^cf "; then
    UVICORN="conda run -n cf uvicorn"
elif command -v mamba >/dev/null 2>&1 && mamba env list 2>/dev/null | grep -q "^cf "; then
    UVICORN="mamba run -n cf uvicorn"
else
    echo "No Snipe Python environment found. Run install.sh first." >&2; exit 1
fi

mkdir -p data
echo "Starting Snipe API → http://localhost:8510 ..."
exec $UVICORN api.main:app --host 0.0.0.0 --port 8510 "${@}"
STARTSCRIPT
    chmod +x "$SNIPE_DIR_ACTUAL/start-local.sh"

    # serve-ui.sh — serves the built Vue frontend (dev only)
    cat > "$SNIPE_DIR_ACTUAL/serve-ui.sh" << 'UISCRIPT'
#!/usr/bin/env bash
# Serve the pre-built Vue frontend (dev only — use nginx for production).
# See docs/nginx-self-hosted.conf for a production nginx config.
cd "$(dirname "$0")/web/dist"
echo "Serving Snipe UI → http://localhost:8509 (Ctrl+C to stop)"
exec python3 -m http.server 8509
UISCRIPT
    chmod +x "$SNIPE_DIR_ACTUAL/serve-ui.sh"

    ok "Start scripts written"
}

_install_bare_metal() {
    header "Bare-metal install"
    _install_xvfb
    _setup_python_env
    _build_frontend
    _write_start_scripts

    echo
    ok "Snipe installed (bare-metal mode)"
    printf '%0.s─' {1..60}; echo
    echo -e "  ${GREEN}Start API:${NC}   cd $SNIPE_DIR_ACTUAL && ./start-local.sh"
    echo -e "  ${GREEN}Serve UI:${NC}    cd $SNIPE_DIR_ACTUAL && ./serve-ui.sh  ${DIM}(separate terminal)${NC}"
    echo -e "  ${GREEN}API docs:${NC}    http://localhost:8510/docs"
    echo -e "  ${GREEN}Web UI:${NC}      http://localhost:8509  ${DIM}(after ./serve-ui.sh)${NC}"
    echo
    echo -e "  ${DIM}For production, configure nginx to proxy /api/ to localhost:8510${NC}"
    echo -e "  ${DIM}and serve web/dist/ as the document root.${NC}"
    echo -e "  ${DIM}See: $SNIPE_DIR_ACTUAL/docs/nginx-self-hosted.conf${NC}"
    printf '%0.s─' {1..60}; echo
    echo
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    if [[ "$INSTALL_MODE" == "docker" ]]; then
        _install_docker
    else
        _install_bare_metal
    fi
}

main
