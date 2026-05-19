#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# start_hermes_full.sh — One-command launcher with auto-recovery
#
# Subcommands:
#   start         Start all components (default)
#   stop          Kill all Hermes processes
#   restart       Stop then start
#   status        Show component health
#   watch         Run in foreground with auto-restart for dead components
#   test          Run the full system health check
#   rotate        Rotate all log files
#   enable-cron   Install a systemd user timer for auto-start + health checks
#
# The --watch flag auto-restarts any component that dies within 3 seconds.
# Cron mode runs a health check every 5 minutes and restarts dead components.
#
# Usage examples:
#   ./scripts/start_hermes_full.sh start
#   ./scripts/start_hermes_full.sh start --no-qt
#   ./scripts/start_hermes_full.sh watch          # foreground auto-recovery
#   ./scripts/start_hermes_full.sh watch --daemon # background auto-recovery
#   ./scripts/start_hermes_full.sh status
#   ./scripts/start_hermes_full.sh rotate
#   ./scripts/start_hermes_full.sh enable-cron
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Paths ──
HERMES_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_Q_ROOT="$HOME/Projects/project-q"
COORDINATOR_BIN="$PROJECT_Q_ROOT/herald/herald_coordinator.py"
WORKER_BIN="$PROJECT_Q_ROOT/herald/herald_worker.py"
PYTHON_APP="$HERMES_ROOT/src/main.py"
QT_APP="$HERMES_ROOT/build/hermes-elysium"
HEALTH_CHECK="$HERMES_ROOT/scripts/full_system_test.py"
PID_DIR="$HOME/.hermes/pids"
LOG_DIR="$HOME/.hermes/logs"
WATCH_PID_FILE="$PID_DIR/watch_daemon.pid"
COORDINATOR_PORT="${COORDINATOR_PORT:-9100}"
MAX_RESTART_INTERVAL=30  # seconds — throttle restarts to avoid rapid crash loops

# Ensure directories exist
mkdir -p "$PID_DIR" "$LOG_DIR"

# ── Named components (order matters for startup & shutdown) ──
declare -A COMPONENTS
COMPONENTS["coordinator"]="python3 \"$COORDINATOR_BIN\" --port $COORDINATOR_PORT"
COMPONENTS["worker"]="python3 \"$WORKER_BIN\" --coordinator 127.0.0.1:$COORDINATOR_PORT --name garuda-worker"
COMPONENTS["hermes-python"]="python3 \"$PYTHON_APP\""
COMPONENTS["hermes-qt"]="\"$QT_APP\""

# Track which are optional (won't warn on failure to start)
OPTIONAL_COMPONENTS=("hermes-qt" "worker")

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR]${NC}   $*" >&2; }

# ── Helpers ──

_is_optional() {
    local name="$1"
    for opt in "${OPTIONAL_COMPONENTS[@]}"; do
        if [ "$opt" = "$name" ]; then return 0; fi
    done
    return 1
}

_is_running() {
    local pid_file="$PID_DIR/$1.pid"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        # Stale PID file
        rm -f "$pid_file"
    fi
    return 1
}

_pid_of() {
    local pid_file="$PID_DIR/$1.pid"
    if [ -f "$pid_file" ]; then
        cat "$pid_file" 2>/dev/null || echo ""
    fi
}

_write_pid() {
    echo $$ > "$PID_DIR/$1.pid"
}

# ── Log rotation (simple: copy + truncate, keep 3 rotated backups) ──
_rotate_log() {
    local log="$1"
    if [ ! -f "$log" ]; then return 0; fi
    local size
    size=$(stat -c%s "$log" 2>/dev/null || echo "0")
    if [ "$size" -lt 1048576 ]; then return 0; fi  # < 1MB, skip
    for i in 3 2 1; do
        local src="${log}.$((i - 1))"
        local dst="${log}.$i"
        [ -f "$src" ] && mv "$src" "$dst" 2>/dev/null || true
    done
    cp "$log" "${log}.1" 2>/dev/null || true
    : > "$log"  # truncate
    ok "Rotated $log ($((size / 1024))KB)"
}

_rotate_all_logs() {
    info "Rotating all log files..."
    for log in "$LOG_DIR"/*.log; do
        [ -f "$log" ] && _rotate_log "$log"
    done
    ok "Log rotation complete"
}

# ── Start component ──

# Global restart tracker: component_name -> last_restart_epoch
declare -A _last_restart

_start_component() {
    local name="$1"
    local cmd="${COMPONENTS[$name]}"
    local log="$LOG_DIR/$name.log"
    local optional=false
    _is_optional "$name" && optional=true

    # Check if binary exists for optional components
    if $optional; then
        # Extract the binary path from the command
        local bin_path
        bin_path=$(echo "$cmd" | awk '{print $1}' | tr -d '"')
        if [ ! -f "$bin_path" ] && [ ! -x "$bin_path" ]; then
            return 0  # silently skip optional components with no binary
        fi
    fi

    # Prevent rapid restart loops
    local now
    now=$(date +%s)
    local last="${_last_restart[$name]:-0}"
    local elapsed=$((now - last))
    if [ "$elapsed" -lt "$MAX_RESTART_INTERVAL" ]; then
        local wait_sec=$((MAX_RESTART_INTERVAL - elapsed))
        if [ "$optional" = false ]; then
            warn "$name: throttling restart for ${wait_sec}s (avoiding crash loop)"
        fi
        return 1
    fi

    info "Starting $name..."
    # cd to appropriate directory before starting
    local workdir="$HERMES_ROOT"
    case "$name" in
        coordinator|worker) workdir="$PROJECT_Q_ROOT" ;;
    esac
    nohup bash -c "cd \"$workdir\" && $cmd" >> "$log" 2>&1 &
    local pid=$!
    echo $pid > "$PID_DIR/$name.pid"
    _last_restart["$name"]=$now
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        ok "$name started (PID: $pid)"
        return 0
    else
        if $optional; then
            info "$name not available (skipped)"
            rm -f "$PID_DIR/$name.pid"
            return 0
        fi
        err "$name failed to start — check $log"
        return 1
    fi
}

_stop_component() {
    local name="$1"
    local pid
    pid=$(_pid_of "$name")
    if [ -n "$pid" ]; then
        kill "$pid" 2>/dev/null && ok "$name stopped (PID: $pid)" || true
        rm -f "$PID_DIR/$name.pid"
    fi
}

# ── Component order ──
COMPONENT_ORDER=("coordinator" "worker" "hermes-python" "hermes-qt")
COMPONENT_ORDER_REVERSE=("hermes-qt" "hermes-python" "worker" "coordinator")

# ── Watch loop (the heart of auto-recovery) ──

_watch_loop() {
    local daemon_mode="${1:-false}"
    info "Auto-recovery watch loop started (PID: $$)"
    info "Checking every 15 seconds..."

    # Initial start
    _rotate_all_logs
    for name in "${COMPONENT_ORDER[@]}"; do
        _start_component "$name" || true
    done

    # Record start time for cron readiness check
    local start_time
    start_time=$(date +%s)

    local check_interval=15
    local rotate_interval=3600  # rotate once per hour
    local last_rotate=$start_time

    while true; do
        sleep "$check_interval"

        local now
        now=$(date +%s)

        # Log rotation
        if [ $((now - last_rotate)) -ge "$rotate_interval" ]; then
            _rotate_all_logs
            last_rotate=$now
        fi

        # Check each component
        for name in "${COMPONENT_ORDER[@]}"; do
            local pid_file="$PID_DIR/$name.pid"
            if [ -f "$pid_file" ]; then
                local pid
                pid=$(cat "$pid_file" 2>/dev/null || echo "")
                if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
                    warn "$name (PID: ${pid:-unknown}) died — restarting"
                    rm -f "$pid_file"
                    _start_component "$name" || true
                fi
            else
                # Never started or cleaned up — (re)start if not optional
                local optional=false
                _is_optional "$name" && optional=true
                if ! $optional; then
                    _start_component "$name" || true
                fi
            fi
        done
    done
}

# ── Subcommands ──

do_start() {
    local no_qt=false
    local no_welcome=false
    for arg in "$@"; do
        case "$arg" in 
            --no-qt) no_qt=true ;;
            --no-welcome) no_welcome=true ;;
        esac
    done

    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║        Hermes-Elysium — Full Stack Launcher                 ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""

    _rotate_all_logs
    for name in "${COMPONENT_ORDER[@]}"; do
        if [ "$name" = "hermes-qt" ] && $no_qt; then
            info "Skipping hermes-qt (--no-qt flag)"
            continue
        fi
        _start_component "$name" || true
    done

    if [ "$no_welcome" = false ]; then
        info "Running voice-first welcome sequence..."
        python3 "$HERMES_ROOT/scripts/welcome_sequence.py"
    else
        info "Welcome sequence skipped (--no-welcome)"
    fi

    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║  All components started.                                     ║"
    echo "║  Logs: $LOG_DIR                                          ║"
    echo "║  PIDs: $PID_DIR                                           ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""
    do_status
}

do_stop() {
    echo ""
    info "Stopping all Hermes components..."
    for name in "${COMPONENT_ORDER_REVERSE[@]}"; do
        _stop_component "$name"
    done
    # Also clean up any orphaned process matching hermes components
    pkill -f "hermes-elysium/src/main.py" 2>/dev/null || true
    pkill -f "herald_coordinator.py" 2>/dev/null || true
    pkill -f "herald_worker.py" 2>/dev/null || true
    rm -f "$WATCH_PID_FILE"
    ok "All components stopped"
}

do_restart() {
    do_stop
    sleep 1
    do_start
}

do_status() {
    echo ""
    printf "  %-25s %-10s %s\n" "Component" "Status" "PID"
    printf "  %-25s %-10s %s\n" "---------" "------" "---"
    local any_running=false
    for name in "${COMPONENT_ORDER[@]}"; do
        if _is_running "$name"; then
            local pid
            pid=$(_pid_of "$name")
            printf "  ${GREEN}%-25s${NC} %-10s ${GREEN}%s${NC}\n" "$name" "Running" "$pid"
            any_running=true
        else
            printf "  %-25s %-10s\n" "$name" "${RED}Stopped${NC}"
        fi
    done
    if [ -f "$WATCH_PID_FILE" ]; then
        local wpid
        wpid=$(cat "$WATCH_PID_FILE" 2>/dev/null || echo "")
        if [ -n "$wpid" ] && kill -0 "$wpid" 2>/dev/null; then
            printf "  ${GREEN}%-25s${NC} %-10s ${GREEN}%s${NC}\n" "watch-daemon" "Running" "$wpid"
        else
            printf "  %-25s %-10s\n" "watch-daemon" "${YELLOW}Stale${NC}"
        fi
    fi
    echo ""
    if ! $any_running; then
        info "No components running. Use 'start' or 'watch' to bring them up."
    fi
}

do_watch() {
    local daemon=false
    for arg in "$@"; do
        case "$arg" in
            --daemon|-d) daemon=true ;;
        esac
    done

    if $daemon; then
        info "Starting watch daemon in background..."
        nohup "$0" watch --foreground > "$LOG_DIR/watch_daemon.log" 2>&1 &
        local wpid=$!
        echo $wpid > "$WATCH_PID_FILE"
        ok "Watch daemon started (PID: $wpid)"
        echo "Auto-recovery is active. Components will restart on failure."
        echo "Log: $LOG_DIR/watch_daemon.log"
    else
        # Foreground watch (or background via --daemon)
        echo ""
        echo "╔═══════════════════════════════════════════════════════════════╗"
        echo "║  Watch Mode — Auto-Recovery Active                          ║"
        echo "║  Press Ctrl+C to stop all components and exit               ║"
        echo "╚═══════════════════════════════════════════════════════════════╝"
        echo ""
        # Trap Ctrl+C to clean up
        trap 'echo ""; info "Shutting down..."; do_stop; exit 0' SIGINT SIGTERM
        _watch_loop
    fi
}

do_test() {
    echo ""
    info "Running full system health check..."
    echo ""
    python3 "$HEALTH_CHECK"
    local rc=$?
    if [ $rc -eq 0 ]; then
        ok "Health check PASSED"
    else
        err "Health check FAILED (exit code $rc)"
    fi
    return $rc
}

do_rotate() {
    _rotate_all_logs
}

do_enable_cron() {
    local unit_name="hermes-health-check"
    local unit_dir="$HOME/.config/systemd/user"
    local service_file="$unit_dir/${unit_name}.service"
    local timer_file="$unit_dir/${unit_name}.timer"

    mkdir -p "$unit_dir"

    # Service unit: runs the health check, restarts dead components
    cat > "$service_file" <<-SERVICEEOF
[Unit]
Description=Hermes-Elysium Health Check & Auto-Recovery

[Service]
Type=oneshot
ExecStart=%h/Projects/hermes-elysium/scripts/full_system_test.py --exit-code
ExecStartPost=%h/Projects/hermes-elysium/scripts/start_hermes_full.sh start --no-qt
StandardOutput=journal
StandardError=journal
SERVICEEOF

    # Timer unit: fires every 5 minutes
    cat > "$timer_file" <<-TIMEREOF
[Unit]
Description=Hermes-Elysium 5-minute Health Check

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
TIMEREOF

    systemctl --user daemon-reload
    systemctl --user enable --now "${unit_name}.timer"
    ok "systemd timer installed: ${unit_name}.timer (runs every 5 minutes)"
    systemctl --user status "${unit_name}.timer" --no-pager 2>&1 | head -5
}

# ── Main ──

case "${1:-start}" in
    start)
        shift || true
        do_start "$@"
        ;;
    stop)
        do_stop
        ;;
    restart)
        do_restart
        ;;
    status)
        do_status
        ;;
    watch)
        shift || true
        do_watch "$@"
        ;;
    test|check|health)
        do_test
        ;;
    rotate)
        do_rotate
        ;;
    enable-cron|cron)
        do_enable_cron
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|watch|test|rotate|enable-cron} [--no-qt] [--no-welcome] [--daemon]"
        echo ""
        echo "  start        Start all components (default)"
        echo "  stop         Kill all Hermes processes"
        echo "  restart      Stop then start"
        echo "  status       Show component health"
        echo "  watch        Foreground auto-recovery (Ctrl+C to stop)"
        echo "  watch -d     Background auto-recovery daemon"
        echo "  test         Run full system health check"
        echo "  rotate       Rotate all log files"
        echo "  enable-cron  Install systemd 5-min health check timer"
        echo ""
        echo "Flags:"
        echo "  --no-qt       Skip Qt UI"
        echo "  --no-welcome  Skip voice onboarding sequence"
        exit 1
        ;;
esac
