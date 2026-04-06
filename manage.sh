#!/usr/bin/env bash
set -euo pipefail

SERVICE=snipe
PORT=8509        # Vue web UI (nginx) — dev
API_PORT=8510    # FastAPI — dev
CLOUD_PORT=8514  # Vue web UI (nginx) — cloud (menagerie.circuitforge.tech/snipe)
COMPOSE_FILE="compose.yml"
CLOUD_COMPOSE_FILE="compose.cloud.yml"
CLOUD_PROJECT="snipe-cloud"

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|open|build|update|test"
    echo "           |cloud-start|cloud-stop|cloud-restart|cloud-status|cloud-logs|cloud-build}"
    echo ""
    echo "Dev:"
    echo "  start         Build (if needed) and start all services"
    echo "  stop          Stop and remove containers"
    echo "  restart       Stop then start"
    echo "  status        Show running containers"
    echo "  logs [svc]    Follow logs (api | web — defaults to all)"
    echo "  open          Open web UI in browser"
    echo "  build         Rebuild Docker images without cache"
    echo "  update        Pull latest images and rebuild"
    echo "  test          Run pytest test suite in the api container"
    echo ""
    echo "Cloud (menagerie.circuitforge.tech/snipe):"
    echo "  cloud-start   Build cloud images and start snipe-cloud project"
    echo "  cloud-stop    Stop cloud instance"
    echo "  cloud-restart Stop then start cloud instance"
    echo "  cloud-status  Show cloud containers"
    echo "  cloud-logs    Follow cloud logs [api|web — defaults to all]"
    echo "  cloud-build   Rebuild cloud images without cache (required after code changes)"
    exit 1
}

cmd="${1:-help}"
shift || true

case "$cmd" in
    start)
        docker compose -f "$COMPOSE_FILE" up -d
        echo "$SERVICE started — web: http://localhost:$PORT  api: http://localhost:$API_PORT"
        ;;
    stop)
        docker compose -f "$COMPOSE_FILE" down --remove-orphans
        ;;
    restart)
        docker compose -f "$COMPOSE_FILE" down --remove-orphans
        docker compose -f "$COMPOSE_FILE" up -d
        echo "$SERVICE restarted — http://localhost:$PORT"
        ;;
    status)
        docker compose -f "$COMPOSE_FILE" ps
        ;;
    logs)
        # logs [api|web]  — default: all services
        target="${1:-}"
        if [[ -n "$target" ]]; then
            docker compose -f "$COMPOSE_FILE" logs -f "$target"
        else
            docker compose -f "$COMPOSE_FILE" logs -f
        fi
        ;;
    open)
        xdg-open "http://localhost:$PORT" 2>/dev/null || open "http://localhost:$PORT" 2>/dev/null || \
            echo "Open http://localhost:$PORT in your browser"
        ;;
    build)
        docker compose -f "$COMPOSE_FILE" build --no-cache
        echo "Build complete."
        ;;
    update)
        docker compose -f "$COMPOSE_FILE" pull
        docker compose -f "$COMPOSE_FILE" up -d --build
        echo "$SERVICE updated — http://localhost:$PORT"
        ;;
    test)
        echo "Running test suite..."
        docker compose -f "$COMPOSE_FILE" exec api \
            python -m pytest /app/snipe/tests/ -v "${@}"
        ;;

    # ── Cloud commands ────────────────────────────────────────────────────────
    cloud-start)
        docker compose -f "$CLOUD_COMPOSE_FILE" -p "$CLOUD_PROJECT" up -d --build
        echo "$SERVICE cloud started — https://menagerie.circuitforge.tech/snipe"
        ;;
    cloud-stop)
        docker compose -p "$CLOUD_PROJECT" down --remove-orphans
        ;;
    cloud-restart)
        docker compose -p "$CLOUD_PROJECT" down --remove-orphans
        docker compose -f "$CLOUD_COMPOSE_FILE" -p "$CLOUD_PROJECT" up -d --build
        echo "$SERVICE cloud restarted — https://menagerie.circuitforge.tech/snipe"
        ;;
    cloud-status)
        docker compose -p "$CLOUD_PROJECT" ps
        ;;
    cloud-logs)
        target="${1:-}"
        if [[ -n "$target" ]]; then
            docker compose -p "$CLOUD_PROJECT" logs -f "$target"
        else
            docker compose -p "$CLOUD_PROJECT" logs -f
        fi
        ;;
    cloud-build)
        docker compose -f "$CLOUD_COMPOSE_FILE" -p "$CLOUD_PROJECT" build --no-cache
        echo "Cloud build complete. Run './manage.sh cloud-restart' to deploy."
        ;;

    *)
        usage
        ;;
esac
