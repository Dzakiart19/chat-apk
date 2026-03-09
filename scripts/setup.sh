#!/usr/bin/env bash
#
# Dzeck AI - Auto Setup & Install Dependencies
# Installs Node.js (npm) and Python (pip) dependencies in parallel
# for faster setup time.
#
# Usage:
#   ./scripts/setup.sh          # Install all dependencies
#   ./scripts/setup.sh --clean  # Clean install (remove existing deps first)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Log file for detailed output
LOG_DIR="$PROJECT_ROOT/.setup-logs"
mkdir -p "$LOG_DIR"
NPM_LOG="$LOG_DIR/npm-install.log"
PIP_LOG="$LOG_DIR/pip-install.log"

# Timing
START_TIME=$(date +%s)

# ─── Helper Functions ───────────────────────────────────────────────

print_header() {
  echo ""
  echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}${BOLD}║     Dzeck AI - Auto Setup & Install      ║${NC}"
  echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════╝${NC}"
  echo ""
}

print_step() {
  echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} ${BOLD}$1${NC}"
}

print_success() {
  echo -e "${GREEN}[$(date +%H:%M:%S)] $1${NC}"
}

print_warning() {
  echo -e "${YELLOW}[$(date +%H:%M:%S)] $1${NC}"
}

print_error() {
  echo -e "${RED}[$(date +%H:%M:%S)] ERROR: $1${NC}"
}

elapsed_time() {
  local end_time=$(date +%s)
  local elapsed=$((end_time - START_TIME))
  local minutes=$((elapsed / 60))
  local seconds=$((elapsed % 60))
  if [ "$minutes" -gt 0 ]; then
    echo "${minutes}m ${seconds}s"
  else
    echo "${seconds}s"
  fi
}

# ─── Dependency Checks ─────────────────────────────────────────────

check_node() {
  if ! command -v node &> /dev/null; then
    print_error "Node.js is not installed!"
    echo "  Install it from: https://nodejs.org/"
    return 1
  fi
  local version=$(node --version)
  print_success "Node.js $version found"
}

check_npm() {
  if ! command -v npm &> /dev/null; then
    print_error "npm is not installed!"
    return 1
  fi
  local version=$(npm --version)
  print_success "npm v$version found"
}

detect_python() {
  # Returns python command via stdout - do NOT print anything else to stdout
  if command -v python3 &> /dev/null; then
    echo "python3"
  elif command -v python &> /dev/null; then
    echo "python"
  else
    return 1
  fi
}

check_pip() {
  local python_cmd="$1"
  if $python_cmd -m pip --version &> /dev/null; then
    local version=$($python_cmd -m pip --version 2>&1 | head -1)
    print_success "pip found: $version"
    return 0
  fi
  print_warning "pip not found, attempting to install..."
  $python_cmd -m ensurepip --upgrade 2>/dev/null || {
    print_error "Could not install pip automatically"
    echo "  Install manually: $python_cmd -m ensurepip --upgrade"
    return 1
  }
  print_success "pip installed successfully"
}

# ─── Install Functions ──────────────────────────────────────────────

install_npm_deps() {
  local clean_install="$1"

  if [ "$clean_install" = "true" ] && [ -d "$PROJECT_ROOT/node_modules" ]; then
    print_step "Removing existing node_modules..."
    rm -rf "$PROJECT_ROOT/node_modules"
  fi

  if [ -f "$PROJECT_ROOT/package-lock.json" ]; then
    print_step "Installing Node.js dependencies (npm ci)..."
    cd "$PROJECT_ROOT"
    npm ci --loglevel=warn > "$NPM_LOG" 2>&1
  else
    print_step "Installing Node.js dependencies (npm install)..."
    cd "$PROJECT_ROOT"
    npm install --loglevel=warn > "$NPM_LOG" 2>&1
  fi
}

install_pip_deps() {
  local python_cmd="$1"
  local clean_install="$2"

  if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
    print_warning "No requirements.txt found, skipping Python dependencies"
    return 0
  fi

  print_step "Installing Python dependencies (pip install)..."
  cd "$PROJECT_ROOT"
  $python_cmd -m pip install -r requirements.txt --quiet > "$PIP_LOG" 2>&1
}

# ─── Main ───────────────────────────────────────────────────────────

main() {
  local clean_install="false"

  # Parse arguments
  for arg in "$@"; do
    case "$arg" in
      --clean)
        clean_install="true"
        ;;
      --help|-h)
        echo "Usage: ./scripts/setup.sh [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --clean    Clean install (remove existing deps first)"
        echo "  --help     Show this help message"
        exit 0
        ;;
    esac
  done

  print_header

  if [ "$clean_install" = "true" ]; then
    print_warning "Clean install mode enabled"
    echo ""
  fi

  # ─── Step 1: Check prerequisites ──────────────────────────────
  print_step "Checking prerequisites..."

  local prereq_ok=true

  check_node || prereq_ok=false
  check_npm || prereq_ok=false

  local python_cmd
  python_cmd=$(detect_python) || true

  if [ -z "$python_cmd" ]; then
    print_error "Python 3 is not installed!"
    echo "  Install it from: https://python.org/"
    prereq_ok=false
  else
    local py_version=$($python_cmd --version 2>&1)
    print_success "$py_version found"
  fi

  if [ "$prereq_ok" = "false" ]; then
    echo ""
    print_error "Missing prerequisites. Please install them and try again."
    exit 1
  fi

  check_pip "$python_cmd" || prereq_ok=false

  if [ "$prereq_ok" = "false" ]; then
    echo ""
    print_error "Missing prerequisites. Please install them and try again."
    exit 1
  fi

  echo ""

  # ─── Step 2: Install dependencies in parallel ─────────────────
  print_step "Installing dependencies in parallel..."
  echo ""

  local npm_pid pip_pid
  local npm_status=0 pip_status=0

  # Start npm install in background
  (install_npm_deps "$clean_install") &
  npm_pid=$!

  # Start pip install in background
  (install_pip_deps "$python_cmd" "$clean_install") &
  pip_pid=$!

  # Wait for npm
  echo -ne "  ${BLUE}npm${NC}:    installing..."
  if wait "$npm_pid" 2>/dev/null; then
    npm_status=0
    echo -e "\r  ${GREEN}npm${NC}:    done!              "
  else
    npm_status=1
    echo -e "\r  ${RED}npm${NC}:    FAILED             "
  fi

  # Wait for pip
  echo -ne "  ${BLUE}pip${NC}:    installing..."
  if wait "$pip_pid" 2>/dev/null; then
    pip_status=0
    echo -e "\r  ${GREEN}pip${NC}:    done!              "
  else
    pip_status=1
    echo -e "\r  ${RED}pip${NC}:    FAILED             "
  fi

  echo ""

  # ─── Step 3: Report results ───────────────────────────────────
  local total_time=$(elapsed_time)
  local has_errors=false

  if [ "$npm_status" -ne 0 ]; then
    has_errors=true
    print_error "npm install failed! Check log: $NPM_LOG"
    echo ""
    echo -e "${RED}Last 10 lines of npm log:${NC}"
    tail -10 "$NPM_LOG" 2>/dev/null || true
    echo ""
  fi

  if [ "$pip_status" -ne 0 ]; then
    has_errors=true
    print_error "pip install failed! Check log: $PIP_LOG"
    echo ""
    echo -e "${RED}Last 10 lines of pip log:${NC}"
    tail -10 "$PIP_LOG" 2>/dev/null || true
    echo ""
  fi

  if [ "$has_errors" = "true" ]; then
    echo ""
    print_error "Setup completed with errors in $total_time"
    exit 1
  fi

  # ─── Step 4: Verify installation ──────────────────────────────
  print_step "Verifying installation..."

  local verify_ok=true

  # Check node_modules
  if [ -d "$PROJECT_ROOT/node_modules" ]; then
    local npm_pkg_count=$(ls -1 "$PROJECT_ROOT/node_modules" | wc -l)
    print_success "node_modules: $npm_pkg_count packages installed"
  else
    print_error "node_modules directory not found"
    verify_ok=false
  fi

  # Check g4f
  if $python_cmd -c "import g4f" 2>/dev/null; then
    local g4f_version=$($python_cmd -c "import g4f; print(g4f.__version__)" 2>/dev/null || echo "unknown")
    print_success "g4f v$g4f_version installed"
  else
    print_error "g4f Python package not found"
    verify_ok=false
  fi

  echo ""

  if [ "$verify_ok" = "false" ]; then
    print_error "Verification failed. Some dependencies may be missing."
    exit 1
  fi

  # ─── Done! ────────────────────────────────────────────────────
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║         Setup completed in $total_time!         ${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ${BOLD}Quick Start:${NC}"
  echo -e "    ${CYAN}npm run server:dev${NC}        Start the backend server"
  echo -e "    ${CYAN}npx expo start --web${NC}     Start the Expo web app"
  echo -e "    ${CYAN}npx expo start${NC}           Start Expo (all platforms)"
  echo ""
}

main "$@"
