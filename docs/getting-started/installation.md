# Installation

## Requirements

- Docker with Compose plugin
- Git
- No API keys required to get started

## One-line install

```bash
bash <(curl -fsSL https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/raw/branch/main/install.sh)
```

This clones the repo to `~/snipe` and starts the stack. Open **http://localhost:8509** when it completes.

## Manual install

Snipe's API image is built from a context that includes `circuitforge-core`. Both repos must sit as siblings:

```
workspace/
├── snipe/               ← this repo
└── circuitforge-core/   ← required sibling
```

```bash
mkdir snipe-workspace && cd snipe-workspace
git clone https://git.opensourcesolarpunk.com/Circuit-Forge/snipe.git
git clone https://git.opensourcesolarpunk.com/Circuit-Forge/circuitforge-core.git
cd snipe
cp .env.example .env
./manage.sh start
```

## Managing the stack

```bash
./manage.sh start     # build and start all containers
./manage.sh stop      # stop containers
./manage.sh restart   # rebuild and restart
./manage.sh status    # container health
./manage.sh logs      # tail logs
./manage.sh open      # open in browser
```

## Updating

```bash
git pull
./manage.sh restart
```

## Ports

| Service | Default port |
|---------|-------------|
| Web UI  | 8509        |
| API     | 8510        |

Both ports are configurable in `.env`.

---

## No-Docker install (bare metal)

Run `install.sh --bare-metal` to skip Docker and install via conda or venv instead.
This sets up the Python environment, builds the Vue frontend, and writes helper scripts.

**Requirements:** Python 3.11+, Node.js 20+, `xvfb` (for the eBay scraper).

```bash
bash <(curl -fsSL https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/raw/branch/main/install.sh) --bare-metal
```

After install, you get two scripts:

| Script | What it does |
|--------|-------------|
| `./start-local.sh` | Start the FastAPI API on port 8510 |
| `./serve-ui.sh` | Serve the built frontend with `python3 -m http.server 8509` (dev only) |

`serve-ui.sh` is single-threaded and suitable for testing only. For a real deployment, use nginx.

### nginx config (production bare-metal)

Install nginx, copy the sample config, and reload:

```bash
sudo cp docs/nginx-self-hosted.conf /etc/nginx/sites-available/snipe
sudo ln -s /etc/nginx/sites-available/snipe /etc/nginx/sites-enabled/snipe
# Edit the file — update `root` to your actual web/dist path
sudo nginx -t && sudo systemctl reload nginx
```

See [`docs/nginx-self-hosted.conf`](../nginx-self-hosted.conf) for the full config with TLS notes.

### Chromium / Xvfb note

Snipe uses headed Chromium via Xvfb to bypass Kasada (the anti-bot layer on eBay seller profile pages). If Chromium is not detected, the scraper falls back to the eBay Browse API — add `EBAY_APP_ID` / `EBAY_CERT_ID` to `.env` so that fallback has credentials.

The installer detects and installs Xvfb automatically on Debian/Ubuntu/Fedora. Chromium is installed via `playwright install chromium`. macOS is not supported for the scraper path.
