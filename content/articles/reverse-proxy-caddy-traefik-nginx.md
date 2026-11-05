---
title: "Caddy 2.11 против Traefik и nginx: автоматический TLS и цена конфигурации"
date: 2026-11-05T09:47:10+03:00
description: "Caddy 2.11.9, Traefik 3.7.17 и nginx 1.30.6/1.31.8: кто управляет сертификатами, что переживает reload и где автоматизация расширяет границы доверия."
showToc: true
tocOpen: true
---

## Аннотация

Для одного администратора выбор reverse proxy — прежде всего выбор владельца состояния и способа изменения маршрутов. Caddy сокращает явную настройку обычного публичного HTTPS; Traefik связывает маршрутизацию с событиями и метаданными контейнеров; nginx оставляет больше явной политики, но уже умеет автоматизировать сертификаты официальным опциональным ACME-модулем. Поэтому сравнение «Caddy с автоматическим TLS против nginx с ручным продлением» больше не описывает актуальный выбор.[^5][^14][^15][^23]

Данные на **2026-11-05**: **Caddy v2.11.9**, опубликованный сегодня в **01:30:24 UTC**, **Traefik v3.7.17** от **2026-10-30**, **nginx stable 1.30.6 / mainline 1.31.8**, отдельно — **nginx-acme 0.4.1**. Исходная предпосылка о Caddy 2.11.7 устарела: это уже не текущий релиз ветки. Допущение обзора — один узел Docker Compose, небольшой набор сервисов, один администратор; публичный DNS и доступность входящих портов определяются отдельно. Это анализ документации и кода, **без запуска proxy, проверки конфигураций на стенде, выпуска сертификатов и измерения производительности**.[^1][^2][^3][^25]

## Введение

**Исследовательский вопрос:** какой из трёх proxy уменьшает именно эксплуатационную нагрузку небольшого self-hosted контура, не скрывая критические обязанности? Рассмотрим шесть подвопросов: что запускает выпуск сертификата; где хранится состояние; кто вправе менять маршруты; что происходит при ошибке обновления; как обрабатываются долгоживущие соединения; где заканчивается доверие к предыдущему proxy. «Цена конфигурации» здесь — качественная оценка числа владельцев состояния, полномочий и проверяемых переходов, а не подсчёт строк YAML или человеко-часов.

В [обзоре NixOS, Ansible и Compose](/articles/nixos-ansible-compose/) обсуждались уровни управления сервером и общие границы отката. Здесь предмет уже: **control plane** принимает описание ingress и сертификатную политику, **data plane** обслуживает запросы и соединения. Это аналитическое разделение обязанностей, не утверждение о разных процессах. Caddy меняет конфигурацию через API; Traefik получает routing configuration от providers; nginx переключает поколения workers. Эти механизмы задают разные единицы изменения.[^9][^14][^29]

За рамками — Kubernetes ingress, коммерческие редакции как самостоятельные продукты, WAF, универсальный рейтинг безопасности и сравнение скорости. Официальные документы и tagged source подходят для проверки defaults и ветвей обработки ошибок, но не доказывают, что один продукт потребует меньше ночных вмешательств. Далее рекомендации отделены от фактов словами «вывод», «разумно» и «предлагаемый порядок».

## 1. Автоматический TLS: сначала доказательство контроля, потом удобство

ACME автоматизирует доказательство контроля над именем и получение сертификата, а не доступность приложения. В HTTP-01 удостоверяющий центр проверяет специальный ресурс; RFC 8555, §8.3, задаёт внешний порт недвусмысленно. Перенос HTTP-listener внутрь контейнера на другой порт не меняет этого требования к внешней доставке запроса.[^4]

> “This request MUST be sent to TCP port 80 on the HTTP server.”[^4]

По документации Caddy HTTP-01 и TLS-ALPN-01 включены по умолчанию: второй требует внешнего доступа на 443. DNS-01 не требует входящих портов, но добавляет учётные данные DNS-провайдера и управление TXT-записями; для wildcard у Let's Encrypt нужен именно DNS challenge. Traefik также документирует эти три варианта. Следовательно, «сервис доступен только через частную сеть» не исключает публичного сертификата через DNS-01, но меняет границу доверия: proxy или ACME-клиент получает возможность изменять DNS.[^5][^18]

У Caddy есть и другая ветка: внутренний HTTPS с собственным CA. Это не публичный ACME и не автоматическое доверие всех клиентских устройств. Администратор отвечает за распространение корня; установка в trust store контейнера не означает установки на телефон. В коде v2.11.9 IP-идентификаторы без явной automation policy направляются к внутреннему issuer. Это поведение default policy, а не доказательство, что публичные сертификаты для IP невозможны вообще.[^5][^6]

Практический вывод: до сравнения синтаксиса нужно выбрать сценарий. Для обычных публичных имён проверяют DNS и доставку challenge; для закрытых сервисов с публичным именем — DNS API и права ключа; для внутренней PKI — доверие клиентов. Ни один краткий конфигурационный пример не отменяет этот выбор.[^4][^5][^18]

## 2. Caddy: меньше явных связей, но не меньше важного состояния

Сильная сторона Caddy — автоматический жизненный цикл HTTPS, когда сервер знает обслуживаемое имя. Однако префикс `http://`, исключительно HTTP-listener, явное отключение automation или уже загруженный подходящий сертификат меняют поведение. Документация формулирует принцип точнее, чем обещание «HTTPS без настроек»: автоматизация дополняет явную конфигурацию, а не переопределяет её.[^5][^6]

> “Automatic HTTPS never overrides explicit configuration, it only augments it.”[^5]

Для малого, относительно постоянного набора приложений отсюда следует преимущество: администратору не обязательно связывать отдельный scheduler продления с установкой сертификата в proxy. Но короткий Caddyfile не описывает всё эксплуатационное состояние. Data directory содержит сертификаты, приватные ключи и другие необходимые данные; config directory с autosave — отдельный объект, как и исходный файл. Сохранять только Caddyfile недостаточно для воспроизведения того же состояния.[^5][^7]

> “The data directory must not be treated as a cache.”[^7]

Цена компактного языка — знание адаптера. По текущей документации Caddyfile многие директивы сортируются в заранее заданном порядке, а не исполняются просто сверху вниз; `route` сохраняет явную последовательность. Поэтому при добавлении аутентификации или исключения из общего маршрута проверять следует полученную цепочку обработки, а не визуальную близость строк. Детальные правила сортировки здесь подтверждены изменяемой документацией, не отдельным исследованием tagged adapter.[^8]

Управление процессом тоже требует выбора источника истины. `caddy reload` использует административный API; отключение admin endpoint исключает этот путь. API по умолчанию слушает `localhost:2019`, но превращать его в обычный публичный route нельзя считать нейтральным изменением: это полномочие менять конфигурацию proxy. Несколько запросов API не образуют транзакцию. При конкурентных изменениях документация предлагает `Etag` и `If-Match`; несовпадение даёт HTTP 412, а не незаметную перезапись чужого изменения.[^9][^11]

В v2.11.9 новая конфигурация запускается до переключения текущего контекста и очистки старого. Если загрузка завершается ошибкой, прежняя рабочая конфигурация остаётся, а её raw-представление восстанавливается. Но autosave выполняется после переключения: ошибки создания каталога или записи логируются, после чего функция может вернуть `nil`. **Принято в памяти не равно сохранено для следующего старта.** Это ограничение видно в коде, а не установлено экспериментом с отказом диска.[^10]

Наконец, certificate management по умолчанию работает в фоне: процесс может уже обслуживать listeners, пока сертификаты ещё не готовы. Частые изменения конфигурации отменяют незавершённые задачи, включая ACME-транзакции. Для одного администратора разумно пакетировать связанные изменения и проверять итоговый TLS снаружи, а не считать успешный reload доказательством готовности имени.[^5][^6]

## 3. Traefik: автоматизация начинается с графа объектов и полномочий

Traefik v3.7.17 разделяет **install/startup configuration** — прежнюю static — и **routing configuration** — прежнюю dynamic. Первая задаёт providers и entryPoints, вторая описывает обработку запросов и обновляется без перезапуска. Это важная экономия при изменении состава сервисов, но не обещание hot reload любых startup-параметров. Способы задания install-конфигурации через файл, flags или environment документация называет взаимоисключающими; это не запрещает одновременно получать routing configuration от нескольких providers.[^14]

В Docker-сценарии labels переносят описание маршрута к приложению, а provider наблюдает события. Администратор избавляется от отдельного ручного реестра адресов, но получает связанные сущности: entryPoint, router, middleware, service и certificate resolver. При нескольких exposed ports документация описывает выбор самого низкого; явные backend port и Docker network уменьшают неоднозначность. Это качественный обмен ручной синхронизации на правила discovery, не измеренная экономия времени.[^15][^16]

Существенный default — `providers.docker.exposedByDefault=true`. Для небольшого self-hosted окружения разумнее явно выбрать `false` и включать нужные контейнеры через `traefik.enable=true`. Но opt-in ограничивает **генерацию маршрутов**, а не права на Docker API. Официальное предупреждение прямо связывает неограниченный доступ к API с возможным доступом атакующего к хосту. Mount сокета с `:ro` не следует принимать за доказанную авторизацию API; доступ и допустимые действия нужно ограничивать отдельно.[^15]

TLS здесь состоит из разных решений. `tls` переводит router в HTTPS; `tls.certResolver` указывает механизм автоматического получения сертификата; `tls.options` задаёт параметры TLS. Resolver объявляется на startup-уровне, а router ссылается на него. Поэтому `tls=true` само по себе не означает доверенный автоматически выпущенный сертификат: документация entryPoints описывает и self-signed default, когда сертификаты не заданы.[^16][^17][^18]

Особенно опасно смешивать примеры наследования. В **v3.7.17** собственная TLS-секция router, даже пустая, **заменяет** TLS-конфигурацию entryPoint, а не дополняет её. Добавляя отдельную TLS-настройку, можно потерять ожидаемый унаследованный resolver или options. Проверять нужно итоговую политику конкретного router, а не только глобальное наличие ACME-настроек.[^17]

> “Defining a router `tls` section (even empty, or with any field such as `certResolver`) replaces the entrypoint TLS configuration for that router (no merge).”[^17]

Состояние ACME остаётся чувствительным файлом. Unix-реализация v3.7.17 создаёт его с `0600` и отклоняет существующий файл с выставленными group/other permission bits. Практическая цель — persistent, доступный на запись владельцу `acme.json`, а не world-readable bind mount. Автоматизация renewal не устраняет это состояние; более того, руководство предупреждает, что сертификаты, уже не используемые маршрутом, могут продолжать обновляться.[^19][^18]

Hot reload зависит и от доставки изменения. File provider использует fsnotify; замена отдельного bind-mounted файла через rename может разорвать связь с файлом внутри контейнера. Руководство рекомендует каталог и mount родительского каталога. Отдельно надо различать ошибки: в tagged file provider неудачная сборка snapshot возвращает ошибку **до** отправки нового состояния; в router manager структурно принятый, но семантически некорректный router может получить ошибку и быть пропущен при построении нового muxer. Это не универсальный all-or-nothing rollback всех маршрутов.[^20][^21][^22]

## 4. nginx: уже не «без ACME», но с явным выбором конвейера

У nginx OSS есть официальный опциональный **nginx-acme 0.4.1**. Он не обязан присутствовать в любом binary или Docker image. Помимо справочника, проверены официальные Ubuntu package pools: там есть пакеты модуля для **stable 1.30.6** и **mainline 1.31.8**. Значит, утверждения «только Plus» и «только mainline» неверны для этого среза. Наличие этих пакетов, однако, не проверяет установку на любой ОС или архитектуре.[^23][^24][^25][^26][^27]

В native-варианте администратор явно выбирает issuer и его directory URI, настраивает resolver, связывает `acme_certificate` с server и подключает `$acme_certificate` / `$acme_certificate_key` к SSL-директивам. По README тега 0.4.1 default challenge — HTTP-01, также поддерживается TLS-ALPN-01. DNS-01 в опубликованном наборе нет, wildcard не поддерживается. Это ограничение конкретного клиента ACME внутри nginx, а не запрет nginx обслуживать wildcard-сертификат, полученный снаружи.[^23][^24]

> “regular expressions and wildcards are not supported.”[^24]

Состояние тоже не следует оценивать по первому preview. Начиная с 0.2.0 каталог issuer создаётся по умолчанию; `state_path off` отключает сохранение. В 0.4.1 он содержит account key, сертификаты и приватные ключи. Поэтому цена native-пути — совместимый модуль, явная ACME-политика и постоянный защищённый каталог, а не обязательный внешний cron. При собственной сборке README отдельно требует согласованности nginx и SSL-реализации; это аргумент проверять совместимость, не доказательство нестабильности готовых пакетов.[^24][^25]

Второй путь — внешний Certbot; в корпусе закреплён User Guide **v5.9.0**. Он тоже автоматизирован: большинство установок уже получают scheduler продления. `--nginx` может устанавливать сертификат и менять webserver configuration; `certonly --webroot` позволяет получать сертификаты без остановки действующего webserver. Требование освободить порт в standalone-сценарии нельзя переносить на все способы работы Certbot.[^28]

Если конфигурацией nginx управляет сам администратор, предлагаемый конвейер — успешное продление, проверка конфигурации, graceful reload. Для действия только после фактического renewal руководство указывает `--deploy-hook`: нулевой код `certbot renew` бывает и когда продлевать ничего не требуется. Но это рекомендация для собственного workflow, не утверждение, что штатный nginx installer лишён автоматического применения сертификата.[^28]

nginx reload не равен restart контейнера. Master проверяет синтаксис и возможность применить конфигурацию, включая открытие logs и listeners. При неуспехе сохраняет старую; при успехе запускает новых workers, а старые перестают принимать соединения и обслуживают прежних клиентов. Живое соединение не переносится магически в новое поколение. Из этого следует эксплуатационный компромисс: долгоживущие потоки могут удерживать старые workers; `worker_shutdown_timeout` ограничивает ожидание ценой попытки закрыть оставшиеся соединения.[^29][^30]

> “Old worker processes close listen sockets and continue to service old clients.”[^29]

## 5. Data plane: defaults меняются, доверие само не появляется

Старые nginx-рецепты требуют особенно внимательного чтения. С **1.29.7** default `proxy_http_version` изменён на **1.1**, а `Connection` перестал отправляться upstream по умолчанию. Обе исследованные реализации — **1.30.6 и 1.31.8** — подтверждают это. В актуальной справке `proxy_set_header` при этом сохранился фрагмент с `Connection close`; для выбранных версий приоритет имеют tagged source и changelog.[^31][^32][^34]

> “the default value for "proxy_http_version" is "1.1"; the "Connection" proxy header is not sent by default anymore.”[^31]

Это не отменяет явную настройку WebSocket Upgrade: `Upgrade` и `Connection` — hop-by-hop заголовки, и документация nginx требует передавать их специально. Для обычных HTTP-запросов и Upgrade можно выбрать разные значения через `map`. Ещё одна независимая граница — idle timeout: отсутствие данных от upstream по умолчанию закрывает соединение через 60 секунд; это не максимальная общая продолжительность WebSocket, а основание согласовать heartbeat и `proxy_read_timeout`.[^33][^34]

У Caddy другой компромисс: `stream_close_delay` откладывает закрытие потоков при выгрузке proxy-конфигурации, по умолчанию задержки нет. Следовательно, обещание API «zero downtime» нельзя читать как гарантию сохранения каждого WebSocket. Конечная задержка помогает растянуть переподключения, но не делает поток бессрочно независимым от lifecycle handler. Наличие встроенных health checks также не означает, что они активны для любого upstream: документация отдельно задаёт условия их включения и исключает active checks для dynamic upstreams.[^9][^12][^13]

Автоматический TLS не удостоверяет присланный клиентом IP. Caddy по умолчанию не принимает на веру входные `X-Forwarded-For`, `X-Forwarded-Proto` и `X-Forwarded-Host`; использование прежних значений зависит от доверия непосредственному proxy. Для установки за CDN или LB документация рекомендует общую настройку `trusted_proxies`. Traefik на уровне entryPoint задаёт `forwardedHeaders.trustedIPs`; `insecure=true` означает доверять всегда и рекомендован только для тестов.[^12][^13][^17]

У nginx `$proxy_add_x_forwarded_for` добавляет `$remote_addr` к **уже входящему** XFF. Append не очищает цепочку от подделок. Если nginx — первый доверенный edge, разумно формировать значения из реального соединения, а приложение научить доверять только своему proxy. Если перед ним другой ingress, `set_real_ip_from` и `real_ip_header` определяют допустимых отправителей и источник замены адреса; `real_ip_recursive on` выбирает последний недоверенный адрес. Этот механизм не проверяет автоматически смысл `X-Forwarded-Proto` или Host.[^34][^35]

## 6. Как сравнивать цену изменения, а не длину файла

Следующая таблица — авторский синтез механизмов, не результат измерения трудозатрат. При постоянном наборе сервисов централизованное описание Caddy может быть удобнее provider-графа; при частом добавлении контейнеров перенос маршрута в labels может оправдать Traefik. nginx имеет смысл оценивать с уже выбранным native или внешним ACME workflow: сравнивать неопределённый конвейер с готовыми defaults некорректно.[^5][^14][^15][^23][^28]

| Вопрос владельца | Caddy | Traefik | nginx |
|---|---|---|---|
| Что связывает имя с TLS | Automation для известного имени[^5] | Router TLS и ссылка на resolver либо defaults entryPoint[^16][^17] | Issuer/сертификат модуля либо внешний клиент[^23][^28] |
| Какое состояние защищать | Certificate data отдельно от config autosave[^7] | ACME-файл и startup/routing policy[^14][^19] | State модуля либо состояние внешнего клиента[^24][^28] |
| Где дополнительная граница полномочий | Admin API[^9] | Provider и доступ к Docker API[^15] | Загрузка модуля или внешний установщик сертификата[^24][^28] |
| Что проверить после изменения | Активный config, autosave, внешний TLS[^5][^10] | Доставку события и наличие конкретного router[^20][^21][^22] | Применение поколения и поведение соединений[^29][^30] |

Предлагаемый порядок приёмки изменения состоит из разных проверок. Сначала сверяют исходное описание и выбранный путь обновления, затем проверяют факт принятия конфигурации, затем — конкретный маршрут, сертификат и ожидаемую идентичность клиента снаружи. Отдельно проверяют, что нужное состояние переживёт пересоздание контейнера. Причина разделения не абстрактная осторожность: Caddy может работать до готовности сертификатов, Traefik — пропустить некорректный router, nginx — успешно применить конфигурацию, не доказав здоровье backend.[^5][^10][^22][^29]

Для Caddy `validate` сильнее простой сериализации: он provisions modules, но не запускает конфигурацию. При этом отдельный процесс проверки может столкнуться с эксклюзивным ресурсом действующего экземпляра. Для Traefik проверка YAML не заменяет проверку routing graph и доставки fsnotify. Для nginx корректная конфигурация и graceful reload не подтверждают прикладной ответ. Поэтому один универсальный зелёный индикатор здесь был бы ложной моделью приёмки.[^11][^20][^22][^29]

## Дискуссионные вопросы и противоречия

**«Автоматический TLS против ручного nginx».** Эта позиция сохраняет смысл только для конкретной старой установки без автоматизации. Современные источники показывают native-модуль и автоматический Certbot workflow; различается размещение и явность конвейера. Аналогично ранние ограничения preview про отсутствие TLS-ALPN и default persistence нельзя переносить на nginx-acme 0.4.1: changelog фиксирует оба изменения в 0.2.0.[^23][^24][^25][^28]

**«Успех reload гарантирует рабочий сервис».** Caddy API обещает возврат к старому config при неудачной загрузке, но код отделяет успех переключения от успеха autosave, а reverse proxy — lifecycle потоков от listener availability. У Traefik parse failure до snapshot и семантическая ошибка router проходят разными путями. У nginx старые workers продолжают обслуживать старых клиентов. Это не взаимоисключающие описания: они относятся к разным единицам успеха.[^9][^10][^13][^21][^22][^29]

**«Общий сертификатный state даёт HA».** Caddy действительно документирует sharing ресурсов и координацию certificate management через общее storage, но это не репликация маршрутов и не резервный входящий адрес. В ACME-руководстве Traefik раздел HA направляет к distributed/external certificate management; там при этом сохранилась историческая формулировка про «Traefik 2.0». На неё нельзя опираться как на доказательство невозможности любой современной multi-instance топологии. Более узкий практический вывод: общий `acme.json` сам по себе не является обоснованным clustered ACME-протоколом.[^5][^10][^18][^19]

## Недостаточность данных

Корпус позволяет проверить конфигурационные механизмы, но не ранжировать скорость, RAM, частоту сбоев или время восстановления. Поиск ограничений был выполнен, однако сообщения об ошибках других версий не использованы как доказательство дефектов этих baseline. Нет стендового подтверждения renewal, fsnotify на выбранной файловой системе, draining под реальной нагрузкой и совместимости конкретного образа nginx с модулем.

Требуют отдельной проверки DNS-provider plugins и минимальные полномочия их ключей, реализация distributed locks выбранного Caddy storage, поведение всех клиентов при reconnect, а также полный lifecycle модулей при отказах. Часть документации Caddy и nginx изменяемая; отмеченные defaults и ветви обработки ошибок сверены с доступными tagged-файлами, но это не исчерпывающий аудит исходников. Набор первоисточников не является независимым исследованием эксплуатационного превосходства.

## Заключение

Для одного узла с небольшим стабильным набором приложений **Caddy — обоснованный исходный кандидат**, если нужен встроенный обычный HTTPS и приемлем централизованный control plane. Выгода — меньше явных связей certificate workflow, а не отсутствие состояния: certificate storage, autosave и доступ к API остаются обязанностями владельца. Для потоковых приложений отдельно проектируют reconnect при смене конфигурации.[^5][^7][^9][^13]

**Traefik оправдан, когда меняется состав контейнеров**, а routing metadata действительно удобнее хранить рядом с приложениями. Условие этой рекомендации — осознанный Docker API access, opt-in discovery и проверка итогового router TLS, включая отсутствие merge с entryPoint defaults. **nginx остаётся полноценным вариантом**, особенно при уже понятной политике proxy и сертификатов; оценивать его следует с официальным native ACME либо конкретным внешним клиентом, а не со стереотипом о ручном renewal.[^15][^17][^23][^28]

Главный критерий выбора: сможет ли единственный администратор объяснить, **кто имеет право изменить входящий маршрут, где лежат ключи и какое наблюдение доказывает успешность изменения**. По рассмотренным механизмам это более содержательный вопрос, чем число строк конфигурации; числовую разницу в эксплуатационной стоимости данный обзор не устанавливает.

## Quality Metrics

| Metric | Value |
|--------|-------|
| Sources found | 168 |
| Sources read | 41 |
| Sources cited | 35 |
| Academic sources | 0 |
| Official/documentation | 35 |
| Industry reports | 0 |
| News/journalism | 0 |
| Blog/forum | 0 |
| Citation coverage | 90% (46/51 содержательных абзацев) |
| Words (checker) | 3474 |
| Word-count scope | Checker включает библиографию и таблицы; основной текст до Quality Metrics — 2943 слова, в том числе 2113 русских слов |
| Counter-arguments searched | Yes |
| Runtime testing | Нет; документация и статическое чтение кода |
| Count units | Found — уникальные candidate URL без поисковых/API-запросов; read/cited — разные работы, не число URL или независимых исследований |
| Deduplication | Представления RFC, live/tagged руководств и одного proxy source для двух baseline объединены; категории типов разделяют множество cited |
| Evidence limits | Официальные источники — 100%; релевантные разделы, без abstract-only; не независимые измерения стоимости |

[^1]: Caddy project. «Release v2.11.9 · caddyserver/caddy». https://github.com/caddyserver/caddy/releases/tag/v2.11.9. 2026-11-05. Прочитано 2026-11-05.
[^2]: Traefik maintainers. «Release v3.7.17 · traefik/traefik». https://github.com/traefik/traefik/releases/tag/v3.7.17. 2026-10-30T08:32:41Z. Прочитано 2026-11-05.
[^3]: nginx project. «nginx: download». https://nginx.org/en/download.html. Прочитано 2026-11-05.
[^4]: Barnes, Hoffman-Andrews, McCarney, Kasten. «Automatic Certificate Management Environment (ACME)». https://www.rfc-editor.org/rfc/rfc8555.txt. 2019-03. Прочитано 2026-11-05.
[^5]: Caddy project. «Automatic HTTPS - Caddy Documentation». https://caddyserver.com/docs/automatic-https. Прочитано 2026-11-05.
[^6]: Caddy project. «caddy/modules/caddyhttp/autohttps.go at v2.11.9 · caddyserver/caddy · GitHub». https://github.com/caddyserver/caddy/blob/v2.11.9/modules/caddyhttp/autohttps.go. Прочитано 2026-11-05.
[^7]: Caddy project. «Conventions - Caddy Documentation». https://caddyserver.com/docs/conventions. Прочитано 2026-11-05.
[^8]: Caddy project. «Caddyfile Directives - Caddy Documentation». https://caddyserver.com/docs/caddyfile/directives. Прочитано 2026-11-05.
[^9]: Caddy project. «API - Caddy Documentation». https://caddyserver.com/docs/api. Прочитано 2026-11-05.
[^10]: Caddy project. «caddy/caddy.go at v2.11.9 · caddyserver/caddy · GitHub». https://github.com/caddyserver/caddy/blob/v2.11.9/caddy.go. Прочитано 2026-11-05.
[^11]: Caddy project. «Command Line - Caddy Documentation». https://caddyserver.com/docs/command-line. Прочитано 2026-11-05.
[^12]: Caddy project. «reverse_proxy (Caddyfile directive) - Caddy Documentation». https://caddyserver.com/docs/caddyfile/directives/reverse_proxy. Прочитано 2026-11-05.
[^13]: Caddy project. «caddy/modules/caddyhttp/reverseproxy/reverseproxy.go at v2.11.9 · caddyserver/caddy · GitHub». https://github.com/caddyserver/caddy/blob/v2.11.9/modules/caddyhttp/reverseproxy/reverseproxy.go. Прочитано 2026-11-05.
[^14]: Traefik maintainers. «Configuration Introduction¶». https://doc.traefik.io/traefik/v3.7/getting-started/configuration-overview/; текст тега v3.7.17: https://raw.githubusercontent.com/traefik/traefik/v3.7.17/docs/content/getting-started/configuration-overview.md. Прочитано 2026-11-05.
[^15]: Traefik maintainers. «Traefik & Docker¶». https://doc.traefik.io/traefik/v3.7/reference/install-configuration/providers/docker/; текст тега v3.7.17: https://raw.githubusercontent.com/traefik/traefik/v3.7.17/docs/content/reference/install-configuration/providers/docker.md. Прочитано 2026-11-05.
[^16]: Traefik maintainers. «Router». https://doc.traefik.io/traefik/v3.7/reference/routing-configuration/http/routing/router/; текст тега v3.7.17: https://raw.githubusercontent.com/traefik/traefik/v3.7.17/docs/content/reference/routing-configuration/http/routing/router.md. Прочитано 2026-11-05.
[^17]: Traefik maintainers. «EntryPoints». https://doc.traefik.io/traefik/v3.7/reference/install-configuration/entrypoints/; текст тега v3.7.17: https://raw.githubusercontent.com/traefik/traefik/v3.7.17/docs/content/reference/install-configuration/entrypoints.md. Прочитано 2026-11-05.
[^18]: Traefik maintainers. «Traefik & ACME Certificates Resolver | Traefik». https://doc.traefik.io/traefik/v3.7/reference/install-configuration/tls/certificate-resolvers/acme/; текст тега v3.7.17: https://raw.githubusercontent.com/traefik/traefik/v3.7.17/docs/content/reference/install-configuration/tls/certificate-resolvers/acme.md. Прочитано 2026-11-05.
[^19]: Traefik maintainers. «traefik/pkg/provider/acme/local_store_unix.go at v3.7.17 · traefik/traefik · GitHub». https://github.com/traefik/traefik/blob/v3.7.17/pkg/provider/acme/local_store_unix.go. Прочитано 2026-11-05.
[^20]: Traefik maintainers. «File¶». https://doc.traefik.io/traefik/v3.7/reference/install-configuration/providers/others/file/; текст тега v3.7.17: https://raw.githubusercontent.com/traefik/traefik/v3.7.17/docs/content/reference/install-configuration/providers/others/file.md. Прочитано 2026-11-05.
[^21]: Traefik maintainers. «traefik/pkg/provider/file/file.go at v3.7.17 · traefik/traefik · GitHub». https://github.com/traefik/traefik/blob/v3.7.17/pkg/provider/file/file.go. Прочитано 2026-11-05.
[^22]: Traefik maintainers. «traefik/pkg/server/router/router.go at v3.7.17 · traefik/traefik · GitHub». https://github.com/traefik/traefik/blob/v3.7.17/pkg/server/router/router.go. Прочитано 2026-11-05.
[^23]: nginx project. «Module ngx_http_acme_module». https://nginx.org/en/docs/http/ngx_http_acme_module.html. Прочитано 2026-11-05.
[^24]: nginx project. «nginx-acme». https://raw.githubusercontent.com/nginx/nginx-acme/v0.4.1/README.md. 2026-05-01. Прочитано 2026-11-05.
[^25]: nginx project. «Changelog». https://raw.githubusercontent.com/nginx/nginx-acme/v0.4.1/CHANGELOG.md. 2026-05-01. Прочитано 2026-11-05.
[^26]: nginx project. «Index of /packages/ubuntu/pool/nginx/n/nginx-module-acme/». https://nginx.org/packages/ubuntu/pool/nginx/n/nginx-module-acme/. Прочитано 2026-11-05.
[^27]: nginx project. «Index of /packages/mainline/ubuntu/pool/nginx/n/nginx-module-acme/». https://nginx.org/packages/mainline/ubuntu/pool/nginx/n/nginx-module-acme/. Прочитано 2026-11-05.
[^28]: Certbot project. «User Guide». https://raw.githubusercontent.com/certbot/certbot/v5.9.0/certbot/docs/using.rst. Прочитано 2026-11-05.
[^29]: nginx project. «Controlling nginx». https://nginx.org/en/docs/control.html. Прочитано 2026-11-05.
[^30]: nginx project. «Core functionality». https://nginx.org/en/docs/ngx_core_module.html. Прочитано 2026-11-05.
[^31]: nginx project. «Changes with nginx 1.31.8                                        21 Oct 2026». https://nginx.org/en/CHANGES. 2026-10-21. Прочитано 2026-11-05.
[^32]: nginx project. «nginx/src/http/modules/ngx_http_proxy_module.c at release-1.30.6 · nginx/nginx · GitHub». https://raw.githubusercontent.com/nginx/nginx/release-1.30.6/src/http/modules/ngx_http_proxy_module.c; «nginx/src/http/modules/ngx_http_proxy_module.c at release-1.31.8 · nginx/nginx · GitHub». https://raw.githubusercontent.com/nginx/nginx/release-1.31.8/src/http/modules/ngx_http_proxy_module.c. Прочитано 2026-11-05.
[^33]: nginx project. «WebSocket proxying». https://nginx.org/en/docs/http/websocket.html. Прочитано 2026-11-05.
[^34]: nginx project. «Module ngx_http_proxy_module». https://nginx.org/en/docs/http/ngx_http_proxy_module.html. Прочитано 2026-11-05.
[^35]: nginx project. «Module ngx_http_realip_module». https://nginx.org/en/docs/http/ngx_http_realip_module.html. Прочитано 2026-11-05.
