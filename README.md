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
opkg install ./geo-route_0.1.2_aarch64-3.10.ipk
```

Сборка ipk: `package/geo-route/build-ipk.sh` → `Work/geo-route_*_aarch64-3.10.ipk` и `Work/feed/aarch64-3.10/`.

Релиз: пуш в `main` выкладывает opkg-feed в Pages; тег `v*` собирает ipk в GitHub Release. В настройках репозитория: Pages → Source = GitHub Actions. Окружение `github-pages` разрешает деплой только с `main`, не с тегов.


## Если `opkg update` падает с `libpcre2`

После частичного обновления Entware `wget-ssl` может оказаться новее установленной `libpcre2`. Типичный симптом:

```text
wget: /opt/lib/libpcre2-8.so.0: no version information available (required by wget)
```

Например, `wget` уже требует `PCRE2_10.47`, а локально осталась `libpcre2 10.42-1`. В этом состоянии обычный `opkg update` может не работать, потому что сам `opkg` вызывает проблемный `wget`.

Проверь установленные версии:

```sh
opkg list-installed | grep -E '^(libpcre2|pcre2|wget|wget-ssl) '
```

Узнать актуальную версию `libpcre2` в Entware feed можно через BusyBox, не используя `wget-ssl`:

```sh
/opt/bin/busybox wget -qO- http://bin.entware.net/aarch64-k3.10/Packages.gz \
  | /opt/bin/busybox gzip -dc \
  | /opt/bin/busybox sed -n '/^Package: libpcre2$/,/^$/p'
```

Затем скачай указанный в поле `Filename` пакет тем же BusyBox. Например:

```sh
/opt/bin/busybox wget -O /tmp/libpcre2.ipk \
  http://bin.entware.net/aarch64-k3.10/libpcre2_10.47-1_aarch64-3.10.ipk
```

И обнови библиотеку локальным пакетом:

```sh
opkg install /tmp/libpcre2.ipk
```

После этого проверь `wget` и повтори обновление индекса:

```sh
wget --version | head -1
opkg update
```

Версию `libpcre2` в URL не следует копировать вслепую: сначала возьми текущий `Filename` из `Packages.gz`.
