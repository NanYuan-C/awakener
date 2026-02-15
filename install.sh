#!/usr/bin/env bash
# =============================================================================
# Awakener - One-Click Installation Script
# =============================================================================
# Usage:
#   bash install.sh                  # Install to /opt/awakener (default)
#   bash install.sh /path/to/dir     # Install to custom directory
#
# What this script does:
#   1. Check and install system dependencies (Python 3.10+, pip, git)
#   2. Clone the repository (or skip if already present)
#   3. Create a Python virtual environment
#   4. Install Python dependencies
#   5. Create the agent home directory
#   6. Create .env file from template (if not exists)
#   7. Print next steps
#
# After installation, start with:
#   cd /opt/awakener && source venv/bin/activate && python app.py
# =============================================================================

set -e

# -- Configuration -----------------------------------------------------------
DEFAULT_INSTALL_DIR="/opt/awakener"
REPO_URL="https://github.com/NanYuan-C/awakener.git"
PYTHON_MIN_VERSION="3.10"
AGENT_HOME="/home/agent"

# -- Colors ------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# -- Parse arguments ---------------------------------------------------------
INSTALL_DIR="${1:-$DEFAULT_INSTALL_DIR}"

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║        AWAKENER - Installation Script        ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
info "Install directory: $INSTALL_DIR"
info "Agent home: $AGENT_HOME"
echo ""

# -- Step 1: Check system dependencies --------------------------------------
info "Step 1/6: Checking system dependencies..."

# Check if running as root (recommended for /opt and /home)
if [ "$EUID" -ne 0 ] && [ "$INSTALL_DIR" = "$DEFAULT_INSTALL_DIR" ]; then
    warn "Not running as root. You may need sudo for /opt and /home directories."
fi

# Update package index first (critical for fresh servers)
APT_UPDATED=false
update_apt() {
    if [ "$APT_UPDATED" = false ] && command -v apt-get &> /dev/null; then
        info "Updating package index..."
        apt-get update -qq
        APT_UPDATED=true
    fi
}

# Check Python
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &> /dev/null; then
        PY_VERSION=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        PY_MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        PY_MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    warn "Python >= $PYTHON_MIN_VERSION not found. Attempting to install..."
    if command -v apt-get &> /dev/null; then
        update_apt
        apt-get install -y -qq python3 python3-pip
        PYTHON_CMD="python3"
    elif command -v yum &> /dev/null; then
        yum install -y python3 python3-pip
        PYTHON_CMD="python3"
    elif command -v dnf &> /dev/null; then
        dnf install -y python3 python3-pip
        PYTHON_CMD="python3"
    else
        error "Cannot install Python automatically. Please install Python >= $PYTHON_MIN_VERSION manually."
    fi
fi

PY_VERSION=$("$PYTHON_CMD" --version 2>&1)
PY_MINOR=$("$PYTHON_CMD" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
PY_MAJOR=$("$PYTHON_CMD" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
ok "Python: $PY_VERSION ($PYTHON_CMD)"

# Check pip
if ! "$PYTHON_CMD" -m pip --version &> /dev/null; then
    warn "pip not found. Attempting to install..."
    if command -v apt-get &> /dev/null; then
        update_apt
        apt-get install -y -qq python3-pip
    else
        "$PYTHON_CMD" -m ensurepip --upgrade 2>/dev/null || error "Cannot install pip. Please install it manually."
    fi
fi
ok "pip: $("$PYTHON_CMD" -m pip --version 2>&1 | head -1)"

# Check venv module
# On Ubuntu/Debian, the venv module requires a version-specific package
# e.g., python3.12-venv for Python 3.12
# We test by actually trying to create a temporary venv to ensure it works
VENV_TEST_DIR="/tmp/awakener-venv-test-$$"
if ! "$PYTHON_CMD" -m venv "$VENV_TEST_DIR" &> /dev/null; then
    rm -rf "$VENV_TEST_DIR"
    warn "venv module not functional. Attempting to install..."
    if command -v apt-get &> /dev/null; then
        update_apt
        # Try version-specific package first (e.g., python3.12-venv),
        # then fall back to generic python3-venv
        VENV_PKG="python${PY_MAJOR}.${PY_MINOR}-venv"
        info "Installing $VENV_PKG ..."
        apt-get install -y -qq "$VENV_PKG" 2>/dev/null || apt-get install -y -qq python3-venv
        
        # Test again after installation
        if ! "$PYTHON_CMD" -m venv "$VENV_TEST_DIR" &> /dev/null; then
            rm -rf "$VENV_TEST_DIR"
            error "Failed to install python3-venv. Please install python${PY_MAJOR}.${PY_MINOR}-venv manually."
        fi
    else
        error "Cannot install python3-venv. Please install it manually."
    fi
fi
rm -rf "$VENV_TEST_DIR"
ok "venv module available"

# Check git
if ! command -v git &> /dev/null; then
    warn "git not found. Attempting to install..."
    if command -v apt-get &> /dev/null; then
        update_apt
        apt-get install -y -qq git
    elif command -v yum &> /dev/null; then
        yum install -y git
    else
        error "Cannot install git. Please install it manually."
    fi
fi
ok "git: $(git --version)"

echo ""

# -- Step 2: Clone or update repository -------------------------------------
info "Step 2/6: Setting up repository..."

if [ -d "$INSTALL_DIR/.git" ]; then
    ok "Repository already exists at $INSTALL_DIR"
    info "Pulling latest changes..."
    cd "$INSTALL_DIR"
    git pull origin main || warn "Could not pull updates (maybe local changes exist)"
elif [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/app.py" ]; then
    ok "Project files found at $INSTALL_DIR (not a git repo)"
else
    info "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    ok "Repository cloned to $INSTALL_DIR"
fi

cd "$INSTALL_DIR"
echo ""

# -- Step 3: Create virtual environment -------------------------------------
info "Step 3/6: Setting up Python virtual environment..."

# Check if venv exists and is valid (has activate script)
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    ok "Virtual environment already exists"
else
    # Remove incomplete venv if it exists
    if [ -d "venv" ]; then
        warn "Removing incomplete virtual environment..."
        rm -rf venv
    fi
    "$PYTHON_CMD" -m venv venv
    ok "Virtual environment created: $INSTALL_DIR/venv"
fi

# Activate venv
source venv/bin/activate
ok "Virtual environment activated"
echo ""

# -- Step 4: Install Python dependencies ------------------------------------
info "Step 4/6: Installing Python dependencies..."

pip install --upgrade pip -q
pip install -r requirements.txt -q
ok "All dependencies installed"
echo ""

# -- Step 5: Create agent home directory -------------------------------------
info "Step 5/6: Creating agent home directory..."

if [ -d "$AGENT_HOME" ]; then
    ok "Agent home already exists: $AGENT_HOME"
else
    mkdir -p "$AGENT_HOME"
    ok "Agent home created: $AGENT_HOME"
fi

# Create data directory
mkdir -p data/skills data/logs
ok "Data directories ready"
echo ""

# -- Step 6: Create .env file -----------------------------------------------
info "Step 6/6: Checking configuration files..."

if [ -f ".env" ]; then
    ok ".env file already exists"
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        ok ".env file created from template"
        warn "Please edit .env to add your API keys"
    else
        cat > .env << 'ENVEOF'
# Awakener - API Keys
# Add your LLM provider API key below.
# At least one key is required for the agent to function.

# DEEPSEEK_API_KEY=sk-your-key-here
# OPENAI_API_KEY=sk-your-key-here
# ANTHROPIC_API_KEY=sk-your-key-here
ENVEOF
        ok ".env file created"
        warn "Please edit .env to add your API keys"
    fi
fi

if [ -f "config.yaml" ]; then
    ok "config.yaml exists"
else
    warn "config.yaml not found — it will be created with defaults on first run"
fi

echo ""

# -- Done! -------------------------------------------------------------------
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║        Installation Complete! ✓              ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Add your API key:"
echo "     nano $INSTALL_DIR/.env"
echo ""
echo "  2. Start Awakener:"
echo "     cd $INSTALL_DIR"
echo "     source venv/bin/activate"
echo "     python app.py"
echo ""
echo "  3. Or run in tmux (recommended for production):"
echo "     tmux new -s awakener"
echo "     cd $INSTALL_DIR && source venv/bin/activate && python app.py"
echo "     # Press Ctrl+B then D to detach"
echo ""
echo "  Console will be available at: http://your-server-ip:39120"
echo ""
