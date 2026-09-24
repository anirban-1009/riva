#!/usr/bin/env bash
# ==============================================================================
# Riva Dev Stack Manager: MLX Server, Riva AI Gateway & OpenClaw
# ==============================================================================
# Usage:
#   ./scripts/start_stack.sh [start|dev|stop|restart|status|logs|chat]
#
# Commands:
#   start    (default) Starts mlx_lm.server, Riva AI Gateway, and checks OpenClaw
#   dev      Starts MLX backend in background and runs Gateway in foreground with auto-reload
#   stop     Stops running mlx_lm.server and Riva AI Gateway processes
#   restart  Stops and restarts the stack
#   status   Checks health and port status of all three components
#   logs     Follows combined logs for MLX server and Riva Gateway
#   chat     Starts the stack and launches the OpenClaw interactive terminal UI
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Ports and Model Configuration
MLX_PORT="${MLX_PORT:-8081}"
GATEWAY_PORT="${GATEWAY_PORT:-8085}"
DEFAULT_MODEL="mlx-community/gemma-4-E4B-it-qat-4bit"

# Extract model from config.yml if available, otherwise fall back to default
if [[ -f "${REPO_ROOT}/config.yml" ]]; then
    CONFIG_MODEL=$(grep -E "^model:" "${REPO_ROOT}/config.yml" | head -n 1 | awk '{print $2}' | tr -d '"'\''')
    MODEL="${CONFIG_MODEL:-$DEFAULT_MODEL}"
else
    MODEL="$DEFAULT_MODEL"
fi

# Log and PID Paths
LOG_DIR="${HOME}/.riva/logs"
mkdir -p "${LOG_DIR}"
MLX_LOG="${LOG_DIR}/mlx_server.log"
GATEWAY_LOG="${LOG_DIR}/riva_gateway.log"
MLX_PID_FILE="${LOG_DIR}/mlx_server.pid"
GATEWAY_PID_FILE="${LOG_DIR}/riva_gateway.pid"

# Colors for output
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✔${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✖${NC} $1"
}

# ------------------------------------------------------------------------------
# Helpers: Port & Health Checks
# ------------------------------------------------------------------------------
is_port_in_use() {
    local port="$1"
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1 || return 1
    return 0
}

get_pid_on_port() {
    local port="$1"
    (lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true) | awk 'NR==2 {print $2}'
}

wait_for_http_200() {
    local url="$1"
    local max_retries="$2"
    local service_name="$3"
    local count=0

    echo -n "Waiting for ${service_name} to be ready..."
    while [[ $count -lt $max_retries ]]; do
        local status_code
        status_code=$(curl -s -o /dev/null -w "%{http_code}" "${url}" 2>/dev/null || echo "000")
        if [[ "${status_code}" == "200" ]]; then
            echo -e " ${GREEN}ready!${NC}"
            return 0
        fi
        sleep 1
        echo -n "."
        count=$((count + 1))
    done
    echo -e " ${RED}timed out!${NC}"
    return 1
}

# ------------------------------------------------------------------------------
# Start Components
# ------------------------------------------------------------------------------
start_mlx() {
    log_info "Checking MLX Server on port ${MLX_PORT}..."
    if is_port_in_use "${MLX_PORT}"; then
        local pid
        pid=$(get_pid_on_port "${MLX_PORT}")
        log_success "MLX Server is already running on port ${MLX_PORT} (PID: ${pid})."
        return 0
    fi

    if ! command -v mlx_lm.server >/dev/null 2>&1; then
        log_error "mlx_lm.server command not found in PATH."
        log_error "Please ensure mlx-lm is installed in your Python environment."
        return 1
    fi

    log_info "Starting mlx_lm.server with model '${MODEL}' (1GB KV cache bound)..."
    nohup mlx_lm.server --model "${MODEL}" --port "${MLX_PORT}" \
        --prompt-cache-bytes 1073741824 \
        --prompt-cache-size 2 > "${MLX_LOG}" 2>&1 &
    local pid=$!
    echo "${pid}" > "${MLX_PID_FILE}"
    disown "${pid}" 2>/dev/null || true

    if ! wait_for_http_200 "http://127.0.0.1:${MLX_PORT}/v1/models" 45 "MLX Server"; then
        log_error "MLX Server failed to start. Showing last 20 lines of log (${MLX_LOG}):"
        tail -n 20 "${MLX_LOG}"
        return 1
    fi
    log_success "MLX Server is healthy on port ${MLX_PORT} (PID: ${pid})."
}

start_gateway() {
    log_info "Checking Riva AI Gateway on port ${GATEWAY_PORT}..."
    if is_port_in_use "${GATEWAY_PORT}"; then
        local pid
        pid=$(get_pid_on_port "${GATEWAY_PORT}")
        log_success "Riva AI Gateway is already running on port ${GATEWAY_PORT} (PID: ${pid})."
        return 0
    fi

    if ! command -v uv >/dev/null 2>&1; then
        log_error "uv command not found in PATH."
        return 1
    fi

    log_info "Starting Riva AI Gateway via uv..."
    cd "${REPO_ROOT}"

    # Use uvicorn module execution directly to support both dev and feature branches
    nohup uv run --package riva-agent uvicorn riva_agent.api.gateway:app \
        --host 0.0.0.0 --port "${GATEWAY_PORT}" > "${GATEWAY_LOG}" 2>&1 &
    local pid=$!
    echo "${pid}" > "${GATEWAY_PID_FILE}"
    disown "${pid}" 2>/dev/null || true

    if ! wait_for_http_200 "http://127.0.0.1:${GATEWAY_PORT}/v1/models" 20 "Riva Gateway"; then
        log_error "Riva AI Gateway failed to start. Showing last 20 lines of log (${GATEWAY_LOG}):"
        tail -n 20 "${GATEWAY_LOG}"
        return 1
    fi
    log_success "Riva AI Gateway is healthy on port ${GATEWAY_PORT} (PID: ${pid})."
}

check_or_start_openclaw() {
    log_info "Checking OpenClaw status..."
    if ! command -v openclaw >/dev/null 2>&1; then
        log_warn "openclaw CLI not found in PATH. Skipping OpenClaw checks."
        return 0
    fi

    # Verify if openclaw gateway service is running
    local oc_status
    oc_status=$(openclaw gateway status 2>&1 || true)
    if echo "${oc_status}" | grep -qi "running"; then
        log_success "OpenClaw Gateway service is active."
    else
        log_info "OpenClaw Gateway service not active, attempting to start/restart service..."
        openclaw gateway restart >/dev/null 2>&1 || openclaw gateway start >/dev/null 2>&1 || true
        log_success "OpenClaw Gateway service signaled."
    fi
}

# ------------------------------------------------------------------------------
# Stop Components
# ------------------------------------------------------------------------------
stop_service_on_port() {
    local port="$1"
    local name="$2"
    local pid_file="$3"

    local pid
    pid=$(get_pid_on_port "${port}")

    if [[ -z "${pid}" && -f "${pid_file}" ]]; then
        pid=$(cat "${pid_file}" 2>/dev/null || true)
    fi

    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
        log_info "Stopping ${name} (PID: ${pid})..."
        kill "${pid}" 2>/dev/null || true
        
        # Wait up to 5 seconds for graceful shutdown
        local count=0
        while kill -0 "${pid}" 2>/dev/null && [[ $count -lt 5 ]]; do
            sleep 1
            count=$((count + 1))
        done

        if kill -0 "${pid}" 2>/dev/null; then
            log_warn "${name} did not stop gracefully. Sending SIGKILL..."
            kill -9 "${pid}" 2>/dev/null || true
        fi
        log_success "${name} stopped."
    else
        log_info "${name} is not running on port ${port}."
    fi

    rm -f "${pid_file}"
}

stop_all() {
    log_info "Stopping Riva Stack..."
    stop_service_on_port "${GATEWAY_PORT}" "Riva AI Gateway" "${GATEWAY_PID_FILE}"
    stop_service_on_port "${MLX_PORT}" "MLX Server" "${MLX_PID_FILE}"
}

# ------------------------------------------------------------------------------
# Status Command
# ------------------------------------------------------------------------------
status_all() {
    echo -e "${BOLD}--- Riva Dev Stack Status ---${NC}"
    
    # MLX Server
    local mlx_pid
    mlx_pid=$(get_pid_on_port "${MLX_PORT}")
    local mlx_http
    mlx_http=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${MLX_PORT}/v1/models" 2>/dev/null || echo "DOWN")
    if [[ -n "${mlx_pid}" && "${mlx_http}" == "200" ]]; then
        echo -e "  MLX Server:     ${GREEN}ACTIVE${NC} (Port ${MLX_PORT}, PID ${mlx_pid}, HTTP 200)"
    elif [[ -n "${mlx_pid}" ]]; then
        echo -e "  MLX Server:     ${YELLOW}STARTING / UNHEALTHY${NC} (Port ${MLX_PORT}, PID ${mlx_pid}, HTTP ${mlx_http})"
    else
        echo -e "  MLX Server:     ${RED}STOPPED${NC} (Port ${MLX_PORT})"
    fi

    # Riva Gateway
    local gw_pid
    gw_pid=$(get_pid_on_port "${GATEWAY_PORT}")
    local gw_http
    gw_http=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${GATEWAY_PORT}/v1/models" 2>/dev/null || echo "DOWN")
    if [[ -n "${gw_pid}" && "${gw_http}" == "200" ]]; then
        echo -e "  Riva Gateway:   ${GREEN}ACTIVE${NC} (Port ${GATEWAY_PORT}, PID ${gw_pid}, HTTP 200)"
    elif [[ -n "${gw_pid}" ]]; then
        echo -e "  Riva Gateway:   ${YELLOW}STARTING / UNHEALTHY${NC} (Port ${GATEWAY_PORT}, PID ${gw_pid}, HTTP ${gw_http})"
    else
        echo -e "  Riva Gateway:   ${RED}STOPPED${NC} (Port ${GATEWAY_PORT})"
    fi

    # OpenClaw
    if command -v openclaw >/dev/null 2>&1; then
        local oc_status
        oc_status=$(openclaw gateway status 2>&1 || true)
        if echo "${oc_status}" | grep -qi "running"; then
            echo -e "  OpenClaw:       ${GREEN}GATEWAY SERVICE RUNNING${NC}"
        else
            echo -e "  OpenClaw:       ${YELLOW}GATEWAY SERVICE STOPPED / MANUAL${NC}"
        fi
    else
        echo -e "  OpenClaw:       ${RED}NOT INSTALLED IN PATH${NC}"
    fi

    echo -e "-----------------------------"
    echo -e "Logs:"
    echo -e "  MLX:     ${MLX_LOG}"
    echo -e "  Gateway: ${GATEWAY_LOG}"
}

# ------------------------------------------------------------------------------
# Test End-to-End Chat
# ------------------------------------------------------------------------------
test_connection() {
    log_info "Testing end-to-end chat request via Riva Gateway (port ${GATEWAY_PORT})..."
    local response
    response=$(curl -s -X POST "http://localhost:${GATEWAY_PORT}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK\"}],\"max_tokens\":10}" 2>/dev/null || true)

    if echo "${response}" | grep -q "choices"; then
        log_success "End-to-end chat test succeeded!"
    else
        log_warn "Chat test did not return expected response: ${response}"
    fi
}

# ------------------------------------------------------------------------------
# Main Dispatcher
# ------------------------------------------------------------------------------
cmd="${1:-start}"

case "${cmd}" in
    start)
        echo -e "${BOLD}Starting Riva Dev Stack (MLX + AI Gateway + OpenClaw)...${NC}"
        start_mlx
        start_gateway
        check_or_start_openclaw
        test_connection
        echo ""
        log_success "All services are up!"
        echo -e "  • MLX Backend:   http://localhost:${MLX_PORT}/v1"
        echo -e "  • Riva Gateway:  http://localhost:${GATEWAY_PORT}/v1"
        echo -e "  • OpenClaw Target: http://localhost:${GATEWAY_PORT}/v1"
        echo -e "Run '${0} chat' to open the OpenClaw terminal UI."
        ;;
    dev)
        echo -e "${BOLD}Starting Riva in Dev Mode (MLX background + Gateway foreground with auto-reload)...${NC}"
        start_mlx
        check_or_start_openclaw
        echo ""
        log_info "Launching Riva AI Gateway in FOREGROUND with auto-reload..."
        echo -e "  • Gateway listening at: ${BOLD}http://localhost:${GATEWAY_PORT}${NC}"
        echo -e "  • Watching directories: src, common"
        echo -e "  • Press ${BOLD}Ctrl+C${NC} to stop the gateway."
        echo ""
        cd "${REPO_ROOT}"
        uv run --package riva-agent uvicorn riva_agent.api.gateway:app \
            --host 0.0.0.0 --port "${GATEWAY_PORT}" --reload \
            --reload-dir src --reload-dir common
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 1
        "${0}" start
        ;;
    status)
        status_all
        ;;
    logs)
        echo -e "${BOLD}Following logs from:${NC}"
        echo -e "  ${MLX_LOG}"
        echo -e "  ${GATEWAY_LOG}"
        tail -f "${MLX_LOG}" "${GATEWAY_LOG}"
        ;;
    chat)
        "${0}" start
        if command -v openclaw >/dev/null 2>&1; then
            log_info "Launching OpenClaw TUI..."
            openclaw tui
        else
            log_error "openclaw command not found."
            exit 1
        fi
        ;;
    help|--help|-h)
        sed -n '2,15p' "$0" | tr -d '#'
        ;;
    *)
        log_error "Unknown command: ${cmd}"
        echo "Usage: $0 {start|dev|stop|restart|status|logs|chat}"
        exit 1
        ;;
esac
