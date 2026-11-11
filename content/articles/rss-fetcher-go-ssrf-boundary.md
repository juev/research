---
title: "RSS-fetcher как граница доверия: SSRF, redirects и DNS rebinding в Go"
date: 2026-11-11T09:36:00+03:00
description: "Как связать проверку URL с реальным TCP-соединением, не обойти защиту через proxy и redirects и ограничить время, распаковку и вторичные загрузки RSS."
showToc: true
tocOpen: true
---

## Аннотация

Безопасный RSS-fetcher — не функция «проверить URL, затем вызвать `http.Get`». Это цепочка решений о полномочиях: какие адреса разрешены, кто выполняет DNS resolution, к какому IP открывается соединение, какие переходы допускаются и сколько ресурсов может потратить ответ. Проверка имени до запроса не закрывает DNS rebinding; проверка TCP peer не защищает от произвольной цели за доверенным proxy. В Go эти границы распределены между `net/url`, `net.Dialer`, `http.Transport` и `http.Client`.[^1][^8][^9][^10]

**Данные на 2026-11-11.** Допущение автономного обзора: один self-hosted агрегатор на Linux загружает произвольные публичные RSS/Atom feeds; его сеть содержит сервисы, которым нельзя доверять такие запросы. База анализа — **Go 1.27.4**, указанный официальным каталогом как stable, и исходники именно тега `go1.27.4`. Документация OWASP, IANA, AWS, curl и Miniflux рассматривается как прочитанный на эту дату снимок; Miniflux 2.2.18 — отдельный исторический пример, а не заявленная текущая версия. Это документальное исследование: fetcher не реализовывался, сетевые атаки, локальные fixtures и нагрузочные испытания **не запускались**.[^3][^20]

Вывод обзора: для публичных feeds нужен выделенный direct-egress контур с контролем фактического адреса соединения, явной redirect policy и ограничением распакованного тела. Приватные feeds и доверенный egress proxy следует оформлять как другие профили полномочий, а не исключения из общего запрета. Ни одна из рассмотренных библиотечных настроек сама по себе не доказывает безопасность установленного агрегатора.[^1][^2][^9][^21]

## Введение

RSS-сервер получает URL от пользователя, но обращается к нему **с собственными сетевыми возможностями**. OWASP API7 описывает SSRF как принуждение сервера к запросу по неожиданному адресу, в том числе несмотря на firewall или VPN. Само наличие аутентификации в агрегаторе не превращает произвольное направление запроса в доверенное. Даже если тело ответа не возвращается пользователю, blind SSRF остаётся отдельным классом поведения.[^2][^19]

**Цель** — определить проверяемый defensive fetch pipeline для Go: от разбора адреса до передачи ограниченного документа парсеру. В [обзоре Google Reader API](/articles/google-reader-api/) предметом была синхронизация состояния читателя; в [материале об Open WebUI](/articles/open-webui-web-search/) — получение поискового контекста; в [сравнении Meilisearch и Typesense](/articles/selfhosted-search-meilisearch-typesense/) — собственный индекс приложения. Здесь разбирается предшествующий им слой: кому процесс вообще вправе отправлять исходящие HTTP-запросы.

**Границы** — HTTP/HTTPS, DNS, IP policy, redirects, proxy и ресурсы. Ниже нет аудита конкретного RSS-продукта, универсальной таблицы «все опасные CIDR», готовой security-библиотеки или утверждения об отсутствии обходов. Инженерные рекомендации отделены от поведения Go; предлагаемые бюджеты и сценарии приёмки не являются полученными измерениями.

## 1. Модель угроз: пользователь выбирает ресурс, не полномочия

Угроза не ограничивается чтением локального HTTP endpoint. OWASP перечисляет разведку внутренних сервисов, раскрытие информации, обход сетевых ограничений, отказ в обслуживании и использование сервера как proxy. PortSwigger объясняет, почему локальный источник запроса особенно опасен: backend может доверять соединениям от самого сервера или соседнего сегмента сильнее, чем внешним клиентам.[^2][^19]

Для небольшого homelab я предлагаю разделить три профиля: **public fetcher** без доступа к внутренним сетям; **private-feed connector** с административно заданными destinations и credentials; **proxy-egress fetcher**, чья destination policy обеспечивается также на стороне proxy. Это проектное решение на основе рекомендованной OWASP сетевой изоляции. Оно позволяет не расширять полномочия всех недоверенных подписок ради одной внутренней ленты.[^1][^2]

Это не абстрактная несовместимость безопасности и RSS. В release notes **Miniflux 2.2.18** одновременно перечислены запрет private networks по умолчанию, исправление TOCTOU/DNS rebinding, применение защиты к redirect targets и обработка shared address space. Для локальных feeds релиз требует явно включать `FETCHER_ALLOW_PRIVATE_NETWORKS=1`. История демонстрирует набор независимых границ, а не доказывает защищённость всех последующих версий и конфигураций Miniflux.[^20]

## 2. URL: синтаксически допустимый не значит разрешённый

В Go 1.27.4 `url.Parse` может вернуть относительную ссылку, а `URL.IsAbs()` проверяет только наличие непустой схемы. `Hostname()` отделяет порт и снимает IPv6 brackets; `Port()` возвращает портовую часть, но не определяет бизнес-политику. Следовательно, успех парсинга — лишь начало валидации, а не разрешение сетевого действия.[^4]

Для public-профиля предлагается принимать только иерархические URL с `http` или `https`, непустым hostname и пустым `Opaque`; запрещать userinfo, управляющие символы, неоднозначные authority и IPv6 zone identifiers. Стандартные назначения — HTTP на 80 и HTTPS на 443; нестандартный порт становится отдельной административной возможностью. Это **выбранная политика**, а не требование RSS или default Go: OWASP рекомендует ограничивать схемы и порты, но конкретный набор определяет приложение.[^1][^2][^4][^5]

Нормализовать адрес нужно минимально и последовательно. Не стоит многократно URL-decode строку, искать запрещённую подстроку регулярным выражением или считать, что браузер, frontend и сервер всегда одинаково понимают входные байты. Документация curl отдельно предупреждает о расхождении RFC-style и WHATWG parsing; её рекомендации относятся к curl, а не устанавливают поведение Go. Для Go-пайплайна практический вывод — проверять тот разобранный destination, из которого строится реальный запрос, и не передавать его затем другому неконтролируемому парсеру.[^1][^4][^17]

Особенно важен отказ от userinfo: Go 1.27.4 может построить Basic `Authorization` из имени и пароля в URL, если соответствующий заголовок ещё не задан. Поэтому запрет credentials в публичном адресе — не косметика для логов. Для действительно приватной подписки credential следует привязать к доверенному origin отдельным механизмом, не перенося такую возможность на общий public-fetcher.[^10]

## 3. IP policy: почему IsPrivate и IsGlobalUnicast недостаточно

В исходнике `net/netip` Go 1.27.4 есть предупреждение, которое полезнее многих примеров SSRF-фильтра:

> “IsPrivate does not describe a security property of addresses, and should not be used for access control.”[^5]

`IsPrivate()` охватывает IPv4 private-use по RFC 1918 и IPv6 ULA, но не всю область, которую нужно запретить fetcher. `IsGlobalUnicast()` тоже не означает «можно безопасно загрузить из интернета»: его документация прямо включает private IPv4 и IPv6 ULA. Объединение двух predicates не становится автоматически полной destination policy.[^5]

Реестры IANA показывают причину. Помимо private-use есть loopback, link-local, shared address space, documentation, benchmarking и другие special-purpose allocations. Например, **`100.64.0.0/10` — Shared Address Space**, а не RFC 1918; Miniflux 2.2.18 отдельно называет его non-public. Для overlay-сети такой диапазон может оказаться особенно значимым, но даже без overlay он не должен исчезать между классификацией IP и политикой сервиса.[^6][^20]

Для IPv6 нужен симметричный анализ, а не дополнительная проверка `::1`. IANA отдельно регистрирует ULA, link-local, documentation, IPv4-mapped и translation prefixes. Перед сопоставлением IPv4 CIDR следует приводить mapped-адрес через `Addr.Unmap()`; zone identifier в предлагаемом public-профиле отклоняется. При этом `Unmap()` убирает именно IPv4-mapped prefix: он не является универсальным декодером всех механизмов IPv4-over-IPv6.[^5][^7]

Мой консервативный профиль — отклонять invalid, unspecified, loopback, multicast, link-local, private-use, shared, документационные и прочие неподходящие special-purpose адреса; дополнительно запрещать собственные service ranges и административные destinations. Неоднозначные или неизвестные special-purpose записи не должны молча превращаться в разрешённые. Категории и исключения лучше хранить как версионируемые данные с тестами, опираясь на оба реестра IANA, а не выдавать короткий список CIDR за окончательное решение.[^1][^6][^7]

Есть важное ограничение: поле IANA `Globally Reachable` описывает возможность forwarding за административный домен, **не безопасность HTTP endpoint**. Реестр предупреждает, что перечисленные prefixes не гарантируют routability в конкретной сети. Даже публичный IP может быть адресом собственного административного сервиса; его придётся запрещать локальной политикой. Напротив, блокировка всех специальных IPv6 prefixes может сознательно отрезать полезные translation paths. Это плата за выбранную область поддержки, а не дефект реестра.[^6][^7]

## 4. DNS rebinding: проверять нужно адрес использования

Сломанная последовательность выглядит так: приложение разрешает `feeds.example.org`, проверяет полученный IP, затем отдаёт исходное имя обычному HTTP-клиенту. Клиент выполняет ещё одно разрешение, и destination может измениться. OWASP прямо предупреждает, что второй unchecked DNS lookup между validation и connection обходит проверку; Doyensec описывает тот же разрыв как TOCTOU.[^1][^16]

> “A second, unchecked DNS lookup between validation and connection can bypass these checks; see GitLab's URL blocker guidance.”[^1]

Для рассматриваемого профиля я выбираю **resolve → validate entire returned set → dial a literal IP from that set**. Проверяются все полученные кандидаты A/AAAA, пустой результат и ошибка разрешения считаются отказом. Если хотя бы один кандидат запрещён, отклоняется вся операция. Это более строгая политика, чем «выбрать любой разрешённый IP»: она упрощает расследование смешанных ответов, но может уменьшать доступность. Утверждать, что resolver получил все теоретически существующие записи зоны, нельзя; инвариант относится к набору, который реально возвращён для этой попытки.[^1][^8]

Критично, чтобы retries и fallback использовали **только проверенные IP**, а не снова имя. В Go 1.27.4 `net.Dialer.DialContext` сам выполняет resolution и может организовывать параллельные попытки для семейств адресов. Если приложение реализует собственный выбор кандидатов, оно также принимает ответственность за timeout и fallback: последовательная реализация не получает поведение Happy Eyeballs автоматически.[^8]

Существует другой полезный механизм — `net.Dialer.Control` или `ControlContext`. В Go 1.27.4 hook вызывается после создания socket, но **до фактического dialing**; `ControlContext` имеет приоритет над `Control`. Doyensec использует этот уровень для проверки адреса выбранной попытки. Это не post-connect подтверждение `RemoteAddr` и не синоним предварительной проверки всего DNS-набора: hook может надёжно запрещать конкретный dial, не реализуя выбранную выше политику «смешанный ответ запрещён целиком».[^8][^16]

Проверка `RemoteAddr()` после успешного connect пригодна как диагностическая сверка, но слишком поздняя как единственный барьер: сетевое соединение уже произошло. Поэтому защищаемый инвариант формулируется **до подключения**: каждый адрес каждой разрешённой попытки принадлежит допустимому набору. При custom dialer, HTTP transport или proxy этот инвариант нужно заново проследить по реальному пути, а не предполагать по имени функции.[^1][^8][^9]

## 5. Transport: сохранить hostname, не сохранить обход

При dialing к IP нельзя просто заменить hostname в URL на числовой адрес и отключить TLS verification «чтобы работало». HTTP authority должен остаться исходным, а TLS — проверять исходное имя. Go 1.27.4 `Transport` заполняет пустой `TLSClientConfig.ServerName` именем destination; `crypto/tls` использует `ServerName` для проверки hostname и SNI, если это не IP literal. Поэтому IP pinning лучше реализовать на dial-слое, не меняя логическую идентичность ресурса.[^9][^11]

> “ServerName is used to verify the hostname on the returned certificates unless InsecureSkipVerify is given.”[^11]

Нужен выделенный transport с понятным набором hooks. В Go 1.27.4 custom `DialTLSContext` для direct HTTPS обходит обычные `Dial`/`DialContext`; при нём также игнорируются `TLSClientConfig` и `TLSHandshakeTimeout` самого transport. Проверить только один hook и объявить защищёнными оба URL schemes нельзя. Следует либо не задавать альтернативный TLS dialer, либо включать его в тот же проверяемый контракт.[^9]

Connection reuse меняет момент проверки. `Transport` кэширует соединения, а документация `DialContext` допускает, что запрос воспользуется ранее открытым соединением вместо только что начатого dial. Следовательно, корректное утверждение — «каждое **новое соединение** открыто по политике», а не «каждый HTTP-запрос заново проверил DNS». Новый запрещённый DNS-ответ сам по себе не перенаправляет существующий TCP socket, но ужесточение политики не отзывает уже выданное соединение автоматически.[^9]

Практический вывод — не делить transport между public и private профилями, а смену security policy сопровождать управлением жизненным циклом clients и соединений. `CloseIdleConnections()` закрывает idle connections, не отменяя активные запросы. Для строгого отзыва полномочий нужно отдельно прекращать активные jobs и не отдавать новым jobs старый transport. Это рекомендация управления полномочиями, не требование отключать keep-alive у каждого feed.[^9][^10]

## 6. Redirect — новый запрос с новым решением

OWASP рекомендует отключать redirects как простой способ не обходить input validation. Go 1.27.4 по умолчанию следует переходам; default policy ограничивает цепочку, но не проверяет, разрешён ли следующий destination. Наличие ограничения числа переходов не является SSRF-фильтром.[^1][^2][^10]

Для RSS возможны два честных режима. Строгий возвращает `http.ErrUseLastResponse` из `CheckRedirect`, после чего приложение получает последний ответ без автоматического продолжения и обязано закрыть его body. Совместимый разрешает переходы, но проверяет каждый upcoming request: scheme, authority, порт, downgrade, credentials и бюджет hops; для каждого нового соединения применяется тот же guarded dialer. Конкретный небольшой hop budget выбирается приложением, а не выдаётся за границу безопасности Go.[^4][^9][^10]

Относительный `Location` тоже требует проверки **после** разрешения относительно предыдущего URL. В `net/url` для этого существует `ResolveReference`; результат может изменить authority или scheme. Проверить буквальную строку `Location` на отсутствие private IP недостаточно: имя следующего адреса может разрешиться во внутреннюю сеть, а переход может использовать уже существующее соединение. Проверка URL и управление transport дополняют друг друга.[^4][^9][^10]

Credential policy должна быть строже браузерной удобности. Go 1.27.4 при redirects сохраняет некоторые sensitive headers для того же домена и subdomain match; это не равенство origin по scheme/host/port. Кроме того, автоматически вычисляемый `Referer` может содержать path и query предыдущего URL. Для public-fetcher разумно вообще не наследовать входящие `Authorization`, `Cookie` и пользовательские headers, а `Referer` удалять в redirect hook. Для private feeds credentials должны повторно допускаться только к явно разрешённому origin.[^10]

## 7. Proxy: проверенный peer ещё не проверенная цель

В Go 1.27.4 `DefaultTransport` использует `ProxyFromEnvironment`: учитываются `HTTP_PROXY`, `HTTPS_PROXY` и `NO_PROXY`, включая lowercase variants. У `Transport.Proxy == nil` другой смысл — proxy не используется. Поэтому создание transport и клонирование default transport могут давать разную egress policy, даже если в коде fetcher переменная proxy не встречается.[^9]

Это меняет смысл dial-time защиты. При HTTP proxy TCP-соединение устанавливается с proxy; конечный hostname может разрешать уже он. Если hook разрешил IP proxy, он ещё не подтвердил адрес ресурса за ним. Запретить внутренние адреса только в локальном dialer и одновременно разрешить произвольные proxy destinations — значит оставить другую сторону границы без проверки.[^9][^17]

Для direct-профиля предлагается **явно `Proxy: nil`** и отсутствие пользовательского выбора proxy. Для proxy-профиля следует административно закрепить сам proxy, его credentials и destination policy на его стороне; запретить прямой fallback, если этого требует модель доверия. Такой proxy может находиться на частном IP, но исключение должно разрешать **конкретный egress service**, а не любые private destinations. Изоляция маршрутов остаётся вторым барьером, рекомендованным OWASP.[^1][^2][^9]

В прочитанном снимке конфигурации Miniflux есть отдельный `FETCHER_ALLOW_PRIVATE_FEED_PROXY`: документ предупреждает, что он применяется ко всем authenticated users и требует доверия к private proxy boundary. Это особенно полезное различие с `FETCHER_ALLOW_PRIVATE_NETWORKS`. Здесь фиксируется содержание документации на дату обзора, **не** поведение произвольно выбранного бинарника Miniflux.[^21]

## 8. Ограничивать нужно время и результат распаковки

SSRF policy отвечает «куда», но не отвечает «сколько». У Go 1.27.4 `Client.Timeout` включает connection time, redirects и чтение response body; ноль означает отсутствие timeout. `ResponseHeaderTimeout` у transport ограничивает ожидание headers после отправки запроса, но не чтение тела. Context исходящего request управляет сетевым жизненным циклом, включая body; он не превращает произвольный CPU-bound parser в автоматически отменяемую работу.[^9][^10][^12]

Поэтому предлагается несколько разных бюджетов: общий job deadline; DNS/dial/TLS/header timeouts; максимум redirects; header bytes; encoded и decoded body bytes; число документов и вторичных загрузок; общий и per-origin parallelism. Это не набор найденных оптимальных чисел. Например, лимит feed body следует выбирать по реально поддерживаемым лентам, а не объявлять единственно безопасным размером. `MaxConnsPerHost` ограничивает соединения к одному host, но не заменяет общий лимит jobs по множеству origins.[^9][^10][^17]

Важная деталь Go 1.27.4: когда transport **сам** запросил gzip, он прозрачно декодирует ответ в `Response.Body`; при явно заданном `Accept-Encoding: gzip` автоматической распаковки нет. Следовательно, `Content-Length` и число байтов, прочитанное из body, могут относиться к разным представлениям. Принятая архитектура должна однозначно устанавливать, кто декодирует ответ и где измеряется результат.[^9]

Для простого варианта можно оставить штатное automatic gzip и ограничивать читаемый `Response.Body` как decoded stream. Для раздельного контроля обоих размеров — отключить automatic compression, самостоятельно принять только поддерживаемый `Content-Encoding` и поставить ограничения до и после декодера. Неизвестные encodings отклоняются. У `gzip.Reader` Go 1.27.4 по умолчанию включён multistream: несколько gzip members считаются одной последовательностью данных. Decoded budget поэтому должен быть общим на документ, а не обнуляться на очередном member.[^9][^14]

`io.LimitReader(r, N)` не сообщает «данных оказалось больше»: он возвращает EOF после N байтов. Поэтому при разрешённом максимуме N нужно прочитать **не более N+1**, проверить ошибку и отклонить результат, если его длина больше N. `io.ReadAll` считает EOF нормальным завершением. Частично прочитанный либо обрезанный документ нельзя объявлять успешно загруженным только потому, что parser сумел извлечь несколько entries.[^13]

Ограничение decoded bytes сдерживает объём передаваемых парсеру данных, но не задаёт точный cap heap и CPU. Для декодирования, структуры XML/HTML, charset conversion и объектов приложения остаются отдельные расходы; в обзоре они не измерены. OWASP XXE guidance требует учитывать внешние entities, DTD, XInclude и другие механизмы загрузки ресурсов **в зависимости от конкретного parser**. Из этой рекомендации нельзя вывести, что штатный Go `encoding/xml` обязательно выполняет сетевые запросы.[^18]

## 9. Вторичные загрузки и операционный контракт

Политика бессмысленна, если ею пользуется только первичная RSS-загрузка. Feed discovery, full-text extraction, favicon, изображения, attachments и внешние parser resources следует инвентаризировать как возможных производителей новых URL. Это предложенная карта аудита, не утверждение о наличии всех путей в каждом продукте. Основание — описанные OWASP и PortSwigger SSRF через вложенные форматы и дополнительные fetch paths.[^1][^18][^19]

Предлагаемый pipeline выражается следующим контрактом. Стрелки показывают порядок допуска, а не готовую реализацию:

```text
Недоверенный URL
  → один parser и URL policy
  → public/private/proxy профиль, выбранный не самим URL
  → общий job deadline и допуск нагрузки
  → разрешённый destination каждого redirect
  → guarded direct dial ИЛИ административно доверенный egress proxy
  → TLS identity исходного hostname
  → status/media-type policy
  → bounded decoding и bounded decoded document
  → parser без неучтённых внешних fetch paths
  → сохранение результата или явная ошибка
```

Чтобы этот проект можно было принять, предлагается следующая **ещё не выполненная** матрица локальных проверок. Fixtures должны использовать управляемый resolver, fake dial sink и локальные HTTP-серверы: обращаться к настоящим административным адресам, metadata service или чужим узлам не требуется.

- **Parsing/IP:** отклоняются opaque URL, userinfo, zone identifier и запрещённые special-purpose classes; IPv4-mapped форма получает то же решение, что исходный IPv4.
- **DNS:** разрешённый кандидат плюс запрещённый дают отказ до dial; каждый fallback принадлежит проверенному snapshot; повторного unchecked lookup нет.
- **Redirect:** относительный и абсолютный targets проходят одинаковую policy; переход во внутреннюю сеть не достигает sink; цепочка исчерпывает общий deadline и hop budget.
- **TLS/hooks:** hostname identity сохраняется при IP dialing; альтернативный HTTPS dialer не обходит policy; неверный сертификат не принимается.
- **Proxy:** отдельный subprocess с proxy environment не меняет direct-профиль; публичный proxy, способный разрешить внутреннюю цель, не считается автоматически безопасным.
- **Body:** oversized и slow responses завершаются ошибкой; gzip members делят общий decoded budget; N байтов принимаются, N+1 отклоняются; ошибка чтения не превращается в успешный импорт.
- **Полнота:** тот же контракт применён к discovery и full text; private credentials не переходят между профилями, origins и пользователями.

Для эксплуатации я также рекомендую учитывать отказ по policy отдельно от DNS, TLS, timeout и body-limit ошибок; логировать policy revision и категорию destination, но не полные секретные query strings и credentials. У curl security guidance есть прямое предупреждение, что URL, cookies и filenames в логах могут раскрывать чувствительные данные. Конкретный формат журналов и метрик здесь — рекомендация автора, не существующий стандарт RSS.[^17]

## Дискуссионные вопросы и противоречия

**Отключить redirects или сохранить совместимость?** OWASP предлагает отключение как более простую защиту; Go предоставляет `CheckRedirect`, позволяющий продолжать цепочку с контролем. Противоречие не в семантике HTTP, а в стоимости доказательства: автоматическое следование требует правильной URL-, credential- и connection-policy на каждом шаге. Если такой приёмки нет, ограниченный режим честнее обещания «поддерживаем любые feeds безопасно».[^1][^2][^10]

**Проверять весь DNS-набор или только выбранный IP?** Guard на конкретном dial, показанный Doyensec, защищает адрес данной попытки; предварительное отклонение смешанного набора — дополнительная выбранная строгость. Эти модели не следует выдавать за одно и то же. Строгий режим проще объяснить администратору, но без собственного эксперимента нельзя оценить, сколько реальных feeds он отрежет; проверка каждого фактически используемого IP остаётся обязательной для обеих моделей.[^1][^8][^16]

**Denylist или allowlist?** Для неизвестного множества публичных feeds OWASP отдельно рассматривает block-list approach; для известных интеграций рекомендует allowlist. Это разные задачи. Выбранные в статье public и private профили позволяют не маскировать проблему одним глобальным переключателем. Реестры IANA помогают поддерживать IP-классификацию, но не предоставляют готовую security policy конкретного homelab.[^1][^6][^7][^20]

**Достаточно ли закрыть cloud metadata через IMDSv2?** AWS документирует создание token через `PUT` и передачу token в следующих запросах. Это полезный дополнительный барьер, особенно для строго ограниченного GET-fetcher, но не разрешение обращаться ко всем внутренним HTTP services. IMDSv2 защищает конкретный интерфейс; egress policy должна независимо ограничивать destination и методы. В этой работе запросы к metadata service не выполнялись.[^2][^15]

## Недостаточность данных

Не установлены фактическая полнота outbound paths какого-либо агрегатора, устойчивость реализации к гонкам, поведение resolver в конкретном deployment, доступность feeds при строгом отклонении смешанного DNS-набора и overhead предложенных ограничений. Не проводились fuzzing, тесты HTTP/2, NAT64/DNS64, custom proxy или перепривязки маршрутов. Рассмотренные документы описывают механизмы, но не дают измерения безопасности и совместимости готового профиля.

Отдельный пробел — полный актуальный набор запрещаемых destinations для сети читателя. IANA задаёт внешнюю классификацию; локальные маршруты, административные публичные адреса, translation gateways и private-feed exceptions из неё не выводятся. Поэтому таблица адресов без deployment-specific review была бы ложной полнотой.[^6][^7]

## Заключение

Основная единица доверия — **разрешённый сетевой путь**, не URL-строка. Для direct-fetcher проверка должна доходить до IP каждой попытки соединения без второго unchecked DNS lookup; исходный hostname сохраняется для HTTP/TLS identity. Redirects, альтернативные dial hooks и connection reuse входят в тот же контракт. Для proxy-профиля конечную destination policy нельзя доказать одной проверкой локального peer.[^1][^8][^9][^11]

Практический порядок внедрения: сначала инвентаризировать все fetch paths и разделить public/private/proxy полномочия; затем связать URL policy с dialing и redirects; после этого ограничить время, decoded bytes, parser и очередь; наконец выполнить локальную матрицу и проверку сетевой изоляции. Это программа приёмки, **не выполненный аудит**. Удалённый сервер должен оставаться недоверенным даже после успешного TLS и разрешённого IP: он всё ещё определяет содержимое, размер и темп ответа.[^2][^9][^10][^17][^18]

## Quality Metrics

| Metric | Value |
|--------|-------|
| Sources found | 63 |
| Sources read | 21 |
| Sources cited | 21 |
| Academic sources | 0 |
| Official/documentation | 19 |
| Vendor educational material | 1 |
| Blog/forum | 1 |
| Count units | Found: дедуплицированные candidate URLs; read/cited: отдельные документы и source files; альтернативные представления одного документа объединены |
| Access scope | Прочитаны релевантные разделы; загрузка source file не означает построчное чтение всего файла |
| Citation coverage | 86% (51/59 substantive paragraphs) |
| Counter-arguments searched | Yes |
| Research rounds | 3 |
| Main-text words, excluding code and bibliography | 3252 |
| Own runtime/security tests | Не проводились; матрица приёмки — предложение |
| Independence limitation | Несколько Go source files описывают одну реализацию и не являются независимыми подтверждениями её безопасности |
| Remaining gaps | Совместимость, накладные расходы, реальный deployment и полнота outbound paths не проверены |

[^1]: OWASP. "Server-Side Request Forgery Prevention Cheat Sheet." Снимок документации, прочитан 2026-11-11. https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
[^2]: OWASP. "API7:2023 Server Side Request Forgery." API Security Top 10, 2023; прочитан 2026-11-11. https://owasp.org/API-Security/editions/2023/en/0xa7-server-side-request-forgery/
[^3]: The Go Authors. "All releases." Каталог загрузок, прочитан 2026-11-11. https://go.dev/dl/
[^4]: The Go Authors. "src/net/url/url.go." Go 1.27.4, Parse, IsAbs, Hostname, Port, ResolveReference. https://raw.githubusercontent.com/golang/go/go1.27.4/src/net/url/url.go
[^5]: The Go Authors. "src/net/netip/netip.go." Go 1.27.4, IsPrivate, IsGlobalUnicast, Unmap, Zone. https://raw.githubusercontent.com/golang/go/go1.27.4/src/net/netip/netip.go
[^6]: IANA. "IPv4 Special-Purpose Address Space." Реестр, Last Updated 2025-10-09; прочитан 2026-11-11. https://www.iana.org/assignments/iana-ipv4-special-registry/iana-ipv4-special-registry.xhtml
[^7]: IANA. "IPv6 Special-Purpose Address Space." Реестр, Last Updated 2025-10-09; прочитан 2026-11-11. https://www.iana.org/assignments/iana-ipv6-special-registry/iana-ipv6-special-registry.xhtml
[^8]: The Go Authors. "src/net/dial.go." Go 1.27.4, DialContext, Control, ControlContext, dialParallel. https://raw.githubusercontent.com/golang/go/go1.27.4/src/net/dial.go
[^9]: The Go Authors. "src/net/http/transport.go." Go 1.27.4, DefaultTransport, dial hooks, proxy, TLS, compression и limits. https://raw.githubusercontent.com/golang/go/go1.27.4/src/net/http/transport.go
[^10]: The Go Authors. "src/net/http/client.go." Go 1.27.4, Client.Timeout, CheckRedirect, credential forwarding, refererForURL. https://raw.githubusercontent.com/golang/go/go1.27.4/src/net/http/client.go
[^11]: The Go Authors. "src/crypto/tls/common.go." Go 1.27.4, Config.ServerName и InsecureSkipVerify. https://raw.githubusercontent.com/golang/go/go1.27.4/src/crypto/tls/common.go
[^12]: The Go Authors. "src/net/http/request.go." Go 1.27.4, context lifecycle исходящего Request. https://raw.githubusercontent.com/golang/go/go1.27.4/src/net/http/request.go
[^13]: The Go Authors. "src/io/io.go." Go 1.27.4, LimitReader, LimitedReader и ReadAll. https://raw.githubusercontent.com/golang/go/go1.27.4/src/io/io.go
[^14]: The Go Authors. "src/compress/gzip/gunzip.go." Go 1.27.4, Reader и Multistream. https://raw.githubusercontent.com/golang/go/go1.27.4/src/compress/gzip/gunzip.go
[^15]: AWS. "Use the Instance Metadata Service to access instance metadata." EC2 User Guide, прочитан 2026-11-11. https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html
[^16]: Alessandro Cotto, Viktor Chuchurski. "safeurl for Go." Doyensec Blog, 2022-12-13. Историческое описание механизма, не аудит текущей библиотеки. https://blog.doyensec.com/2022/12/13/safeurl.html
[^17]: curl project. "libcurl security considerations." Прочитан 2026-11-11; используется для общих рисков, не как спецификация Go. https://curl.se/libcurl/security.html
[^18]: OWASP. "XML External Entity Prevention Cheat Sheet." Общие рекомендации по parser security, прочитан 2026-11-11. https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html
[^19]: PortSwigger. "Server-side request forgery (SSRF)." Web Security Academy, прочитан 2026-11-11. https://portswigger.net/web-security/ssrf
[^20]: Miniflux. "Miniflux 2.2.18." Версионные release notes, прочитаны 2026-11-11; дата публикации в доступном извлечении не указана. https://miniflux.app/releases/2.2.18.html
[^21]: Miniflux. "Configuration Parameters." Обновляемая документация, снимок прочитан 2026-11-11. https://miniflux.app/docs/configuration.html
