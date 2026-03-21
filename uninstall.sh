#!/usr/bin/env bash
# uninstall.sh — Removes the `plagcheck` command and its venv

COMMAND_NAME="plagcheck"
TARGET="/usr/local/bin/$COMMAND_NAME"
VENV_DIR="$HOME/.plagcheck-venv"

if [ -f "$TARGET" ]; then
    sudo rm "$TARGET"
    echo "[✓] Removed $TARGET"
else
    echo "[!] Command not found at $TARGET"
fi

if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    echo "[✓] Removed venv at $VENV_DIR"
fi

echo "    '$COMMAND_NAME' has been fully uninstalled."
