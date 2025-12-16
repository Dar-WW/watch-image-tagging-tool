#!/bin/bash
# CVAT Local Management Script
# Usage: ./run_cvat_local.sh [start|stop|restart|status|logs|shell|create-superuser]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
export CVAT_SHARE_DIR="${CVAT_SHARE_DIR:-$(cd .. && pwd)/downloaded_images}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
}

docker_compose_cmd() {
    if docker compose version &> /dev/null 2>&1; then
        docker compose "$@"
    else
        docker-compose "$@"
    fi
}

start_cvat() {
    print_status "Starting CVAT..."
    print_status "Shared images directory: $CVAT_SHARE_DIR"
    
    if [ ! -d "$CVAT_SHARE_DIR" ]; then
        print_warning "Shared directory does not exist: $CVAT_SHARE_DIR"
        print_warning "Creating directory..."
        mkdir -p "$CVAT_SHARE_DIR"
    fi

    docker_compose_cmd up -d

    print_status "Waiting for CVAT to start..."
    sleep 10

    print_status "CVAT is now running!"
    echo ""
    echo -e "${GREEN}Access CVAT at:${NC} http://localhost:8080"
    echo ""
    echo "First time setup:"
    echo "  1. Run: ./run_cvat_local.sh create-superuser"
    echo "  2. Login with your credentials at http://localhost:8080"
    echo ""
}

stop_cvat() {
    print_status "Stopping CVAT..."
    docker_compose_cmd down
    print_status "CVAT stopped."
}

restart_cvat() {
    stop_cvat
    start_cvat
}

show_status() {
    print_status "CVAT container status:"
    docker_compose_cmd ps
}

show_logs() {
    if [ -z "$2" ]; then
        docker_compose_cmd logs -f
    else
        docker_compose_cmd logs -f "$2"
    fi
}

create_superuser() {
    print_status "Creating CVAT superuser..."
    docker exec -it cvat_server python manage.py createsuperuser
}

open_shell() {
    print_status "Opening shell in CVAT server container..."
    docker exec -it cvat_server bash
}

show_help() {
    echo "CVAT Local Management Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start           Start CVAT services"
    echo "  stop            Stop CVAT services"
    echo "  restart         Restart CVAT services"
    echo "  status          Show container status"
    echo "  logs [service]  Show logs (optionally for specific service)"
    echo "  shell           Open shell in CVAT server container"
    echo "  create-superuser Create admin user for CVAT"
    echo "  help            Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  CVAT_SHARE_DIR  Path to shared images directory (default: ../downloaded_images)"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start CVAT"
    echo "  $0 create-superuser         # Create admin user"
    echo "  $0 logs cvat_server         # View server logs"
    echo ""
}

# Main
check_docker

case "${1:-help}" in
    start)
        start_cvat
        ;;
    stop)
        stop_cvat
        ;;
    restart)
        restart_cvat
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$@"
        ;;
    shell)
        open_shell
        ;;
    create-superuser)
        create_superuser
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
