---
title: "Quadlet вместо Compose: что systemd даёт контейнерам и чего не даёт"
date: 2026-11-20T09:37:00+03:00
description: "Когда перенос с Docker Compose на Podman Quadlet упрощает запуск и восстановление на одном Linux-хосте, а когда лишь усложняет описание стека."
showToc: true
tocOpen: true
---

## Аннотация

Quadlet хорош там, где контейнер должен вести себя как обычная служба Linux: стартовать при загрузке, ждать нужный mount и восстанавливаться по правилам systemd. Но `active` ещё не означает, что приложение отвечает, а откат образа не возвращает схему базы. Docker Compose проще, когда единица работы — весь проект: его нужно поднять, проверить и убрать одной командой, не раскладывая конфигурацию по юнитам хоста.[^1][^2][^3][^4][^5]

Данные на **2026-11-20**. Допущение: один Linux-хост с cgroup v2, постоянно работающие API и база данных, периодическое задание. Срез: **Podman 6.2.0**, **systemd 262.2** и **Docker Compose 5.8.0** с Docker Engine. Здесь сравниваются документированное поведение и код этих версий, а не быстродействие. Контейнеры не запускались; готовность и восстановление предложено проверить на отдельной машине перед переносом.[^6][^7][^8][^1]

## Введение

В [сравнении NixOS, Ansible и Compose](/articles/nixos-ansible-compose/) речь шла об уровнях конфигурации и отката. В [обзоре cgroup v2](/articles/homelab-cgroup-memory-pressure-budgets/) — о том, кто расходует ресурсы хоста и что происходит при их исчерпании. Здесь вопрос другой: **что изменится после переноса, если база запустится медленно, приложение зависнет, а следующая версия образа не заработает?** Чтобы ответить, надо отдельно проследить, кто поднимает контейнер, кто объявляет его готовым и кто принимает решение о повторном запуске.[^1][^2][^9][^10]

Ветка Podman 6.1 началась не осенью: релиз 6.1.0 вышел 12 августа. Для этого обзора важнее ноябрьский Podman 6.2.0: в нём появился `SetMountsDependency=` и исправлен сбой на стыке `Notify=healthy` и таймаута запуска. Compose 5.8.0, в свою очередь, добавил задания по расписанию, хотя для них требуется поддержка со стороны Engine. Сравнивать нынешние инструменты по старому признаку «в Compose нет планировщика» уже нельзя.[^11][^6][^7]

## Что именно становится юнитом

Quadlet — генератор, а не постоянно работающий диспетчер поверх systemd. При загрузке менеджера и при `daemon-reload` он читает файлы вроде `api.container`, `app.network` и `db-data.volume` и создаёт соответствующие `.service`. Параметры `[Container]` превращаются в аргументы Podman, а обычные настройки `[Unit]` и `[Service]` остаются частью контракта systemd. В коде генератора видно, что для контейнера это не только команда `podman run`: предусмотрен и cleanup через `ExecStopPost=`, в том числе на случай гибели conmon. Редактировать надо входной Quadlet, не полученный `.service`.[^1][^12][^13]

Сгенерированный сервис не включается на автозапуск обычным `systemctl enable`: генератор сам применяет поддерживаемые ключи секции `[Install]`. Например, `WantedBy=default.target` в rootless Quadlet привязывает его к пользовательскому target. Если после `daemon-reload` нужного сервиса нет, начинать стоит с `podman-system-generator --user --dryrun`: ошибка может означать, что файл найден, но установленный генератор не понимает новый ключ. И наоборот, появление новой версии `.service` после `daemon-reload` не подтверждает, что работающий контейнер уже пересоздан: перечитать описание и запустить сервис — разные действия.[^1][^12]

В Compose исходная единица — проект. Сервисы, сети и тома описываются в одной модели; `docker compose up` применяет её и при изменении образа или конфигурации пересоздаёт затронутые контейнеры, сохраняя смонтированные тома. У detached-запуска другой контракт: CLI заканчивает работу, контейнеры остаются под Docker Engine. `podman compose` тоже не является Quadlet: это обёртка над внешним Compose provider, которому передаются параметры и доступ к сокету Podman. Если задача в замене runtime без переписывания стека, совместимость этого пути стоит проверять отдельно, на выбранном provider.[^4][^5][^14]

В исследовании Eng, Hindle и Stroulia разобраны 527 Compose-подобных файлов из 218 GitHub-проектов; в выборке встречались `extends`, override-файлы и генерация YAML. Это наблюдение за конфигурациями отобранных проектов, а не замер надёжности и не сравнение с Quadlet. Но оно объясняет, почему миграция сложнее замены синтаксиса: если upstream поставляет один проект с несколькими режимами, местные юниты становятся ещё одним описанием, которое нужно обновлять вместе с upstream.[^15][^4]

## Сначала порядок, потом готовность

В systemd `After=` отвечает за порядок, но не добавляет другую службу в запуск; `Wants=` или `Requires=` втягивает её в транзакцию, но само по себе не задаёт порядок. Авторы справочника называют эти зависимости «independent of and orthogonal to the requirement dependencies». Если для API задать `Requires=db.container` и `After=db.container`, Quadlet переведёт ссылку на сгенерированный сервис и запуск API будет ждать окончания запуска базы. Неудачный старт базы заблокирует такой старт API. **Что считать окончанием запуска**, решает уже тип сервиса и его сигнал готовности.[^1][^16][^2]

Для `.container` Quadlet 6.2.0 по умолчанию генерирует `Type=notify`, но `Notify=` в Quadlet по умолчанию равно `false`. В этой комбинации используется `--sdnotify=conmon`: готовность для systemd означает, что контейнер запущен. `Notify=true` оставляет уведомление приложению, которое должно отправить `READY=1`; если оно не умеет этого делать, такое переключение само по себе ничего не исправляет. `Notify=healthy` использует встроенный или заданный Podman healthcheck и посылает уведомление после перехода в healthy. Старту API полезен только тест, который проверяет действительно нужную ему операцию базы, а не просто наличие процесса.[^1][^2][^17][^13]

У Compose аналогичная граница выражена прямо в проекте: обычный `depends_on` задаёт порядок старта, а условие `service_healthy` ждёт healthcheck зависимости. Есть и `service_completed_successfully` для зависимости с конечным результатом, например одноразовой подготовки схемы. Это условия выполнения команды, а не обещание заново применять граф при каждом изменении здоровья. `docker compose up -d --wait` полезен для приёмки выкладки: с healthcheck команда ждёт healthy, а там, где проверки нет, «running» может быть достаточным. Не стоит считать нулевой exit code доказательством успешного запроса к API.[^9][^5][^18][^19]

Важно согласовать дедлайны. На старте Quadlet может ещё тянуть образ, а база — восстанавливаться до первой успешной проверки. `TimeoutStartSec=` сервиса должен учитывать оба этапа, если они входят в её запуск. Для `Type=oneshot` таймаут запуска по умолчанию, напротив, отключён. В трекере Podman описан случай на 5.6.2, когда `HealthStartPeriod` был длиннее `TimeoutStartSec`, а systemd убивал ещё запускающийся контейнер; в 6.2.0 есть конкретный фикс по этому issue. Из него не следует, что можно назначить любой дедлайн и считать readiness проверенной.[^1][^2][^20][^6]

## Кто поднимает сервис после сбоя

`Notify=healthy` отвечает только за старт. Позднее Podman может пометить контейнер unhealthy, но действие `HealthOnFailure` по умолчанию — `none`. Если приложение не завершится само, у systemd не обязательно появится причина перезапустить юнит. Схема с `HealthOnFailure=kill` даёт systemd событие, на которое может отреагировать `Restart=`. Для управляемого systemd контейнера документация Podman рекомендует использовать именно `[Service] Restart=`, а не параллельный `podman run --restart`. Повторные старты ограничиваются `StartLimitIntervalSec=` и `StartLimitBurst=`; выставляя их, администратор задаёт предел попыток в выбранном временном окне, прежде чем потребуется вмешательство.[^1][^21][^22][^16][^2]

В Compose важно не перепутать два `restart`. Ключ `restart:` самого сервиса задаёт политику контейнера в Engine. `restart: true` **внутри** `depends_on` распространяет явную операцию Compose, например `docker compose restart db`, на зависимый сервис. В документации есть точное ограничение: «excludes automated restart by the container runtime». В исходниках Compose 5.8.0 команда `restart` выбирает рёбра с этим флагом из проектного графа; их наличие не превращает Engine в контроллер всего приложения. Если база сама перезапустилась после падения, API по-прежнему должен уметь переподключиться либо обнаружить, что не может обслуживать запросы.[^10][^18][^23]

В systemd тоже не стоит связывать всё со всем. `PartOf=` передаёт остановку и рестарт в одном направлении; оно не означает «запусти весь стек». `BindsTo=` вместе с `After=` привязывает активность одного юнита к другому гораздо жёстче, включая неожиданную деактивацию. Для API, умеющего переподключаться, это может превратить короткий сбой базы в ненужную остановку API. Пара `BindsTo=` и `After=` полезна, когда работа без зависимости недопустима, но всё равно работает со **статусом юнита**, а не с результатом SQL-запроса. Сценарий «остановить при падении и запустить обратно после восстановления» следует проверять целиком, а не выводить из одного ребра.[^1][^16][^2]

## Rootless, загрузка хоста и расписание

Rootless Quadlet живёт в пользовательском systemd, а не в системном менеджере с добавленным `User=`. Например, файлы можно положить в `~/.config/containers/systemd/`. Для запуска до первого входа и работы после выхода нужен живой пользовательский менеджер: `loginctl enable-linger` позволяет создать его при загрузке и сохранить после logout. Это отдельно от выбора `WantedBy=`: linger поднимает менеджер, а `[Install]` подключает конкретную службу. Проверка из уже открытой SSH-сессии не отвечает на вопрос, поднимется ли сервис без этой сессии.[^1][^24]

Rootful Quadlet добавляет зависимость от `network-online.target`; rootless использует `podman-user-wait-network-online.service`. В поставляемом для 6.2.0 helper видно, что он ждёт `systemctl is-active network-online.target`, а не делает DNS-запрос или pull. И сам target — одноразовый рубеж загрузки: после старта systemd «will not track the online state of the system anymore». Поэтому для хоста с нестабильным каналом полезно отдельно оценить, нужно ли тянуть образы во время загрузки и может ли сервис подняться с локальным образом. Отключение добавляемых Quadlet зависимостей через `[Quadlet] DefaultDependencies=false` не создаёт новой проверки связи.[^1][^25][^26]

За локальные данные лучше отвечать явно. По ссылке на `db-data.volume` Quadlet добавляет зависимость от юнита тома, но имя самого тома по умолчанию будет с префиксом `systemd-`, если не задан `VolumeName=`. В 6.2.0 `SetMountsDependency=` позволяет выбрать `RequiresMountsFor=`, `WantsMountsFor=` или не добавлять зависимость для исходных путей mount. Это рычаг для внешнего диска или сетевого mount, а не подтверждение правильного содержимого каталога. До переключения стоит проверить, какой том фактически смонтирован, под каким UID он доступен и читается ли из него ожидаемая база.[^1][^16][^6]

Для периодического экспорта Quadlet можно соединить задачу `Type=oneshot` с `.timer`; `Persistent=true` у календарного таймера нужен, если следует наверстать пропущенное срабатывание после простоя. Не надо оставлять периодическую задачу в `active` через `RemainAfterExit=yes`: активный сервис при следующем срабатывании таймера не перезапустится. В Compose 5.8.0 альтернатива — верхнеуровневый `jobs:`. Согласно релизу, для расписания нужен Engine 29.10+ с включённым jobs extension (по умолчанию выключен), `up` или `create` регистрирует задания в Engine, а `down` снимает их. Выбор здесь — где должен жить жизненный цикл задания: вместе с проектом или вместе с хостом.[^1][^27][^7]

## Обновление: зачем проверять не только новый образ

`AutoUpdate=registry` не меняет текст Quadlet: `podman auto-update` сравнивает digest локального и опубликованного образов по полной ссылке, скачивает обновление и перезапускает юнит. У `local` источник сравнения — локальное хранилище образов. Поставляемый `podman-auto-update.timer` настроен на ежедневный запуск со случайной задержкой до 900 секунд и `Persistent=true`, а `--dry-run` показывает кандидатов без скачивания и рестартов. Фильтрация контейнеров не обещает рестарт строго одного контейнера: граница операции — его сервис, а связанные юниты могут быть затронуты.[^3][^28][^27]

У `--rollback` в Podman 6.2.0 значение по умолчанию `true`. Условие сформулировано узко:[^3]

> If restarting a systemd unit after updating the image has failed, rollback to using the previous image and restart the unit another time.[^3]

При первом `READY` от conmon рестарт может уже считаться успешным, когда приложение ещё не успело упасть. Более содержательный `READY=1` от приложения или `Notify=healthy` с проверкой нужны, чтобы отказ стал виден *во время запуска*. Если новый процесс успел применить миграцию и затем не прошёл readiness, возврат образа не вернёт прежнее состояние тома. Поэтому автоматический rollback полезен для отказов старта, но не заменяет сохранённую копию данных и проверку совместимости миграций в обратную сторону.[^1][^2][^3][^17][^29]

У Compose этапы проще разделить вручную: `pull` скачивает образы, но не запускает из них контейнеры, а `up` применяет изменения. Для базы разумен управляемый выпуск с закреплённым digest, резервной копией и внешней проверкой до подтверждения выкладки. Это применимо и к Quadlet: digest идентифицирует содержимое образа, а не данные приложения. При переносе не следует использовать `docker compose down -v` как способ «аккуратно остановить» старый стек: `-v` удаляет и объявленные именованные тома, и присоединённые анонимные. Сохранить том и восстановить согласованную базу из него — тоже не одно и то же.[^30][^5][^31][^29]

## Дискуссионные вопросы и противоречия

**«Quadlet заменяет Compose».** Да, если за этими словами стоит перенос постоянных служб под управление одного Linux-хоста, с таймерами и привязкой к mount. Нет, если требуется сохранить проект как переносимый артефакт с сетями, томами, overrides и командами для разработчиков. Quadlet проще для оператора, который управляет одним сервисом; Compose проще для команды, которая регулярно поднимает и разбирает проект целиком. Возможен промежуточный вариант: оставить Compose, а systemd поручить лишь старт проекта. Такой unit не получит по одному статусу systemd на каждый контейнер; разбирать внутренние сбои всё равно нужно по состоянию Engine и самого приложения.[^1][^2][^10][^4][^5][^15]

**«Если проверка упала, надо перезапустить».** Для зависшего одиночного процесса это может дать полезное восстановление. Если один и тот же healthcheck падает у всех экземпляров API из-за общей базы, рестарт API сам по себе базу не вернёт. Стартовую готовность, доступность внешних зависимостей и причину убить процесс лучше разделить. У Quadlet `Notify=healthy` и `HealthOnFailure=` — независимые решения; у Compose условие `service_healthy` и политика `restart:` тоже отвечают на разные вопросы. Это причина проверять поведение при сбоях, а не переносить значения из YAML в одноимённые поля.[^1][^21][^9][^10][^18]

## Недостаточность данных

Не найдено сопоставимого испытания, которое сравнивает Quadlet 6.2.0 и Compose 5.8.0 на одном хосте после холодной загрузки, потери БД и неудачной выкладки. Исследование Compose отвечает на вопрос о структуре конфигураций; отчёт об ошибке Podman показывает отдельный отказ readiness на старой версии. Из этих источников нельзя получить ни разницу во времени простоя, ни вероятность восстановления. Не проверялись также совместимость сторонних Compose providers и наличие нового jobs extension в пакетах конкретного дистрибутива.[^15][^20][^7][^14]

## Заключение

Перенос оправдан, если оператору нужны именованные службы systemd, собственные правила рестарта, запуск без интерактивного входа и зависимости от ресурсов хоста. Оставить Compose разумнее, если при обычной работе важнее одна модель проекта и быстрый подъём стека целиком, а приложению достаточно политики Engine и собственных переподключений. Выбирать между ними по одному зелёному старту или слову `healthy` не стоит.[^1][^16][^2][^24][^10][^4][^5]

Для приёмки достаточно нескольких осмысленных отказов на тестовой машине: перезагрузиться без входа в систему, дать базе стартовать медленнее API, уронить уже готовую базу, затем подать образ, который поднимает процесс, но не обслуживает запрос. Отдельно проверить возврат прежнего образа **с уже изменёнными данными** на копии тома. По каждому случаю записать не только состояние юнита или контейнера, но и отвечает ли API и кто вернул его в рабочее состояние. Этот тест выявляет разницу, ради которой вообще стоит переходить на Quadlet.[^1][^2][^24][^3][^9][^5]

## Quality Metrics

| Metric | Value |
|---|---:|
| Sources found | 76 |
| Sources read | 31 |
| Sources cited | 31 |
| Count unit | Found: уникальные URL кандидатов; read/cited: отдельные работы и документы |
| Academic sources | 1 |
| Official/documentation | 29 |
| Industry reports | 0 |
| News/journalism | 0 |
| Blog/forum | 1 |
| Citation coverage | 100% (29/29) |
| Main-text words | 2161 |
| Counter-arguments searched | Yes |
| Research rounds | 3 |
| Questions emerged | 5 |
| Questions resolved | 3 |
| Questions insufficient data | 2 |

[^1]: Podman contributors. «podman-systemd.unit(5)». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/docs/source/markdown/podman-systemd.unit.5.md
[^2]: systemd contributors. «systemd.service(5)». systemd v262.2. https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd.service.xml
[^3]: Podman contributors. «podman-auto-update(1)». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/docs/source/markdown/podman-auto-update.1.md.in
[^4]: Docker. «How Compose works». Docker Docs, 2026-11-20 (дата обращения). https://docs.docker.com/compose/intro/compose-application-model/
[^5]: Docker Compose contributors. «docker compose up». Docker Compose v5.8.0. https://raw.githubusercontent.com/docker/compose/v5.8.0/docs/reference/compose_up.md
[^6]: Podman contributors. «Release v6.2.0». GitHub, 2026-11-10. https://github.com/podman-container-tools/podman/releases/tag/v6.2.0
[^7]: Docker Compose contributors. «Release v5.8.0». GitHub, 2026-11-17. https://github.com/docker/compose/releases/tag/v5.8.0
[^8]: systemd contributors. «Release systemd-stable v262.2». GitHub, 2026-11-05. https://github.com/systemd/systemd/releases/tag/v262.2
[^9]: Docker. «Control startup and shutdown order in Compose». Docker Docs, 2026-11-20 (дата обращения). https://docs.docker.com/compose/how-tos/startup-order/
[^10]: Docker. «Start containers automatically». Docker Docs, 2026-11-20 (дата обращения). https://docs.docker.com/engine/containers/start-containers-automatically/
[^11]: Podman contributors. «Release v6.1.0». GitHub, 2026-08-12. https://github.com/podman-container-tools/podman/releases/tag/v6.1.0
[^12]: systemd contributors. «systemd.generator(7)». systemd v262.2. https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd.generator.xml
[^13]: Podman contributors. «quadlet.go». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/pkg/systemd/quadlet/quadlet.go
[^14]: Podman contributors. «podman-compose(1)». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/docs/source/markdown/podman-compose.1.md.in
[^15]: Kalvin Eng, Abram Hindle, Eleni Stroulia. «Patterns of Multi-Container Composition for Service Orchestration with Docker Compose». arXiv:2305.11293v2, 2024-05-08. https://arxiv.org/html/2305.11293v2
[^16]: systemd contributors. «systemd.unit(5)». systemd v262.2. https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd.unit.xml
[^17]: Podman contributors. «--sdnotify». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/docs/source/markdown/options/sdnotify.md
[^18]: Docker. «Define services in Docker Compose». Docker Docs, 2026-11-20 (дата обращения). https://docs.docker.com/reference/compose-file/services/
[^19]: Docker Compose contributors. «dependency_wait.go». Docker Compose v5.8.0. https://raw.githubusercontent.com/docker/compose/v5.8.0/pkg/compose/dependency_wait.go
[^20]: Podman issue tracker. «Quadlet: Container with `Notify=healthy` does not respect `HealthStartPeriod` larger than systemd `TimeoutStartSec`». Issue #27290, 2025-10-14. https://github.com/podman-container-tools/podman/issues/27290
[^21]: Podman contributors. «--health-on-failure». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/docs/source/markdown/options/health-on-failure.md
[^22]: Podman contributors. «--restart». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/docs/source/markdown/options/restart.md
[^23]: Docker Compose contributors. «restart.go». Docker Compose v5.8.0. https://raw.githubusercontent.com/docker/compose/v5.8.0/pkg/compose/restart.go
[^24]: systemd contributors. «loginctl(1)». systemd v262.2. https://raw.githubusercontent.com/systemd/systemd/v262.2/man/loginctl.xml
[^25]: systemd contributors. «systemd.special(7)». systemd v262.2. https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd.special.xml
[^26]: Podman contributors. «podman-user-wait-network-online.service». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/contrib/systemd/user/podman-user-wait-network-online.service
[^27]: systemd contributors. «systemd.timer(5)». systemd v262.2. https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd.timer.xml
[^28]: Podman contributors. «podman-auto-update.timer». Podman v6.2.0. https://raw.githubusercontent.com/podman-container-tools/podman/v6.2.0/contrib/systemd/system/podman-auto-update.timer
[^29]: Open Container Initiative. «OCI Content Descriptors». OCI Image Format v1.1.1. https://raw.githubusercontent.com/opencontainers/image-spec/v1.1.1/descriptor.md
[^30]: Docker Compose contributors. «docker compose pull». Docker Compose v5.8.0. https://raw.githubusercontent.com/docker/compose/v5.8.0/docs/reference/compose_pull.md
[^31]: Docker Compose contributors. «docker compose down». Docker Compose v5.8.0. https://raw.githubusercontent.com/docker/compose/v5.8.0/docs/reference/compose_down.md
