# Contributing to Daisy

Thanks for taking the time to help out. This is a small, single-purpose app, so
the bar for contributing is intentionally low.

## Reporting bugs

1. Search the [issues](https://github.com/T-to-the-K/Daisy/issues) to avoid
   duplicates.
2. Open a bug report and include:
   - Your distro and release (e.g. Ubuntu 24.04).
   - Whether you're on **X11 or Wayland** (`echo $XDG_SESSION_TYPE`).
   - The exact steps that triggered the problem.
   - The log file at `/tmp/filewheel.log` (trim any private paths first).

## Suggesting features

Open a feature request. Describe what you want and the workflow it would
unblock. Keep scope small — Daisy is meant to stay lightweight.

## Development setup

```bash
git clone https://github.com/T-to-the-K/Daisy.git
cd Daisy
# deps (Debian/Ubuntu)
sudo apt install python3-gi python3-gi-cairo python3-xlib python3-pil \
  gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly libreoffice ghostscript poppler-utils zip xclip libnotify-bin
```

Run the test suite (no GUI needed):

```bash
python3 -m unittest discover -s tests -v
```

## Pull requests

- Keep changes focused on one thing.
- Add or update tests for any change to `ops.py` logic.
- Run `python3 -m unittest discover -s tests -v` before pushing.
- CI runs the same tests automatically on every PR.

## Code of conduct

Be kind and constructive. We're here to build something useful, not to gatekeep.
