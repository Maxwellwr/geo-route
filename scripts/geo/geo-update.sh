#!/bin/sh
# geo-update.sh — geosite/geoip/домены из $GEO_DIR/common.conf (+includes)
# в генерируемый конфиг dnsmasq (ipset=.../<set>-site) и geoip-сеты (<set>-ip).
# POSIX sh, busybox. Зависимости: curl, jq, geoview, ipset.
# Флаг: -n | --no-download — не качать .dat заново.

set -u

GEO_DIR="${GEO_DIR:-/opt/etc/geo}"
GEO_VAR="${GEO_VAR:-/opt/var/geo}"
CONF_MAIN="$GEO_DIR/common.conf"
GEOSITE_DAT="$GEO_VAR/geosite.dat"
GEOIP_DAT="$GEO_VAR/geoip.dat"
GEOSITE_URL="https://github.com/runetfreedom/russia-blocked-geosite/releases/latest/download/geosite.dat"
GEOIP_URL="https://github.com/runetfreedom/russia-blocked-geoip/releases/latest/download/geoip.dat"
DNSMASQ_OUT="/opt/etc/dnsmasq.d/geo-generated.conf"
DNSMASQ_INIT="/opt/etc/init.d/S56dnsmasq"
LOG="$GEO_VAR/geo-update.log"

DOMAIN_RE='^([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$'
TLD_RE='^[A-Za-z]{2,}$'
CIDR_RE='^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(/(3[0-2]|[12]?[0-9]))?$'
SET_RE='^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$'
SITE_TIMEOUT=3600

DOWNLOAD=1
[ "${1:-}" = "-n" ] || [ "${1:-}" = "--no-download" ] && DOWNLOAD=0

TMP=$(mktemp -d /tmp/geo-update.XXXXXX) || exit 1
trap 'rm -rf "$TMP"' EXIT INT
mkdir -p "$GEO_VAR"

log()  { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
warn() { log "WARN: $*"; }
die()  { log "ERROR: $*"; exit 1; }

command -v geoview >/dev/null 2>&1 || die "нет geoview"
command -v jq      >/dev/null 2>&1 || die "нет jq"
command -v ipset   >/dev/null 2>&1 || die "нет ipset"
[ -f "$CONF_MAIN" ] || die "нет $CONF_MAIN"

# ---------- 1. Скачивание dat ----------

if [ "$DOWNLOAD" -eq 1 ]; then
    command -v curl >/dev/null 2>&1 || die "нет curl"
    # прогресс-бар только при интерактивном запуске
    CURL_Q="-s"; [ -t 1 ] && CURL_Q="-#"
    for pair in "$GEOSITE_URL $GEOSITE_DAT" "$GEOIP_URL $GEOIP_DAT"; do
        url=${pair% *}; dst=${pair#* }
        log "скачиваю $(basename "$dst") ..."
        if curl -fL $CURL_Q --max-time 600 "$url" -o "$dst.tmp" 2>&2; then
            mv "$dst.tmp" "$dst"
            log "скачан $(basename "$dst") ($(wc -c < "$dst") байт)"
        else
            rm -f "$dst.tmp"
            [ -f "$dst" ] || die "не скачан $url и нет старой копии"
            warn "не удалось скачать $url — использую старую копию"
        fi
    done
fi

[ -f "$GEOSITE_DAT" ] || die "нет $GEOSITE_DAT"
[ -f "$GEOIP_DAT" ]   || die "нет $GEOIP_DAT"

# кэш извлечённых доменов/CIDR по тегам — нужен geo-why.sh для поиска источников
CACHE="$GEO_VAR/cache"
mkdir -p "$CACHE"
rm -f "$CACHE"/*

# ---------- 2. Парсинг конфигурации ----------

VISITED=""

# parse_file <path>
parse_file() {
    f=$1
    d=$(cd "$(dirname "$f")" 2>/dev/null && pwd) || { warn "$f: нет каталога"; return; }
    f="$d/$(basename "$f")"
    case "$VISITED" in
        *"|$f|"*) warn "$f: циклический include, пропуск"; return ;;
    esac
    VISITED="$VISITED|$f|"
    [ -f "$f" ] || { warn "$f: файл не найден"; return; }

    cur_set=""
    n=0
    while IFS= read -r line || [ -n "$line" ]; do
        n=$((n + 1))
        line=${line%%#*}
        line=$(printf '%s' "$line" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        [ -z "$line" ] && continue

        case "$line" in
            \[*\])
                s=$(printf '%s' "$line" | sed 's/^\[//;s/\]$//;s/[[:space:]]//g')
                if printf '%s' "$s" | grep -qE "$SET_RE"; then
                    cur_set=$s
                    : >> "$TMP/$s.domains"
                    : >> "$TMP/$s.cidrs"
                    : >> "$TMP/$s.geoip"
                else
                    warn "$f:$n: некорректная секция [$s]"
                    cur_set=""
                fi
                ;;
            include*)
                rest=${line#include}
                case "$rest" in
                    ""|"${rest# }"*) : ;; # пробел или таб дальше — ок
                esac
                pat=$(printf '%s' "$rest" | sed 's/^[[:space:]]*//')
                if [ -z "$pat" ]; then
                    warn "$f:$n: пустой include"
                    continue
                fi
                case "$pat" in
                    /*) incs=$pat ;;
                    *)  incs=$d/$pat ;;
                esac
                found=0
                for inc in $incs; do
                    [ -e "$inc" ] || continue
                    found=1
                    parse_file "$inc"
                done
                [ "$found" -eq 0 ] && warn "$f:$n: include не найден: $pat"
                ;;
            geosite:*)
                tag=${line#geosite:}
                if [ -z "$cur_set" ]; then warn "$f:$n: вне секции: $line"; continue; fi
                printf '%s\n' "$tag" >> "$TMP/$cur_set.geosite"
                ;;
            geoip:*)
                tag=${line#geoip:}
                if [ -z "$cur_set" ]; then warn "$f:$n: вне секции: $line"; continue; fi
                printf '%s\n' "$tag" >> "$TMP/$cur_set.geoip"
                ;;
            *)
                if [ -z "$cur_set" ]; then warn "$f:$n: вне секции: $line"; continue; fi
                if printf '%s' "$line" | grep -qE "$CIDR_RE"; then
                    printf '%s\n' "$line" >> "$TMP/$cur_set.cidrs"
                elif printf '%s' "$line" | grep -qE "$DOMAIN_RE" || printf '%s' "$line" | grep -qE "$TLD_RE"; then
                    printf '%s\n' "$line" >> "$TMP/$cur_set.domains"
                else
                    warn "$f:$n: невалидная строка: $line"
                fi
                ;;
        esac
    done < "$f"
}

VISITED=""
parse_file "$CONF_MAIN"

# ---------- 3. geosite -> домены ----------

for df in "$TMP"/*.domains; do
    [ -e "$df" ] || die "конфигурация пуста — ни одной секции"
    set_name=$(basename "$df" .domains)
    gf="$TMP/$set_name.geosite"
    [ -s "$gf" ] || continue
    for tag in $(sort -u "$gf"); do
        log "$set_name: конвертирую geosite:$tag ..."
        # NB: с -output geoview пишет бинарный .srs, JSON отдаёт только на stdout
        if ! geoview -type geosite -action convert -input "$GEOSITE_DAT" -list "$tag" \
                -format ruleset -lowmem > "$TMP/gv.json" 2>"$TMP/geoview.err"; then
            warn "$set_name: geosite:$tag — ошибка geoview: $(head -c 200 "$TMP/geoview.err")"
            continue
        fi
        jq -r '[.rules[] | (.domain_suffix[]?, (if (.domain | type) == "array" then .domain[]? else .domain // empty end))] | unique | .[]' \
            "$TMP/gv.json" 2>/dev/null > "$CACHE/$set_name.geosite.$tag.list"
        cnt=$(wc -l < "$CACHE/$set_name.geosite.$tag.list")
        if [ "${cnt:-0}" -eq 0 ]; then
            warn "$set_name: geosite:$tag — пустой результат (тег существует?)"
        else
            cat "$CACHE/$set_name.geosite.$tag.list" >> "$TMP/$set_name.domains"
            log "$set_name: geosite:$tag → $cnt доменов"
        fi
    done
done

# ---------- 4. dnsmasq-конфиг ----------

GEN=$TMP/geo-generated.conf
{
    echo "# generated by geo-update.sh — не редактировать"
    for df in "$TMP"/*.domains; do
        set_name=$(basename "$df" .domains)
        [ -s "$df" ] || continue
        sort -u "$df" | while IFS= read -r dom; do
            printf 'ipset=/%s/%s-site\n' "$dom" "$set_name"
        done
    done
} > "$GEN"

total=$(grep -c '^ipset=' "$GEN")
[ "$total" -gt 0 ] || die "сгенерированный конфиг пуст"
log "dnsmasq: $total правил ipset="

if cmp -s "$GEN" "$DNSMASQ_OUT" 2>/dev/null; then
    log "dnsmasq: без изменений"
else
    cp "$GEN" "$DNSMASQ_OUT.new" && mv "$DNSMASQ_OUT.new" "$DNSMASQ_OUT"
    log "dnsmasq: конфиг обновлён, рестарт"
    "$DNSMASQ_INIT" restart >/dev/null 2>&1 || warn "рестарт dnsmasq не удался"
fi

# ---------- 5. ipset: структура + geoip ----------

for df in "$TMP"/*.domains; do
    set_name=$(basename "$df" .domains)

    ipset create "$set_name-site" hash:ip family inet hashsize 4096 maxelem 131072 timeout $SITE_TIMEOUT -exist 2>/dev/null \
        || warn "$set_name-site: не удалось создать hash:ip"
    ipset create "$set_name-ip" hash:net family inet hashsize 8192 maxelem 262144 -exist 2>/dev/null \
        || warn "$set_name-ip: не удалось создать hash:net"
    if ipset create "$set_name" list:set -exist 2>/dev/null; then
        ipset add "$set_name" "$set_name-site" -exist 2>/dev/null
        ipset add "$set_name" "$set_name-ip" -exist 2>/dev/null
    else
        warn "$set_name: не удалось создать list:set"
    fi

    cidrs=$TMP/$set_name.cidrs
    cf="$TMP/$set_name.geoip"

    if [ -s "$cf" ]; then
        for tag in $(sort -u "$cf"); do
            log "$set_name: конвертирую geoip:$tag ..."
            if ! geoview -type geoip -action convert -input "$GEOIP_DAT" -list "$tag" \
                    -format ruleset -lowmem > "$TMP/gv.json" 2>"$TMP/geoview.err"; then
                warn "$set_name: geoip:$tag — ошибка geoview: $(head -c 200 "$TMP/geoview.err")"
                continue
            fi
            jq -r '.rules[].ip_cidr[]? | select(contains(":") | not)' \
                "$TMP/gv.json" 2>/dev/null | sort -u > "$CACHE/$set_name.geoip.$tag.cidr"
            cnt=$(wc -l < "$CACHE/$set_name.geoip.$tag.cidr")
            if [ "${cnt:-0}" -eq 0 ]; then
                warn "$set_name: geoip:$tag — пустой результат (тег существует?)"
            else
                cat "$CACHE/$set_name.geoip.$tag.cidr" >> "$cidrs"
                log "$set_name: geoip:$tag → $cnt CIDR (IPv4)"
            fi
        done
    fi

    [ -s "$cidrs" ] || continue

    ncidr=$(sort -u "$cidrs" | wc -l)

    # атомарная перезаливка: new -> swap -> destroy
    log "$set_name-ip: заливаю $ncidr CIDR ..."
    ipset destroy "$set_name-ip-new" 2>/dev/null
    {
        echo "create $set_name-ip-new hash:net family inet hashsize 8192 maxelem 262144"
        sort -u "$cidrs" | sed "s|^|add $set_name-ip-new |"
    } > "$TMP/$set_name.restore"

    if ipset restore < "$TMP/$set_name.restore"; then
        if ipset list "$set_name-ip" >/dev/null 2>&1; then
            ipset swap "$set_name-ip-new" "$set_name-ip"
            ipset destroy "$set_name-ip-new"
        else
            ipset create "$set_name-ip" hash:net family inet hashsize 8192 maxelem 262144
            ipset swap "$set_name-ip-new" "$set_name-ip"
            ipset destroy "$set_name-ip-new"
            ipset add "$set_name" "$set_name-ip" -exist 2>/dev/null
        fi
        log "$set_name-ip: залито $ncidr CIDR"
    else
        warn "$set_name-ip: ipset restore не удался, старые данные сохранены"
        ipset destroy "$set_name-ip-new" 2>/dev/null
    fi
done

log "готово"
exit 0
