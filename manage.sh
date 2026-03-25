#!/usr/bin/env bash
set -euo pipefail

SERVICE=snipe
PORT=8509  # Vue web UI (nginx)
COMPOSE_FILE="compose.yml"

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|open|update}"
    exit 1
}

cmd="${1:-help}"
shift || true

case "$cmd" in
    start)
        docker compose -f "$COMPOSE_FILE" up -d
        echo "$SERVICE started on http://localhost:$PORT"
        ;;
    stop)
        docker compose -f "$COMPOSE_FILE" down
        ;;
    restart)
        docker compose -f "$COMPOSE_FILE" down
        docker compose -f "$COMPOSE_FILE" up -d
        echo "$SERVICE restarted on http://localhost:$PORT"
        ;;
    status)
        docker compose -f "$COMPOSE_FILE" ps
        ;;
    logs)
        docker compose -f "$COMPOSE_FILE" logs -f "${@:-$SERVICE}"
        ;;
    open)
        xdg-open "http://localhost:$PORT" 2>/dev/null || open "http://localhost:$PORT"
        ;;
    update)
        docker compose -f "$COMPOSE_FILE" pull
        docker compose -f "$COMPOSE_FILE" up -d --build
        ;;
    *)
        usage
        ;;
esac
