#!/bin/bash
# ============================================================
#  Awakener - Server Setup Script
#
#  Usage:
#    1. Upload the awakener/ directory to the server
#    2. Run: chmod +x setup.sh && sudo ./setup.sh
#    3. Edit config.json to set your API key and model
#    4. Edit persona.md to customize agent personality
#    5. Start: cd activator && source ../venv/bin/activate && python main.py
#
#  Recommended: run in tmux for persistence
#    tmux new -s awakener
#    cd /opt/awakener/activator && source ../venv/bin/activate && python main.py
#    (Ctrl+B then D to detach)
# ============================================================

set -e

INSTALL_DIR="/opt/awakener"
AGENT_HOME="/home/agent"

echo "================================================"
echo "  Awakener - Setup"
echo "================================================"

# ── 1. System dependencies ──
echo "[1/5] Installing system dependencies..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv tmux curl git

# ── 2. Copy project files ──
echo "[2/5] Installing Awakener..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${INSTALL_DIR}"
cp -r "${SCRIPT_DIR}/activator"    "${INSTALL_DIR}/"
cp    "${SCRIPT_DIR}/config.json"  "${INSTALL_DIR}/"
cp    "${SCRIPT_DIR}/persona.md"   "${INSTALL_DIR}/"
cp    "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
mkdir -p "${INSTALL_DIR}/logs"

# ── 3. Python venv ──
echo "[3/5] Creating virtual environment..."
cd "${INSTALL_DIR}"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# ── 4. Agent home directory ──
echo "[4/5] Creating agent home..."
mkdir -p "${AGENT_HOME}"

# Create empty notebook
if [ ! -f "${AGENT_HOME}/notebook.md" ]; then
    touch "${AGENT_HOME}/notebook.md"
    echo "  Created empty notebook.md"
fi

# ── 5. Protect activator files ──
echo "[5/5] Protecting activator files..."
chmod 444 "${INSTALL_DIR}/activator/"*.py

echo ""
echo "================================================"
echo "  Setup Complete!"
echo "================================================"
echo ""
echo "  Next steps:"
echo "  1. Set API key:    nano ${INSTALL_DIR}/config.json"
echo "  2. Set persona:    nano ${INSTALL_DIR}/persona.md"
echo "  3. Start:"
echo "     tmux new -s awakener"
echo "     cd ${INSTALL_DIR}/activator"
echo "     source ../venv/bin/activate"
echo "     python main.py"
echo ""
echo "  Observer dashboard: http://<server-ip>:8080"
echo ""
