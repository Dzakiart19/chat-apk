#!/usr/bin/env bash
#
# Dzeck AI — Auto Setup & Install Dependencies
# Run from project root: ./setup.sh
#
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_step()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} ${BOLD}$1${NC}"; }
print_ok()    { echo -e "${GREEN}  ✓ $1${NC}"; }
print_warn()  { echo -e "${YELLOW}  ⚠ $1${NC}"; }
print_error() { echo -e "${RED}  ✗ $1${NC}"; }

echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║     Dzeck AI — Setup & Install           ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ─── Python detection ─────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then PYTHON="$cmd"; break; fi
done
if [ -z "$PYTHON" ]; then print_error "Python not found! Install Python 3.10+"; exit 1; fi
print_ok "Python: $($PYTHON --version)"

# ─── Node.js check ────────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then print_error "Node.js not found! Install Node.js 18+"; exit 1; fi
print_ok "Node.js: $(node --version) / npm: $(npm --version)"

# ─── npm packages ─────────────────────────────────────────────────────────────
print_step "Installing Node.js packages..."
cd "$PROJECT_ROOT"
npm install --no-audit --prefer-offline 2>&1 | grep -E "added|updated|packages" | head -3 || true
print_ok "Node.js packages ready"

# ─── Python packages ──────────────────────────────────────────────────────────
print_step "Installing Python packages..."

PIP_FLAGS=""
if $PYTHON -m pip install --help 2>&1 | grep -q 'break-system'; then
  PIP_FLAGS="--break-system-packages"
fi

# Current required packages (synced with project state)
PYTHON_PACKAGES=(
  "pydantic>=2.0.0"
  "beautifulsoup4>=4.12.0"
  "requests>=2.31.0"
  "aiohttp>=3.9.0"
  "playwright>=1.40.0"
  "websockify>=0.11.0"
)

for pkg in "${PYTHON_PACKAGES[@]}"; do
  pkg_name="${pkg%%[>=<]*}"
  import_name="${pkg_name//-/_}"
  if $PYTHON -c "import ${import_name}" &>/dev/null 2>&1; then
    print_ok "$pkg_name (already installed)"
  else
    echo -n "  Installing $pkg_name..."
    if $PYTHON -m pip install $PIP_FLAGS "$pkg" -q 2>&1; then
      print_ok " done"
    else
      print_warn " failed — you may need to install manually"
    fi
  fi
done

# ─── Playwright browser ───────────────────────────────────────────────────────
print_step "Checking Playwright browser (Chromium)..."
if $PYTHON -m playwright install chromium --quiet 2>&1; then
  print_ok "Playwright Chromium ready"
else
  print_warn "Run manually: python3 -m playwright install chromium"
fi

# ─── System tools for VNC ─────────────────────────────────────────────────────
print_step "Checking VNC streaming tools..."
VNC_OK=true
for tool in Xvfb x11vnc; do
  if command -v "$tool" &>/dev/null; then
    print_ok "$tool found"
  else
    print_warn "$tool not found — VNC live streaming unavailable (screenshot mode will be used)"
    VNC_OK=false
  fi
done
if $VNC_OK; then print_ok "VNC stack available — live browser streaming enabled"; fi

# ─── .env file ────────────────────────────────────────────────────────────────
print_step "Checking .env configuration..."
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  if [ -f "$PROJECT_ROOT/.env.example" ]; then
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    print_warn ".env created from .env.example — set CF_API_KEY, CF_ACCOUNT_ID, CF_GATEWAY_NAME"
  else
    cat > "$PROJECT_ROOT/.env" <<'EOF'
# Cloudflare AI Gateway — required
CF_API_KEY=
CF_ACCOUNT_ID=
CF_GATEWAY_NAME=

# Model selection (optional)
CF_MODEL=@cf/meta/llama-3-8b-instruct
CF_AGENT_MODEL=@cf/meta/llama-3.1-70b-instruct

# Optional features
PLAYWRIGHT_ENABLED=true
PORT=5000
NODE_ENV=development
EOF
    print_warn ".env created — fill in CF_API_KEY, CF_ACCOUNT_ID, CF_GATEWAY_NAME"
  fi
else
  print_ok ".env file exists"
fi

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   Setup selesai!                         ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Mulai server:${NC}"
echo -e "    ${CYAN}npm run server:dev${NC}     → http://localhost:5000"
echo ""
echo -e "  ${BOLD}Konfigurasi AI:${NC}"
echo -e "    Edit ${CYAN}.env${NC} → isi CF_API_KEY, CF_ACCOUNT_ID, CF_GATEWAY_NAME"
echo ""
