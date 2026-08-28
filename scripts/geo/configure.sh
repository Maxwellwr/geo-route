#!/opt/bin/sh

# Configure ipset based policy routing on Keenetic NDMS
#
# only-ru:       сброс connmark/mark в 0 -> прямой путь через main table (WAN).
#                Policy routing НЕ используется: маркированный трафик через eth3
#                ломается об аппаратный NAT (PPE) NDMS.
#                При коллизии (IP в обоих сетах) выигрывает only-ru.
# blocked-sites: traffic -> WireGuard nwg0, mark 0x1002, routing table 1002
#                Правила применяются как к транзитному (PREROUTING), так и к
#                локально созданному роутером трафику (OUTPUT).
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

BLOCKED_MARK="0x1002"
BLOCKED_TABLE="1002"

# ------------------------------------------------------------
# iptables rules
# ------------------------------------------------------------

del_rules() {
    $IPTABLES -t mangle -D PREROUTING \
        -m conntrack --ctstate NEW \
        -m set --match-set $ONLY_RU_SET dst \
        -j CONNMARK --set-mark 0 2>/dev/null

    $IPTABLES -t mangle -D PREROUTING \
        -m conntrack --ctstate NEW \
        -m set --match-set $BLOCKED_SET dst \
        -j CONNMARK --set-mark $BLOCKED_MARK 2>/dev/null

    $IPTABLES -t mangle -D PREROUTING \
        -m set --match-set $BLOCKED_SET dst \
        -j CONNMARK --restore-mark 2>/dev/null

    # router-local traffic
    $IPTABLES -t mangle -D OUTPUT \
        -m set --match-set $BLOCKED_SET dst \
        -j MARK --set-mark $BLOCKED_MARK 2>/dev/null

    $IPTABLES -t mangle -D OUTPUT \
        -m set --match-set $ONLY_RU_SET dst \
        -j MARK --set-mark 0 2>/dev/null

    # Локальный пакет получает source address до OUTPUT. После policy reroute
    # через nwg0 он может сохранить WAN source, поэтому требуется MASQUERADE.
    $IPTABLES -t nat -D POSTROUTING \
        -o nwg0 -m mark --mark $BLOCKED_MARK \
        -j MASQUERADE 2>/dev/null
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

    # Router-local traffic never traverses PREROUTING, so mark it in OUTPUT.
    # only-ru is added after blocked-sites to preserve collision precedence.
    $IPTABLES -t mangle -C OUTPUT \
        -m set --match-set $BLOCKED_SET dst \
        -j MARK --set-mark $BLOCKED_MARK 2>/dev/null || \
    $IPTABLES -t mangle -A OUTPUT \
        -m set --match-set $BLOCKED_SET dst \
        -j MARK --set-mark $BLOCKED_MARK

    $IPTABLES -t mangle -C OUTPUT \
        -m set --match-set $ONLY_RU_SET dst \
        -j MARK --set-mark 0 2>/dev/null || \
    $IPTABLES -t mangle -A OUTPUT \
        -m set --match-set $ONLY_RU_SET dst \
        -j MARK --set-mark 0

    # Policy reroute happens after OUTPUT, when a local socket may already have
    # selected the WAN source address. Rewrite it to the nwg0 address.
    $IPTABLES -t nat -C POSTROUTING \
        -o nwg0 -m mark --mark $BLOCKED_MARK \
        -j MASQUERADE 2>/dev/null || \
    $IPTABLES -t nat -I POSTROUTING 1 \
        -o nwg0 -m mark --mark $BLOCKED_MARK \
        -j MASQUERADE
}

# ------------------------------------------------------------
# Stop mode
# ------------------------------------------------------------

if [ "$1" = "-stop" ]; then
    echo "Removing policy routing rules"

    ip rule del fwmark $BLOCKED_MARK table $BLOCKED_TABLE priority $BLOCKED_TABLE 2>/dev/null

    del_rules

    exit 0
fi

# ------------------------------------------------------------
# Create ipsets (list:set над hash:ip + hash:net)
# ------------------------------------------------------------

for s in $SETS; do
    $IPSET create "$s-site" hash:ip family inet hashsize 4096 maxelem 131072 timeout $SITE_TIMEOUT -exist
    $IPSET create "$s-ip" hash:net family inet hashsize 8192 maxelem 262144 -exist
    $IPSET create "$s" list:set -exist
    $IPSET add "$s" "$s-site" -exist
    $IPSET add "$s" "$s-ip" -exist
done

# ------------------------------------------------------------
# Configure iptables rules
# ------------------------------------------------------------

del_rules
add_rules

# ------------------------------------------------------------
# Restore routing rules
# ------------------------------------------------------------

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
