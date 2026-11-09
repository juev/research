---
title: "Docker и IPv6: когда опубликованный порт обходит ожидаемую границу firewall"
date: 2026-11-09T09:37:49+03:00
description: "Путь пакета к Docker bridge: IPv4 и IPv6, loopback и wildcard, NAT и routed, DOCKER-USER и native nftables — без ложных гарантий INPUT и reverse proxy."
showToc: true
tocOpen: true
---

## Аннотация

Опубликованный Docker-порт — самостоятельный вход к приложению, а не внутренний маршрут reverse proxy. В обычном bridge/NAT входящий пакет после DNAT становится пересылаемым и не проходит host `INPUT`; при IPv6→IPv4 через userland proxy, напротив, соединение принимает локальный процесс. Поэтому ни «у меня закрыт INPUT», ни универсальный рецепт для `DOCKER-USER` не описывают все пути. Более того, в `routed` режиме публикация разрешает порт **на адресе контейнера**, а указанные host port и конкретный host address не становятся ограничением этого доступа.[^2][^3][^10][^17][^20]

**Данные на 2026-11-09.** База обзора — Docker Engine **29.9.3**, опубликованный 3 ноября, его tagged source и generated rules, а также снимок Docker network documentation в commit `16e452c8` от 5 ноября. Допущение автономного исследования: rootful Docker Engine на одном Linux-хосте, standalone-контейнеры в user-defined bridge; внешняя маршрутизация управляется отдельно. Это документальный обзор, **без запуска контейнеров, изменения firewall, внешнего сканирования и измерения производительности**. Матрицы ниже — ожидаемая семантика, не протокол испытаний установленного сервера.[^1][^2][^17][^18][^19]

## Введение

**Исследовательский вопрос:** при каких сочетаниях семейства адресов, bind address, gateway mode и firewall backend опубликованный порт оказывается доступен не так, как ожидает администратор? Разделим его на семь частей: где проходит пакет; когда IPv6 обслуживает IPv4-only контейнер; что ограничивает loopback; как устроен direct routing; где размещать дополнительные запреты; как уменьшить поверхность в Compose; чем подтвердить итоговую доступность. Основание такого разделения — разные механизмы port publishing, маршрутизации и фильтрации в официальной документации.[^2][^3][^4]

Это продолжение [обзора reverse proxy](/articles/reverse-proxy-caddy-traefik-nginx/), но не новый выбор между Caddy, Traefik и nginx. В [статье об управлении homelab](/articles/nixos-ansible-compose/) предметом были уровни конфигурации и отката; в [разборе overlay-сетей](/articles/overlay-networks-internals/) — прохождение NAT между узлами. Здесь граница уже: **какие адреса и порты Linux-хоста и контейнера принимают входящие соединения**. HTTPS-маршрут не отменяет отдельно опубликованный backend: публикация сама создаёт доступ снаружи bridge.[^2][^9]

За пределами матрицы — Swarm, Docker Desktop, Kubernetes CNI, macvlan/ipvlan и rootless networking. Это не косметические исключения: `host` разделяет сетевой namespace хоста и игнорирует port mapping; rootless запускает daemon и контейнеры в user namespace; native nftables backend в изученной документации ещё experimental и не поддерживает Swarm. Переносить на эти режимы схему standalone bridge без отдельной проверки нельзя.[^4][^15][^16]

## 1. Firewall должен стоять на пути пакета

Для обычного внешнего подключения к опубликованному NAT-порту полезна схема: внешний интерфейс → `prerouting` и DNAT → решение маршрутизации → `forward` → bridge → контейнер. Netfilter отдельно определяет локальную доставку через `input` и пересылку через `forward`. Docker использует NAT для port mapping, а свои filter chains подключает к `FORWARD`. Следовательно, запрет `INPUT tcp dport 8080` нельзя считать запретом трафика, который уже перенаправлен на контейнерный порт 80.[^3][^10]

Это объясняет предупреждение Docker о совместимости с ufw: контейнерный трафик перенаправляется прежде, чем достигает ожидаемых администратором `INPUT`/`OUTPUT` chains. Но фраза «Docker обходит firewall» слишком широка. Он не обходит все Netfilter hooks: он программирует другой путь и разрешающие правила на нём. Дополнительный запрет в правильной точке пересылки остаётся существенным; host firewall и container ingress policy просто не тождественны.[^3][^5]

У iptables backend штатная точка дополнительной политики — `DOCKER-USER`, обрабатываемая раньше основных разрешений Docker. Правила, просто дописанные в конец `FORWARD`, могут не увидеть уже принятый трафик. Важна и стадия трансляции: к моменту `DOCKER-USER` пакет после DNAT содержит адрес и порт контейнера, а не первоначальные host address и host port.[^3]

> “When packets arrive to the `DOCKER-USER` chain, they have already passed through a Destination Network Address Translation (DNAT) filter.”[^3]

Если политика формулируется через исходный внешний endpoint, документация предлагает conntrack extension с `--ctorigdst` и `--ctorigdstport`; обычный `--dport` после DNAT решает другую задачу. Docker предупреждает о возможной цене conntrack matching для производительности. Это не численный benchmark: из предупреждения нельзя вывести ни процент потерь, ни необходимость такого matching для каждого allowlist.[^3]

Практический вывод — перед правилом записать четыре вещи: ingress interface, family, адрес назначения **на этой стадии** и транспортный порт. Иначе администратор легко запрещает host:8080 в цепочке, которая видит container:80, либо ограничивает локальный listener вместо транзитного потока. Этот вывод следует из последовательности hooks и DNAT, а не из испытаний конкретного ruleset.[^3][^10]

## 2. IPv6 может существовать только на внешней половине соединения

«В моей Docker-сети нет IPv6» не означает «к приложению нельзя подключиться по IPv6 хоста». Docker прямо описывает случай: host IP в mapping не указан, bridge IPv4-only, `--userland-proxy=true` — значение по умолчанию; тогда порт на IPv6-адресе хоста может отображаться на IPv4-адрес контейнера. Поэтому состав IPAM bridge и внешняя поверхность публикации — разные проверки.[^2]

В source тега `docker-v29.9.3` эта совместимость видна в `sortAndNormPBs`: при отсутствии container IPv6 и включённом proxy в качестве backend выбирается container IPv4. Для отключённого proxy код содержит обратное ограничение: «There's no way to map from host-IPv6 to container-IPv4 with the userland proxy disabled». Это утверждение о данном механизме Docker, не о невозможности построить отдельный транслятор вообще.[^17]

Здесь меняется и модель firewall. Tagged TCP proxy вызывает `listener.Accept()`, затем `net.DialTCP` к backend и копирует данные между двумя TCP-соединениями. Сопоставляя это с Netfilter hooks, получаем вывод: внешний участок к локальному proxy относится к локальной доставке, а backend-соединение создаётся процессом хоста. Это **не тот же транзитный пакет**, который достаточно ограничить единственным правилом в `DOCKER-USER`. Классификация пути — вывод из кода и схемы hooks, а не результат packet capture.[^10][^20]

Если bridge действительно dual-stack, IPv6 настраивается отдельно: для user-defined network используется `--ipv6` или Compose `enable_ipv6`; настройки `ipv6` и `fixed-cidr-v6` в daemon configuration относятся к default bridge. Документация также связывает `ip6tables` с IPv6 isolation и port mapping. Один только флаг адресации нельзя принимать за готовую внешнюю IPv6-политику.[^7]

Из этого следует порядок диагностики: сначала внешний destination family, затем публикация и наличие proxy, затем family контейнерного endpoint. Проверять только `iptables` или только IPv6-адрес внутри контейнера недостаточно: первое пропускает IPv6 policy, второе — host IPv6→container IPv4. Для nftables семейство `inet` позволяет описать обе IP-версии, но условие `ip saddr` внутри него по-прежнему относится только к IPv4.[^2][^12][^17]

## 3. Матрица NAT и routed: один синтаксис, разные обещания

Ниже рассматривается **одна выбранная IP-family**, настроенная на bridge. Предполагаются работающий listener в контейнере, штатные правила Docker и отсутствие дополнительного внешнего запрета. Для NAT не включены `allow-direct-routing` и trusted interfaces. «Возможен» означает, что Docker допускает путь при наличии маршрута; это не гарантия доставки через провайдера. Для mixed-family сети режим надо определить отдельно для IPv4 и IPv6.[^2][^6]

| Family и mode | Bind в публикации | Куда приходит внешний клиент | Ожидание по документации |
|---|---|---|---|
| IPv4, `nat` | `127.0.0.1` | Host IPv4:published | Только локальная публикация; обычный внешний путь закрыт[^2][^18] |
| IPv6, `nat` | `::1` | Host IPv6:published | Только локальная публикация[^2] |
| IPv4, `nat` | Явный `0.0.0.0` | Host IPv4:published | Доступ возможен на IPv4-адресах хоста[^2][^6][^17] |
| IPv6, `nat` | Явный `::` | Host IPv6:published | Доступ возможен на IPv6-адресах хоста[^2][^17] |
| IPv4, `routed` | `0.0.0.0` | Container IPv4:target | Host port не используется; нужен маршрут[^2] |
| IPv6, `routed` | `::` | Container IPv6:target | Host port не используется; нужен маршрут[^2] |
| IPv4, `routed` | Конкретный адрес, включая loopback | Container IPv4:target | Конкретный bind не ограничивает routed-доступ[^2][^17] |
| IPv6, `routed` | Конкретный адрес, включая loopback | Container IPv6:target | Конкретный bind не ограничивает routed-доступ[^2][^17] |

Последние две строки — ловушка чтения `-p` как обычного `bind()`. В `routed` host address служит выбору family, конкретный адрес и host port не имеют ожидаемого ограничительного смысла. Документация рекомендует unspecified address и отсутствие host port; неподходящие параметры дают предупреждение, а не превращают routed service в loopback-only listener.[^2]

> “In `routed` mode, a host port in a `-p` or `--publish` port mapping is not used, and the host address is only used to decide whether to apply the mapping to IPv4 or IPv6.”[^2]

Ещё одно различие: **явный** `-p 0.0.0.0:8080:80` выбирает IPv4. Но значение `0.0.0.0` у настройки **default host binding address** означает default-публикацию на IPv4 и IPv6; опущенный host IP может развернуться в две записи. Одинаковую строку нельзя интерпретировать без знания, является она явным параметром mapping или default network option. Tagged code отдельно описывает создание дублирующей IPv6 binding при отсутствии HostIP.[^6][^17]

Для смешанного режима официальная документация приводит IPv4 `nat` и IPv6 `routed`: `-p 8080:80` открывает IPv4 host:8080, а IPv6 — container:80, **не host:8080**. В `NetworkSettings.Ports` IPv6 mapping имеет пустой `HostPort`. Поэтому проверка одного host port или отсутствие привычного listener не доказывает закрытость приложения: вторая family использует другой адрес назначения и другой порт.[^2]

## 4. Direct routing и предел обещания «только localhost»

По умолчанию внешним узлам запрещён прямой доступ к адресам контейнеров bridge; одного маршрута недостаточно. Но daemon option `allow-direct-routing` разрешает direct access к опубликованным портам во всех Linux bridge networks, а `com.docker.network.bridge.trusted_host_interfaces` позволяет выбрать входные интерфейсы конкретной сети. Это дополнительные пути, которые нужно включать в модель, даже если host mapping выглядит локальным.[^2][^3]

В документации есть особенно показательный пример: контейнер публикует `127.0.0.1:8080:80`, однако через trusted interfaces его порт 80 доступен непосредственно на container IP при наличии маршрута. Противоречие с кратким обещанием «localhost доступен только хосту» снимается областью действия: ограничен **host-published endpoint**, но отдельно разрешён доступ к **container endpoint**. Для безопасности проверять нужно оба.[^2]

Режим `routed` тоже оставляет фильтрацию: NAT и masquerading отсутствуют, но извне разрешаются опубликованные container ports. Это не равнозначно `nat-unprotected`: в последнем режиме direct routing открывает также неопубликованные порты. Документация называет его совместимостью с legacy behaviour; выбирать его как «просто NAT без проблем firewall» — менять саму границу доступа.[^2]

Tagged generated nftables rules для routed IPv4 подтверждают различие механизмов: нет правила `DROP DIRECT ACCESS` в raw prerouting и нет masquerade для этой сети, зато присутствуют разрешение `tcp dport 80` на container address и последующий `UNPUBLISHED PORT DROP`. Это сохранённый проектом пример правил для версии 29.9.3, **не вывод команд на исследуемом здесь хосте** и не отдельное испытание IPv6.[^19]

Есть и историческая граница. Для релизов **старше 28.0.0** Docker предупреждает о доступе соседей того же L2 segment к localhost-published ports. Release notes 28.0.0 фиксируют исправление; generated iptables rules тега 29.9.3 показывают raw-prerouting DROP для remote traffic к loopback mapping. Это основание не повторять старый баг как universal current default — но и не забывать проверять версию установленного daemon.[^2][^13][^18]

Даже конкретный non-loopback host IP не обязательно равен входному интерфейсу: при IP forwarding документация допускает доступ к опубликованному адресу через другой интерфейс, если клиент имеет соответствующий маршрут. Привязка к destination address и фильтрация по `iif` отвечают на разные вопросы. Поэтому политика «только через VPN-интерфейс» требует проверки интерфейса/маршрута, а не только выбора адреса в `ports`.[^2]

## 5. iptables и native nftables: переносить надо политику, не имя цепочки

Для iptables backend дополнительный deny размещают с учётом `DOCKER-USER`, обеих IP-family и DNAT. Но эта цепочка не универсальный переключатель доступа: запрещённый штатной защитой direct-routed пакет может быть отброшен ещё в raw `PREROUTING`, прежде filter table. Разрешение в поздней цепочке не воскресит уже удалённый пакет. Для разрешённого direct routing используются документированные network/daemon options.[^3]

У **native nftables backend** нет `DOCKER-USER`. Docker владеет таблицами `ip docker-bridges` и `ip6 docker-bridges`; пользовательскую политику предлагается держать в отдельных tables/base chains с нужным hook и priority. Наличие утилиты `nft` на хосте само по себе не сообщает, какой backend выбран daemon: предмет проверки — `firewall-backend` и фактически установленные правила. Редактировать Docker-owned tables документация не рекомендует: изменения могут исчезнуть.[^4][^5]

> “In Docker's nftables implementation, there is no `DOCKER-USER` chain.”[^4]

При переносе важно различать deny и allow. Netfilter обрабатывает base chains по возрастанию численного priority; одинаковый priority не гарантирует взаимного порядка. `drop` окончателен, но `accept` завершает текущую base chain, не запрещая следующей цепочке отбросить пакет. Поэтому «мой accept стоит до Docker» не означает override его drop. Для ограничивающей политики самостоятельный drop понятнее, чем попытка превратить ранний accept в глобальное разрешение.[^10][^11]

Docker описывает специальный override через `--bridge-accept-fwmark`: mark должен быть проставлен раньше Docker forward rules. Но этот механизм не отменяет raw-prerouting drop прямого доступа, потому что тот происходит ещё раньше. Вывод: сначала определить, **какую именно** Docker-политику требуется изменить; не заменять это произвольным ACCEPT или fwmark. Настройка override не является рекомендацией включать его на обычном публичном сервере.[^4]

Миграция backend меняет и обязанности вокруг forwarding. Native nftables backend сам не включает IP forwarding и не создаёт default drop policy; нужные sysctls и запрет нежелательной пересылки между non-Docker interfaces остаются администратору. Старый iptables `FORWARD policy DROP` может продолжать отбрасывать трафик, уже принятый nftables. Успешный тест сразу после переключения недостаточен: оставшийся jump в `DOCKER-USER` способен работать до его удаления или reboot, скрывая неполную миграцию.[^4]

Отключение `iptables`/`ip6tables` — не короткий путь к безопасной совместимости. Эти flags влияют и на native nftables; Docker предупреждает о поломке networking, исчезновении masquerading и доступности всех container ports из локальной сети без replacement rules. Аналогично наличие firewalld нельзя читать как готовый запрет: Docker создаёт zone `docker` с target `ACCEPT` и policy `docker-forwarding` из `ANY` в эту zone. Интеграция — механизм, не подтверждение желаемого allowlist.[^4][^5]

## 6. Compose: сначала убрать лишнюю публикацию

Для reverse proxy в том же Compose network обычный backend не требует host port: service-to-service соединение использует container port и имя сервиса. Предлагаемый минимальный принцип — публиковать edge, а не каждое приложение и БД. Это уменьшает число внешних endpoints, но не создаёт межконтейнерный firewall: на стандартной общей user-defined bridge containers имеют доступ к портам друг друга.[^6][^9]

`expose` в Compose не является внешним publish и не служит allowlist остальных портов. Документация описывает internal container ports; bridge driver отдельно гарантирует обычную связность участников сети. Если контейнер скомпрометирован, отсутствие `ports` у соседнего backend не означает отсутствие доступа из общей сети. Разделение frontend/backend networks ограничивает участников, а не аутентифицирует приложения внутри разрешённого сегмента.[^6][^8][^9]

Когда reverse proxy работает **на хосте**, loopback mapping в NAT — другой обоснованный профиль. Например, фрагмент ниже явно выбирает IPv4 host endpoint. Это иллюстрация синтаксиса для уже существующего сервиса, не полный проверенный deployment; режим сети предполагается `nat`, direct-routing exceptions не включены. Если proxy нужен IPv6 loopback, его mapping следует описать отдельно, а не полагаться на wildcard default.[^2][^8]

```yaml
services:
  app:
    # image и остальные параметры задаются отдельно
    ports:
      - target: 8080
        published: "18080"
        host_ip: "127.0.0.1"
        protocol: tcp
```

Разумный выбор профиля зависит от места proxy: в общей Docker network — без host publish у backend; на хосте — явный loopback publish в NAT; для настоящего routed IPv6 — отдельная политика на container addresses и опубликованных target ports. Это авторский синтез трёх механизмов, а не универсальный готовый firewall. Default `com.docker.network.bridge.host_binding_ipv4=127.0.0.1` может уменьшить случайную wildcard-публикацию в user-defined networks, но не отменяет явные overrides и routed semantics.[^2][^6][^9]

## 7. Проверять доступность, а не красивый YAML

Предлагаемый протокол начинается с инвентаризации: версия daemon; выбранный backend; driver каждой сети; gateway mode отдельно для IPv4/IPv6; `Ports`; container addresses; наличие proxy и direct-routing options. `docker network inspect` возвращает подробности сети, а port-publishing documentation показывает чтение `NetworkSettings.Ports`. Полный container inspect лучше не публиковать: для этой задачи достаточно адресов и mappings, без environment приложения.[^2][^14]

```sh
docker version --format '{{.Server.Version}}'
docker network inspect <network>
docker container inspect <container> --format '{{json .NetworkSettings.Ports}}'
```

Следующий шаг — прочитать фактические правила в соответствующих namespaces и обеих families: `iptables-save`, `ip6tables-save`, `nft list ruleset`, затем сопоставить hooks и counters с ожидаемым путём. Важно не просто найти слово DROP: оно должно относиться к нужному ingress, destination после DNAT и family. Эти команды здесь не запускались; названия chains и tables следует сверять с backend и версией, а не механически искать `DOCKER-USER` везде.[^3][^4][^10]

Для внешней проверки нужен принадлежащий администратору отдельный узел с рабочими IPv4 и IPv6. Предлагаемый набор целей: host IPv4:published; host IPv6:published; container IPv4:target и container IPv6:target, если direct routing предусмотрен. Для loopback-profile ожидают локальный успех и внешний запрет, но дополнительно проверяют отсутствие разрешённого прямого container endpoint. Набор следует строить из реальных адресов своего сервера, не сканировать чужие сети.[^2][^17]

DNS-проверку полезно отделить от transport-проверки: `curl -4` и `curl -6` к `https://app.example.org/` проверяют две семьи edge; прямое соединение к backend — другой тест. Для mixed NAT/routed нельзя автоматически подставить один и тот же порт в обе команды. Успех публичного HTTPS не устанавливает, что backend закрыт в обход proxy; неудача с локальной машины не доказывает внешний запрет, поскольку local delivery/output и forwarding имеют разные пути.[^2][^9][^10]

Отрицательный результат тоже требует объяснения. Timeout может возникнуть из-за отсутствия маршрута, внешнего firewall или host/container policy; один timeout не различает причины. Поэтому предлагается сопоставлять внешнюю пробу с counters либо packet capture на собственном хосте и фиксировать family, destination, interface и время. После разрешённого изменения backend или обновления daemon протокол стоит повторять, включая reboot-проверку persistent policy: документация миграции прямо описывает правила, исчезающие после перезапуска хоста.[^4][^10]

## Дискуссионные вопросы и противоречия

**«Localhost доступен только хосту» против direct routing.** Первая формулировка описывает обычную NAT-публикацию; та же документация показывает trusted-interface exception с loopback mapping и доступным container IP. Это не повод объявить loopback бесполезным. Это повод ограничить гарантию конкретным endpoint и проверить, не включён ли второй путь.[^2]

**«DOCKER-USER решает проблему Docker firewall» против native nftables.** Для iptables это документированная точка дополнительной forward-policy; для native nftables такой цепочки нет. Более того, host IPv6→IPv4 proxy не сводится к тому же forward packet. Противоречие появляется при переносе рецепта между backend и data paths, а не между двумя взаимоисключающими описаниями одного режима.[^3][^4][^20]

**«Нет NAT — нет защиты».** `routed` оставляет published-port filtering; `nat-unprotected` убирает именно эту границу для direct routing. NAT, адресуемость и разрешение порта — независимые свойства. Но и обратное неверно: наличие NAT не доказывает закрытость опубликованного порта, поскольку Docker специально делает его доступным.[^2][^19]

**«IPv4-only bridge закрывает IPv6».** Это верно для отсутствующего native container IPv6 endpoint, но не для внешней IPv6-публикации через включённый userland proxy. Контраргумент подтверждается и документацией, и tagged source; ни один из них не доказывает, что конкретный сервер действительно имеет доступный извне IPv6-адрес и разрешающую внешнюю политику.[^2][^17]

## Недостаточность данных

Не установлена фактическая доступность какого-либо production-хоста: не читались его daemon configuration, routes, provider firewall и effective rules, не выполнялись внешние пробы. Поэтому обзор не отвечает «открыт ли порт у вас». Официальная семантика с условием маршрутизации не заменяет измерение конкретной топологии.[^2][^14]

Не измерены throughput, latency и стоимость conntrack либо userland proxy. Прочитан код пересылки и предупреждение Docker о возможной деградации matching, но из них нельзя получить численный рейтинг NAT против routed или proxy против kernel forwarding. Эти вопросы требуют отдельного bounded experiment с зафиксированными версиями и одинаковыми нагрузками.[^3][^20]

Наконец, не проверена совместимость произвольного набора ufw, firewalld, VPN и сторонних сетевых инструментов. Документация объясняет несколько конфликтов, но порядок всех дополнительных chains и marks зависит от установленной системы. Предложенный протокол — способ собрать недостающее доказательство, а не заявление, что каждая такая комбинация уже проверена.[^4][^5][^11]

## Заключение

Надёжная граница строится не вокруг слова «Docker», а вокруг полного набора endpoints и data paths. Для NAT нужно различать host publication и DNAT/forward; для routed — container address и target port; для host IPv6→IPv4 proxy — две части соединения с локальным процессом между ними. Loopback ограничивает обычную локальную публикацию, но не отменяет отдельно разрешённый direct routing и не сохраняет bind-смысл внутри `routed`.[^2][^10][^17][^20]

Практическая рекомендация: убрать лишние backend publishes, явно выбрать families и режимы, разместить deny на реально используемом hook, а после изменения проверить разрешённые **и запрещённые** пути с внешнего собственного узла. Для iptables и native nftables это разные способы реализации политики; зелёный HTTPS, закрытый INPUT и пустое поле HostPort по отдельности не доказывают закрытость container ingress.[^2][^3][^4][^9]

## Quality Metrics

| Metric | Value |
|--------|-------|
| Sources found | 34 |
| Sources read | 21 |
| Sources cited | 20 |
| Academic sources | 0 |
| Official/documentation | 20 |
| Industry reports | 0 |
| News/journalism | 0 |
| Blog/forum | 0 |
| Citation coverage | 96% (52/54 абзаца по checker) |
| Main-text words | 3050; без frontmatter, метрик и сносок |
| Counter-arguments searched | Yes |
| Research rounds | 2 |
| Source units | Отдельные документы и source files; pinned/HTML-копии одного документа считаются один раз |
| Access scope | Релевантные разделы полного текста; abstract-only sources нет |
| Independence | Maintainer docs/code; не 20 независимых эксплуатационных подтверждений |
| Runtime verification | Не проводилась; матрица документальная |

[^1]: Docker / Moby. «Release v29.9.3 · moby/moby». docker-v29.9.3. https://github.com/moby/moby/releases/tag/docker-v29.9.3
[^2]: Docker / Moby. «Port publishing and mapping». docker/docs, commit 16e452c8. https://raw.githubusercontent.com/docker/docs/16e452c8eaea26cec842cbf1065037fb2015001f/content/manuals/engine/network/port-publishing.md
[^3]: Docker / Moby. «Docker with iptables». docker/docs, commit 16e452c8. https://raw.githubusercontent.com/docker/docs/16e452c8eaea26cec842cbf1065037fb2015001f/content/manuals/engine/network/firewall-iptables.md
[^4]: Docker / Moby. «Docker with nftables». docker/docs, commit 16e452c8. https://raw.githubusercontent.com/docker/docs/16e452c8eaea26cec842cbf1065037fb2015001f/content/manuals/engine/network/firewall-nftables.md
[^5]: Docker / Moby. «Packet filtering and firewalls». docker/docs, commit 16e452c8. https://raw.githubusercontent.com/docker/docs/16e452c8eaea26cec842cbf1065037fb2015001f/content/manuals/engine/network/packet-filtering-firewalls.md
[^6]: Docker / Moby. «Bridge network driver». docker/docs, commit 16e452c8. https://raw.githubusercontent.com/docker/docs/16e452c8eaea26cec842cbf1065037fb2015001f/content/manuals/engine/network/drivers/bridge.md
[^7]: Docker / Moby. «Use IPv6 networking». docker/docs, commit 16e452c8. https://raw.githubusercontent.com/docker/docs/16e452c8eaea26cec842cbf1065037fb2015001f/content/manuals/engine/daemon/ipv6.md
[^8]: Docker / Moby. «Define services in Docker Compose». документация, срез 2026-11-09. https://docs.docker.com/reference/compose-file/services/
[^9]: Docker / Moby. «Networking in Compose». документация, срез 2026-11-09. https://docs.docker.com/compose/how-tos/networking/
[^10]: Netfilter project. «Netfilter hooks». документация, срез 2026-11-09. https://wiki.nftables.org/wiki-nftables/index.php/Netfilter_hooks
[^11]: Netfilter project. «Configuring chains». документация, срез 2026-11-09. https://wiki.nftables.org/wiki-nftables/index.php/Configuring_chains
[^12]: Netfilter project. «Nftables families». документация, срез 2026-11-09. https://wiki.nftables.org/wiki-nftables/index.php/Nftables_families
[^13]: Docker / Moby. «Docker Engine version 28 release notes». документация, срез 2026-11-09. https://docs.docker.com/engine/release-notes/28/
[^14]: Docker / Moby. «docker network inspect». документация, срез 2026-11-09. https://docs.docker.com/reference/cli/docker/network/inspect/
[^15]: Docker / Moby. «Host network driver». документация, срез 2026-11-09. https://docs.docker.com/engine/network/drivers/host/
[^16]: Docker / Moby. «Rootless mode». документация, срез 2026-11-09. https://docs.docker.com/engine/security/rootless/
[^17]: Docker / Moby. «daemon/libnetwork/drivers/bridge/port_mapping_linux.go». docker-v29.9.3. https://raw.githubusercontent.com/moby/moby/docker-v29.9.3/daemon/libnetwork/drivers/bridge/port_mapping_linux.go
[^18]: Docker / Moby. «Container on a user-defined network, with a port published on a loopback address». docker-v29.9.3. https://raw.githubusercontent.com/moby/moby/docker-v29.9.3/integration/network/bridge/iptablesdoc/generated/usernet-portmap-lo.md
[^19]: Docker / Moby. «Container on a routed-mode network, with a published port». docker-v29.9.3. https://raw.githubusercontent.com/moby/moby/docker-v29.9.3/integration/network/bridge/nftablesdoc/generated/usernet-portmap-routed.md
[^20]: Docker / Moby. «cmd/docker-proxy/tcp_proxy_linux.go». docker-v29.9.3. https://raw.githubusercontent.com/moby/moby/docker-v29.9.3/cmd/docker-proxy/tcp_proxy_linux.go
