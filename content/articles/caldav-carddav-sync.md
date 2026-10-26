---
title: "CalDAV и CardDAV: как на самом деле работает синхронизация календарей, задач и контактов"
date: 2026-10-26T09:36:00+03:00
description: "Разбор CalDAV и CardDAV на уровне HTTP: sync-token и ctag, ETag и If-Match, Schedule-Tag, цена retention и почему клиенты по-разному теряют правки."
showToc: true
tocOpen: true
---

## Аннотация

CalDAV и CardDAV — это не «API календаря и адресной книги», а WebDAV-коллекции с двумя расширениями: набором REPORT-запросов и жёсткими правилами записи целых iCalendar- и vCard-объектов[^1][^2]. Разбор собран по первичным источникам: спецификациям IETF (RFC 4791, 6352, 6578, 6638, 6764, 5545), исходникам Radicale, sabre/dav и Nextcloud, коду клиентов Thunderbird и evolution-data-server, отчётам CalConnect о тестировании интероперабельности и трекерам ошибок. Данные на 2026-10-26; версии реализаций указаны там, где они важны для вывода.

Главный вывод: протокол синхронизирует файлы, а не поля. Единица обмена — целый iCalendar-объект, в котором лежит компонент и все его переопределения, поэтому правка одного экземпляра повторяющейся встречи перезаписывает файл целиком[^3]. Поверх этого работают два независимых механизма обнаружения изменений: устаревшее расширение Apple `getctag` и стандартизованный `sync-collection` из RFC 6578, причём серверы реализуют их по-разному — от целочисленного счётчика в sabre/dav до sha256-хеша истории в Radicale[^4][^5][^34]. Разрешение конфликтов протокол не определяет вовсе: он даёт лишь предустановки HTTP (`If-Match`, `If-None-Match`) и коды `412`/`409`, а решение «чья правка победила» принимает клиент. Отсюда и расхождения: DAVx⁵ документирует «побеждает сервер», Thunderbird считает конфликтом и `409`, и `412`, Evolution вынужден угадывать формат токена, а один ресурс без ETag способен остановить синхронизацию всей коллекции[^7][^8][^9].

## Введение

**Актуальность.** CalDAV остаётся единственным способом подключить self-hosted календарь к нативным клиентам — от «Календаря» на iOS до Thunderbird и DAVx⁵ на Android. При этом стек активно меняется: sabre/dav выпустил 4.7.1 в июле 2026-го, Radicale дошёл до 3.9.0, а Nextcloud продолжает переносить на свой бэкенд семантику sabre[^4][^28][^10]. Каждая из этих реализаций по-своему отвечает на вопросы, которые спецификация оставляет открытыми: как выглядит sync-token, сколько истории хранить, что делать с ресурсом без ETag и считать ли отсутствие `If-Match` конфликтом.

**Цель** — разобрать протокол на уровне конкретных HTTP-запросов и заголовков и показать, откуда берутся расхождения клиентов при офлайн-правках, дубликаты после импорта и «залипшие» ошибки синхронизации.

**Границы.** Не рассматриваются: iMIP- и iSchedule-транспорт как отдельная тема, мобильные SDK, производительность конкретных серверов в замерах (независимых бенчмарков мы не нашли) и коммерческие тарифы. Примеры доменов обезличены (`example.org`).

## 1. Маршрут подключения: коллекция, а не «календарь»

Точка входа описана в RFC 6764: клиент либо получает путь из DNS (`_caldavs._tcp TXT path=/caldav`), либо идёт на `/.well-known/caldav`, который обязан быть редиректом[^1]. Здесь же спецификация запрещает размещать сам сервис на этом URL: «Servers MUST NOT locate the actual CalDAV or CardDAV service endpoint at the '.well-known' URI»[^1]. На практике это первое место, где self-hosted серверы расходятся: часть отдаёт `301` на `/dav/`, часть — `401` до аутентификации, часть просто держит календарь на корне домена.

Дальше клиент делает `PROPFIND` и ищет `DAV:current-user-principal` — свой principal-ресурс[^11], — а от него `CALDAV:calendar-home-set`, то есть коллекцию, внутри которой лежат уже сами календари. Параллельно он читает `DAV:supported-report-set`: это и есть механизм согласования возможностей, на котором построено всё дальнейшее поведение[^12]. Никакого «handshake» в протоколе нет — клиент просто спрашивает, какие REPORT сервер умеет, и выбирает алгоритм.

Единица хранения задана жёстко. В одном ресурсе не может быть компонентов разного типа, а компоненты с одинаковым `UID` обязаны лежать в одном ресурсе: «Calendar components with the same UID property value, in a given calendar collection, MUST be contained in the same calendar object resource. This ensures that all components in a recurrence "set" are contained in the same calendar object resource»[^3]. Отсюда следуют все дальнейшие неприятности. Правка одного экземпляра серии — это не «патч одной встречи», а перезапись файла с master-компонентом и всеми `RECURRENCE-ID`-переопределениями; два клиента, правившие разные экземпляры одной серии офлайн, гарантированно конфликтуют на уровне файла, даже если их правки логически не пересекаются[^3].

## 2. Два способа узнать, что изменилось

Исторически сложились два механизма, и оба живы. Первый — расширение Apple `getctag` в пространстве имён `http://calendarserver.org/ns/`: клиент делает `PROPFIND Depth:0`, получает непрозрачный токен и, если он совпал с закэшированным, не делает больше ничего[^5]. Спецификация требует, чтобы значение менялось при любом добавлении, изменении или удалении ресурса в коллекции: «Whenever a calendar resource is added to, modified or deleted from the calendar collection, the value of the CS:getctag property MUST change»[^5].

Второй — `sync-collection` из RFC 6578: `REPORT` с элементом `sync-token`, уровнем `sync-level` (`1` — только непосредственные дети, `infinite` — всё поддерево) и списком запрашиваемых свойств. Ответ содержит новый токен и по одному `response` на каждый добавленный или изменённый ресурс, а удаления помечаются статусом `404`[^6]. Токен непрозрачен для клиента и, что важно, не привязан к уровню: «DAV:sync-token values returned by the server are not specific to the value of the DAV:sync-level XML element used in the request»[^6].

Соотношение двух механизмов спецификация Apple закрыла сама, признав `getctag` устаревшим: «IMPORTANT: The feature defined by this specification is now deprecated in favor of support for the WebDAV Sync REPORT as defined by [RFC6578]. Clients MUST NOT rely on this feature to detect changes to collections, instead they MUST support the WebDAV Sync REPORT»[^5]. Там же предложен рецепт совместимости: серверы «MAY continue to support this specification by simply using the DAV:sync-token property value for the getctag property value»[^5].

Именно этот рецепт реализации выполняют по-разному, и разница видна в коде. В sabre/dav (а значит, в Nextcloud и Baikal) `getctag` буквально собран из того же числа, что и токен: `'getctag' => 'http://sabre.io/ns/sync/'.($row['synctoken'] ?: '0')`, `'{http://sabredav.org/ns}sync-token' => $row['synctoken']`, а ETag ресурса — `md5` от тела объекта[^4]. В Radicale токен — «sha256 hash of all history etags of present and past items of the collection», а `getctag` отдаёт `collection.etag`, то есть хеш содержимого коллекции, совсем другое пространство значений[^34][^35]. Формально оба сервера соответствуют RFC 6578; практически клиент, который переключился с `ctag` на `sync-token`, не может перенести сохранённое значение и обязан сделать полную синхронизацию.

Сколько это стоит, показывает сам код Evolution, где заложено угадывание: «the sync-token is supposed to be a URI; if it's not, the stored value can be from the getctag, then ignore it. Do not really parse the URI, just check the string contains ':'. Neither Google nor iCloud use URI, only something like path»[^13]. То есть два крупнейших коммерческих CalDAV-сервера нарушают ожидание «токен — это URI», и клиенты вынуждены это компенсировать.

## 3. Цена токена: retention, инвалидция и 507

Механизм `sync-collection` требует, чтобы сервер помнил историю изменений. Спецификация прямо разрешает её терять: «Servers might need to invalidate tokens previously returned to clients. Doing so will cause the clients to fall back to doing full synchronization using the report, though that will not require clients to download resources that are already cached and have not changed»[^6]. Предустановка на невалидный токен — `403` с `DAV:valid-sync-token`, и требование сформулировано как «MUST be a valid token previously returned by the server for the collection targeted by the request-URI»[^6].

Цена этой инвалидции в self-hosted инсталляции измеряется таблицей истории. Документация Nextcloud описывает риск без обиняков: «The default is keeping 10,000 entries. This option should be set adequate to the number of users. E.g. on an installation with 5000 active synced calendars the system would only keep an average of 10 changes per calendar. This will lead to premature data deletion and synchronization problems», и там же оговорка, что настройка «will also influence CardDAV data retention»[^10]. Иными словами, дефолт рассчитан на небольшую инсталляцию; на общей инсталляции с тысячами календарей каждый клиент будет регулярно получать `403` и уходить в полную пересинхронизацию.

Как это выглядит для клиента, пошагово описал DAVx⁵: при невалидном токене он «forget the sync-token», сбрасывает флаги «present remotely» у всех локальных ресурсов, включает режим initial sync и повторяет запрос без токена[^7]. Тот же документ фиксирует обработку усечения: «Are there further changes on the server (HTTP 507 on collection URL in multiget response)? → If yes, continue with 3»[^7]. По RFC 6578 сервер обязан сообщать об усечении именно так: «If the result set is truncated, the response MUST use status code 207 (Multi-Status), return a DAV:multistatus response body, and indicate a status of 507 (Insufficient Storage) for the request-URI»[^6].

Интересен мотив Radicale, который отдаёт на невалидный токен `403`, а не `409`: в коде стоит комментарий «client.CONFLICT doesn't work with some clients (e.g. InfCloud)»[^12]. Это редкий случай, когда реализация сознательно отступает от буквы, чтобы не ломать конкретный клиент, — и ровно такие отступления накапливаются в «де-факто стандарт».

## 4. Запись: ETag, If-Match и 412, который значит разное

Чтение терпит расхождения, запись — нет. RFC 4791 требует от GET сильного ETag: «A response to a GET request targeted at a calendar object resource MUST contain an ETag response header field indicating the current value of the strong entity tag of the calendar object resource»[^3]. Но дальше спецификация честно оговаривает случай, когда сервер не хранит тело байт-в-байт: «In the case where the data stored by a server as a result of a PUT request is not equivalent by octet equality to the submitted calendar object resource, the behavior of the ETag response header is not specified here, with the exception that a strong entity tag MUST NOT be returned in the response»[^3].

Практический смысл: сервер, который при сохранении нормализует данные (переставляет свойства, добавляет `VTIMEZONE`, перекодирует строки), обязан не отдавать сильный ETag — и клиент теряет оптимистичный сценарий «поставил If-Match, получил новый ETag из ответа». Ему приходится перечитывать ресурс после каждой записи, что при массовом импорте превращается в двойной трафик.

Сама запись описывается двумя заголовками: создание — `PUT` с `If-None-Match: *`, обновление — `PUT` с `If-Match: <etag>`. Так это и делает DAVx⁵: «If no previous ETag/Schedule-Tag of the resource is known ... use HTTP PUT with If-None-Match: * to avoid overwriting a possibly existing resource with the same name», иначе — `If-Match`[^7]. Thunderbird в коде поступает так же: при `aEtag == "*"` ставит `If-None-Match`, иначе `If-Match`[^8].

Дальше начинается самая практичная часть — семантика отказов. `412 Precondition Failed` в WebDAV означает, что не прошла проверка предусловия[^14], `409 Conflict` в CalDAV имеет конкретную причину — нарушение `CALDAV:no-uid-conflict`: ресурс «MUST NOT specify an iCalendar UID property value already in use in the targeted calendar collection»[^3]. То есть `412` — «ты писал по устаревшей версии», `409` — «этот UID уже занят», и лечатся они по-разному. Клиенты их путают: в Thunderbird оба кода попадают в один геттер `get conflict() { return this.status == 409 || this.status == 412; }`[^8].

Более показателен разбор в DAVx⁵. Мейнтейнер признал неверное допущение: «We currently expect 404/410 on PUT with If-Match when the target resource doesn't exist anymore. That seems to be a wrong assumption, the correct code seems to be 412»[^9]. Следствие — вечный ретрай и незачищенный dirty-флаг, то есть локальная правка, которая никогда не уедет на сервер. И там же — важное наблюдение о том, что один и тот же клиент ведёт себя по-разному в зависимости от выбранного алгоритма: при collection sync удаление обрабатывается «without looking at the dirty flag, it's basically 'remote deletion wins'»[^9].

Отдельно стоит строгость сервера. Radicale раньше принимал `PUT` без `If-Match` и с устаревшим ETag: автор issue описал это как «the last client to write "wins", regardless of the ETag», после чего мейнтейнер согласился сделать строгую проверку поведением по умолчанию[^15]. Строгий режим превращает молчаливую потерю правки в `412`, который клиент может обработать; мягкий — в тихую перезапись.

## 5. Schedule-Tag: исключение, которое ломает наивную модель

Отдельная механика нужна, когда ресурс меняется не владельцем. RFC 6638 вводит свойство `CALDAV:schedule-tag`, заголовки `Schedule-Tag` и `If-Schedule-Tag-Match` — «to allow client changes to be appropriately merged with server changes in the case where the changes on the server were the result of an "inconsequential" scheduling message update (one that simply updates the status information of "Attendees" due to a reply from another "Attendee")»[^16]. Требование к серверу сформулировано императивно: «Servers MUST automatically resolve conflicts with "inconsequential" changes done to scheduling object resources when the If-Schedule-Tag-Match request header is specified»[^16].

Причина в том, что ответ участника (`PARTSTAT=ACCEPTED`) физически меняет файл организатора: тот же `UID`, тот же `SEQUENCE`, другой ETag. Клиент организатора, который держит `If-Match` с прошлого чтения, получит `412` из-за чужого действия — ровно та ситуация, для которой `If-Match` не предназначен. Поэтому корректный клиент посылает оба заголовка и различает «мою версию перебили» и «участник ответил».

Кто эту механику не реализует, тот живёт с постоянными ложными конфликтами. Google в документации на CalDAV API прямо перечисляет усечённый набор: поддерживаются `GET`, `PUT`, `HEAD`, `DELETE`, `POST`, `OPTIONS`, `PROPFIND`, `PROPPATCH`, но не поддерживаются «the HTTP methods LOCK, UNLOCK, COPY, MOVE, MKCOL, or the If* header (except for If-Match)»; scheduling-«inbox» там «trivial "inbox," which is always empty», приглашения сразу попадают в коллекцию событий, а free-busy не поддерживается вовсе[^17]. Это не мелкая недоработка: без `If-Schedule-Tag-Match` и без настоящего inbox вся серверная часть планирования отсутствует, и «CalDAV-совместимость» Google означает только доступ к событиям.

Второй слой — необязательные расширения, которых нет в RFC. Apple-серверы, например, объявляют в ответе на `OPTIONS` поле `calendarserver-private-comments`, чтобы участники могли передавать организатору приватные комментарии к событию[^33]. На протокол синхронизации это влияет косвенно, но существенно: поскольку запись перезаписывает файл целиком, а не патчит поля, любое неизвестное свойство, которое клиент не сохранил, исчезает при следующей записи. DAVx⁵ поэтому хранит неизвестные iCalendar-свойства отдельно и возвращает их при генерации файла — «iCalendar properties which are not processed by DAVx⁵ (like X- properties) are retained (unless they're larger than ≈ 25 kB)»[^7]. Клиент, который так не делает, тихо вычищает чужие данные.

## 6. Почему клиенты расходятся при офлайн-правках

Расхождение клиентов — не череда багов, а три легальные развилки, каждая из которых по-своему соответствует спецификации.

**Развилка первая: алгоритм синхронизации.** DAVx⁵ выбирает его по возможностям сервера и своим настройкам: для CardDAV — collection sync, если сервер его умеет, иначе `PROPFIND`; для событий CalDAV — collection sync только «if supported by server and past time event limit is disabled», иначе `REPORT calendar-query`; для задач — всегда `calendar-query`[^7]. Thunderbird приоритеты расставляет иначе и в коде объясняет почему: «It is redundant to send a request to get the collection tag (getctag) on a calendar if it supports webdav sync, the sync request will only return data if something changed»[^18]. Evolution поддерживает оба механизма и включает collection sync только при отсутствии ограничения по дням[^13]. Один и тот же сервер и три разных клиента могут использовать три разных пути к одному результату.

**Развилка вторая: политика конфликта.** Здесь спецификация молчит, и клиенты заполняют пустоту противоположными решениями. DAVx⁵ формулирует своё правило без смягчений: «DAVx⁵ relies on HTTP ETag to determine whether a resource has been changed on the server. The server always wins. If a local resource can't be uploaded or deleted safely because it has been modified on the server in the meanwhile, local changes are discarded and the server version is used», и добавляет, что не спрашивает пользователя, потому что работает в фоне тихо[^7]. Автоматического слияния vCard, которое предлагает vCard 4, там тоже нет[^7]. Thunderbird, судя по коду, пытается различать случаи через `409`/`412` и перечитывать ресурс[^8], но при этом не имеет механизма слияния вовсе.

**Развилка третья: что считать достоверным состоянием коллекции.** Коллекция только для чтения — хороший тест. Если сервер использует collection sync, локально изменённый контакт никогда не откатится, пока его не изменят на сервере: «the changed contact is only reverted to the original version when the contact is edited on the server. If this specific contact is never changed on the server the locally edited contact will never be reverted, because Collection Sync only transmits the changed contents» — issue открыт с 2024 года[^19]. Обходной путь, предложенный мейнтейнером, — принудительно использовать `PROPFIND`/`REPORT`, который замечает «лишние» локальные записи[^19].

Цена хрупкости тоже распределена неравномерно. Один ресурс без ETag в ответе сервера валит синхронизацию всей коллекции: в отчёте о баге — «When a server lists an event without ETag … and in 4.5.20 that fails the whole sync. In 4.5.19 it did not»[^20]. В соседнем случае — с пустым ответом multiget — пострадали «16 out of 379 resources in one task collection», и «all ~363 otherwise-valid tasks in that same collection stopped syncing because of them»[^21]. Мейнтейнер согласен, что «a single corrupt entry must not crash the whole sync», но тут же называет цену обхода: записи без ETag противоречат RFC, и «every 15 minutes 10.000 entries without ETag are downloaded again and again»[^20][^21].

Есть и клиенты, которые просто не масштабируются. Баг Thunderbird о календаре на 10 000 событий открыт с февраля 2016 года: полная выгрузка делает клиент «VERY SLOW», а контраргумент в том же баге — что поведение зависит от выбранного фильтра отображения, а не от протокола[^22]. У Evolution проблема «stale getctag» проявилась на Confluence: сервер принимает правку и меняет ETag ресурса, но не меняет `getctag` коллекции, и клиент пропускает листинг — «Thunderbird did never show a problem, but evolution calendar did»[^23]. Это ровно тот класс отказа, который RFC 6578 устраняет, а `getctag` допускает.

## 7. UID, SEQUENCE и происхождение дублей

У объекта в CalDAV два идентификатора: `UID` внутри iCalendar и href ресурса. `UID` уникален в пределах коллекции, href — в пределах сервера[^3]. Пока объект живёт на одном сервере, различие незаметно; как только пользователь копирует `.ics` между серверами или импортирует архив, оно становится источником дублей. Импорт файла с занятым `UID` по новому href даёт `409` и `CALDAV:no-uid-conflict`[^3]; импорт с новым `UID` создаёт вторую сущность, которую ни один клиент не свяжет с первой.

`SEQUENCE` задуман как счётчик ревизий организатора, а не как механизм слияния. RFC 5545: «When a calendar component is created, its sequence number is 0. It is monotonically incremented by the "Organizer's" CUA each time the "Organizer" makes a significant revision to the calendar component»[^24]. Здесь и проходит граница: участник не имеет права увеличивать `SEQUENCE`, поэтому его ответ меняет файл без изменения номера ревизии — именно этот случай и обслуживает `Schedule-Tag`[^16].

Насколько это хрупко на практике, зафиксировал CalConnect по итогам тестового события 2010 года: «We would like to clarify wording in standard such that when an RRULE is modified, the SEQUENCE number MUST be incremented (some implementations reset to 0), specifically Microsoft Exchange. ... Incrementing the RRULE allows other implementations to treat the change as an update rather than forcing the entire series to be blown away and recreated»[^25]. Участники того же события отдельно перечислили проблемные сценарии повторяющихся встреч: обновление экземпляра с `THISANDFUTURE`, обновление серии без исключений, обновление серии с сохранением исключений и разделение серии с новым `UID`[^25]. То есть даже внутри одного протокола «изменить серию» имеет четыре разных представления, и не все реализации понимают все четыре.

Академическая попытка формализовать это появилась только в 2026 году: препринт строит граф зависимостей свойств RFC 5545 (27 свойств, 20 рёбер) и классифицирует их по пригодности к слиянию — «safe, dependent, scheduling, immutable, and always-update—that determine whether concurrent edits can be combined without user intervention»[^26]. Автор документирует «25 bugs across 17 calendar projects spanning 8 programming languages», причём правило «тип EXDATE должен совпадать с типом DTSTART» даёт «7+ separate bugs» в независимых реализациях[^26]. Вывод для практики жёсткий: слияние на уровне полей в календарях не реализовано нигде, потому что оно требует именно такого графа зависимостей, а не сравнения версий.

## 8. CardDAV: та же механика, другие пределы

CardDAV устроен как зеркальное отражение: адресные книги вместо календарей, `addressbook-query` и `addressbook-multiget` вместо календарных REPORT, `CARDDAV:address-data` вместо `calendar-data`[^2]. Обнаружение изменений — тот же `sync-collection` или `getctag`; ETag и условные заголовки — те же.

Отличия начинаются в поиске. Фильтр `text-match` параметризован коллацией: серверы обязаны поддерживать `i;ascii-casemap` (RFC 4790) и `i;unicode-casemap` (RFC 5051), «MAY support other collations», а набор обязаны объявлять свойством `CARDDAV:supported-collation-set`; на неподдерживаемую клиентом коллацию сервер отвечает предустановкой `CARDDAV:supported-collation`[^2]. То есть свобода реализации здесь не подразумевается, а явно разрешена — и потому набор коллаций у двух серверов может не совпадать. Пределы тоже описаны формально: при усечении результата сервер обязан вернуть `507` и предустановку `DAV:number-of-matches-within-limits`, а клиент может ограничить выдачу элементом `CARDDAV:limit` с `nresults`[^2].

Ограничения на размер задаются сервером и объявляются свойствами: `CARDDAV:max-resource-size` описывает максимальный размер объекта, и попытка записать больше обязана привести к нарушению этой предустановки[^2]. Как это выглядит у крупного провайдера, видно по лимитам iCloud: 50 000 карточек, карточка до 256 KB, фото до 224 KB, группа до 256 KB[^27]. Для календарей там же: 50 000 событий и напоминаний, 100 календарей, 1 GB суммарно, событие с вложениями до 20 MB, до 300 приглашённых[^27]. Это не протокольные пределы, а операционные — но именно они определяют, когда self-hosted сервер начинает отказывать клиенту, который до этого работал.

Слияния в CardDAV нет тем более: `vCard` 4.0 его описывает, но DAVx⁵ прямо пишет, что не поддерживает[^7]. Практическое следствие — для контактов «побеждает последняя запись целиком», и правка телефона на телефоне затирает правку адреса, сделанную на десктопе, если десктопный клиент записал файл позже с устаревшим адресом.

## 9. Что это значит на своём сервере

**Выбирать сервер по семантике синхронизации, а не по списку возможностей.** Семейство sabre (Nextcloud, Baikal, собственная сборка sabre/dav) даёт целочисленный `synctoken`, `getctag` как алиас токена и настраиваемый retention[^4][^10]. Radicale даёт ETag по sha256 содержимого — это удобно для отладки (хеш меняется ровно тогда, когда меняется тело), но `getctag` там не алиас токена, а хеш коллекции[^35][^36][^28]. И это осознанная позиция: документация Radicale заявляет, что проект «does not and will not blindly implement the CalDAV and CardDAV standards»[^28].

**Настроить retention под число реально синхронизируемых календарей.** Дефолтные 10 000 записей в Nextcloud — это примерно 10 изменений на календарь при 5000 активных календарей, что документация сама называет причиной «premature data deletion and synchronization problems»[^10]. Правильная оценка — умножить число активных клиентов на типичное число правок в месяц и добавить запас на отпуск клиента.

**Следить за двумя кодами в логах.** `403` с `DAV:valid-sync-token` означает, что клиенты уходят в полную пересинхронизацию; `507` на URL коллекции означает усечение выдачи[^6]. Оба — не ошибки клиента, а сигнал, что история или лимиты не соответствуют нагрузке.

**Не включать кеш по mtime на файловых системах с грубым mtime.** В Radicale опция кеша элементов по «last modification time (in nanoseconds) and size» выключена по умолчанию, и в документации стоит предупреждение «check used filesystem mtime precision before enabling»[^28]: при грубой точности ETag перестанет меняться после правки, и клиент не увидит изменение вовсе.

**Помнить про лимиты как про конфигурацию.** У Radicale это `max_content_length` (100 MB по умолчанию), `max_resource_size` (10 MB, объявляется клиентам через `max-resource-size`) и `max_vevent_rrule_occurrence` (10 000)[^28]. У Nextcloud — rate limit на создание календарей (10 в час) и максимум 30 календарей на пользователя[^10]. Всё это влияет на то, какой клиент и с каким календарём вообще сможет работать.

**Не считать токены и ETag резервной копией.** Ни `sync-token`, ни `getctag` не переживают пересоздание коллекции, а retention истории прямо предусматривает её удаление[^6][^10]. Резервная копия — это файлы или экспорт `.ics`/`.vcf`, а не состояние синхронизации.

## Дискуссионные вопросы и противоречия

**«sync-token лучше ctag» — но ctag никто не выключил.** Apple объявила `getctag` устаревшим и требует от клиентов опираться на RFC 6578[^5]. При этом Google продолжает описывать `ctag` как штатный механизм («The calendar ctag is like a resource etag; it changes when anything in the calendar has changed»)[^17], Thunderbird сохраняет ветку с `CS:getctag` как резервную[^18], Evolution держит оба механизма одновременно[^13]. Формально правы все: RFC 6578 никого не обязывает убрать `getctag`.

**«Сервер всегда прав» против смысла `If-Match`.** DAVx⁵ выбирает отбрасывание локальной правки и объясняет это фоновой работой[^7]. Но `If-Match` в WebDAV существует, чтобы обнаружить конфликт, а не чтобы его молча разрешить в пользу сервера[^14]. Показательно, что тот же клиент в соседнем сценарии ведёт себя иначе: при collection sync удалённый на сервере ресурс удаляется локально независимо от dirty-флага[^9], а в read-only коллекции локальная правка не откатывается вовсе[^19]. Три разных правила в одном клиенте — следствие того, что протокол не задаёт политику.

**Спецификация против реализаций: что именно чинили CalConnect.** В отчёте 2010 года участники обнаружили, что «the vCard 4 specification in CardDAV was invalid and time was spent discussion and writing changes to the actual specification»[^25]. В отчёте 2013 года — расхождения в часовых поясах, «mostly related to the particular aliases being used», и проблема единого адреса для планирования: «When sending invitations to attendees it is not clear where the invitation should go and the fallback of using email is not altogether satisfactory»[^29]. То есть часть расхождений объясняется не ленью разработчиков, а дырами в спецификации, которые закрывали постфактум.

**Google: API жив, но «CalDAV» там ограничен.** С 16 сентября 2013 года CalDAV API Google доступен только по white-list: «CalDAV API will become available for whitelisted developers, and will be shut down for other developers on September 16, 2013. Most developers' use cases are handled well by Google Calendar API»[^30]. При этом руководство обновлено 9 октября 2026 года и по-прежнему описывает выдачу OAuth-клиента[^17]. Ограничения при этом принципиальные: нет `VTODO` и `VJOURNAL`, нет `MKCALENDAR`, нет free-busy, нет `COPY`/`MOVE` и почти всех `If*`-заголовков[^17]. Mozilla в 2013 году описала и конкретный сбой совместимости: Google добавил поддержку webdav-sync, но «Google does not implement the fallback mechanism we rely on»[^31]. «Совместимо с CalDAV» и «совместимо с конкретным клиентом» — разные утверждения.

## Недостаточность данных

Публичного отчёта CalConnect, где фиксировались бы расхождения именно по `text-match` и коллациям в CardDAV, найти не удалось: в отчётах 2010–2013 годов такого пункта нет, а более поздние документы в открытом реестре `standards.calconnect.org` мы не обнаружили. Академическая литература по теме тонка: рецензируемые работы посвящены дизайну протокола и планированию (IEEE Internet Computing, 2005), а не синхронизации как таковой[^32]; формализация зависимостей свойств iCalendar появилась только как препринт 2026 года[^26]. Независимых замеров стоимости `sync-collection` на больших коллекциях мы не нашли — все числа в разборе взяты из документации, кода и баг-репортов, а не из воспроизведённых испытаний.

## Заключение

CalDAV и CardDAV стоит читать как два слоя. Нижний — WebDAV: коллекция, ресурс, ETag, условные заголовки, коды `412` и `409`. Верхний — два расширения: способ обнаружения изменений (`getctag` или `sync-collection`) и способ планирования (`schedule-inbox`/`schedule-outbox` с `Schedule-Tag`). Почти все практические проблемы self-hosted календаря живут на стыке этих слоёв: сервер корректно реализует WebDAV, но помнит слишком короткую историю токенов; клиент корректно ставит `If-Match`, но не различает `412` и `404`; календарь хранит целый файл серии, а пользователь ждёт слияния по полям.

Три практических вывода. Первый: единица синхронизации — файл, поэтому «разные устройства правят разные экземпляры одной серии» — это конфликт по построению, а не баг клиента. Второй: политика конфликта задаётся клиентом, и её надо знать заранее — DAVx⁵ отбросит локальную правку, Thunderbird попробует перечитать, а сервер с мягкой проверкой `If-Match` просто перезапишет. Третий: `sync-token` — расходуемый ресурс; retention, лимиты и коды `403`/`507` в логах нужно рассматривать как эксплуатационные параметры, а не как внутренности протокола.

Что осталось непроверенным и о чём стоит помнить: поведение конкретных клиентов на конкретных версиях серверов меняется от релиза к релизу (sabre/dav 4.7.1 вышел в июле 2026-го, а issue DAVx⁵ о событии без ETag, обрывающем синхронизацию, закрыт только 5 октября 2026-го), поэтому любые утверждения о «правильном» клиенте стоит перепроверять на своей паре сервер-клиент, а не переносить из обзоров[^4][^20].

## Quality Metrics

| Metric | Value |
|--------|-------|
| Total sources | 36 |
| Academic sources | 2 |
| Official/documentation | 23 |
| Industry reports | 2 |
| News/journalism | 0 |
| Blog/forum | 9 |
| Citation coverage | 85% |
| Counter-arguments searched | Yes |
| Research rounds | 3 |
| Questions emerged | 9 |
| Questions resolved | 7 |
| Questions insufficient data | 2 |

[^1]: C. Daboo. "Locating Services for Calendaring and Contacts (CalDAV and CardDAV)." RFC 6764, IETF, March 2016. https://www.rfc-editor.org/rfc/rfc6764.txt
[^2]: C. Daboo. "vCard Extensions to WebDAV (CardDAV)." RFC 6352, IETF, August 2011. https://www.rfc-editor.org/rfc/rfc6352.txt
[^3]: C. Daboo, B. Desruisseaux, L. Dusseault. "Calendaring Extensions to WebDAV (CalDAV)." RFC 4791, IETF, March 2007. https://www.rfc-editor.org/rfc/rfc4791.txt
[^4]: sabre/dav. "CalDAV/Backend/PDO.php" (master) и "ChangeLog 4.7.1 (2026-07-07)." GitHub, 2026. https://github.com/sabre-io/dav/blob/master/lib/CalDAV/Backend/PDO.php
[^5]: C. Daboo. "Calendar Collection Entity Tag (CTag) in CalDAV." Internet-Draft caldav-ctag-03, Apple, 27 May 2015. https://github.com/apple/ccs-calendarserver/blob/master/doc/Extensions/caldav-ctag.txt
[^6]: C. Daboo, A. Quillaud. "Collection Synchronization for Web Distributed Authoring and Versioning (WebDAV)." RFC 6578, IETF, March 2012. https://www.rfc-editor.org/rfc/rfc6578.txt
[^7]: bitfireAT. "DAVx⁵ — Technical information, 8.1 Synchronization." DAVx⁵ manual, accessed 26 October 2026. https://manual.davx5.com/technical_information.html
[^8]: Thunderbird. "CalDavRequest.sys.mjs" (main). Mozilla, accessed 26 October 2026. https://raw.githubusercontent.com/thunderbird/thunderbird-desktop/main/calendar/providers/caldav/modules/CalDavRequest.sys.mjs
[^9]: bitfireAT. "Issue #2739: Task with local change, deleted on server: sync conflict does not get resolved." davx5-ose, 1 August 2026. https://github.com/bitfireAT/davx5-ose/issues/2739
[^10]: Nextcloud. "Calendar / CalDAV — admin manual (stable)." Nextcloud documentation, accessed 26 October 2026. https://docs.nextcloud.com/server/stable/admin_manual/groupware/calendar.html
[^11]: J. Reschke. "WebDAV Current Principal Extension." RFC 5397, IETF, December 2008. https://www.rfc-editor.org/rfc/rfc5397.txt
[^12]: Radicale. "radicale/app/report.py" (master). GitHub, accessed 26 October 2026. https://github.com/Kozea/Radicale/blob/master/radicale/app/report.py
[^13]: GNOME. "e-cal-backend-caldav.c" (master). evolution-data-server, accessed 26 October 2026. https://gitlab.gnome.org/GNOME/evolution-data-server/-/raw/master/src/calendar/backends/caldav/e-cal-backend-caldav.c
[^14]: L. Dusseault (ed.). "HTTP Extensions for Web Distributed Authoring and Versioning (WebDAV)." RFC 4918, IETF, June 2007. https://www.rfc-editor.org/rfc/rfc4918.txt
[^15]: Kozea. "Issue #1897: Feature request: optional strict ETag / precondition enforcement on PUT." Radicale, 15 October 2025. https://github.com/Kozea/Radicale/issues/1897
[^16]: C. Daboo, B. Desruisseaux. "Scheduling Extensions to CalDAV." RFC 6638, IETF, June 2012. https://www.rfc-editor.org/rfc/rfc6638.txt
[^17]: Google. "CalDAV API Developer's Guide." Google for Developers, last updated 9 October 2026. https://developers.google.com/workspace/calendar/caldav/v2/guide
[^18]: Thunderbird. "CalDavCalendar.sys.mjs" (main). Mozilla, accessed 26 October 2026. https://raw.githubusercontent.com/thunderbird/thunderbird-desktop/main/calendar/providers/caldav/CalDavCalendar.sys.mjs
[^19]: bitfireAT. "Issue #849: Changes to a read-only contact locally does not reset the contact to server version when 'collection sync' is used." davx5-ose, 12 June 2024. https://github.com/bitfireAT/davx5-ose/issues/849
[^20]: bitfireAT. "Issue #2934: Event without ETag will abort calendar sync midway." davx5-ose, 5 October 2026. https://github.com/bitfireAT/davx5-ose/issues/2934
[^21]: bitfireAT. "Issue #2941: [4.5.20] Empty multi-get response (no calendar-data) aborts entire collection sync instead of being skipped." davx5-ose, 6 October 2026. https://github.com/bitfireAT/davx5-ose/issues/2941
[^22]: Mozilla. "Bug 1247240: Enable configurable time sync window to mitigate performance problems on very large calendars." Bugzilla, 10 February 2016 (status NEW). https://bugzilla.mozilla.org/show_bug.cgi?id=1247240
[^23]: GNOME. "Issue #673: CalDAV refresh failure with Confluence Team Calendars and stale getctag." evolution-data-server, 7 October 2026. https://gitlab.gnome.org/GNOME/evolution-data-server/-/issues/673
[^24]: C. Desruisseaux (ed.). "Internet Calendaring and Scheduling Core Object Specification (iCalendar)." RFC 5545, IETF, September 2009. https://www.rfc-editor.org/rfc/rfc5545.txt
[^25]: P. Egen, N. Barry, C. Daboo, M. Douglass, A. Quillaud. "October 2010 CalConnect Interoperability Test Event Report." CC/A 1014:2011, CalConnect, 2011. https://standards.calconnect.org/cc/cc-a-1014-2011.html
[^26]: iCalDAV. "Formalizing Implicit Property Dependencies in RFC 5545: Toward Safe Property-Level Calendar Synchronization." Zenodo preprint, 28 March 2026. https://zenodo.org/records/19299689
[^27]: Apple. "Limits for iCloud Contacts, Calendars, Reminders, Bookmarks, and Maps." Apple Support, accessed 26 October 2026. https://support.apple.com/en-us/103188
[^28]: Radicale. "Radicale 3 documentation" (v3.9.0). radicale.org, accessed 26 October 2026. https://radicale.org/v3.html
[^29]: M. Douglass. "Report on Interoperability Test Event XXVII, June 3-5, 2013." CC/A 1305:2013, CalConnect, June 2013. https://standards.calconnect.org/cc/cc-a-1305-2013.html
[^30]: Google. "A second spring of cleaning." Official Google Blog, 24 May 2013. https://blog.google/company-news/inside-google/company-announcements/a-second-spring-of-cleaning/
[^31]: P. Kewisch. "Google is changing the Location URL of their CalDAV Calendars." Mozilla Calendar Project Blog, 16 September 2013. https://blog.mozilla.org/calendar/2013/09/google-is-changing-the-location-url-of-their-caldav-calendars/
[^32]: L. Dusseault, E. J. Whitehead. "Open Calendar Sharing and Scheduling with CalDAV." IEEE Internet Computing, 2005. https://doi.org/10.1109/mic.2005.43
[^33]: C. Daboo. "Private Attendee Comments in CalDAV Scheduling." Calendar Server Extension, Apple, 14 August 2008. https://github.com/apple/ccs-calendarserver/blob/master/doc/Extensions/caldav-privatecomments.txt
[^34]: Radicale. "radicale/storage/multifilesystem/sync.py" (master). GitHub, accessed 26 October 2026. https://github.com/Kozea/Radicale/blob/master/radicale/storage/multifilesystem/sync.py
[^35]: Radicale. "radicale/app/propfind.py" (master). GitHub, accessed 26 October 2026. https://github.com/Kozea/Radicale/blob/master/radicale/app/propfind.py
[^36]: Radicale. "radicale/item/__init__.py" (master), функция `get_etag`. GitHub, accessed 26 October 2026. https://github.com/Kozea/Radicale/blob/master/radicale/item/__init__.py
