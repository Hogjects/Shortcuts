#!/usr/bin/env bash
# Builds tarball and AppImage into dist without bundling Python or GTK4
# Usage build.sh tarball or appimage or all with all as default
set -euo pipefail

APP_NAME="shortcuts"
APP_ID="com.local.shortcuts"
VERSION="${VERSION:-0.1.0}"
TARGET="${1:-all}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# build.sh lives in src/. Icons, build/ and dist/ sit at the repo root next to src/
SRC_DIR="$SCRIPT_DIR"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ICONS_DIR="$ROOT_DIR/icons"
BUILD_DIR="$ROOT_DIR/build"
DIST_DIR="$ROOT_DIR/dist"
APPIMAGETOOL_CACHE="$ROOT_DIR/.cache/appimagetool-x86_64.AppImage"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"

# Exact runtime file set
APP_FILES=(
  main.py action_library.py action_widgets.py automation_editor_window.py
  automation_engine.py automation_widgets.py dialogs.py editor_window.py
  icons.py main_window.py models.py plugin_api.py plugin_manager.py plugin_store.py
  plugin_store_window.py plugins_window.py
  run_engine.py runner.py storage.py system_actions.py trigger_library.py
  style.css
)

log() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$1" >&2; exit 1; }

verify_source() {
  for f in "${APP_FILES[@]}"; do
    [ -f "$SRC_DIR/$f" ] || die "missing source file: $f (expected next to build.sh)"
  done
  [ -d "$ICONS_DIR/hicolor/scalable/actions" ] || die "missing icons/ at the repo root (run: python3 tools/make_icons.py)"
}

write_launcher() {
  # Writes the launcher used as run.sh in the tarball and AppRun in the AppImage
  cat > "$1" << 'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

has_gtk4() {
  "$1" -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk' 2>/dev/null
}

# An explicit PYTHON is used as is otherwise prefer the system interpreter
# since pyenv or conda ones often lack PyGObject
if [ -n "${PYTHON:-}" ]; then
  PYTHON_BIN=""
  has_gtk4 "$PYTHON" && PYTHON_BIN="$PYTHON"
else
  PYTHON_BIN=""
  for candidate in /usr/bin/python3 python3; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if has_gtk4 "$candidate"; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  if [ -n "${PYTHON:-}" ]; then
    echo "error: \$PYTHON=$PYTHON doesn't have GTK 4 + PyGObject." >&2
  else
    echo "error: this needs GTK 4 + PyGObject; checked /usr/bin/python3 and python3 on PATH." >&2
    echo "  If you use pyenv/conda/asdf/mise, your shell's python3 may be shadowing the" >&2
    echo "  system one - try: PYTHON=/usr/bin/python3 $0" >&2
  fi
  echo "  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 python3-gi-cairo" >&2
  echo "  Fedora:        sudo dnf install python3-gobject gtk4" >&2
  echo "  Arch:          sudo pacman -S python-gobject gtk4" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$HERE/app/main.py" "$@"
LAUNCHER
  chmod +x "$1"
}

write_desktop_file() {
  cat > "$1" << DESKTOP
[Desktop Entry]
Type=Application
Name=Shortcuts
Comment=Automate system actions with shortcuts and automations
Exec=$APP_NAME
Icon=$APP_NAME
Categories=Utility;
Terminal=false
StartupWMClass=$APP_ID
DESKTOP
}

# Embedded icon PNG with a blue gradient and a white bolt
write_icon() {
  base64 -d > "$1" << 'ICON_PNG'
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
ICON_PNG
}

build_tarball() {
  log "building tarball"
  local pkg_name="${APP_NAME}-${VERSION}-linux"
  local pkg_dir="$BUILD_DIR/tarball/$pkg_name"
  rm -rf "$BUILD_DIR/tarball"
  mkdir -p "$pkg_dir/app"

  for f in "${APP_FILES[@]}"; do
    cp "$SRC_DIR/$f" "$pkg_dir/app/$f"
  done
  cp -r "$ICONS_DIR" "$pkg_dir/app/icons"
  write_launcher "$pkg_dir/run.sh"

  mkdir -p "$DIST_DIR"
  (cd "$BUILD_DIR/tarball" && tar -czf "$DIST_DIR/$pkg_name.tar.gz" "$pkg_name")
  log "tarball: dist/$pkg_name.tar.gz ($(du -h "$DIST_DIR/$pkg_name.tar.gz" | cut -f1))"
}

ensure_appimagetool() {
  if [ -x "$APPIMAGETOOL_CACHE" ]; then
    return
  fi
  command -v curl >/dev/null 2>&1 || die "curl is required to fetch appimagetool (or place it at $APPIMAGETOOL_CACHE yourself)"
  log "downloading appimagetool (cached at .cache/ for next time)"
  mkdir -p "$(dirname "$APPIMAGETOOL_CACHE")"
  curl -fL -o "$APPIMAGETOOL_CACHE" "$APPIMAGETOOL_URL"
  chmod +x "$APPIMAGETOOL_CACHE"
}

build_appimage() {
  log "building AppImage"
  ensure_appimagetool

  local appdir="$BUILD_DIR/AppDir"
  rm -rf "$appdir"
  mkdir -p "$appdir/app" "$appdir/usr/share/applications" "$appdir/usr/share/icons/hicolor/256x256/apps"

  for f in "${APP_FILES[@]}"; do
    cp "$SRC_DIR/$f" "$appdir/app/$f"
  done
  cp -r "$ICONS_DIR" "$appdir/app/icons"
  write_launcher "$appdir/AppRun"
  write_desktop_file "$appdir/$APP_NAME.desktop"
  cp "$appdir/$APP_NAME.desktop" "$appdir/usr/share/applications/$APP_NAME.desktop"
  write_icon "$appdir/$APP_NAME.png"
  cp "$appdir/$APP_NAME.png" "$appdir/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"

  mkdir -p "$DIST_DIR"
  local out="$DIST_DIR/Shortcuts-x86_64.AppImage"
  rm -f "$out"
  ARCH=x86_64 "$APPIMAGETOOL_CACHE" "$appdir" "$out" >/dev/null
  log "AppImage: dist/$(basename "$out") ($(du -h "$out" | cut -f1))"
}

verify_source
mkdir -p "$BUILD_DIR"

case "$TARGET" in
  tarball) build_tarball ;;
  appimage) build_appimage ;;
  all) build_tarball; build_appimage ;;
  *) die "unknown target '$TARGET' (use tarball, appimage, or all)" ;;
esac

rm -rf "$BUILD_DIR"