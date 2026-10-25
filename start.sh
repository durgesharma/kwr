#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1

echo "========================================================"
echo "  KWR - Keyword Research Intelligence Suite"
echo "========================================================"
echo ""

# Find available Python binary
if command -v python3 &>/dev/null; then
    PY_BIN="python3"
elif command -v python &>/dev/null; then
    PY_BIN="python"
else
    echo "[!] Error: Python is not installed. Please install Python 3.8+."
    exit 1
fi

echo "[*] Checking and installing dependencies with $PY_BIN..."
$PY_BIN -m pip install -r requirements.txt 2>/dev/null || \
$PY_BIN -m pip install --break-system-packages -r requirements.txt 2>/dev/null || \
$PY_BIN -m pip install flask requests 2>/dev/null || \
$PY_BIN -m pip install --break-system-packages flask requests 2>/dev/null || \
echo "[i] Proceeding with current Python environment..."

echo ""
echo "[*] Starting Web Command Center..."
$PY_BIN kwr.py start
