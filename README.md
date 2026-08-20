# Entware geo-route (Keenetic)

Geo-маршрутизация: geosite/geoip → ipset/dnsmasq, веб-UI на LAN. Пакет только для **aarch64-3.10** (Keenetic Entware).

Официальный feed Entware этот ipk не содержит. Нужен свой.

BusyBox `wget` не умеет HTTPS. Один раз (пакет `wget-ssl` ставится с HTTP-репозитория Entware):

```
opkg install wget-ssl
ln -sf /opt/libexec/wget-ssl /opt/usr/bin/wget
echo 'src/gz geo-route https://maxwellwr.github.io/geo-route/aarch64-3.10' >> /opt/etc/opkg.conf
opkg update
opkg install geo-route
```

Дальше: `opkg update && opkg upgrade geo-route`. Профиль (`/opt/etc/profile`) не нужен: `wget` в `/opt/usr/bin` указывает на wget-ssl.

Без строки `src/gz` `opkg install geo-route` пакет не найдёт.

Локально, без feed:

```
opkg install ./geo-route_0.1.1_aarch64-3.10.ipk
```

Сборка ipk: `package/geo-route/build-ipk.sh` → `Work/geo-route_*_aarch64-3.10.ipk` и `Work/feed/aarch64-3.10/`.

Релиз: тег `v*` (GitHub Actions собирает ipk и выкладывает feed в Pages). В настройках репозитория: Pages → Source = GitHub Actions.
