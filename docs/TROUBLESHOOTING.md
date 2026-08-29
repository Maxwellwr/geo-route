# Troubleshooting

Этот раздел собран по реальным проблемам, которые уже встречались при установке, обновлении и эксплуатации **geo-route** на Keenetic + Entware.

Главный принцип при диагностике Keenetic: **не очищать таблицы iptables целиком** и не удалять неизвестные `_NDM_*` chains/rules. KeeneticOS сам управляет ими и регулярно пересобирает firewall.

## 1. Быстрая проверка состояния

Перед изменениями полезно снять текущее состояние:

```sh
ip -4 addr
ip rule
ip route show table 1002
ipset list -name
iptables-save -t mangle
iptables-save -t nat
netstat -lntp 2>/dev/null | grep 8787
```

Ожидаемая схема geo-route:

```text
blocked-sites      list:set
├── blocked-sites-site  hash:ip timeout 3600
└── blocked-sites-ip    hash:net

only-ru            list:set
├── only-ru-site        hash:ip timeout 3600
└── only-ru-ip          hash:net
```

Для `blocked-sites`:

```text
fwmark 0x1002
    ↓
ip rule priority 1002
    ↓
table 1002
    ↓
default dev nwg0
```

Для `only-ru` текущая логика — **сброс mark/connmark в 0**, то есть обычный маршрут через main table. Старый вариант с `0x1001/table 1001` больше не нужен.

---

## 2. `opkg update` / `wget`: `libpcre2-8.so.0: no version information available`

### Симптом

```text
wget: /opt/lib/libpcre2-8.so.0: no version information available (required by wget)
```

При этом `opkg update` может перестать работать.

### Причина

После частичного обновления Entware `wget-ssl` может оказаться собран против более новой PCRE2, чем реально установленная библиотека.

Например:

```text
libpcre2 10.42-1
wget-ssl 1.25.0-4
```

а:

```sh
strings /opt/bin/wget | grep -E 'PCRE2_[0-9]' | sort -u
```

показывает:

```text
PCRE2_10.47
```

### Проверка

```sh
opkg list-installed | grep -E '^(libpcre2|pcre2|wget|wget-ssl) '
ls -l /opt/lib/libpcre2-8.so*
```

Актуальную версию в Entware feed можно получить **через BusyBox wget**, не используя сломанный `wget-ssl`:

```sh
/opt/bin/busybox wget -qO- http://bin.entware.net/aarch64-k3.10/Packages.gz \
  | /opt/bin/busybox gzip -dc \
  | /opt/bin/busybox sed -n '/^Package: libpcre2$/,/^$/p'
```

### Исправление

Скачать `Filename`, указанный в `Packages.gz`:

```sh
/opt/bin/busybox wget -O /tmp/libpcre2.ipk \
  http://bin.entware.net/aarch64-k3.10/libpcre2_10.47-1_aarch64-3.10.ipk
```

Версию выше использовать только как пример — сначала проверить текущий `Filename`.

Затем:

```sh
opkg install /tmp/libpcre2.ipk
wget --version | head -1
opkg update
```

Во время самой установки старый `wget` ещё может один раз вывести warning. Если установка завершается строкой `Configuring libpcre2.`, это нормально.

---

## 3. Geo UI не запускается: странный `colorama`

### Симптом

Python видит `colorama`, но модуль выглядит пустым:

```sh
/opt/bin/python3 -c 'import colorama; print(colorama.__file__); print(getattr(colorama,"__version__","NO VERSION")); print(dir(colorama))'
```

выводит примерно:

```text
None
NO VERSION
['__doc__', '__file__', '__loader__', '__name__', '__package__', '__path__', '__spec__']
```

Werkzeug затем может падать, потому что ожидает `colorama.AnsiToWin32`.

### Причина

Старый пакет мог оставить пустой каталог:

```text
/opt/share/geo-routing/backend/vendor/colorama/
```

Python воспринимает его как namespace package, хотя настоящего `colorama` там нет.

### Исправление

В актуальном `postinst` такой пустой каталог удаляется автоматически. Для старой установки:

```sh
rm -rf /opt/share/geo-routing/backend/vendor/colorama
/opt/etc/init.d/S80geo-ui restart
```

Проверка:

```sh
/opt/bin/python3 -c 'import colorama; print(colorama.__file__); print(getattr(colorama,"__version__","NO VERSION")); print("AnsiToWin32:", hasattr(colorama,"AnsiToWin32"))'
```

---

## 4. После установки UI работает, но Apply падает: нет `geosite.dat` / `geoip.dat`

### Симптом

В `/opt/var/geo` отсутствуют:

```text
geosite.dat
geoip.dat
```

При Apply из UI `geo-update` завершается ошибкой вида:

```text
ERROR: нет /opt/var/geo/geosite.dat
ERROR: нет /opt/var/geo/geoip.dat
```

### Причина

UI запускает:

```text
/opt/bin/geo-update -n
```

Флаг `-n` означает «не скачивать dat заново». На чистой установке файлов ещё может не быть.

### Исправление

Один раз запустить обычное обновление без `-n`:

```sh
/opt/bin/geo-update
```

После появления обоих dat Apply из UI может использовать `-n`.

---

## 5. `blocked-sites` заполнен, но iptables ничего не матчится

### Симптом

Например:

```sh
ipset test blocked-sites-ip 1.1.1.1
```

говорит, что адрес есть в set, но:

```sh
iptables -t mangle -L OUTPUT -v -n --line-numbers | grep blocked-sites
```

остаётся с нулевым счётчиком после запроса к `1.1.1.1`.

### Причина

iptables матчится не по `blocked-sites-ip`, а по родительскому `blocked-sites` типа `list:set`.

Если:

```sh
ipset list blocked-sites
```

показывает пустой `Members:`, дочерние set'ы не подключены к родителю.

### Исправление

```sh
ipset add blocked-sites blocked-sites-site -exist
ipset add blocked-sites blocked-sites-ip -exist
```

Проверить:

```sh
ipset list blocked-sites
```

Ожидается:

```text
Members:
blocked-sites-site
blocked-sites-ip
```

Аналогично для `only-ru`:

```sh
ipset add only-ru only-ru-site -exist
ipset add only-ru only-ru-ip -exist
```

Актуальный `configure.sh` сам создаёт структуру и добавляет оба дочерних set'а.

---

## 6. Проверка маршрута `blocked-sites` через WireGuard

Если IP точно находится в `blocked-sites`, проверка policy routing:

```sh
ip route get 1.1.1.1 mark 0x1002
```

Ожидается маршрут через:

```text
dev nwg0
```

Проверить rule:

```sh
ip rule
```

Нужна строка примерно:

```text
1002: from all fwmark 0x1002 lookup 1002
```

И таблица:

```sh
ip route show table 1002
```

Ожидается:

```text
default dev nwg0
```

Если rule есть, но таблица пустая:

```sh
ip route replace table 1002 default dev nwg0
```

Обычно это делает `/opt/share/geo-routing/configure.sh`.

---

## 7. LAN-клиенты маршрутизируются, а запросы самого роутера — нет

### Симптом

Трафик клиентов через `PREROUTING` работает, но локально запущенный на Keenetic:

```sh
nslookup google.com 1.1.1.1
```

не идёт через WG.

### Причина

Router-local traffic не проходит через `PREROUTING`. Для него требуется отдельное правило в `mangle/OUTPUT`:

```text
-m set --match-set blocked-sites dst -j MARK --set-mark 0x1002
```

Проверить:

```sh
iptables -t mangle -L OUTPUT -v -n --line-numbers
```

После запроса счётчик правила `blocked-sites` должен увеличиться.

### Дополнительная причина: source address

Локальный socket может выбрать WAN source address **до** policy reroute через `nwg0`. Поэтому нужен:

```text
nat/POSTROUTING -o nwg0 -m mark --mark 0x1002 -j MASQUERADE
```

Проверка:

```sh
iptables-save -t nat | grep -F 'nwg0'
```

Ожидается:

```text
-A POSTROUTING -o nwg0 -m mark --mark 0x1002 -j MASQUERADE
```

---

## 8. `only-ru`: старые правила `0x1001/table 1001`

В старых версиях использовались:

```text
fwmark 0x1001
table 1001
priority 1001
```

Текущая схема другая: `only-ru` сбрасывает mark/connmark в `0`, после чего трафик идёт по main table.

Если после обновления остались legacy rules:

```sh
ip rule
```

и присутствует:

```text
1001: from all fwmark 0x1001 lookup 1001
```

его можно удалить:

```sh
ip rule del priority 1001
ip route flush table 1001
```

Не удалять системные Keenetic rules вроде priorities `0`, `10`, `100`, `101`, `32766`, `32767` и неизвестные policy rules.

---

## 9. Очистка старой установки без поломки Keenetic firewall

Не использовать:

```text
iptables -F
iptables -t mangle -F
iptables -t nat -F
```

Это удалит правила, которыми управляет NDM.

Удалять только конкретные legacy rules geo-route через `iptables -D ...`.

Полезно сначала найти все старые скрипты:

```sh
find /opt -type f \( -name '*configure*.sh' -o -name '*geo-routing*.sh' \) -print 2>/dev/null
```

Исторически могли оставаться старые hooks в каталогах:

```text
/opt/etc/ndm/ifstatechanged.d/
/opt/etc/ndm/netfilter.d/
```

а старые данные — в:

```text
/opt/root/geo/
```

Если одновременно работают старый hook и новый `10-geo-routing.sh`, правила могут дублироваться или пересоздаваться в неожиданном порядке.

---

## 10. NDM netfilter hook уходит в рекурсию, Entware/SSH начинает ломаться

### Симптом

После установки hook'а система начинает постоянно пересобирать firewall, команды зависают/работают нестабильно, Entware SSH может стать недоступен.

### Причина

`configure.sh` сам меняет как `mangle`, так и `nat`.

Если NDM hook запускает `configure.sh` при событиях **и `mangle`, и `nat`**, изменение `nat` вызывает hook повторно — получается рекурсия.

### Правильный hook

Он должен реагировать только на пересборку `mangle`:

```sh
#!/bin/sh

[ "${type:-}" = "iptables" ] || exit 0
[ "${table:-}" = "mangle" ] || exit 0

exec /opt/share/geo-routing/configure.sh
```

Текущий путь:

```text
/opt/etc/ndm/netfilter.d/10-geo-routing.sh
```

Если после экспериментов SSH пропал, первым делом проверить, нет ли старого hook'а, который всё ещё вызывает `configure.sh` на `nat`.

---

## 11. После reboot пропал Entware SSH

Удаление `configure.sh` само по себе не выключает sshd. Обычно нужно различить:

1. встроенный SSH Keenetic/NDM;
2. SSH-сервис Entware;
3. доступность `/opt` после загрузки.

### Важный нюанс Web CLI

`exec sh` из Web CLI может сразу вернуть обратно в NDM. Это не надёжный способ проверить Entware shell.

Лучше подключиться настоящим SSH к Keenetic:

```sh
ssh admin@ROUTER_IP
```

и уже из NDM CLI:

```text
(config)> exec sh
```

Если и из реального SSH shell сразу возвращается в NDM, проверить монтирование/доступность `/opt` и журнал Opkg.

После входа в shell проверить процессы:

```sh
ps | grep -E '[s]shd|[d]ropbear'
```

И наличие Entware:

```sh
ls -ld /opt /opt/bin /opt/etc/init.d
```

---

## 12. DNS через WG не работает, но policy route правильный

Диагностику лучше идти по слоям.

### 12.1 IP входит в geo set?

```sh
ipset test blocked-sites-ip 1.1.1.1
```

### 12.2 Родительский `list:set` содержит дочерние set'ы?

```sh
ipset list blocked-sites
```

### 12.3 Маршрут для mark правильный?

```sh
ip route get 1.1.1.1 mark 0x1002
```

### 12.4 Router-local OUTPUT реально матчится?

```sh
iptables -t mangle -L OUTPUT -v -n --line-numbers | grep blocked-sites
nslookup google.com 1.1.1.1
iptables -t mangle -L OUTPUT -v -n --line-numbers | grep blocked-sites
```

Счётчик должен увеличиться.

### 12.5 Есть MASQUERADE?

```sh
iptables-save -t nat | grep -F 'nwg0'
```

### 12.6 Если mark и route работают, но ответа нет

Смотреть пакет на туннеле:

```sh
tcpdump -ni nwg0 'host 1.1.1.1 and port 53'
```

Если `tcpdump` установлен.

---

## 13. DNS-сервер отвечает NXDOMAIN только по UDP

Во время диагностики встречалась отдельная внешняя проблема: публичный DNS мог давать неожиданный NXDOMAIN для заблокированного домена по обычному UDP, тогда как другой resolver или TCP-запрос работал.

Это не проблема `ipset` или geo-route.

Если есть подозрение на вмешательство в DNS:

- сравнить несколько resolver'ов;
- проверить Cloudflare `1.1.1.1/1.0.0.1`;
- проверить Quad9 `9.9.9.9/149.112.112.112`;
- при наличии `dig` сравнить UDP и `+tcp`.

Рабочая конфигурация dnsmasq, которую использовали при такой проблеме:

```conf
server=1.1.1.1#53
server=1.0.0.1#53
server=9.9.9.9#53
server=149.112.112.112#53
strict-order
no-resolv
```

Если эти IP входят в `blocked-sites-ip`, DNS самого роутера также должен корректно проходить через `mangle/OUTPUT`.

---

## 14. Импорт старых dnsmasq `ipset=` правил

Для переноса существующих правил:

```sh
/opt/bin/geo-import-dnsmasq
```

Импортер читает:

```text
/opt/etc/dnsmasq.d/*.conf
```

и пропускает сгенерированный `geo-generated.conf` и backup-файлы.

Если зарезервированный set `blocked-sites` или `only-ru` уже существует в старом формате (`hash:ip` / `hash:net`), импортер может преобразовать его в новую структуру `list:set`.

### Импортер отказывается преобразовывать set

Если старый set имеет активные `References > 0`, его нельзя безопасно destroy/recreate.

Сначала найти правила, которые на него ссылаются:

```sh
iptables-save | grep -F 'match-set blocked-sites'
iptables-save | grep -F 'match-set only-ru'
```

Удалить только старые geo-route rules, затем повторить импорт.

---

## 15. Geo UI: как перезапустить и проверить listener

Перезапуск:

```sh
/opt/etc/init.d/S80geo-ui restart
```

На Keenetic `ss` может отсутствовать. Использовать:

```sh
netstat -lntp 2>/dev/null | grep 8787
```

Проверка самого HTTP локально:

```sh
/opt/bin/busybox wget -qO- http://192.168.1.1:8787/ | head
```

---

## 16. UI работает по LAN, но не открывается через `nwg0`

Это важная особенность Keenetic NDM.

### Симптом

`netstat` показывает listener на WG IP, например:

```text
10.88.0.4:8787 LISTEN
```

но локально:

```sh
/opt/bin/busybox wget -qO- http://10.88.0.4:8787/
```

возвращает:

```text
Connection refused
```

При этом:

```sh
ip route get 10.88.0.4
```

показывает:

```text
local 10.88.0.4 dev lo table local
```

и INPUT на `lo` разрешён.

### Причина

Keenetic может создавать статический DNAT для сервиса на public interface:

```sh
iptables -t nat -L _NDM_STATIC_DNAT -v -n --line-numbers
```

и там обнаруживается:

```text
10.88.0.4 tcp dpt:8787 -> 127.0.0.1:8787
```

То есть запрос к `10.88.0.4:8787` NDM перенаправляет на loopback.

Если приложение слушает только `10.88.0.4:8787`, на `127.0.0.1:8787` никто не принимает соединение — отсюда `Connection refused`.

### Правильная схема bind

Geo UI должен слушать:

```text
LAN_IP:8787
127.0.0.1:8787
```

и **не обязан напрямую слушать `nwg0`**.

Тогда:

```text
LAN -> LAN_IP:8787
nwg0 -> NDM DNAT -> 127.0.0.1:8787
WAN -> listener отсутствует
```

---

## 17. Как понять, firewall ли виноват в `Connection refused`

При проблеме с локальным `10.88.0.4:8787` мы проверяли:

```sh
iptables -t filter -L INPUT -v -n --line-numbers | grep ' lo '
```

Затем делали один запрос и повторяли команду.

Если счётчик `ACCEPT ... lo` увеличивается, SYN дошёл до локального INPUT и был разрешён. Значит проблема уже не в filter/INPUT.

Дальше смотреть NAT:

```sh
iptables -t nat -L OUTPUT -v -n --line-numbers
iptables -t nat -L _NDM_DNAT -v -n --line-numbers
iptables -t nat -L _NDM_STATIC_DNAT -v -n --line-numbers
```

Это и позволило обнаружить DNAT `8787 -> 127.0.0.1:8787`.

---

## 18. Старые файлы в `/opt/root/geo`

Очень ранние версии/ручные установки могли хранить:

```text
/opt/root/geo/common.conf
/opt/root/geo/geo.d/
/opt/root/geo/geosite.dat
/opt/root/geo/geoip.dat
```

Автоматическая миграция из `/opt/root/geo` позже была удалена из package scripts.

Если обновляется очень старая установка, переносить нужные данные вручную:

```text
config -> /opt/etc/geo/
dat    -> /opt/var/geo/
```

Не считать наличие `/opt/root/geo` признаком актуальной конфигурации.

---

# Maintainer troubleshooting

## 19. GitHub Actions run есть, но `jobs: []`

### Симптом

Workflow отображается в Actions, завершается failure, но jobs отсутствуют.

### Причина

YAML workflow может быть синтаксически повреждён и не парситься GitHub Actions вообще.

Такое уже происходило с `.github/workflows/release.yml`: shell-строка с regex была оборвана, а хвост workflow продублирован.

### Защита

PR CI запускает `actionlint` для всех workflows:

```text
.github/workflows/ipk.yml
```

Не обходить этот check при изменениях GitHub Actions.

---

## 20. Release не создаётся после merge

Текущая автоматизация:

1. merged PR в `main`;
2. `release.yml` вычисляет следующий patch tag;
3. создаёт GitHub Release/tag;
4. dispatch'ит `publish.yml`;
5. `publish.yml` checkout'ит именно tag, собирает IPK и публикует Pages feed.

Если semantic version tags отсутствуют, release workflow специально завершается ошибкой:

```text
No semantic version tags found; create bootstrap tag first
```

Проверка:

```sh
git tag -l 'v*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V
```

Package version в source не хранится: build требует `GEO_ROUTE_VERSION=X.Y.Z`.

---

## 21. GitHub Pages не публикуется напрямую от tag event

Для этого репозитория публикация сделана через `workflow_dispatch` на `main`, а сам build checkout'ит release tag.

Это обходит ограничения/особенности GitHub Pages environment, когда deploy разрешён только из `main`, и проблему event chaining через стандартный `GITHUB_TOKEN`.

Не возвращать схему «tag push напрямую deploy'ит Pages», не проверив permissions/environment.

---

## 22. Проверка после обновления пакета

После `opkg upgrade geo-route`:

```sh
/opt/etc/init.d/S80geo-ui restart
/opt/share/geo-routing/configure.sh
```

Проверить:

```sh
ipset list blocked-sites
ipset list only-ru
ip rule
ip route show table 1002
iptables-save -t mangle | grep -E 'blocked-sites|only-ru'
iptables-save -t nat | grep -F 'nwg0'
netstat -lntp 2>/dev/null | grep 8787
```

Если это чистая установка и dat ещё нет:

```sh
/opt/bin/geo-update
```

После этого проверить Apply в UI.

---

## 23. Что приложить к bug report

Минимальный диагностический набор:

```sh
opkg list-installed | grep -E '^(geo-route|wget|wget-ssl|libpcre2|python3)'
ip -4 addr
ip rule
ip route show table 1002
ipset list blocked-sites
ipset list only-ru
iptables-save -t mangle
iptables-save -t nat
netstat -lntp 2>/dev/null | grep 8787
tail -100 /opt/var/geo/geo-update.log 2>/dev/null
```

Если проблема только с конкретным IP:

```sh
ipset test blocked-sites-ip IP
ipset test blocked-sites-site IP
ip route get IP mark 0x1002
```

Это обычно позволяет сразу понять, на каком слое проблема: конфигурация → dnsmasq/ipset → mark → policy route → NAT → приложение.
