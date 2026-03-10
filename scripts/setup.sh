#!/usr/bin/env bash
#
# Dzeck AI - Auto Setup & Install Dependencies
# Installs Node.js (npm) + Python (pip) packages and creates .env file.
#
# Usage:
#   ./scripts/setup.sh          # Install all dependencies
#   ./scripts/setup.sh --clean  # Clean install (remove existing deps first)
#

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LOG_DIR="$PROJECT_ROOT/.setup-logs"
mkdir -p "$LOG_DIR"
NPM_LOG="$LOG_DIR/npm-install.log"
PIP_LOG="$LOG_DIR/pip-install.log"

START_TIME=$(date +%s)

# ─── Helper Functions ──────────────────────────────────────────────────────────

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
  local end_time end_time
  end_time=$(date +%s)
  local elapsed=$((end_time - START_TIME))
  local minutes=$((elapsed / 60))
  local seconds=$((elapsed % 60))
  if [ "$minutes" -gt 0 ]; then
    echo "${minutes}m ${seconds}s"
  else
    echo "${seconds}s"
  fi
}

# ─── Dependency Checks ─────────────────────────────────────────────────────────

check_node() {
  if ! command -v node &> /dev/null; then
    print_error "Node.js is not installed! Install from: https://nodejs.org/"
    return 1
  fi
  local version
  version=$(node --version)
  print_success "Node.js $version found"
}

check_npm() {
  if ! command -v npm &> /dev/null; then
    print_error "npm is not installed!"
    return 1
  fi
  local version
  version=$(npm --version)
  print_success "npm v$version found"
}

detect_python() {
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
    local version
    version=$($python_cmd -m pip --version 2>&1 | head -1)
    print_success "pip found: $version"
    return 0
  fi
  print_warning "pip not found, attempting to install..."
  $python_cmd -m ensurepip --upgrade 2>/dev/null || {
    print_error "Could not install pip automatically"
    return 1
  }
  print_success "pip installed successfully"
}

# ─── .env Auto-Create ─────────────────────────────────────────────────────────

create_env_file() {
  local env_file="$PROJECT_ROOT/.env"
  local example_file="$PROJECT_ROOT/.env.example"

  if [ -f "$env_file" ]; then
    print_success ".env file already exists — skipping creation"
    return 0
  fi

  if [ ! -f "$example_file" ]; then
    print_warning ".env.example not found — skipping .env creation"
    return 0
  fi

  print_step "Creating .env file from .env.example..."
  cp "$example_file" "$env_file"

  # ── Auto-fill known env vars from current environment (Replit Secrets) ──
  local filled=0
  local keys=(
    CF_API_KEY CF_ACCOUNT_ID CF_GATEWAY_NAME
    CF_MODEL CF_AGENT_MODEL
    MONGODB_URI
    REDIS_HOST REDIS_PORT REDIS_PASSWORD
    SESSION_TTL_HOURS PLAYWRIGHT_ENABLED
    PORT NODE_ENV APP_DOMAIN
    EXPO_PUBLIC_DOMAIN CORS_ORIGINS
  )

  for key in "${keys[@]}"; do
    local val="${!key:-}"
    if [ -n "$val" ]; then
      # Replace placeholder in .env using sed (cross-platform)
      if grep -q "^${key}=" "$env_file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$env_file"
        filled=$((filled + 1))
      fi
    fi
  done

  if [ "$filled" -gt 0 ]; then
    print_success ".env created and auto-filled $filled values from environment"
  else
    print_success ".env created from .env.example (fill in your credentials)"
    echo -e "    ${YELLOW}Edit ${CYAN}$env_file${YELLOW} with your Cloudflare/MongoDB/Redis credentials${NC}"
  fi
}

# ─── Install Functions ─────────────────────────────────────────────────────────

install_npm_deps() {
  local clean_install="$1"

  if [ "$clean_install" = "true" ] && [ -d "$PROJECT_ROOT/node_modules" ]; then
    print_step "Removing existing node_modules..."
    rm -rf "$PROJECT_ROOT/node_modules"
  fi

  cd "$PROJECT_ROOT"
  if [ -f "package-lock.json" ]; then
    npm ci --loglevel=warn > "$NPM_LOG" 2>&1
  else
    npm install --loglevel=warn > "$NPM_LOG" 2>&1
  fi
}

install_pip_deps() {
  local python_cmd="$1"

  if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
    print_warning "No requirements.txt found — skipping Python deps"
    return 0
  fi

  cd "$PROJECT_ROOT"

  if $python_cmd -m pip install -r requirements.txt --quiet > "$PIP_LOG" 2>&1; then
    return 0
  fi
  if $python_cmd -m pip install -r requirements.txt \
      --quiet --break-system-packages >> "$PIP_LOG" 2>&1; then
    return 0
  fi
  if $python_cmd -m pip install -r requirements.txt \
      --quiet --user >> "$PIP_LOG" 2>&1; then
    return 0
  fi

  if $python_cmd -c "import pydantic, requests" 2>/dev/null; then
    echo "Packages already available via system packager" >> "$PIP_LOG"
    return 0
  fi

  return 1
}

install_playwright_browsers() {
  local python_cmd="$1"

  if ! $python_cmd -c "import playwright" 2>/dev/null; then
    print_warning "playwright not installed — skipping browser install"
    return 0
  fi

  if $python_cmd -m playwright install chromium --quiet 2>/dev/null; then
    print_success "Playwright Chromium browser installed"
  else
    print_warning "Could not install Playwright Chromium (HTTP fallback will be used)"
  fi
}

# ─── Verify Functions ──────────────────────────────────────────────────────────

verify_tsx() {
  if npx tsx --version &> /dev/null 2>&1; then
    local ver
    ver=$(npx tsx --version 2>/dev/null | head -1) || ver="unknown"
    print_success "tsx ${ver} (TypeScript runner for backend)"
    return 0
  else
    print_error "tsx not found (required to run backend server)"
    return 1
  fi
}

verify_pydantic() {
  local python_cmd="$1"
  if $python_cmd -c "import pydantic; assert int(pydantic.VERSION.split('.')[0]) >= 2" 2>/dev/null; then
    local ver
    ver=$($python_cmd -c "import pydantic; print(pydantic.VERSION)" 2>/dev/null) || ver="unknown"
    print_success "pydantic v${ver} (required for agent data models)"
    return 0
  else
    print_error "pydantic v2+ not found (required for agent data models)"
    return 1
  fi
}

verify_motor() {
  local python_cmd="$1"
  if $python_cmd -c "import motor" 2>/dev/null; then
    local ver
    ver=$($python_cmd -m pip show motor 2>/dev/null | grep "^Version:" | awk '{print $2}') || ver="unknown"
    print_success "motor v${ver} (MongoDB async driver)"
    return 0
  else
    print_warning "motor not found (MongoDB session persistence will be disabled)"
    return 1
  fi
}

verify_redis() {
  local python_cmd="$1"
  if $python_cmd -c "import redis" 2>/dev/null; then
    local ver
    ver=$($python_cmd -m pip show redis 2>/dev/null | grep "^Version:" | awk '{print $2}') || ver="unknown"
    print_success "redis v${ver} (Redis session cache)"
    return 0
  else
    print_warning "redis not found (Redis cache will be disabled)"
    return 1
  fi
}

verify_playwright() {
  local python_cmd="$1"
  if $python_cmd -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    local ver
    ver=$($python_cmd -m pip show playwright 2>/dev/null | grep "^Version:" | awk '{print $2}') || ver="unknown"
    print_success "playwright v${ver} (real browser automation)"
    return 0
  else
    print_warning "playwright not found (browser tool will use HTTP fallback)"
    return 1
  fi
}

verify_beautifulsoup4() {
  local python_cmd="$1"
  if $python_cmd -c "import bs4" 2>/dev/null; then
    local ver
    ver=$($python_cmd -m pip show beautifulsoup4 2>/dev/null | grep "^Version:" | awk '{print $2}') || ver="unknown"
    print_success "beautifulsoup4 v${ver} (HTML parsing for browser tool)"
    return 0
  else
    print_warning "beautifulsoup4 not found (browser HTML parsing may be limited)"
    return 1
  fi
}

verify_aiohttp() {
  local python_cmd="$1"
  if $python_cmd -c "import aiohttp" 2>/dev/null; then
    local ver
    ver=$($python_cmd -m pip show aiohttp 2>/dev/null | grep "^Version:" | awk '{print $2}') || ver="unknown"
    print_success "aiohttp v${ver} (async HTTP client)"
    return 0
  else
    print_warning "aiohttp not found (optional)"
    return 1
  fi
}

# ─── Main ─────────────────────────────────────────────────────────────────────

main() {
  local clean_install="false"

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

  # ─── Step 1: Prerequisites ────────────────────────────────────────
  print_step "Checking prerequisites..."

  local prereq_ok=true

  check_node || prereq_ok=false
  check_npm  || prereq_ok=false

  local python_cmd=""
  python_cmd=$(detect_python) || true

  if [ -z "$python_cmd" ]; then
    print_error "Python 3 is not installed! Install from: https://python.org/"
    prereq_ok=false
  else
    local py_version
    py_version=$($python_cmd --version 2>&1)
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
    print_error "pip not available. Please install it manually."
    exit 1
  fi

  echo ""

  # ─── Step 2: Auto-create .env ─────────────────────────────────────
  create_env_file
  echo ""

  # ─── Step 3: Install deps in parallel ────────────────────────────
  print_step "Installing dependencies in parallel..."
  echo ""

  local npm_pid pip_pid
  local npm_status=0 pip_status=0

  (install_npm_deps "$clean_install") &
  npm_pid=$!

  (install_pip_deps "$python_cmd") &
  pip_pid=$!

  echo -ne "  ${BLUE}npm${NC}:    installing..."
  if wait "$npm_pid" 2>/dev/null; then
    npm_status=0
    echo -e "\r  ${GREEN}npm${NC}:    done!              "
  else
    npm_status=1
    echo -e "\r  ${RED}npm${NC}:    FAILED             "
  fi

  echo -ne "  ${BLUE}pip${NC}:    installing..."
  if wait "$pip_pid" 2>/dev/null; then
    pip_status=0
    echo -e "\r  ${GREEN}pip${NC}:    done!              "
  else
    pip_status=1
    echo -e "\r  ${YELLOW}pip${NC}:    skipped (system-managed)  "
  fi

  echo ""

  if [ "$npm_status" -ne 0 ]; then
    print_error "npm install failed! Check log: $NPM_LOG"
    tail -10 "$NPM_LOG" 2>/dev/null || true
    echo ""
    exit 1
  fi

  if [ "$pip_status" -ne 0 ]; then
    print_warning "pip install could not run directly (may be system-managed on Replit/NixOS)"
    echo ""
  fi

  # ─── Step 4: Install Playwright browsers ─────────────────────────
  print_step "Installing Playwright browser..."
  install_playwright_browsers "$python_cmd"
  echo ""

  # ─── Step 5: Verify installation ─────────────────────────────────
  print_step "Verifying installation..."

  local verify_ok=true

  if [ -d "$PROJECT_ROOT/node_modules" ]; then
    local npm_pkg_count
    npm_pkg_count=$(ls -1 "$PROJECT_ROOT/node_modules" | wc -l)
    print_success "node_modules: $npm_pkg_count packages installed"
  else
    print_error "node_modules directory not found"
    verify_ok=false
  fi

  verify_tsx             || verify_ok=false
  verify_pydantic        "$python_cmd" || verify_ok=false
  verify_motor           "$python_cmd" || true
  verify_redis           "$python_cmd" || true
  verify_playwright      "$python_cmd" || true
  verify_beautifulsoup4  "$python_cmd" || true
  verify_aiohttp         "$python_cmd" || true

  echo ""

  if [ "$verify_ok" = "false" ]; then
    print_error "Verification failed. Some required dependencies are missing."
    echo ""
    echo -e "  ${YELLOW}On Replit/NixOS, install Python packages via the Replit Packager, or run:${NC}"
    echo -e "  ${CYAN}pip install --break-system-packages pydantic motor redis playwright beautifulsoup4 aiohttp${NC}"
    exit 1
  fi

  # ─── Done! ────────────────────────────────────────────────────────
  local total_time
  total_time=$(elapsed_time)
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║    Setup completed in ${total_time}!              ${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ${BOLD}Quick Start:${NC}"
  echo -e "    ${CYAN}npm run server:dev${NC}                  Backend server (port 5000)"
  echo -e "    ${CYAN}npx --yes expo start --localhost${NC}    Expo frontend (port 8081)"
  echo ""
  echo -e "  ${BOLD}AI Configuration:${NC}"
  echo -e "    Chat model:  ${CYAN}\$CF_MODEL${NC}       (fast, llama-3-8b)"
  echo -e "    Agent model: ${CYAN}\$CF_AGENT_MODEL${NC} (powerful, llama-3.1-70b)"
  echo -e "    Credentials: ${CYAN}.env${NC} file (CF_API_KEY, CF_ACCOUNT_ID, CF_GATEWAY_NAME)"
  echo ""
  echo -e "  ${BOLD}New Features:${NC}"
  echo -e "    MongoDB session persistence  ${CYAN}\$MONGODB_URI${NC}"
  echo -e "    Redis session cache          ${CYAN}\$REDIS_HOST${NC} / ${CYAN}\$REDIS_PASSWORD${NC}"
  echo -e "    Playwright real browser      ${CYAN}\$PLAYWRIGHT_ENABLED=true${NC}"
  echo ""
}

main "$@"
