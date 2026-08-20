# Entware geo-route (Keenetic)

Geo-маршрутизация: geosite/geoip → ipset/dnsmasq, веб-UI на LAN. Пакет только для **aarch64-3.10** (Keenetic Entware).

Официальный feed Entware этот ipk не содержит. Нужен свой:

```
echo 'src/gz geo-route https://maxwellwr.github.io/geo-route/aarch64-3.10' >> /opt/etc/opkg.conf
opkg update
opkg install geo-route
```

Дальше: `opkg update && opkg upgrade geo-route`.

Без строки `src/gz` `opkg install geo-route` пакет не найдёт.

Локально, без feed:

```
opkg install ./geo-route_0.1.0_aarch64-3.10.ipk
```

Сборка ipk: `package/geo-route/build-ipk.sh` → `Work/geo-route_0.1.0_aarch64-3.10.ipk` и `Work/feed/aarch64-3.10/`.

Релиз: тег `v0.1.0` (GitHub Actions собирает ipk и выкладывает feed в Pages). В настройках репозитория: Pages → Source = GitHub Actions.
