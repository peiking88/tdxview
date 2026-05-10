#!/usr/bin/env bash
#
# tdxview All-in-One Script: Install, Configure, Run
# Usage: bash scripts/setup_dev.sh <command> [options]
#
# Commands:
#   setup     Install dependencies & configure environment (default)
#   run       Start the Streamlit application
#   test      Run unit & integration tests
#   e2e       Run E2E UI tests (Playwright)
#   all       Setup + Run application
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
LOG_DIR="${PROJECT_ROOT}/log"
APP_LOG="${LOG_DIR}/setup_dev.log"
APP_PORT=8501

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SKIP_E2E=false
SKIP_PLAYWRIGHT=false
SKIP_DB=false
SKIP_RUN=false
VERBOSE=false

info()    { echo -e "${BLUE}[INFO]${NC} $*" | tee -a "${APP_LOG}" 2>/dev/null || echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[ OK ]${NC} $*" | tee -a "${APP_LOG}" 2>/dev/null || echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "${APP_LOG}" 2>/dev/null || echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()    { echo -e "${RED}[FAIL]${NC} $*" | tee -a "${APP_LOG}" 2>/dev/null || echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

STEP=0
TOTAL_SETUP=8

step() {
    STEP=$((STEP + 1))
    echo ""
    echo -e "${CYAN}>>> Step ${STEP}/${TOTAL_SETUP}: $*${NC}"
    echo "--------------------------------------------"
}

banner() {
    echo ""
    echo "============================================"
    echo -e "  ${CYAN}$*${NC}"
    echo "============================================"
    echo ""
}

# ============================================================
# Argument Parsing
# ============================================================

COMMAND="setup"

usage() {
    cat <<'EOF'
Usage: bash scripts/setup_dev.sh <command> [options]

Commands:
  setup     Install dependencies & initialize environment (default)
  run       Start the Streamlit application
  test      Run unit & integration tests
  e2e       Run E2E UI tests (Playwright)
  all       Full setup then start application
  help      Show this help message

Options (for setup/all):
  --skip-e2e         Skip E2E test dependencies
  --skip-playwright  Skip Playwright browser download
  --skip-db          Skip database initialization
  --verbose          Show detailed pip output

Examples:
  bash scripts/setup_dev.sh setup                   # Full environment setup
  bash scripts/setup_dev.sh run                     # Start app on port 8501
  bash scripts/setup_dev.sh run --port 9000         # Start app on custom port
  bash scripts/setup_dev.sh test                    # Run unit + integration tests
  bash scripts/setup_dev.sh test -- -k "test_data"  # Pass extra pytest args
  bash scripts/setup_dev.sh e2e                     # Run E2E UI tests
  bash scripts/setup_dev.sh all                     # Setup + start app
  bash scripts/setup_dev.sh setup --skip-e2e        # Setup without E2E deps
EOF
    exit 0
}

if [ $# -gt 0 ]; then
    case "$1" in
        setup|run|test|e2e|all) COMMAND="$1"; shift ;;
        help|--help|-h)         usage ;;
    esac
fi

EXTRA_ARGS=()
RUN_PORT="${APP_PORT}"
while [ $# -gt 0 ]; do
    case "$1" in
        --skip-e2e)        SKIP_E2E=true; shift ;;
        --skip-playwright) SKIP_PLAYWRIGHT=true; shift ;;
        --skip-db)         SKIP_DB=true; shift ;;
        --verbose)         VERBOSE=true; shift ;;
        --port)            RUN_PORT="$2"; shift 2 ;;
        --)                shift; EXTRA_ARGS=("$@"); break ;;
        *)                 EXTRA_ARGS+=("$1"); shift ;;
    esac
done

cd "${PROJECT_ROOT}"
mkdir -p "${LOG_DIR}"

# ============================================================
# Setup Functions
# ============================================================

activate_venv() {
    if [ ! -d "${VENV_DIR}" ]; then
        return 1
    fi
    source "${VENV_DIR}/bin/activate"
    return 0
}

ensure_venv() {
    if ! activate_venv; then
        info "Virtual environment not found, creating..."
        create_venv
    fi
}

check_python() {
    step "Checking Python version"
    local py_cmd=""
    for cmd in python3 python; do
        if command -v "${cmd}" &>/dev/null; then
            py_cmd="${cmd}"
            break
        fi
    done
    [ -z "${py_cmd}" ] && fail "Python not found. Install Python 3.10+ first."

    local py_version
    py_version=$(${py_cmd} -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local major minor
    major=$(echo "${py_version}" | cut -d. -f1)
    minor=$(echo "${py_version}" | cut -d. -f2)

    if [ "${major}" -lt 3 ] || { [ "${major}" -eq 3 ] && [ "${minor}" -lt 10 ]; }; then
        fail "Python ${py_version} found, but 3.10+ required."
    fi
    ok "Python ${py_version} (${py_cmd})"
}

create_venv() {
    step "Creating virtual environment"
    if [ -d "${VENV_DIR}" ]; then
        info "Virtual environment already exists at ${VENV_DIR}"
    else
        python3 -m venv "${VENV_DIR}"
        ok "Created virtual environment at ${VENV_DIR}"
    fi

    source "${VENV_DIR}/bin/activate"
    local pip_flags="--quiet"
    [ "${VERBOSE}" = true ] && pip_flags=""
    pip install --upgrade pip ${pip_flags}
    ok "pip $(pip --version | awk '{print $2}')"
}

install_deps() {
    step "Installing Python dependencies"
    local pip_flags="--quiet"
    [ "${VERBOSE}" = true ] && pip_flags=""

    if [ -f "${PROJECT_ROOT}/requirements.txt" ]; then
        pip install -r "${PROJECT_ROOT}/requirements.txt" ${pip_flags}
        ok "Core dependencies installed"
    else
        fail "requirements.txt not found"
    fi

    pip install pytest-timeout pytest-base-url Faker ${pip_flags} 2>/dev/null || true
    ok "Test utilities installed"
}

install_e2e() {
    if [ "${SKIP_E2E}" = true ]; then
        step "Skipping E2E test dependencies (--skip-e2e)"
        return
    fi
    step "Installing E2E test dependencies"
    local pip_flags="--quiet"
    [ "${VERBOSE}" = true ] && pip_flags=""

    pip install pytest-playwright requests ${pip_flags}
    ok "pytest-playwright and requests installed"

    if [ "${SKIP_PLAYWRIGHT}" = true ]; then
        warn "Skipping Playwright browser download (--skip-playwright)"
        warn "Run 'playwright install chromium' manually when ready."
    else
        info "Downloading Chromium browser..."
        playwright install chromium
        ok "Chromium browser installed"
    fi
}

init_database() {
    if [ "${SKIP_DB}" = true ]; then
        step "Skipping database initialization (--skip-db)"
        return
    fi
    step "Initializing database"
    python "${PROJECT_ROOT}/scripts/init_database.py"
    ok "Database initialized"
}

create_dirs() {
    step "Creating project directories"
    local dirs=(
        "${PROJECT_ROOT}/data/parquet"
        "${PROJECT_ROOT}/data/cache"
        "${PROJECT_ROOT}/log"
        "${PROJECT_ROOT}/plugins/indicators"
    )
    for d in "${dirs[@]}"; do
        mkdir -p "${d}"
    done
    ok "data/parquet, data/cache, log, plugins/indicators"
}

verify_setup() {
    step "Verifying installation"
    local errors=0

    local modules=("streamlit" "duckdb" "plotly" "pandas" "pytest")
    for mod in "${modules[@]}"; do
        if python -c "import ${mod}" 2>/dev/null; then
            local ver
            ver=$(python -c "import ${mod}; print(${mod}.__version__)" 2>/dev/null || echo "ok")
            ok "  ${mod} ${ver}"
        else
            fail "  ${mod} not importable"
            errors=$((errors + 1))
        fi
    done

    if [ "${SKIP_E2E}" = false ]; then
        if python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
            ok "  playwright installed"
        else
            warn "  playwright not importable"
        fi
    fi

    if [ -f "${PROJECT_ROOT}/data/tdxview.db" ]; then
        ok "  Database file exists"
    else
        warn "  Database file not found (run: python scripts/init_database.py)"
    fi

    echo ""
    if [ "${errors}" -gt 0 ]; then
        fail "Verification failed with ${errors} error(s)"
    else
        ok "All verifications passed!"
    fi
}

# ============================================================
# Run Functions
# ============================================================

run_app() {
    banner "Starting tdxview Application"
    ensure_venv

    if [ ! -f "${PROJECT_ROOT}/data/tdxview.db" ]; then
        warn "Database not found, initializing..."
        python "${PROJECT_ROOT}/scripts/init_database.py"
    fi

    info "Starting Streamlit on port ${RUN_PORT}..."
    info "Press Ctrl+C to stop"
    echo ""

    streamlit run app/main.py \
        --server.port "${RUN_PORT}" \
        --server.address "0.0.0.0" \
        --server.headless true \
        --browser.gatherUsageStats false
}

# ============================================================
# Test Functions
# ============================================================

run_tests() {
    banner "Running Unit & Integration Tests"
    ensure_venv

    local pytest_args=("-v" "--tb=short")
    if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
        pytest_args=("${EXTRA_ARGS[@]}")
    fi

    info "pytest ${pytest_args[*]} tests/"
    echo ""
    pytest "${pytest_args[@]}" tests/
}

run_e2e() {
    banner "Running E2E UI Tests (Playwright)"
    ensure_venv

    if ! python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
        fail "Playwright not installed. Run: bash scripts/setup_dev.sh setup"
    fi

    local pytest_args=("-v" "--timeout=180")
    if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
        pytest_args=("${EXTRA_ARGS[@]}")
    fi

    info "pytest ${pytest_args[*]} tests/e2e/"
    echo ""
    pytest "${pytest_args[@]}" tests/e2e/
}

# ============================================================
# Main
# ============================================================

do_setup() {
    banner "tdxview Environment Setup"
    check_python
    create_venv
    install_deps
    install_e2e
    create_dirs
    init_database
    verify_setup

    echo ""
    echo "============================================"
    echo -e "  ${GREEN}Setup Complete!${NC}"
    echo "============================================"
    echo ""
    echo "Quick Start:"
    echo ""
    echo "  bash scripts/setup_dev.sh run              # Start application"
    echo "  bash scripts/setup_dev.sh test             # Run tests"
    echo "  bash scripts/setup_dev.sh e2e              # Run E2E tests"
    echo ""
    echo "Default admin: admin / admin123"
    echo ""
}

do_all() {
    do_setup
    echo ""
    run_app
}

case "${COMMAND}" in
    setup) do_setup ;;
    run)   run_app ;;
    test)  run_tests ;;
    e2e)   run_e2e ;;
    all)   do_all ;;
    *)     usage ;;
esac
