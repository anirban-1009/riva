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
#   status   Checks health and port status of components
#   logs     Follows combined logs for MLX server and Riva Gateway
#   chat     Starts the stack and launches the OpenClaw interactive terminal UI
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Ensure ~/.local/bin is in PATH for tools installed via uv/pip
export PATH="${HOME}/.local/bin:${PATH}"

# Ports and Model Configuration
MLX_PORT="${MLX_PORT:-8081}"
GATEWAY_PORT="${GATEWAY_PORT:-8085}"
DEFAULT_MLX_MODEL="mlx-community/gemma-4-E4B-it-qat-4bit"
DEFAULT_MODEL="${DEFAULT_MLX_MODEL}"

# Extract provider and model from config.yml if available
CONFIG_PROVIDER=""
CONFIG_MODEL=""
if [[ -f "${REPO_ROOT}/config.yml" ]]; then
    CONFIG_PROVIDER=$(grep -E "^provider:" "${REPO_ROOT}/config.yml" | head -n 1 | awk '{print $2}' | tr -d '"'\''')
    CONFIG_MODEL=$(grep -E "^model:" "${REPO_ROOT}/config.yml" | head -n 1 | awk '{print $2}' | tr -d '"'\''')
fi

PROVIDER="${CONFIG_PROVIDER:-openai}"
MODEL="${CONFIG_MODEL:-}"

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
# Helpers: Platform & MLX Support
# ------------------------------------------------------------------------------
is_mlx_supported() {
    [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]
}

ensure_mlx_installed() {
    if command -v mlx_lm.server >/dev/null 2>&1; then
        return 0
    fi

    if ! is_mlx_supported; then
        log_error "mlx_lm.server is not installed and MLX is not supported on this platform."
        log_error "MLX requires macOS on Apple Silicon (arm64). Current platform: $(uname -s) $(uname -m)."
        log_info "If running on Linux or Intel Mac, set 'provider: ollama' in config.yml."
        return 1
    fi

    log_warn "mlx_lm.server command was not found in PATH."

    if [[ -t 0 ]]; then
        local reply
        read -r -p "Would you like to install mlx-lm now? [Y/n]: " reply
        reply="${reply:-Y}"
        if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
            log_error "Cannot start MLX Server without mlx-lm."
            log_info "Install manually via: uv tool install mlx-lm (or pip install mlx-lm)"
            return 1
        fi
    else
        log_info "Non-interactive shell: attempting automatic installation of mlx-lm..."
    fi

    log_info "Installing mlx-lm..."
    if command -v uv >/dev/null 2>&1; then
        log_info "Running 'uv tool install mlx-lm'..."
        if uv tool install mlx-lm; then
            export PATH="${HOME}/.local/bin:${PATH}"
        else
            log_warn "uv tool install mlx-lm failed; trying pip install..."
            python3 -m pip install --user mlx-lm || return 1
        fi
    elif command -v pip3 >/dev/null 2>&1; then
        log_info "Running 'pip3 install mlx-lm'..."
        pip3 install --user mlx-lm || return 1
    elif command -v pip >/dev/null 2>&1; then
        log_info "Running 'pip install mlx-lm'..."
        pip install --user mlx-lm || return 1
    else
        log_error "Neither uv nor pip found to install mlx-lm. Please install mlx-lm manually."
        return 1
    fi

    if command -v mlx_lm.server >/dev/null 2>&1; then
        log_success "mlx-lm installed successfully!"
        return 0
    fi

    log_error "mlx_lm.server is still not found in PATH after installation. Ensure ~/.local/bin is in your PATH."
    return 1
}

save_model_to_config() {
    local target_model="$1"
    local cfg="${REPO_ROOT}/config.yml"

    if [[ ! -f "${cfg}" && -f "${REPO_ROOT}/config.yml.example" ]]; then
        cp "${REPO_ROOT}/config.yml.example" "${cfg}"
    fi

    if [[ -f "${cfg}" ]]; then
        if command -v python3 >/dev/null 2>&1; then
            python3 -c "
import sys, re
cfg_path = sys.argv[1]
m = sys.argv[2]
try:
    with open(cfg_path, 'r') as f:
        content = f.read()
    if re.search(r'^model:', content, flags=re.MULTILINE):
        new_content = re.sub(r'^model:.*', f'model: {m}', content, flags=re.MULTILINE)
    else:
        new_content = content.rstrip() + f'\nmodel: {m}\n'
    with open(cfg_path, 'w') as f:
        f.write(new_content)
except Exception:
    sys.exit(1)
" "${cfg}" "${target_model}" 2>/dev/null || echo "model: ${target_model}" >> "${cfg}"
        else
            echo "model: ${target_model}" >> "${cfg}"
        fi
        log_success "Saved model '${target_model}' to config.yml."
    else
        cat <<EOF > "${cfg}"
provider: openai
model: ${target_model}

openai:
  base_url: http://localhost:8081/v1
EOF
        log_success "Created config.yml with model: ${target_model}."
    fi
}

resolve_model() {
    if [[ -n "${MODEL}" ]]; then
        return 0
    fi

    if [[ -f "${REPO_ROOT}/config.yml" ]]; then
        CONFIG_MODEL=$(grep -E "^model:" "${REPO_ROOT}/config.yml" | head -n 1 | awk '{print $2}' | tr -d '"'\''')
        if [[ -n "${CONFIG_MODEL}" ]]; then
            MODEL="${CONFIG_MODEL}"
            return 0
        fi
    fi

    if [[ "${PROVIDER}" == "ollama" ]]; then
        MODEL="llama3:8b"
        log_info "No model specified in config.yml; using default Ollama model '${MODEL}'."
        return 0
    fi

    if [[ -t 0 ]]; then
        log_warn "No model specified in config.yml."
        echo -e "${BOLD}Select an MLX model to use:${NC}"
        echo "  1) mlx-community/gemma-4-E4B-it-qat-4bit (Default - Fast & balanced 4-bit)"
        echo "  2) mlx-community/Qwen2.5-7B-Instruct-4bit (High reasoning, 4-bit)"
        echo "  3) mlx-community/Meta-Llama-3.1-8B-Instruct-4bit (Standard 8B instruct)"
        echo "  4) Custom Hugging Face model repository"
        local choice
        read -r -p "Enter choice [1-4] (default: 1): " choice
        case "${choice}" in
            2) MODEL="mlx-community/Qwen2.5-7B-Instruct-4bit" ;;
            3) MODEL="mlx-community/Meta-Llama-3.1-8B-Instruct-4bit" ;;
            4)
                local custom_model
                read -r -p "Enter Hugging Face model repository (e.g. mlx-community/...): " custom_model
                MODEL="${custom_model:-$DEFAULT_MLX_MODEL}"
                ;;
            *) MODEL="$DEFAULT_MLX_MODEL" ;;
        esac

        local save_reply
        read -r -p "Would you like to save model '${MODEL}' to config.yml? [Y/n]: " save_reply
        save_reply="${save_reply:-Y}"
        if [[ "${save_reply}" =~ ^[Yy]$ ]]; then
            save_model_to_config "${MODEL}"
        fi
    else
        MODEL="$DEFAULT_MLX_MODEL"
        log_info "No model specified in config.yml; falling back to default '${MODEL}'."
    fi
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
    local pid="${4:-}"
    local count=0

    echo -n "Waiting for ${service_name} to be ready..."
    while [[ $count -lt $max_retries ]]; do
        if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
            echo -e " ${RED}process exited unexpectedly!${NC}"
            return 1
        fi
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
    if [[ "${PROVIDER}" == "ollama" ]]; then
        log_info "Provider configured as 'ollama' in config.yml. Skipping MLX Server."
        if ! curl -s -o /dev/null "http://127.0.0.1:11434/api/tags" 2>/dev/null; then
            log_warn "Ollama does not appear to be running on port 11434. Please ensure Ollama is started."
        else
            log_success "Ollama is active on port 11434."
        fi
        return 0
    fi

    log_info "Checking MLX Server on port ${MLX_PORT}..."
    if is_port_in_use "${MLX_PORT}"; then
        local pid
        pid=$(get_pid_on_port "${MLX_PORT}")
        log_success "MLX Server is already running on port ${MLX_PORT} (PID: ${pid})."
        return 0
    fi

    # Check MLX platform support
    if ! is_mlx_supported; then
        log_error "MLX Server requires macOS on Apple Silicon (arm64)."
        log_error "Detected platform: $(uname -s) $(uname -m)."
        log_info "To use Riva on this machine, consider switching 'provider: ollama' in config.yml."
        return 1
    fi

    # Ensure mlx-lm is installed
    if ! ensure_mlx_installed; then
        return 1
    fi

    # Check if model is cached in Hugging Face Hub or local path
    local is_cached=false
    local hf_cache_dir="${HF_HOME:-$HOME/.cache/huggingface}/hub/models--${MODEL//\//--}"
    if [[ -d "${MODEL}" || -d "${hf_cache_dir}" ]]; then
        is_cached=true
        log_info "Model '${MODEL}' found in local cache."
    else
        log_warn "Model '${MODEL}' not found in local cache."
        log_info "mlx_lm.server will download model weights from Hugging Face on startup."
        log_info "Downloading may take several minutes depending on network bandwidth. (Logs: ${MLX_LOG})"
    fi

    local wait_timeout=45
    if [[ "${is_cached}" == "false" ]]; then
        wait_timeout=600 # 10 minute budget for initial download
    fi

    log_info "Starting mlx_lm.server with model '${MODEL}' (1GB KV cache bound)..."
    nohup mlx_lm.server --model "${MODEL}" --port "${MLX_PORT}" \
        --prompt-cache-bytes 1073741824 \
        --prompt-cache-size 2 > "${MLX_LOG}" 2>&1 &
    local pid=$!
    echo "${pid}" > "${MLX_PID_FILE}"
    disown "${pid}" 2>/dev/null || true

    if ! wait_for_http_200 "http://127.0.0.1:${MLX_PORT}/v1/models" "${wait_timeout}" "MLX Server" "${pid}"; then
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

    if ! wait_for_http_200 "http://127.0.0.1:${GATEWAY_PORT}/v1/models" 20 "Riva Gateway" "${pid}"; then
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
    if [[ "${PROVIDER}" != "ollama" ]] || is_port_in_use "${MLX_PORT}"; then
        stop_service_on_port "${MLX_PORT}" "MLX Server" "${MLX_PID_FILE}"
    fi
}

# ------------------------------------------------------------------------------
# Status Command
# ------------------------------------------------------------------------------
status_all() {
    echo -e "${BOLD}--- Riva Dev Stack Status ---${NC}"
    echo -e "  Backend Provider: ${BOLD}${PROVIDER}${NC}"

    if [[ "${PROVIDER}" == "ollama" ]]; then
        local ollama_http
        ollama_http=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:11434/api/tags" 2>/dev/null || echo "DOWN")
        if [[ "${ollama_http}" == "200" ]]; then
            echo -e "  Ollama:         ${GREEN}ACTIVE${NC} (Port 11434, HTTP 200)"
        else
            echo -e "  Ollama:         ${RED}STOPPED / UNREACHABLE${NC} (Port 11434)"
        fi
        echo -e "  MLX Server:     ${BLUE}INACTIVE${NC} (Provider is set to 'ollama')"
    else
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
    if [[ "${PROVIDER}" != "ollama" ]]; then
        echo -e "  MLX:     ${MLX_LOG}"
    fi
    echo -e "  Gateway: ${GATEWAY_LOG}"
}

# ------------------------------------------------------------------------------
# Test End-to-End Chat
# ------------------------------------------------------------------------------
test_connection() {
    log_info "Testing end-to-end chat request via Riva Gateway (port ${GATEWAY_PORT})..."
    local test_model="${MODEL:-$DEFAULT_MODEL}"
    local response
    response=$(curl -s -X POST "http://localhost:${GATEWAY_PORT}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"${test_model}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK\"}],\"max_tokens\":10}" 2>/dev/null || true)

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
        resolve_model
        echo -e "${BOLD}Starting Riva Dev Stack (MLX + AI Gateway + OpenClaw)...${NC}"
        start_mlx
        start_gateway
        check_or_start_openclaw
        test_connection
        echo ""
        log_success "All services are up!"
        if [[ "${PROVIDER}" != "ollama" ]]; then
            echo -e "  • MLX Backend:   http://localhost:${MLX_PORT}/v1"
        else
            echo -e "  • Ollama Backend: http://localhost:11434"
        fi
        echo -e "  • Riva Gateway:  http://localhost:${GATEWAY_PORT}/v1"
        echo -e "  • OpenClaw Target: http://localhost:${GATEWAY_PORT}/v1"
        echo -e "Run '${0} chat' to open the OpenClaw terminal UI."
        ;;
    dev)
        resolve_model
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
        if [[ "${PROVIDER}" != "ollama" ]]; then
            echo -e "  ${MLX_LOG}"
        fi
        echo -e "  ${GATEWAY_LOG}"
        if [[ "${PROVIDER}" != "ollama" ]]; then
            tail -f "${MLX_LOG}" "${GATEWAY_LOG}"
        else
            tail -f "${GATEWAY_LOG}"
        fi
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
