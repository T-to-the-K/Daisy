# Daisy

![Demo](docs/demo.gif)

**A radial file-conversion wheel for Linux — drag a file, tap a key, and drop it on the format you want.**

[![CI](https://github.com/T-to-the-K/Daisy/actions/workflows/ci.yml/badge.svg)](https://github.com/T-to-the-K/Daisy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Drag a file, tap a modifier key, and a wheel of format options appears at the
pointer. Drop the file on a format to convert it. The converted file is written
beside the original with the new extension, and the original is never
overwritten.

## Demo

It's a desktop app, so there is no hosted web demo — the GIF above shows the
core loop. To try it live, use the one-shot installer below, or grab the latest
binary release from the [Releases](https://github.com/T-to-the-K/Daisy/releases)
page.

## Install (Linux, one shot)

Clone the repo and run the installer — it installs all dependencies, registers
autostart, and launches the wheel:

```bash
git clone https://github.com/T-to-the-K/Daisy.git && cd Daisy && bash install.sh
```

Already cloned? Just:

```bash
cd Daisy && bash install.sh
```

That's it. Press **Ctrl+Alt+W** (or drag a file and hold **Shift**) to summon
the wheel.

### Requirements / troubleshooting

- **X11, not Wayland.** Global hotkeys and drag detection use Xlib, which only
  works in an X11 (Xorg) session. On Ubuntu you may be on Wayland by default —
  log out, pick the **"Xorg"** (or **"Cinnamon"**) session at the login screen,
  and log back in. `echo $XDG_SESSION_TYPE` should print `x11`.
- The installer assumes **Debian/Ubuntu/Mint/Pop!_OS** (`apt`). On other distros
  install the equivalents of: `python3-gi`, `python3-gi-cairo`, `python3-xlib`,
  `python3-pil`, `gstreamer1.0-tools` (+ good/bad/ugly/libav plugins),
  `libreoffice`, `ghostscript`, `poppler-utils`, `zip`, `xclip`,
  `libnotify-bin`.
- Run manually any time: `bash run.sh`. Logs go to `/tmp/filewheel.log`.

## How it works

- Drag a file and tap a modifier key (or press Ctrl+Alt+W) to summon the wheel.
- Hover a wedge and drop the file on it to convert to that format.
- Scroll to page through more formats when there are many.
- Esc cancels.

Keys: Shift shows convert options, Ctrl shows tool options, Alt shows action
options. Only formats that make sense for the dragged file are shown, and the
format the file already is never appears.

## Contributing

Bug reports, feature ideas, and pull requests are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Muhammad Talha Khattak
