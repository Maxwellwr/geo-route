#!/bin/sh
# geo-test.sh <ip> — проверить IP по всем листовым ipset'ам (<set>-site, <set>-ip).
# NB: `ipset test <list:set> <ip>` не работает — для list:set test ищет имя подсета,
# рекурсия есть только в iptables-матче. Поэтому проверяем листья напрямую.

[ -n "${1:-}" ] || { echo "Usage: $0 <ip>"; exit 1; }
ip=$1

found=0
for s in $(ipset list -name | grep -E -- '-(site|ip)$'); do
    if ipset test "$s" "$ip" >/dev/null 2>&1; then
        base=${s%-*}
        echo "$ip -> $s ($base)"
        found=1
    fi
done
[ "$found" -eq 0 ] && echo "$ip: ни в одном сете"
exit 0
