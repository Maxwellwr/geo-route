#!/bin/sh
# Keenetic пересобирает iptables при смене интерфейсов/политик.
# Без этого хука CONNMARK-правила из configure.sh пропадают,
# а ipset и ip rule остаются — трафик blocked-sites идёт в WAN.
#
# Документация: https://support.keenetic.com/carrier/kn-1711/en/42407-opkg-component-description.html
# $type = iptables|ip6tables, $table = filter|nat|mangle|...

[ "${type:-}" = "iptables" ] || exit 0
[ "${table:-}" = "mangle" ] || exit 0

exec /opt/share/geo-routing/configure.sh
