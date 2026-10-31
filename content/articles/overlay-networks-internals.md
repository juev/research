---
title: "Как Tailscale находит путь: NAT traversal, birthday paradox и цена своего DERP"
date: 2026-10-31T09:35:00+03:00
description: "Механика NAT traversal в overlay-сетях: типы NAT по RFC 4787, STUN, hole punching, перебор по birthday paradox, протокол DERP и реальная пропускная способность self-hosted релея."
showToc: true
tocOpen: true
---

## Аннотация

Overlay-сети принято обсуждать на уровне выбора: Tailscale или Headscale, Nebula или Yggdrasil. Между тем почти вся практика — «почему эта пара устройств едет через релей», «почему через релей всего 2 Мбит/с», «зачем мне свой DERP» — определяется не выбором продукта, а механикой: типами NAT, алгоритмом hole punching и устройством релея. Этот обзор разбирает именно этот слой: от правила stateful firewall до формата кадров DERP и от измеренной доли успешных прямых соединений до пропускной способности, которую релей реально отдаёт.

Выводы коротко. Прямое соединение — это не «настройка», а вероятностный процесс: hole punching срабатывает примерно в 70% случаев, если предварительные стадии прошли, и почти всегда с первой попытки; остальное закрывает релей. Релей — не аварийный режим, а штатная часть протокола: соединение всегда начинается через DERP и апгрейдится. И главное: свой DERP решает вопрос доверия и автономности, но не вопрос скорости — встроенный в Headscale сервер мейнтейнеры прямо называют «удобством», а опубликованные замеры дают единицы и десятки мегабит в секунду там, где прямое соединение даёт гигабит. Данные и версии — на 2026-10-31: Tailscale 1.104.4 (28 октября 2026) и Headscale 0.29.7 (30 октября 2026).

## Введение

**Актуальность.** У self-hosted координации — Headscale со своим DERP, peer relay внутри своей сети — есть цена, которую обычно обсуждают качественно, а не количественно. В эксплуатацию вместе с ней пришли вопросы, которые раньше задавали только разработчики протоколов: почему пара «офис — домашний сервер» никогда не соединяется напрямую, почему релей отдаёт 2 Мбит/с при гигабитном канале, что произойдёт, если единственный DERP-сервер ляжет. Ответы на них лежат в механике, а не в конфигурации[^1].

**Цель** — разобрать конвейер установления соединения в overlay-сети на WireGuard-основе по шагам и показать, где именно теряются производительность, автономность и предсказуемость. Заодно проверить, насколько публичные обещания «прямое соединение почти всегда» подтверждаются независимыми измерениями.

**Границы.** Рассматривается стек Tailscale/Headscale как наиболее документированный: протокол DERP, поведение magicsock, встроенный DERP в Headscale и отдельный `derper`. Nebula с её lighthouse, Yggdrasil с распределённой маршрутизацией и WebRTC-стек браузера остаются за рамками — это отдельные архитектуры, и сравнение с ними уже было в предыдущих обзорах. Собственных замеров на устройствах здесь нет: все числа взяты из опубликованных измерений, документации и исходного кода, что само по себе является ограничением (о нём — в разделе о недостаточности данных).

## Две преграды: stateful firewall и NAT

Первая преграда проще, и её полезно проговорить точно, потому что она объясняет половину дальнейших трюков. Stateful firewall для UDP работает по одному правилу: входящий пакет разрешён, если раньше был замечен соответствующий исходящий. «Направление» соединения существует только в голове проектировщика протокола — на проводе это просто пакеты, и firewall помнит, что видел[^1].

Из этого правила сразу следует топология «звезда»: сервер без firewall доступен всем, клиенты за firewall сами инициируют соединения. Проблема начинается, когда два клиента хотят говорить напрямую: оба должны начать первыми, и ни один не может, потому что второй ещё не начал. Решение — одновременная передача: обе стороны шлют пакеты друг другу примерно в одно время, и промежуточные firewall открываются, пока оба пира ещё на месте[^1].

Второй нюанс — таймер. Соединение в stateful firewall живёт, пока идут пакеты; типичное значение для UDP — 30 секунд, после чего состояние забывается и процедуру надо начинать заново[^1]. Именно поэтому в overlay-сетях постоянно идёт keepalive-трафик, и именно поэтому «соединение было, а через минуту стало через релей» — не аномалия, а нормальное поведение при смене сети или перезагрузке NAT.

NAT добавляет к stateful firewall одну деталь: он не только фильтрует, но и переписывает пакеты. Для задач traversal важна только Source NAT — подмена источника, когда множество устройств выходит в интернет через меньшее число адресов[^1]. При первом исходящем пакете создаётся mapping: внутренний `ip:port` становится внешним `ip:port`, и до тех пор, пока mapping жив, ответы приходят обратно.

## Терминология NAT: почему «cone» не работает

Классическая четвёрка «Full Cone / Restricted Cone / Port-Restricted Cone / Symmetric» пришла из ранних исследований и до сих пор гуляет по статьям. RFC 4787 отказывается от неё прямо: «this terminology has been the source of much confusion, as it has proven inadequate at describing real-life NAT behavior»[^3]. Вместо неё вводятся два независимых измерения.

Первое — поведение mapping. При Endpoint-Independent Mapping NAT переиспользует один и тот же внешний порт для пакетов от одного внутреннего адреса ко **любому** внешнему адресату: «The NAT reuses the port mapping for subsequent packets sent from the same internal IP address and port (X:x) to any external IP address and port»[^3]. При Address-Dependent и Address-and-Port-Dependent Mapping внешний порт зависит от адресата (и его порта). Второе измерение — фильтрация: какие входящие пакеты NAT пропускает к уже существующему mapping.

Почему это важнее, чем кажется: два измерения ортогональны, и «страшный» symmetric NAT — это всего лишь комбинация «mapping зависит от адресата» и «фильтрация зависит от адреса и порта». Практический пример из 2025 года: Tailscale спонсировала патч для FreeBSD PF, добавляющий Endpoint-Independent Mapping, но фильтрация там осталась address-dependent — то есть после патча роутер на pfSense стал вести себя как port-restricted cone, а не как полностью открытый NAT[^2]. Один и тот же термин «cone» описывает четыре разные ситуации с разными последствиями для traversal.

RFC 4787 формулирует и требования к «хорошему» NAT: REQ-1 — «A NAT MUST have an "Endpoint-Independent Mapping" behavior», иначе говоря — без EIM не обойтись и придётся использовать релей; REQ-9 — NAT MUST поддерживать hairpinning, то есть передачу трафика между двумя внутренними хостами через сам NAT[^3]. Оба требования выполняются далеко не везде, и именно их нарушение превращает сеть в «hard NAT».

Tailscale в своей документации упрощает таксономию до трёх состояний устройства: «Each device is in one of the following scenarios: no NAT, easy NAT, or hard NAT»[^6]. Hard NAT определён через два признака: каждое исходящее соединение получает собственный port mapping, принимающий ответы только от этого адресата, и внешний порт непредсказуем для внешнего наблюдателя[^11]. Такое определение описывает наблюдаемое поведение, а не RFC-классификацию, — и это удобно для диагностики, но создаёт ловушку при чтении обещаний вендора (о ней ниже).

## STUN: узнать, как тебя видят снаружи

Когда обе стороны за NAT, у задачи появляется неприятное свойство: внешнего `ip:port` ещё не существует, пока не отправлен исходящий пакет. Deadlock разрешается внешним наблюдателем. STUN — это ровно «что я с твоей точки зрения?»: клиент отправляет запрос, сервер отвечает тем адресом, с которого пришёл пакет[^1]. Этот адрес называется reflexive transport address и возвращается в атрибуте XOR-MAPPED-ADDRESS, где он обфусцирован XOR-ом с идентификатором транзакции, чтобы сломанные NAT/ALG не переписали адрес внутри payload[^4].

Важно понимать границы: STUN сам по себе ничего не пробивает. RFC 5389 говорит это явно — «STUN is not a NAT traversal solution by itself. Rather, it is a tool to be used in the context of a NAT traversal solution»[^4]. Это прямая реакция на провал предыдущей спецификации, где классификация типов NAT оказалась нерабочей.

В Tailscale роль STUN-серверов выполняют те же DERP-релеи: «The Tailscale client sends a STUN request to all the DERP relay servers, and the DERP relay servers note the public IP and port it received the request from»[^5]. Опрос нескольких серверов в разных точках сети — это не избыточность, а метод измерения: если разные DERP возвращают разные порты, значит mapping зависит от адресата, то есть перед нами hard NAT. В диагностике это вынесено в поле `MappingVariesByDestIP`, которое документация называет важнейшим для понимания, почему соединение не прямое[^6].

Есть и тонкость, которую легко упустить при реализации своего traversal: STUN нужно делать с того же сокета, который потом будет нести трафик. «Each socket gets a different mapping on the NAT device, so in order to discover your public ip:port, you have to send and receive STUN packets from the socket that you intend to use for communication, otherwise you'll get a useless answer»[^1]. Отсюда требование прямого доступа к сокету и, как следствие, невозможность «прикрутить traversal» к готовой сетевой библиотеке снаружи.

## Hole punching: алгоритм и где он ломается

Сам алгоритм UDP hole punching описан ещё в 2005 году и с тех пор не изменился. Формулировка авторов: координационный сервер сообщает каждому пиру публичный и приватный эндпоинты другого, после чего «A starts sending UDP packets to both of these endpoints, and subsequently "locks in" whichever endpoint first elicits a valid response from B»[^7]. Первый исходящий пакет создаёт состояние в NAT на стороне отправителя, пакет проходит через NAT получателя как «ответ» — и дырки открыты в обе стороны.

Условие успеха — консистентный mapping. Если NAT для каждого адресата выдаёт новый внешний порт, «the hole punching process fails to provide connectivity, because the subsequent incoming messages from B reach NAT A at the wrong port number»[^7]. Это и есть symmetric/hard NAT в действии: не злонамеренность, а побочный эффект экономии таблицы состояний.

Насколько часто это происходит? Измерение 2005 года на 380 точках (68 вендоров, 8 ОС) дало около 82% NAT, поддерживающих UDP hole punching, и 64% — TCP; hairpinning работал в 80 из 335 случаев для UDP и 37 из 286 для TCP[^7]. Выборка была добровольческой, и авторы это честно оговаривают.

Современное число появилось только в 2026 году. Крупнейшее измерение traversal «в дикой природе» — 4,4 млн попыток из 85 000+ сетей в 167 странах на живом протоколе DCUtR в IPFS. Результат: «We establish a conditional success rate of 70% ± 7.1% for the hole-punching stage, given that prerequisite relay reservation and public address discovery succeed»[^8]. Слово «conditional» здесь ключевое: 29% данных отброшено, потому что не прошли предварительные стадии, — то есть сквозная доля успеха ниже 70%.

Второе наблюдение того же измерения ломает интуицию: «97.6% of successful hole punches complete on the very first attempt, with only 2.4% requiring additional retries»[^8]. Hole punching — не итеративный перебор, а синхронизированный залп; если он не сработал, дело почти всегда в топологии, а не в нехватке попыток.

Третье — про транспорт. Распространённое убеждение, что UDP пробивается лучше TCP, эта кампания не подтвердила: «DCUtR's high-precision, RTT-based synchronization yields statistically indistinguishable success rates for both TCP and QUIC (∼70%)»[^9]. Разница между транспортами не в вероятности успеха, а в задержке установления. Моделирование на QUIC даёт 2–2.5 RTT против 2.5–3 RTT у TCP, а при RTT 200 мс — примерно 416 мс против 505 мс[^10]. То есть выбор транспорта влияет на время до первого байта, а не на то, пробьётся ли соединение вообще.

Отдельно стоит отметить ограничения этого измерения, потому что они определяют, насколько число 70% применимо к вашей сети. Авторы прямо называют смещение выборки: волонтёры технически грамотнее и работают в менее ограниченных сетях, а honeypot-архитектура видит только пиров, способных хотя бы на relayed-соединение, — оба фактора завышают результат[^9]. Классификации NAT по типам в работе нет вовсе: «our data cannot distinguish single-NAT from CGNAT peers»[^8].

## Birthday paradox: перебор, который иногда оправдан

Если один конец за hard NAT, а другой за easy, появляется лазейка: IP известен (это допущение подкреплено REQ-2 о пулинге адресов), неизвестен только порт. Пробовать все 65 535 портов — 10 минут при 100 пакетах в секунду, и это выглядит как port scan, чем, по сути, и является[^1].

Birthday paradox превращает это в практичную тактику. Вместо одного порта на «трудной» стороне открывается 256 сокетов, а «лёгкая» сторона шлёт пробы в случайные порты. Вероятности при 256 портах: 174 пробы — 50%, 256 — 64%, 1024 — 98%, 2048 — 99.9%; при 100 пробах в секунду половина случаев закрывается меньше чем за 2 секунды[^1].

С двумя hard NAT схема разваливается: теперь нужна коллизия не по порту назначения, а по паре `{порт источника, порт назначения}`, и поиск становится квадратичным. «After 20 seconds in the same regime as the previous setup (256 probes from one side, 2048 from the other), our chance of success is… 0.01%»[^1]. Чтобы дойти до 99.9%, каждой стороне нужно 170 000 проб — 28 минут при 100 пакетах в секунду[^1].

Есть и цена, которую редко считают: перебор расходует таблицу сессий NAT. «A Juniper SRX 300 maxes out at 64,000 active sessions. We'd consume its entire session table with our one attempt to get through!»[^1]. Для домашнего роутера это не проблема, для офисного шлюза с десятком машин за ним — вполне.

Практический вывод из этого раздела не «используйте birthday attack», а «не забывайте про порт-мэппинг». UPnP IGD, NAT-PMP и PCP при наличии отвечают на простой запрос «пробрось внешний порт на внутренний», и один работающий протокол фактически убирает один NAT из пути[^1]. Ломаются они на double NAT: запрос действует на ближайший NAT, а нужен самый дальний, и информации для «следующего NAT вверх» протоколы не дают[^1].

## Как выбирается путь

Алгоритм выбора на удивление прост и заимствован у ICE: «try everything at once, and pick the best thing that works»[^1]. Клиент собирает список кандидатов — IPv6, LAN-адреса, WAN-адреса из STUN, адреса из порт-мэппинга, статические пробросы — обменивается списками через координационный сервер и шлёт пробы во все сразу; пробы одновременно открывают firewall и служат health-check[^1].

Историческое различие с ICE в критерии выбора: ICE скорит кандидатов заранее (LAN > WAN > WAN+NAT), а Tailscale с версии 0.100.0 перешёл на измеренную round-trip latency, что даёт тот же порядок, но без предварительных догадок: «if multiple potential paths are found (IPv4 vs IPv6, or multiple interface addresses), Tailscale will race them and stick to the one with lowest latency»[^2]. Порядок категорий при этом обнаруживается органически, а не задаётся таблицей[^1].

Порядок действий в актуальной документации описан явно: «All connections start as relayed through a DERP server, and Tailscale then tries to upgrade them to a direct connection. If that fails, Tailscale tries to connect them using a peer relay. If that fails, the connection remains relayed through the DERP server»[^11]. То есть релей — не fallback после неудачи, а стартовая точка, из которой соединение апгрейдится. Это меняет чтение логов: запись `via DERP(ord) in 463ms` означает не «всё плохо навсегда», а «сейчас так, апгрейд идёт».

Для прямого соединения полезно держать открытым UDP-порт 41641: «By default, opening UDP port 41641 on a device's public IP address ensures a direct connection from any peer device, where possible»[^11]. Peer relay (с версии 1.86) занимает промежуточное положение между прямым соединением и DERP: он работает по UDP на заданном порту и обычно быстрее DERP, потому что не гонит трафик через географически удалённый сервер[^12].

## DERP: релей как протокол

DERP решает две задачи одновременно. Первая — собственно релей, когда traversal не удался. Вторая — side channel, через который пиры обмениваются адресами и ключами. Формулировка из блога: «DERP is both our fallback of last resort to get connectivity, and our helper to upgrade to a peer-to-peer connection, when that's possible»[^1]. Именно поэтому полностью отключить DERP нельзя, не сломав установление соединений.

Устройство протокола компактно и описано в комментарии пакета. Адресация — не по IP, а по публичным ключам: «DERP routes packets to clients using curve25519 keys as addresses»[^14]. Кадр — один байт типа плюс четырёхбайтовая длина; версия протокола 2; магическое число — «DERP🔑»; максимальный размер пакета — `64 << 10`, то есть 64 КиБ[^14]. Сердцебиение — раз в 60 секунд, и это минимум, ниже которого сервер не опускается: «KeepAlive is the minimum frequency at which the DERP server sends keep alive frames»[^14].

Логин выглядит так: клиент подключается, сервер присылает `FrameServerKey`, клиент — `FrameClientInfo`, сервер — `FrameServerInfo`. Дальше в установившемся режиме сервер изредка шлёт `FrameKeepAlive` или `FramePing`, клиент отвечает `FramePong`, а полезная нагрузка идёт кадрами `FrameSendPacket` и `FrameRecvPacket`; `FrameNotePreferred` сообщает серверу, выбран ли он домашним[^14]. Есть и служебные кадры: `FrameForwardPacket` — пересылка между узлами одного региона, `FrameWatchConns` — подписка на соединения соседей по mesh, `FrameRestarting` — команда переподключиться через заданный интервал[^14].

Про конфиденциальность важно быть точным, потому что здесь легко сказать лишнее. Полезная нагрузка — это уже зашифрованный WireGuard-трафик, и «it's impossible for a DERP server to decrypt your traffic. A DERP server blindly forwards already-encrypted traffic from one device to another»[^13]. Но служебные кадры `FrameClientInfo` и `FrameServerInfo` зашифрованы naclbox с ключом сервера — сервер их читает, иначе не смог бы узнать имя приложения и версию клиента[^14]. То есть релей не видит содержимого, но видит метаданные: кто с кем и когда.

Топология релеев — сеть регионов. Клиент выбирает домашний DERP по латентности и сообщает выбор координационному серверу; в большинстве регионов не менее трёх серверов, и при недоступности одного клиент переключается на другой в том же регионе, а при отказе региона — на следующий ближайший[^13]. Внутри региона узлы связаны mesh-соединениями и пересылают пакеты друг другу, но «Packets are forwarded only one hop within the region. There is no routing between regions»[^15]. Минимум три узла в регионе объясняется не кворумом, а нежеланием получить каскадный отказ: с двумя узлами отказ одного часто тянет за собой второй[^15].

Выбор домашнего узла по латентности, а не через anycast или балансировщик, — сознательное решение про стоимость: anycast потребовал бы маршрутизации между регионами на стороне сервера[^15]. За это приходится платить тем, что трафик может идти через полмира: в опубликованном кейсе пинг до удалённого пира через DERP составлял 463/441/478 мс на маршруте Дели — Миннеаполис[^25].

## Цена self-hosted координации

Свой DERP начинается с ограничений, которые стоит прочитать до, а не после развёртывания. Официально custom DERP-серверы находятся в alpha, требуют прямого доступа в интернет и не могут стоять за NAT или балансировщиком — иначе ломаются идентификация устройств по адресу источника и совместимость протокола[^17]. Порты фиксированы: HTTP 80 для captive portal checks, HTTPS 443 для релея, STUN 3478; кроме того, сервер должен пропускать ICMP в обе стороны[^17]. Идентификаторы регионов 900–999 зарезервированы под пользовательские, и «There can be only one DERP server per region. If you want DERP redundancy, use multiple regions with only one DERP server in each region»[^17].

Второе ограничение — доступ. Любой, кто знает адрес вашего релея, может добавить его в свою DERP map и гонять через него трафик; защита — флаг `--verify-clients`, при котором `derper` проверяет клиента через локально запущенный `tailscaled`[^17]. В Headscale аналог — `-verify-client-url`, указывающий на `/verify` координационного сервера, но с важной деталью: «By default, it will allow access if Headscale is unreachable»[^18]. То есть при падении Headscale релей открывается, а не закрывается, — для публичного сервера это стоит осознанно переопределить.

Встроенный DERP в Headscale — самый дешёвый по трудозатратам вариант: включается флагом, поднимает STUN на `udp/3478`, получает собственный `region_id` (по умолчанию 999) и приватный ключ, автоматически генерируемый при отсутствии[^19]. Он же автоматически добавляется в DERP map, если не отключить `automatically_add_embedded_derp_region`[^19]. Расплата описана в тех же документах прямо: при удалении стандартных DERP-серверов остаётся один, и это «a single point of failure and could hamper connectivity»[^18], а про производительность сказано без обиняков — «There are no speed or throughput optimisations, the main purpose is to assist in node connectivity»[^18].

Позиция мейнтейнеров ещё жёстче. В обсуждении 2023 года отмечалось, что для базовой связности одного встроенного DERP достаточно, но «you would introduce a single point of failure into your setup, so having more than one might be sensible»[^20]. В 2025 году на вопрос «встроенный DERP медленный?» ответ был прямой: «I've never speed tested the embedded DERP, nor have we done anything to ensure its fast. I would view it as purely for convenience»[^21] — с рекомендацией запускать отдельный бинарник `derper`.

Насколько это медленно на практике, видно по опубликованным замерам, и картина неприятная для тех, кто рассчитывает на «свой релей = полная скорость». Кейс Tailscale: iperf3 между Дели и Миннеаполисом через DERP дал 2.24 Мбит/с на отправителе и 2.20 Мбит/с на получателе, через peer relay на том же маршруте — 32.0 МБ за 120 секунд, то есть 27.7 и 27.5 Мбит/с, «a 12.5x improvement over DERP»[^25]. Причина названа прямо: DERP-серверы — общая инфраструктура, оптимизированная под доступность и покрытие, а не под пропускную способность отдельного соединения, и к ним применяются лимиты «to ensure fair access for everyone»[^25].

Пользовательские отчёты дают тот же порядок величин. В issue 2024 года custom DERP на VPS отдаёт около 50 Мбит/с по Tailscale-адресу при почти 1 Гбит/с по публичному, причём проблема воспроизводится у разных провайдеров и висит открытой больше года[^22]. В отчёте 2025 года на Windows-клиенте через self-hosted DERP — примерно 10 Мбит/с против 40 Мбит/с в WSL на той же машине, что указывает на реализацию клиента, а не на канал[^23]. Это не измерения в контролируемых условиях, а сообщения пользователей, но их согласованность с вендорским кейсом делает картину правдоподобной.

Механика лимитов видна в коде: у сервера есть конфигурация `PerClientRateLimitBytesPerSec` с явной оговоркой «A zero value disables all rate limiting», mesh-пиры освобождены от лимита, а таймаут записи в TCP по умолчанию — 2 секунды[^16]. То есть релей принципиально не пытается выжать максимум из соединения: медленный клиент отрезается, а не тормозит остальных. Конкретные значения лимитов, применяемые в облаке Tailscale, нигде не опубликованы.

Арифметика стоимости выходит неудобной. Если релей постоянно несёт 27.7 Мбит/с, это около 9 ТБ в месяц в одну сторону; при 50 Мбит/с — около 16 ТБ. Для домашнего сервера это мелочь, для облачного VPS с платным egress — статья расходов, которую обычно не считают, потому что «релей же только иногда». Документация Headscale предупреждает об этом качественно, рекомендуя не создавать дополнительную нагрузку на публичные DERP-серверы[^20], но конкретных цифр egress не приводит никто из рассмотренных источников.

Есть и ещё один риск, который редко упоминают в гайдах: «медленно» может означать не только лимит, но и TCP-over-TCP. DERP по умолчанию несёт трафик по TCP/443 — это его главное достоинство, потому что 443 открыт везде. Обратная сторона описана в открытом issue: вложенный TCP может страдать от head-of-line blocking, и «it looks like there might be some head-of-line blocking that could cause TCP meltdown, where the inner TCP spends all its time retransmitting»[^24]. Формулировка осторожная — это гипотеза, а не измеренный результат, и в документации Tailscale такого предупреждения нет.

## Диагностика: где именно вы стоите

Практическая ценность всей этой механики в том, что она превращается в короткий диагностический протокол. Первый шаг — посмотреть на фактический путь: `tailscale ping` печатает `pong from ... via DERP(ord) in 463ms` или `direct <адрес>:41641`, а `tailscale status` показывает тип соединения для каждого пира[^11][^25]. Второй шаг — понять, виноват ли NAT: поле `MappingVariesByDestIP` в `netcheck`-выводе показывает, различается ли внешний адрес между DERP-серверами, и это «the most important field to determine why a device isn't using direct connections»[^6].

Третий шаг — проверить порт-мэппинг. Если `PortMapping` ложно, устройство не может открыть внешний порт, и прямое соединение маловероятно; если хотя бы один из UPnP, NAT-PMP, PCP отвечает, соединение может стать прямым даже при `MappingVariesByDestIP: true`[^6]. Четвёртый — посмотреть карту релеев: `tailscale debug derp-map` и `tailscale debug derp headscale` для встроенного сервера[^18], `cmd/derpprobe` для мониторинга собственных DERP[^17]. Пятый — измерить, а не предполагать: iperf3 через релей и через прямое соединение, как это сделано в опубликованном кейсе[^25].

Полезно держать в голове матрицу «no NAT / easy / hard», потому что она объясняет, когда стараться бессмысленно: комбинация easy + hard и hard + hard в документации всегда даёт relayed[^6]. Это не значит, что birthday attack невозможен — он описан в блоге 2020 года как рабочий трюк, — но в текущей реализации Tailscale ставка на него по умолчанию не делается, и это осознанное решение о цене в виде расхода таблицы сессий.

## Дискуссионные вопросы и противоречия

**Один hard NAT: препятствие или тупик.** Блог 2020 года утверждает, что birthday attack делает один hard NAT «an annoying speedbump»[^1], а документация 2026 года говорит обратное: relayed-соединение используется, если «One device has a hard NAT configuration and the other has an easy NAT configuration»[^6]. Противоречия здесь нет, но есть расхождение обещаний: блог описывает теоретически достижимое, документация — поведение по умолчанию. Для эксплуатации верно второе, и путаница возникает, когда статью 2020 года читают как описание текущей реализации.

**«Почти всегда напрямую» против «70%».** Вендор заявляет: «Internal metrics have indicated success rates for direct NAT traversal well north of 90% in typical conditions»[^2]. Независимое измерение на IPFS/DCUtR даёт 70% ± 7.1% и оговаривает, что это условная вероятность[^8]. Расхождение объясняется тремя факторами: разные протоколы (magicsock с birthday attack и порт-мэппингом против DCUtR), разные популяции (клиенты Tailscale против волонтёров IPFS), разная база отсчёта (доля прямых соединений среди установленных против условной успешности hole punching). Ни одно из чисел не является «неправильным»; сравнивать их напрямую нельзя.

**UDP против TCP.** «Племенное знание» о превосходстве UDP для traversal опровергнуто измерением: успешность TCP и QUIC статистически неразличима при одинаковой синхронизации[^9]. Это, пожалуй, самый практически значимый результат последних лет: он снимает аргумент против QUIC- и TCP-подходов и переносит конкуренцию в область задержки установления[^10].

**Почему DERP медленный.** Три объяснения сосуществуют: общая инфраструктура с лимитами для справедливости[^25], лимиты в коде сервера[^16] и гипотеза TCP meltdown для вложенного TCP[^24]. Первые два подтверждены, третье — нет. При этом встроенный в Headscale DERP не имеет ни одного из вендорских лимитов, но всё равно медленный по свидетельству мейнтейнера[^21], — что указывает на четвёртую причину: отсутствие оптимизаций и разделение веб-сервера с координатором.

**Мелочь, но показательная.** Даже расшифровка аббревиатуры расходится: блог 2020 года называет DERP «Detoured Encrypted Routing Protocol»[^1], а актуальная документация — «Designated Encrypted Relay for Packets»[^13]. На механику это не влияет, но иллюстрирует, насколько осторожно стоит относиться к деталям в статьях о протоколах, включая эту.

## Недостаточность данных

Несколько вопросов остались без ответа, и их стоит зафиксировать явно. Нет публичной статистики Tailscale о доле relayed-соединений и объёме трафика через DERP — вендор приводит только долю успешных прямых соединений (>90%), из которой обратное не выводится[^2]. Нет опубликованных значений per-client rate limit для облачных DERP: конфигурация в коде существует, но числа не раскрыты[^16]. Нет независимого бенчмарка «встроенный DERP Headscale против отдельного derper» — мейнтейнер прямо говорит, что не измерял[^21], а пользовательские отчёты не воспроизводимы.

Самое существенное: крупнейшее измерение traversal не классифицирует типы NAT, поэтому доля symmetric NAT в 2026 году неизвестна[^8]. Цифры, которые обычно цитируют, — 11% EDM в 2011 году и 40% EDM среди CGNAT в 2016-м — взяты из чужих работ с малыми или нерепрезентативными выборками[^9]. Наконец, стоимость egress для self-hosted DERP нигде не сведена в модель: есть предупреждения о нагрузке[^20] и наши собственные арифметические оценки, но не измерения.

## Заключение

Механика overlay-сети объясняет почти всё, что кажется странным в её поведении. Прямое соединение — вероятностный процесс с синхронизированным залпом пакетов, а не настройка; релей — штатная стартовая точка, а не аварийный режим; выбор пути делается по измеренной латентности, а не по категории адреса. Именно поэтому «вчера работало напрямую, сегодня через релей» — не регрессия, а следствие того, что NAT на другом конце сменил mapping.

Практические рекомендации, вытекающие из источников. Сначала диагностика, потом инфраструктура: `tailscale ping`, `MappingVariesByDestIP`, `PortMapping` дают ответ за минуту, а установка второго DERP-сервера — нет[^6][^11]. Если оба конца за hard NAT, прямого соединения не будет по определению, и выбор идёт между DERP и peer relay — последний, по опубликованным замерам, даёт на порядок больше при том же маршруте[^12][^25]. Если нужен свой релей, то отдельный `derper`, а не встроенный в Headscale, минимум два региона вместо одного и `verify-clients` без fail-open по умолчанию[^17][^18][^21]. И считать трафик: релей, несущий десятки мегабит постоянно, — это десятки терабайт в месяц.

Что остаётся открытым для дальнейшего исследования: доля relayed-соединений в реальных tailnet'ах, поведение birthday attack в современных CGNAT с короткими таймаутами и проверяемые замеры встроенного DERP против отдельного `derper` на одинаковом железе. Все три вопроса требуют измерений, а не чтения документации.

## Quality Metrics

| Metric | Value |
|--------|-------|
| Sources found | 46 |
| Sources read | 25 |
| Sources cited | 25 |
| Academic sources | 6 |
| Official/documentation | 11 |
| Industry reports | 0 |
| News/journalism | 0 |
| Blog/forum | 8 |
| Citation coverage | 90% |
| Counter-arguments searched | Yes |
| Research rounds | 3 |
| Questions emerged | 7 |
| Questions resolved | 4 |
| Questions insufficient data | 3 |

[^1]: Anderson, David. "How NAT traversal works." Tailscale Blog, August 21, 2020. https://tailscale.com/blog/how-nat-traversal-works
[^2]: "How Tailscale is improving NAT traversal (part 1)." Tailscale Blog, October 15, 2025. https://tailscale.com/blog/nat-traversal-improvements-pt-1
[^3]: Audet, François, and Cullen Jennings. "Network Address Translation (NAT) Behavioral Requirements for Unicast UDP." RFC 4787 / BCP 127, IETF, January 2007. https://www.rfc-editor.org/rfc/rfc4787.html
[^4]: Rosenberg, Jonathan, et al. "Session Traversal Utilities for NAT (STUN)." RFC 5389, IETF, October 2008. https://www.rfc-editor.org/rfc/rfc5389.html
[^5]: "What is STUN? · Tailscale Docs." Tailscale, last validated August 6, 2025. https://tailscale.com/docs/reference/stun-protocol
[^6]: "Device connectivity · Tailscale Docs." Tailscale, last validated January 7, 2026. https://tailscale.com/docs/reference/device-connectivity
[^7]: Ford, Bryan, Pyda Srisuresh, and Dan Kegel. "Peer-to-Peer Communication Across Network Address Translators." USENIX Annual Technical Conference, 2005. https://bford.info/pub/net/p2pnat.pdf
[^8]: Trautwein, Dennis, et al. "Large-Scale Measurement of NAT Traversal for the Decentralized Web: A Case Study of DCUtR in IPFS." arXiv:2604.12484, April 14, 2026. https://arxiv.org/abs/2604.12484
[^9]: Trautwein, Dennis, et al. "Challenging Tribal Knowledge -- Large Scale Measurement Campaign on Decentralized NAT Traversal." arXiv:2510.27500, October 31, 2025. https://arxiv.org/abs/2510.27500
[^10]: Liang, Jinyu, et al. "Implementing NAT Hole Punching with QUIC." arXiv:2408.01791, August 3, 2024. https://arxiv.org/abs/2408.01791
[^11]: "Connection types · Tailscale Docs." Tailscale, last validated June 1, 2026. https://tailscale.com/docs/reference/connection-types
[^12]: "Tailscale Peer Relays · Tailscale Docs." Tailscale, last validated February 4, 2026. https://tailscale.com/docs/features/peer-relay
[^13]: "DERP servers · Tailscale Docs." Tailscale, last validated January 21, 2026. https://tailscale.com/docs/reference/derp-servers
[^14]: "derp/derp.go — package derp, protocol comments." tailscale/tailscale source, main branch, retrieved October 31, 2026. https://github.com/tailscale/tailscale/blob/main/derp/derp.go
[^15]: "derp/README.md — DERP protocol and regional topology." tailscale/tailscale source, main branch, retrieved October 31, 2026. https://github.com/tailscale/tailscale/blob/main/derp/README.md
[^16]: "derp/derpserver/derpserver.go — rate limiting and TCP write timeouts." tailscale/tailscale source, main branch, retrieved October 31, 2026. https://github.com/tailscale/tailscale/blob/main/derp/derpserver/derpserver.go
[^17]: "Custom DERP servers · Tailscale Docs." Tailscale, last validated October 7, 2026. https://tailscale.com/docs/reference/derp-servers/custom-derp-servers
[^18]: "DERP - Headscale." Headscale documentation, stable. Retrieved October 31, 2026. https://headscale.net/stable/ref/derp/
[^19]: "headscale/docs/ref/derp.md at main · juanfont/headscale." Headscale source and configuration reference, retrieved October 31, 2026. https://github.com/juanfont/headscale/blob/main/docs/ref/derp.md
[^20]: "What specific services does 'embedded DERP (and STUN) server' provide · Issue #1326." juanfont/headscale, GitHub, April 7, 2023. https://github.com/juanfont/headscale/issues/1326
[^21]: "[Bug] Headscale embedded Derper Server speed slow · Issue #2702." juanfont/headscale, GitHub, July 22, 2025. https://github.com/juanfont/headscale/issues/2702
[^22]: "DERP bandwidth limitation · Issue #13133." tailscale/tailscale, GitHub, August 14, 2024. https://github.com/tailscale/tailscale/issues/13133
[^23]: "[Windows] Extremely low upload throughput via DERP compared to WSL on same host (10Mbps vs 40Mbps) · Issue #18017." tailscale/tailscale, GitHub, November 21, 2025. https://github.com/tailscale/tailscale/issues/18017
[^24]: "FR: When tunneling over DERP (TCP), drop packets to manipulate the inner TCP congestion control · Issue #15522." tailscale/tailscale, GitHub, April 3, 2025. https://github.com/tailscale/tailscale/issues/15522
[^25]: Singh, Raj. "Using Tailscale's Peer Relays to fix a homelab connection from across the globe." Tailscale Blog, January 26, 2026. https://tailscale.com/blog/peer-relays-international-networks
