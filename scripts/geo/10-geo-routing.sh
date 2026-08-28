#!/bin/sh
# Keenetic пересобирает iptables при смене интерфейсов/политик.
# Без этого хука правила из configure.sh пропадают,
# а ipset и ip rule остаются — трафик blocked-sites идёт в WAN.
#
# Восстанавливаем правила после пересборки как mangle (маркировка),
# так и nat (MASQUERADE для router-local traffic через WireGuard).
#
# Документация: https://support.keenetic.com/carrier/kn-1711/en/42407-opkg-component-description.html
# $type = iptables|ip6tables, $table = filter|nat|mangle|...

[ "${type:-}" = "iptables" ] || exit 0
case "${table:-}" in
    mangle|nat) ;;
    *) exit 0 ;;
esac

exec /opt/share/geo-routing/configure.sh
