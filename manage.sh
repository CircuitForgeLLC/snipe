#!/usr/bin/env bash
set -euo pipefail

SERVICE=snipe
PORT=8509        # Vue web UI (nginx)
API_PORT=8510    # FastAPI
COMPOSE_FILE="compose.yml"

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|open|build|update|test}"
    echo ""
    echo "  start    Build (if needed) and start all services"
    echo "  stop     Stop and remove containers"
    echo "  restart  Stop then start"
    echo "  status   Show running containers"
    echo "  logs     Follow logs (logs api | logs web | logs — defaults to all)"
    echo "  open     Open web UI in browser"
    echo "  build    Rebuild Docker images without cache"
    echo "  update   Pull latest images and rebuild"
    echo "  test     Run pytest test suite in the api container"
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
            conda run -n job-seeker python -m pytest /app/snipe/tests/ -v "${@}"
        ;;
    *)
        usage
        ;;
esac
