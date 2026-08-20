#!/opt/bin/sh

# Configure ipset based policy routing on Keenetic NDMS
#
# only-ru:       сброс connmark в 0 -> прямой путь через main table (WAN).
#                Policy routing НЕ используется: маркированный трафик через eth3
#                ломается об аппаратный NAT (PPE) NDMS.
#                При коллизии (IP в обоих сетах) выигрывает only-ru.
# blocked-sites: traffic -> WireGuard nwg0, mark 0x1002, routing table 1002
#
# Структура сетов:
#   <name>       list:set  { <name>-site, <name>-ip }  <- его матчит iptables
#   <name>-site  hash:ip timeout 3600  <- dnsmasq (geo-generated.conf)
#   <name>-ip    hash:net              <- geoip (geo-update.sh, без timeout)

IPTABLES="iptables -w"
IPSET="ipset"
SITE_TIMEOUT="3600"

SETS="only-ru blocked-sites"

ONLY_RU_SET="only-ru"
BLOCKED_SET="blocked-sites"

ONLY_RU_MARK="0x1001"
BLOCKED_MARK="0x1002"

ONLY_RU_TABLE="1001"
BLOCKED_TABLE="1002"

# ------------------------------------------------------------
# iptables rules
# ------------------------------------------------------------

del_rules() {
    # текущий вариант: сброс маркировки
    $IPTABLES -t mangle -D PREROUTING \
        -m conntrack --ctstate NEW \
        -m set --match-set $ONLY_RU_SET dst \
        -j CONNMARK --set-mark 0 2>/dev/null

    # legacy-вариант: mark 0x1001 + restore
    $IPTABLES -t mangle -D PREROUTING \
        -m conntrack --ctstate NEW \
        -m set --match-set $ONLY_RU_SET dst \
        -j CONNMARK --set-mark $ONLY_RU_MARK 2>/dev/null

    $IPTABLES -t mangle -D PREROUTING \
        -m set --match-set $ONLY_RU_SET dst \
        -j CONNMARK --restore-mark 2>/dev/null

    $IPTABLES -t mangle -D PREROUTING \
        -m conntrack --ctstate NEW \
        -m set --match-set $BLOCKED_SET dst \
        -j CONNMARK --set-mark $BLOCKED_MARK 2>/dev/null

    $IPTABLES -t mangle -D PREROUTING \
        -m set --match-set $BLOCKED_SET dst \
        -j CONNMARK --restore-mark 2>/dev/null
}

# Порядок критичен. CONNMARK --set-mark меняет connmark немедленно, а
# --restore-mark копирует connmark в nfmark пакета — поэтому restore-mark
# должен идти ПОСЛЕ обоих set-mark, иначе на первом пакете коллизии
# (IP в обоих сетах) в nfmark попадёт промежуточный 0x1002 и соединение
# прибьёт к WG. Итог для коллизии: connmark=0 (only-ru последним) ->
# restore поднимает 0 -> прямой путь через main table.
add_rules() {
    iptables-save -t mangle | grep -q "match-set $BLOCKED_SET .*set-mark" || {
        $IPTABLES -t mangle -A PREROUTING \
            -m conntrack --ctstate NEW \
            -m set --match-set $BLOCKED_SET dst \
            -j CONNMARK --set-mark $BLOCKED_MARK
    }

    iptables-save -t mangle | grep -q "match-set $ONLY_RU_SET " || {
        $IPTABLES -t mangle -A PREROUTING \
            -m conntrack --ctstate NEW \
            -m set --match-set $ONLY_RU_SET dst \
            -j CONNMARK --set-mark 0
    }

    iptables-save -t mangle | grep -q "match-set $BLOCKED_SET .*restore-mark" || {
        $IPTABLES -t mangle -A PREROUTING \
            -m set --match-set $BLOCKED_SET dst \
            -j CONNMARK --restore-mark
    }
}

# ------------------------------------------------------------
# Stop mode
# ------------------------------------------------------------

if [ "$1" = "-stop" ]; then
    echo "Removing policy routing rules"

    ip rule del fwmark $ONLY_RU_MARK table $ONLY_RU_TABLE priority $ONLY_RU_TABLE 2>/dev/null
    ip rule del fwmark $BLOCKED_MARK table $BLOCKED_TABLE priority $BLOCKED_TABLE 2>/dev/null

    del_rules

    exit 0
fi

# ------------------------------------------------------------
# Create ipsets (list:set над hash:ip + hash:net)
# ------------------------------------------------------------

for s in $SETS; do
    # миграция: старый одноимённый сет не list:set -> пересоздать
    # (записи динамические: dnsmasq/geo-update наполнят заново)
    if $IPSET list "$s" >/dev/null 2>&1 && \
       ! $IPSET list "$s" | grep -q "^Type: list:set"; then
        echo "Migrating $s to list:set"
        del_rules
        $IPSET destroy "$s"
    fi

    # миграция: *-site без timeout → пересоздать (ядро само выкидывает IP)
    if $IPSET list "$s-site" >/dev/null 2>&1 && \
       ! $IPSET list "$s-site" | grep -q "^Header:.*timeout"; then
        echo "Migrating $s-site to timeout $SITE_TIMEOUT"
        $IPSET del "$s" "$s-site" 2>/dev/null
        $IPSET destroy "$s-site"
    fi

    $IPSET create "$s-site" hash:ip family inet hashsize 4096 maxelem 131072 timeout $SITE_TIMEOUT -exist
    $IPSET create "$s-ip" hash:net family inet hashsize 8192 maxelem 262144 -exist
    $IPSET create "$s" list:set -exist
    $IPSET add "$s" "$s-site" -exist
    $IPSET add "$s" "$s-ip" -exist
done

# ------------------------------------------------------------
# Configure iptables rules
# ------------------------------------------------------------

# del_rules перед add_rules: убирает legacy-варианты only-ru (mark 0x1001),
# иначе guard в add_rules не добавит новое правило
del_rules
add_rules

# ------------------------------------------------------------
# Restore routing rules
# ------------------------------------------------------------

# Only-RU: policy routing больше не нужен (сброс маркировки) —
# убираем legacy rule/table, если остались от старой версии

ip rule del fwmark $ONLY_RU_MARK table $ONLY_RU_TABLE priority $ONLY_RU_TABLE 2>/dev/null
ip route flush table $ONLY_RU_TABLE 2>/dev/null

# Blocked traffic via WireGuard

if ip link show nwg0 >/dev/null 2>&1; then

    ip rule add \
        fwmark $BLOCKED_MARK \
        table $BLOCKED_TABLE \
        priority $BLOCKED_TABLE \
        2>/dev/null

    ip route replace \
        table $BLOCKED_TABLE \
        default dev nwg0

fi

exit 0
