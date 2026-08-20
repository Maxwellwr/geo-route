#!/bin/sh
# geo-why.sh <ip> — найти источники попадания IP в ipset'ы (диагностика коллизий).
# Для -site: домены из geo-generated.conf, которые сейчас в кэше dnsmasq
#   (dig @127.0.0.1) резолвятся в этот IP + источник (файл:строка / geosite-тег).
#   *-site с timeout: протухшие CDN-IP ядро само выкидывает.
# Для -ip: CIDR, покрывающий IP, + geoip-тег из cache/.
# Зависимости: dig, ipset, awk, xargs.

set -u

[ -n "${1:-}" ] || { echo "Usage: $0 <ip>"; exit 1; }
ip=$1

GEO_DIR="${GEO_DIR:-/opt/etc/geo}"
GEO_VAR="${GEO_VAR:-/opt/var/geo}"
GEN=/opt/etc/dnsmasq.d/geo-generated.conf
CACHE=$GEO_VAR/cache
TMPD=$(mktemp -d /tmp/geo-why.XXXXXX) || exit 1
trap 'rm -rf "$TMPD"' EXIT INT

command -v dig >/dev/null 2>&1 || { echo "нет dig"; exit 1; }

# какие листовые сеты содержат IP
sets=""
for s in $(ipset list -name | grep -E -- '-(site|ip)$'); do
    ipset test "$s" "$ip" >/dev/null 2>&1 && sets="$sets $s"
done
sets=$(echo $sets)  # trim

if [ -z "$sets" ]; then
    echo "$ip: ни в одном сете"
    exit 0
fi

nbases=$(for s in $sets; do echo "${s%-*}"; done | sort -u | wc -l)
[ "$nbases" -gt 1 ] && echo "$ip: КОЛЛИЗИЯ — в нескольких направлениях:$sets" || echo "$ip:$sets"

# источник домена: файл:строка конфига или geosite-тег
domain_source() {
    dom=$1; base=$2
    esc=$(printf '%s' "$dom" | sed 's/\./\\./g')
    hit=$(grep -nE "^[[:space:]]*$esc([[:space:]#]|\$)" "$GEO_DIR/common.conf" "$GEO_DIR"/geo.d/*.conf 2>/dev/null | head -1)
    if [ -n "$hit" ]; then
        echo "$hit"
        return
    fi
    f=$(grep -lx "$dom" "$CACHE"/"$base".geosite.*.list 2>/dev/null | head -1)
    if [ -n "$f" ]; then
        tag=$(basename "$f" .list); tag=${tag#"$base".geosite.}
        echo "geosite:$tag"
    else
        echo "источник не найден"
    fi
}

for s in $sets; do
    base=${s%-*}
    echo "== $s =="
    case $s in
        *-site)
            [ -f "$GEN" ] || { echo "  нет $GEN"; continue; }
            awk -F/ -v s="$s" '$1=="ipset=" && $3==s {print $2}' "$GEN" > "$TMPD/domains"
            total=$(wc -l < "$TMPD/domains")
            echo "  кандидатов-доменов: $total, резолвлю..."
            export TARGET=$ip
            xargs -P 16 -n 1 sh -c '
                d=$0
                dig +time=2 +tries=1 +short "$d" @127.0.0.1 2>/dev/null | grep -qx "$TARGET" && echo "$d"
            ' < "$TMPD/domains" > "$TMPD/hits"
            if [ -s "$TMPD/hits" ]; then
                sort -u "$TMPD/hits" | while IFS= read -r d; do
                    printf '  %s  <-  %s\n' "$d" "$(domain_source "$d" "$base")"
                done
            else
                echo "  ни один домен сейчас не в кэше dnsmasq с этим IP"
                echo "  (timeout ipset или запись уже не в кэше)"
            fi
            ;;
        *-ip)
            # CIDR, покрывающий IP
            ipset list "$s" | awk -v ip="$ip" '
                function ip2n(str, a) { split(str, a, "."); return a[1]*16777216 + a[2]*65536 + a[3]*256 + a[4] }
                BEGIN { ipn = ip2n(ip); inm = 0 }
                /^Members/ { inm = 1; next }
                inm && /^[0-9]/ {
                    split($1, b, "/"); n = b[2] + 0
                    if (n == 0)  { print $1; next }
                    d = 2 ^ (32 - n)
                    if (int(ipn / d) == int(ip2n(b[1]) / d)) print $1
                }' > "$TMPD/cidrs"
            if [ -s "$TMPD/cidrs" ]; then
                while IFS= read -r cidr; do
                    f=$(grep -lxF "$cidr" "$CACHE"/"$base".geoip.*.cidr 2>/dev/null | head -1)
                    if [ -n "$f" ]; then
                        tag=$(basename "$f" .cidr); tag=${tag#"$base".geoip.}
                        printf '  %s  <-  geoip:%s\n' "$cidr" "$tag"
                    else
                        printf '  %s  <-  (тег не определён: нет кэша, запускался geo-update.sh?)\n' "$cidr"
                    fi
                done < "$TMPD/cidrs"
            else
                echo "  CIDR не найден (рассинхрон с кэшем?)"
            fi
            ;;
    esac
done
exit 0
