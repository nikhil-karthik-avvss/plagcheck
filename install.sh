#!/usr/bin/env bash
# install.sh — Installs plagiarism_checker.py as a system-wide `plagcheck` command

set -e

COMMAND_NAME="plagcheck"
VENV_DIR="$HOME/.plagcheck-venv"
INSTALL_DIR="/usr/local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/plagiarism_checker.py"
TARGET="$INSTALL_DIR/$COMMAND_NAME"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Plagiarism Checker — Installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Check Python 3 ─────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Install it with: sudo apt install python3"
    exit 1
fi
echo "[✓] Python 3 found: $(python3 --version)"

# ── 2. Install system deps (optional, non-fatal) ──────────────────────────────
echo ""
echo "[*] Trying to install system dependencies (optional)…"
if sudo apt-get install -y -qq tesseract-ocr 2>/dev/null; then
    echo "[✓] tesseract-ocr installed (enables OCR for scanned PDFs)"
else
    echo "[!] Skipped tesseract-ocr (apt issue — OCR will be unavailable)."
fi

# ── 3. Create a dedicated venv ────────────────────────────────────────────────
echo ""
echo "[*] Creating virtual environment at $VENV_DIR …"
python3 -m venv "$VENV_DIR"
echo "[✓] Virtual environment ready"

# ── 4. Install Python deps inside the venv ────────────────────────────────────
echo ""
echo "[*] Installing Python dependencies inside venv…"
"$VENV_DIR/bin/pip" install --quiet \
    pdfplumber pypdf pdfminer.six \
    pymupdf pillow pytesseract
echo "[✓] Installed: pdfplumber, pypdf, pdfminer.six, pymupdf, pillow, pytesseract"

# ── 5. Copy the script into the venv ──────────────────────────────────────────
cp "$SOURCE" "$VENV_DIR/plagiarism_checker.py"

# ── 6. Write a thin launcher to /usr/local/bin ────────────────────────────────
echo ""
echo "[*] Installing '$COMMAND_NAME' command to $INSTALL_DIR …"
sudo tee "$TARGET" > /dev/null << EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python3" "$VENV_DIR/plagiarism_checker.py" "\$@"
EOF
sudo chmod +x "$TARGET"
echo "[✓] Installed launcher at $TARGET"

# ── 7. Verify ─────────────────────────────────────────────────────────────────
echo ""
if command -v "$COMMAND_NAME" &>/dev/null; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ✅ Done! You can now use it anywhere:"
    echo ""
    echo "     $COMMAND_NAME file1.pdf file2.pdf"
    echo ""
    echo "  Options:"
    echo "     --no-ocr               Skip OCR for scanned PDFs"
    echo "     --no-images            Skip image comparison"
    echo "     --no-sentences         Skip sentence matching"
    echo "     --sentence-threshold T Set similarity threshold (default 0.75)"
    echo "     --help                 Show all options"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo "[WARN] '$COMMAND_NAME' not found in PATH."
    echo "       Try: source ~/.zshrc  or open a new terminal."
fi
echo ""
