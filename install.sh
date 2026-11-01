#!/bin/sh
# Phasentic installer for macOS and Linux. Run:
#   curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/main/install.sh | sh
# Installs uv (a Python installer, no admin rights needed), Python 3.12 and Phasentic,
# downloads the COD reference database (8.6 GB, about 10 GB free disk needed)
# and, on Linux, adds Phasentic to the applications menu.
set -eu

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing Phasentic..."
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/heads/main.zip
uv tool update-shell >/dev/null 2>&1 || true
phasentic="$(uv tool dir --bin)/phasentic"

if ! "$phasentic" setup-cod; then
    echo "The reference database is not installed yet. Run this installer again to resume." >&2
    exit 1
fi

if [ "$(uname)" = "Linux" ]; then
    menu="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$menu"
    printf '[Desktop Entry]\nType=Application\nName=Phasentic\nComment=Powder XRD phase identification\nExec="%s" serve --open\nTerminal=true\nCategories=Science;\n' \
        "$phasentic" > "$menu/phasentic.desktop"
    echo "Added Phasentic to the applications menu."
fi

echo
echo "Phasentic is installed. Open a new terminal and run: phasentic serve --open"
