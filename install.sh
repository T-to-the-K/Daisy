#!/bin/sh
# One-shot setup for Daisy (filewheel) on Debian/Ubuntu/Mint/Pop!_OS.
# Installs dependencies, registers autostart, and launches the wheel.
set -e

cd "$(dirname "$0")"

if ! command -v apt-get >/dev/null 2>&1; then
    echo "error: this installer needs apt (Debian/Ubuntu/Mint/Pop!_OS)." >&2
    echo "Install the equivalent packages manually for your distro." >&2
    exit 1
fi

PACKAGES="python3-gi python3-gi-cairo python3-xlib python3-pil \
gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
gstreamer1.0-plugins-ugly gstreamer1.0-libav libreoffice ghostscript \
poppler-utils zip xclip libnotify-bin"

if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    echo "warning: you are on a Wayland session." >&2
    echo "Global hotkeys need X11. Log out, choose 'Xorg'/'Cinnamon' at the" >&2
    echo "login screen, and log back in." >&2
fi

echo ">> Installing packages (sudo password may be required)"
sudo apt-get update
sudo apt-get install -y $PACKAGES

echo ">> Registering autostart"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/filewheel.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Daisy
Comment=Radial file converter wheel
Exec=$PWD/supervise.sh
Icon=$PWD/icon.png
Terminal=false
Categories=Utility;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

echo ">> Starting the wheel"
./run.sh
echo
echo "Done. Press Ctrl+Alt+W (or drag a file and hold Shift) to summon the wheel."
