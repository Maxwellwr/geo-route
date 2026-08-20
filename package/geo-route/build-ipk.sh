#!/usr/bin/env bash
# Сборка Entware ipk + opkg-индекс в Work/feed/aarch64-3.10/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="${GEO_ROUTE_VERSION:-0.1.0}"
ARCH="aarch64-3.10"
NAME="geo-route"
STAGE="$ROOT/Work/ipk-stage"
CTRL="$ROOT/Work/ipk-control"
OUT_DIR="$ROOT/Work"
FEED="$OUT_DIR/feed/$ARCH"
IPK="$OUT_DIR/${NAME}_${VERSION}_${ARCH}.ipk"
GEOVIEW_URL="${GEOVIEW_URL:-https://github.com/snowie2000/geoview/releases/latest/download/geoview-linux-arm64}"

lf() {
    # POSIX text: убрать CR, чтобы shebang работал на роутере
    sed -i 's/\r$//' "$1"
}

winpath() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        printf '%s' "$1"
    fi
}

rm -rf "$STAGE" "$CTRL"
mkdir -p "$STAGE" "$CTRL" "$FEED"

echo "== frontend =="
(cd "$ROOT/scripts/geo-ui/frontend" && npm run build)

echo "== flask vendor =="
VENDOR="$STAGE/opt/share/geo-routing/backend/vendor"
mkdir -p "$VENDOR"
python -m pip install 'flask>=2.3,<4' -t "$VENDOR" --quiet --no-user
find "$VENDOR" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$VENDOR" -type d -name 'tests' -prune -exec rm -rf {} + 2>/dev/null || true

echo "== geoview =="
mkdir -p "$STAGE/opt/bin"
curl -fL --retry 3 -o "$STAGE/opt/bin/geoview" "$GEOVIEW_URL"
chmod 755 "$STAGE/opt/bin/geoview"

echo "== files =="
install -m 755 "$ROOT/scripts/geo/geo-update.sh" "$STAGE/opt/bin/geo-update"
install -m 755 "$ROOT/scripts/geo/geo-why.sh" "$STAGE/opt/bin/geo-why"
lf "$STAGE/opt/bin/geo-update"
lf "$STAGE/opt/bin/geo-why"

mkdir -p "$STAGE/opt/share/geo-routing/backend" \
         "$STAGE/opt/share/geo-routing/frontend"
install -m 755 "$ROOT/scripts/geo/configure.sh" "$STAGE/opt/share/geo-routing/configure.sh"
lf "$STAGE/opt/share/geo-routing/configure.sh"
for py in app.py apply.py bindaddr.py collisions.py confio.py run.py tags.py; do
    install -m 644 "$ROOT/scripts/geo-ui/backend/$py" "$STAGE/opt/share/geo-routing/backend/$py"
    lf "$STAGE/opt/share/geo-routing/backend/$py"
done
cp -a "$ROOT/scripts/geo-ui/frontend/dist" "$STAGE/opt/share/geo-routing/frontend/dist"

mkdir -p "$STAGE/opt/etc/geo/geo.d" \
         "$STAGE/opt/etc/init.d" \
         "$STAGE/opt/etc/cron.weekly" \
         "$STAGE/opt/etc/ndm/netfilter.d"
install -m 644 "$ROOT/scripts/geo/common.conf" "$STAGE/opt/etc/geo/common.conf"
lf "$STAGE/opt/etc/geo/common.conf"
for conf in custom geosite geoip; do
    install -m 644 "$ROOT/scripts/geo/geo.d/${conf}.conf" "$STAGE/opt/etc/geo/geo.d/${conf}.conf"
    lf "$STAGE/opt/etc/geo/geo.d/${conf}.conf"
done
install -m 755 "$ROOT/scripts/geo-ui/init.d/S80geo-ui" "$STAGE/opt/etc/init.d/S80geo-ui"
install -m 755 "$ROOT/scripts/geo/cron.weekly/geo-update" "$STAGE/opt/etc/cron.weekly/geo-update"
install -m 755 "$ROOT/scripts/geo/10-geo-routing.sh" "$STAGE/opt/etc/ndm/netfilter.d/10-geo-routing.sh"
lf "$STAGE/opt/etc/init.d/S80geo-ui"
lf "$STAGE/opt/etc/cron.weekly/geo-update"
lf "$STAGE/opt/etc/ndm/netfilter.d/10-geo-routing.sh"

cp "$PKG_DIR/CONTROL/control" "$PKG_DIR/CONTROL/conffiles" \
   "$PKG_DIR/CONTROL/postinst" "$PKG_DIR/CONTROL/prerm" "$CTRL/"
lf "$CTRL/control"; lf "$CTRL/conffiles"; lf "$CTRL/postinst"; lf "$CTRL/prerm"
chmod 755 "$CTRL/postinst" "$CTRL/prerm"

SIZE_KB=$(python -c "
import os
n=0
root = r'''$(winpath "$STAGE")'''
for r, ds, fs in os.walk(root):
    for f in fs:
        n += os.path.getsize(os.path.join(r, f))
print((n + 1023) // 1024)
")
printf '\nInstalled-Size: %s\n' "$SIZE_KB" >> "$CTRL/control"

echo "== ipk + feed =="
python "$(winpath "$PKG_DIR/pack_ipk.py")" \
    --stage "$(winpath "$STAGE")" \
    --control "$(winpath "$CTRL")" \
    --ipk "$(winpath "$IPK")" \
    --feed "$(winpath "$FEED")" \
    --filename "${NAME}_${VERSION}_${ARCH}.ipk"

echo "OK $IPK"
echo "OK $FEED"
