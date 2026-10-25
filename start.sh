#!/bin/sh
# Navigate to script directory portably
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "========================================================"
echo "  KWR - Keyword Research Intelligence Suite (Phone Ready)"
echo "========================================================"
echo ""

# Find available Python binary
if command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PY_BIN="python"
else
    if [ -n "$TERMUX_VERSION" ] || [ -d "/data/data/com.termux" ]; then
        echo "[!] Android Termux detected, but Python is not installed yet."
        echo "    Run: pkg install python git -y"
    else
        echo "[!] Python is not installed. Please install Python 3.8+."
    fi
    exit 1
fi

echo "[*] Checking and installing dependencies with $PY_BIN..."
$PY_BIN -m pip install -r requirements.txt >/dev/null 2>&1 || \
$PY_BIN -m pip install --break-system-packages -r requirements.txt >/dev/null 2>&1 || \
$PY_BIN -m pip install flask requests >/dev/null 2>&1 || \
$PY_BIN -m pip install --break-system-packages flask requests >/dev/null 2>&1 || \
echo "[i] Proceeding with existing environment packages..."

echo ""
echo "[*] Starting Web Command Center..."
$PY_BIN kwr.py start
