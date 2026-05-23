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

# ── 2. Create a dedicated venv ────────────────────────────────────────────────
echo ""
echo "[*] Creating virtual environment at $VENV_DIR …"
python3 -m venv "$VENV_DIR"
echo "[✓] Virtual environment ready"

# ── 3. Install all Python dependencies (no system packages needed) ────────────
echo ""
echo "[*] Installing Python dependencies…"
echo "    (easyocr will download its model weights on first run — ~100 MB)"
echo ""
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet \
    pdfplumber \
    pypdf \
    pdfminer.six \
    pymupdf \
    pillow \
    numpy \
    easyocr
echo "[✓] All dependencies installed"
echo ""
echo "  Packages installed:"
echo "    pdfplumber  — digital text extraction (Word, LibreOffice, LaTeX PDFs)"
echo "    pypdf       — fallback text extraction"
echo "    pymupdf     — page rasterization (all PDF types)"
echo "    pillow      — image processing"
echo "    numpy       — array operations"
echo "    easyocr     — OCR engine (fully pip-based, no system binary needed)"

# ── 4. Copy the script into the venv ──────────────────────────────────────────
cp "$SOURCE" "$VENV_DIR/plagiarism_checker.py"

# ── 5. Write a thin launcher to /usr/local/bin ────────────────────────────────
echo ""
echo "[*] Installing '$COMMAND_NAME' command to $INSTALL_DIR …"
sudo tee "$TARGET" > /dev/null << EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python3" "$VENV_DIR/plagiarism_checker.py" "\$@"
EOF
sudo chmod +x "$TARGET"
echo "[✓] Installed launcher at $TARGET"

# ── 6. Verify ─────────────────────────────────────────────────────────────────
echo ""
if command -v "$COMMAND_NAME" &>/dev/null; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ✅ Done! You can now use it anywhere:"
    echo ""
    echo "     $COMMAND_NAME file1.pdf file2.pdf"
    echo ""
    echo "  Options:"
    echo "     --no-ocr               Skip OCR"
    echo "     --no-visuals           Skip visual comparison"
    echo "     --no-sentences         Skip sentence matching"
    echo "     --sentence-threshold T Similarity threshold (default 0.75)"
    echo "     --help                 Show all options"
    echo ""
    echo "  Note: First run downloads easyocr model weights (~100 MB)."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo "[WARN] '$COMMAND_NAME' not found in PATH."
    echo "       Try: source ~/.zshrc  or open a new terminal."
fi
echo ""
