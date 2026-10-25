#!/usr/bin/env bash
echo "========================================================"
echo "  KWR - Keyword Research Intelligence Suite"
echo "========================================================"
echo ""
echo "[*] Checking and installing dependencies..."
pip install -r requirements.txt
echo ""
echo "[*] Starting Web Command Center..."
python3 kwr.py start
