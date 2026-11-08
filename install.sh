#!/bin/sh
# Phasentic installer for macOS and Linux. Run:
#   curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/main/install.sh | sh
# Installs uv (a Python installer, no admin rights needed), Python 3.12 and Phasentic,
# downloads the COD reference database (8.6 GB, about 10 GB free disk needed)
# and adds Phasentic to Applications (macOS) or the applications menu (Linux).
set -eu

assets=https://raw.githubusercontent.com/qaemu/phasentic/main/assets

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

case "$(uname)" in
Darwin)
    apps=/Applications
    [ -w "$apps" ] || { apps="$HOME/Applications"; mkdir -p "$apps"; }
    app="$apps/Phasentic.app"
    rm -rf "$app"
    mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
    curl -fsSL "$assets/phasentic.icns" -o "$app/Contents/Resources/phasentic.icns" || true
    printf '#!/bin/sh\nexec "%s-app"\n' "$phasentic" > "$app/Contents/MacOS/Phasentic"
    chmod +x "$app/Contents/MacOS/Phasentic"
    cat > "$app/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>Phasentic</string>
    <key>CFBundleIconFile</key><string>phasentic</string>
    <key>CFBundleIdentifier</key><string>io.github.qaemu.phasentic</string>
    <key>CFBundleName</key><string>Phasentic</string>
    <key>CFBundlePackageType</key><string>APPL</string>
</dict>
</plist>
EOF
    echo "Added Phasentic to $apps."
    ;;
Linux)
    icon="$HOME/.phasentic/phasentic.svg"
    mkdir -p "$HOME/.phasentic"
    curl -fsSL "$assets/phasentic.svg" -o "$icon" || icon=
    menu="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$menu"
    printf '[Desktop Entry]\nType=Application\nName=Phasentic\nComment=Powder XRD phase identification\nExec="%s-app"\nIcon=%s\nTerminal=false\nCategories=Science;\n' \
        "$phasentic" "$icon" > "$menu/phasentic.desktop"
    echo "Added Phasentic to the applications menu."
    if [ -z "${WAYLAND_DISPLAY:-}" ] && ! ldconfig -p 2>/dev/null | grep -q libxcb-cursor; then
        echo "Note: the Phasentic window needs libxcb-cursor0 (Debian/Ubuntu: sudo apt install libxcb-cursor0);"
        echo "without it Phasentic opens in the browser instead."
    fi
    ;;
esac

echo
echo "Phasentic is installed. Open it from your applications, or run: phasentic-app"
