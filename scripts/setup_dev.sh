#!/usr/bin/env bash
#
# tdxview Development & Testing Environment Setup Script
# Usage: bash scripts/setup_dev.sh [--skip-e2e] [--skip-playwright] [--skip-db] [--help]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SKIP_E2E=false
SKIP_PLAYWRIGHT=false
SKIP_DB=false

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()    { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

usage() {
    cat <<EOF
Usage: bash scripts/setup_dev.sh [OPTIONS]

Options:
  --skip-e2e         Skip E2E test dependencies (pytest-playwright)
  --skip-playwright  Skip Playwright browser installation
  --skip-db          Skip database initialization
  --help             Show this help message

Examples:
  bash scripts/setup_dev.sh                   # Full setup
  bash scripts/setup_dev.sh --skip-e2e        # Without E2E test environment
  bash scripts/setup_dev.sh --skip-playwright # Install deps but skip browser download
EOF
    exit 0
}

for arg in "$@"; do
    case "${arg}" in
        --skip-e2e)        SKIP_E2E=true ;;
        --skip-playwright) SKIP_PLAYWRIGHT=true ;;
        --skip-db)         SKIP_DB=true ;;
        --help|-h)         usage ;;
        *)                 warn "Unknown option: ${arg}" ;;
    esac
done

cd "${PROJECT_ROOT}"

echo ""
echo "============================================"
echo "  tdxview Development Environment Setup"
echo "============================================"
echo ""

STEP=0
TOTAL=7

step() {
    STEP=$((STEP + 1))
    echo ""
    echo -e "${BLUE}>>> Step ${STEP}/${TOTAL}: $*${NC}"
    echo "--------------------------------------------"
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
    pip install --upgrade pip --quiet
    ok "pip upgraded to $(pip --version | awk '{print $2}')"
}

install_deps() {
    step "Installing Python dependencies"
    if [ -f "${PROJECT_ROOT}/requirements.txt" ]; then
        pip install -r "${PROJECT_ROOT}/requirements.txt" --quiet
        ok "Installed dependencies from requirements.txt"
    else
        fail "requirements.txt not found"
    fi

    pip install pytest-timeout pytest-base-url Faker --quiet 2>/dev/null || true
    ok "Installed test utilities"
}

install_e2e() {
    if [ "${SKIP_E2E}" = true ]; then
        step "Skipping E2E test dependencies (--skip-e2e)"
        return
    fi
    step "Installing E2E test dependencies"
    pip install pytest-playwright requests --quiet
    ok "Installed pytest-playwright and requests"

    if [ "${SKIP_PLAYWRIGHT}" = true ]; then
        warn "Skipping Playwright browser installation (--skip-playwright)"
        warn "Run 'playwright install chromium' manually when ready."
    else
        info "Downloading Chromium browser (may take a while)..."
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
    ok "Database initialized at data/tdxview.db"
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
    ok "Directories ready: data/parquet, data/cache, log, plugins/indicators"
}

verify_setup() {
    step "Verifying installation"
    local errors=0

    if ! python -c "import streamlit" 2>/dev/null; then
        fail "  streamlit not importable"; errors=$((errors + 1))
    else
        ok "  streamlit $(python -c 'import streamlit; print(streamlit.__version__)')"
    fi

    if ! python -c "import duckdb" 2>/dev/null; then
        fail "  duckdb not importable"; errors=$((errors + 1))
    else
        ok "  duckdb $(python -c 'import duckdb; print(duckdb.__version__)')"
    fi

    if ! python -c "import plotly" 2>/dev/null; then
        fail "  plotly not importable"; errors=$((errors + 1))
    else
        ok "  plotly $(python -c 'import plotly; print(plotly.__version__)')"
    fi

    if ! python -c "import pandas" 2>/dev/null; then
        fail "  pandas not importable"; errors=$((errors + 1))
    else
        ok "  pandas $(python -c 'import pandas; print(pandas.__version__)')"
    fi

    if ! python -c "import pytest" 2>/dev/null; then
        fail "  pytest not importable"; errors=$((errors + 1))
    else
        ok "  pytest $(python -c 'import pytest; print(pytest.__version__)')"
    fi

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

print_summary() {
    echo ""
    echo "============================================"
    echo -e "  ${GREEN}Setup Complete!${NC}"
    echo "============================================"
    echo ""
    echo "Quick Start:"
    echo ""
    echo "  # Activate the environment"
    echo "  source .venv/bin/activate"
    echo ""
    echo "  # Run the application"
    echo "  streamlit run app/main.py"
    echo ""
    echo "  # Run unit & integration tests"
    echo "  pytest tests/ -v"
    echo ""
    if [ "${SKIP_E2E}" = false ]; then
        echo "  # Run E2E UI tests"
        echo "  pytest tests/e2e/ -v --timeout=180"
        echo ""
    fi
    echo "  # Run with coverage"
    echo "  pytest tests/ --cov=app --cov-report=term-missing"
    echo ""
    echo "Default admin account: admin / admin123"
    echo "============================================"
    echo ""
}

main() {
    check_python
    create_venv
    install_deps
    install_e2e
    create_dirs
    init_database
    verify_setup
    print_summary
}

main
