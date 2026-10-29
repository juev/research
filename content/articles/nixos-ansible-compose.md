---
title: "NixOS, Ansible и Docker Compose для homelab: уровни, откат, секреты и дрейф"
date: 2026-10-29T09:36:19+03:00
description: "Что на самом деле гарантируют NixOS, Ansible и Docker Compose в домашней инфраструктуре: границы версий, откат без общей атомарности, секреты, бэкапы и дрейф по первоисточникам."
showToc: true
tocOpen: true
---

## Аннотация

Обзор сравнивает три инструмента, которые в homelab часто ставят в один ряд: NixOS, Ansible и Docker Compose. По первоисточникам они работают на разных уровнях. NixOS описывает конфигурацию всей ОС и умеет переключаться на прошлую конфигурацию[^1]. Ansible выполняет задачи на хостах в момент запуска playbook и может запускаться по расписанию для периодического исправления[^9]. Compose описывает сервисы, сети и тома контейнерного приложения[^12]. Главный вывод: ни один из трёх не даёт общей атомарной транзакции «ОС + приложение + данные + секреты». Откат NixOS возвращает конфигурацию, но миграции базы откатываются отдельно[^1]. Compose при пересоздании контейнеров сохраняет тома[^14], поэтому возврат старого образа встречает уже изменённые данные. Ansible в прочитанной документации предлагает обработку ошибок через `rescue`[^6] и резервную копию отдельного файла[^11], но не общий откат.

Основа обзора — официальная документация: NixOS Manual 26.05, справочник Nix 2.32.8, страница nix.dev о flakes, README sops-nix, документация ansible-core 2.20, включая руководство по Vault, и Docker Docs по Compose, томам, секретам и образам. К ней добавлена одна ветка форума NixOS Discourse, она используется как иллюстрация, а не как спецификация[^20]. Все процитированные страницы прочитаны 29 октября 2026 года, цитаты сверены с текстом страниц[^1][^5][^12][^24]. Академических работ и замеров в выборке нет. Поэтому выводы касаются гарантий из документации, а не надёжности на практике.

## Введение

**Актуальность.** Типичный домашний сервер совмещает три слоя: ОС с системными сервисами, контейнерные приложения и их данные. Выбор между NixOS, Ansible и Compose часто подают как выбор «декларативного инструмента», хотя декларативность у них разная. NixOS собирает новую конфигурацию и делает её загрузочной по умолчанию[^1]. Ansible в check mode лишь моделирует изменения[^5]. Compose пересоздаёт контейнеры при смене конфигурации или образа[^14]. Отсюда разные ответы на вопросы, которые возникают после неудачного обновления: что откатится, а что нет.

**Цель** — по документации описать, какие гарантии воспроизводимости, отката и защиты секретов даёт каждый инструмент, где эти гарантии заканчиваются и как совмещать инструменты на одном хосте[^1][^9][^14].

**Границы.** Обзор не сравнивает производительность и не измеряет время развёртывания: таких данных в собранных источниках нет. За рамками остаются Kubernetes, Swarm и облачные сервисы. Режим `deploy` в Compose упомянут только как необязательная часть спецификации[^19]. Ansible Vault и секреты Compose разобраны в разделе 6 по официальной документации[^22][^24]. Документацию конкретных средств бэкапа баз данных никто не открывал, поэтому этот вопрос вынесен в раздел о недостатке данных.

## 1. Границы версий на 29 октября 2026

Тезис: каждая гарантия в этом обзоре привязана к конкретной версии документации, и у всех трёх инструментов поведение меняется между релизами[^2][^5][^12].

NixOS Manual, открытый по адресу `stable`, имеет заголовок «Version 26.05»[^1]. Стабильный канал там назван так: «Stable channels, such as nixos-26.05». Он получает «only get conservative bug fixes and package upgrades». Срок жизни канала сформулирован без даты: «generally maintained until the next stable branch is created»[^1]. Для homelab это значит, что дату перехода на следующий релиз нужно отслеживать самостоятельно.

Справочник `nix flake` относится к Nix 2.32.8 и начинается с предупреждения: «This program is experimental and its interface is subject to change»[^2]. Страница nix.dev о flakes добавляет, что функция требует Nix 2.4 и что «Flakes are an experimental extension format with outstanding issues»[^3]. Там же сказано, что с NixOS 26.05 конфигурации можно загружать из единой точки входа `system.nix`[^3]. Получается, что воспроизводимость через `flake.lock` опирается на экспериментальный интерфейс.

Документация Ansible, которую читали исследователи, относится к ansible-core 2.20. На каждой из семи страниц, которые открыл исследователь Ansible, висит предупреждение о релизе 2.19: «The ansible-core 2.19 release has made significant templating changes that might require you to update playbooks and roles»[^5]. Для homelab с давно написанными ролями это прямой риск при обновлении управляющей машины, даже если сами хосты не менялись.

У Compose граница проходит по формату файла. Справочник утверждает, что «Legacy versions 2.x and 3.x of the Compose file format were merged into the Compose Specification». Спецификация реализована в «versions 1.27.0 and above (also known as Compose v2)» Docker Compose CLI[^12]. Там же оговорено, что Compose Specification на Docker Docs — это реализация Docker Compose, а не вся спецификация[^12]. В справочнике `docker compose up` описаны хуки `pre_start`[^14], но версия CLI, с которой они появились, на открытых страницах не указана.

Вывод раздела: сравнение «NixOS против Ansible против Compose» имеет смысл только с указанием версий. Экспериментальный статус flakes и изменения шаблонизации в ansible-core 2.19 — две самые заметные границы на дату обзора[^3][^5].

## 2. NixOS: воспроизводимая конфигурация и откат поколений

Тезис: NixOS действительно делает откат системной конфигурации рутинной операцией, но откатывается именно конфигурация[^1].

Основной цикл описан в руководстве так. Команда `nixos-rebuild switch` нужна «to build the new configuration, make it the default configuration for booting, and try to realise the configuration in the running system (e.g., by restarting system services)»[^1]. Сразу за этим идёт предупреждение: команда «doesn't start/stop user services automatically»[^1]. Слово «try» здесь важно: переключение работающей системы — попытка, а не транзакция.

Режимы проверки различаются по риску, и `nixos-rebuild test` к безрисковым не относится. Он нужен «to build the configuration and switch the running system to it, but without making it the boot default»[^1]. То есть новая конфигурация активируется на работающей машине: перезапускаются сервисы, меняются юниты и монтирования. Руководство так и пишет о действии `test`: текущая система инспектируется, и вычисляются действия для переключения на новую[^1]. Страховка в `test` одна: загрузочная конфигурация остаётся прежней. Руководство прямо допускает, что новая конфигурация «locks up your machine», и предлагает выход «you can just reboot to get back to a working configuration»[^1]. Если активация сломала сеть или SSH, удалённый хост станет недоступен. Перезагрузить его тогда можно только через консоль, IPMI или другой внешний доступ. Это вывод из описания режима, а не формулировка руководства.

Без активации работают другие режимы. `nixos-rebuild build` собирает конфигурацию «but nothing more»[^1]. Действие `dry-activate` «does not really perform the actions but rather prints what it would do if you called it with test»[^1]. `nixos-rebuild build-vm` собирает виртуальную машину с той же конфигурацией, но «The VM does not have any data from your host system»[^1]. Эта оговорка хорошо показывает границу модели: конфигурация переносится, данные — нет.

Откат описан двумя путями. Первый — загрузчик: «the GRUB boot manager allows you to boot into any previous configuration that hasn't been garbage-collected»[^1]. Второй — переключение в работающей системе через `nixos-rebuild switch --rollback`[^1]. Возможность ограничена сборкой мусора: `nix-collect-garbage -d` «deletes old roots, removing the ability to roll back to them»[^1]. Агрессивная очистка диска в homelab тихо сокращает глубину отката.

Граница с данными видна на примере Akkoma. Руководство предупреждает, что после запуска Akkoma «any migrations applied by Akkoma have to be rolled back before the database can be used again with Pleroma»[^1]. Миграцию нужно откатывать отдельной командой `pleroma_ctl ecto.rollback`[^1]. Значит, возврат к прошлому поколению NixOS сам по себе схему базы не возвращает. Это вывод из примера руководства, а не общая формулировка документации. Но ни один из прочитанных источников не утверждает обратного.

Воспроизводимость сборки опирается на lock-файл. Справочник Nix пишет: «To ensure reproducibility, Nix will automatically generate and use a lock file called flake.lock»[^2]. nix.dev уточняет пределы. Flakes по умолчанию работают в pure mode, однако «Even in pure mode, reproducibility is not actually guaranteed»[^3]. Если зависимости не переопределены через `follows`, возможны «multiple versions of the same dependency» и «outdated dependencies»[^3].

Наконец, NixOS допускает императивные изменения рядом с декларативной конфигурацией. `nix-env -iA` ставит пакет в профиль, и такие пакеты не затрагиваются при обновлении системы: «this is the crucial difference with the declarative style of package management»[^1]. Для дрейфа это важно: декларативная конфигурация не исключает ручных изменений на том же хосте. Переход к Ansible — это переход от модели «собрать систему целиком» к модели «выполнить задачи по списку».

## 3. Ansible: идемпотентность задач, check mode и дрейф

Тезис: идемпотентность в Ansible — свойство отдельных модулей и задач, а не гарантия всего playbook[^7][^8].

Модуль `command` по определению произволен. В документации сказано, что команда «is arbitrary and cannot be subject to the check mode semantics»[^7]. Обходной путь — параметры `creates`/`removes`: если файл из `creates` уже существует, «this step will not be run»[^7]. Без этих параметров задача в check mode пропускается: «If these are not supplied, the task will be skipped»[^7]. Идемпотентность такой задачи целиком на авторе playbook.

Даже стандартные модули оговаривают исключения. У модуля `apt` есть прямое предупреждение: «setting allow_downgrade=true can make this module behave in a non-idempotent way»[^8]. Для homelab, где откат пакета часто делают именно понижением версии, это ограничение существенно.

Check mode полезен, но его возможности документация описывает трезво: «Check mode is just a simulation»[^5]. Он не выдаёт результата для задач с условиями на зарегистрированных переменных. А модули без поддержки режима «report nothing and do nothing»[^5]. Поэтому чистый вывод `--check --diff` не доказывает, что реальный запуск пройдёт так же.

Ошибки обрабатываются блоками `rescue` и `always`, похожими на исключения[^6]. Если `rescue` отработал успешно, Ansible «reverts the failed status of the original task» и продолжает play[^6]. Отменяется статус задачи, а не её последствия на хосте. При этом «Errors caused by invalid task definitions and unreachable hosts do not trigger the rescue or always sections of a block»[^6]. Компенсирующие действия, если они нужны, пишет сам автор, и при потере связи с хостом они не выполнятся.

Недоступные хосты выпадают из запуска: Ansible «marks that host as 'UNREACHABLE' and removes it from the list of active hosts for the run»[^10]. Директива `ignore_errors` не спасает от ошибок соединения и синтаксиса[^10]. Итог прогона нужно читать по каждому хосту: часть машин может остаться на старой конфигурации.

Для отдельных файлов есть страховка. Параметр `backup` модуля `template` создаёт копию «so you can get the original file back if you somehow clobbered it incorrectly»[^11]. Параметр `validate` проверяет файл до копирования на место[^11]. Это откат одного файла, а не пакетов, сервисов или данных.

Дрейф Ansible по умолчанию не отслеживает: он приводит хост к описанию в момент запуска. Документация `ansible-pull` предлагает инвертировать модель: узлы сами забирают playbook из репозитория по cron. Это «useful both for extreme scale-out and periodic remediation»[^9]. Флаг `--only-if-changed` запускает playbook, только если репозиторий обновился[^9]. Но при этом флаге ручная правка на хосте до следующего коммита не исправляется. Это вывод из описания флага, на практике не проверен.

Ansible хорошо закрывает хосты, которые не являются NixOS, и поведение «между запусками» он не контролирует: исправление происходит только при следующем запуске[^9]. Следующий слой — само приложение в контейнерах.

## 4. Docker Compose: стек приложения, образы и тома

Тезис: Compose отвечает за жизненный цикл контейнеров приложения. Воспроизводимость здесь зависит от того, как указаны образы, а сохранность данных — от томов[^13][^16].

Обновление в Compose — это пересоздание. Справочник `docker compose up` описывает поведение так. Если конфигурация сервиса или образ изменились после создания контейнера, команда «picks up the changes by stopping and recreating the containers (preserving mounted volumes)»[^14]. Тома переживают обновление по замыслу. Поэтому откат образа на прошлую версию не откатывает данные, которые новая версия уже изменила.

Именованный том создаётся один раз: «Otherwise, the existing volume is used and is recreated if it's manually deleted outside of Compose»[^13]. Тома с `external: true` живут отдельно: «its lifecycle is managed outside of that of the application»[^13]. Пример в той же документации монтирует том базы во второй сервис, «so that it can be periodically backed up»[^13]. Бэкап Compose не делает сам, его нужно описать как отдельный сервис или процесс.

`docker compose down` по умолчанию удаляет контейнеры и сети, но не тома. Оговорка про анонимные тома показывает ловушку: они не удаляются, но «as they don't have a stable name, they are not automatically mounted by a subsequent up»[^15]. Для данных документация советует «explicit paths as bind mounts or named volumes»[^15]. Флаг `-v` удаляет и именованные, и анонимные тома[^15]. На хосте с ценными данными это самая опасная команда в обычном цикле.

Воспроизводимость образов зависит от ссылки. Docker прямо пишет: «Image tags are mutable». Тег вроде `alpine:3.21` через три месяца может указывать на другую сборку, и «you're not guaranteed to get the same for every build»[^16]. Закрепление по digest решает это: «you're guaranteed to always use the same image version, even if a publisher replaces the tag»[^16]. Страница о digest называет его «immutable» и уточняет, что у многоплатформенного образа свой digest на каждую платформу, плюс отдельный digest списка манифестов[^17]. Закрепить digest в Compose можно и без ручного поиска: у `docker compose config` есть флаги `--resolve-image-digests` («Pin image tags to digests») и `--lock-image-digests` («Produces an override file with image digests»)[^28].

Гарантия digest касается только образа. Он не фиксирует содержимое томов, версии ядра, Docker Engine и самого Compose на хосте, файлы секретов и окружения рядом с `compose.yaml`, состояние внешних сервисов. Ни одна из прочитанных страниц не обещает, что одинаковые digest дают одинаковый работающий стек. Тома по замыслу живут вне жизненного цикла контейнера: «A volume's contents exist outside the lifecycle of a given container»[^21]. Поэтому два хоста с одним и тем же `compose.yaml` и одними digest могут вести себя по-разному из-за данных и окружения. Это вывод из описанных границ, а не замер.

Готовность зависимостей — частая причина «плавающих» сбоев после обновления. По умолчанию «Compose does not wait until a container is "ready", only until it's running»[^18]. Для базы данных нужен `healthcheck` и `depends_on` с условием `service_healthy`[^18]. Механизм `rollback_config` описан в разделе `deploy`, но сам раздел — «an optional part of the Compose Specification»[^19]. Описан он в терминах реплик и узлов. Применяет ли его однохостовый `docker compose up`, на прочитанных страницах не сказано, поэтому рассчитывать на него в homelab по этим источникам нельзя.

Compose хорошо фиксирует состав стека, а закрепление по digest делает воспроизводимым выбор образов[^16][^28]. Воспроизводимость полного стека из этого не следует: данные в томах и состояние хоста остаются вне её[^14][^21]. Это подводит к сравнению уровней.

## 5. Сравнение уровней

Тезис: инструменты пересекаются меньше, чем кажется. Правильный вопрос — не «что выбрать», а «какой слой каким инструментом описан»[^1][^9][^12].

| Слой | NixOS | Ansible | Compose |
|---|---|---|---|
| Что описывает | Конфигурацию ОС и системных сервисов[^1] | Задачи, выполняемые на хостах[^9] | Сервисы, сети, тома приложения[^12] |
| Фиксация версий | `flake.lock`, интерфейс экспериментальный[^2] | На прочитанных страницах не описана; `allow_downgrade` ломает идемпотентность[^8] | Digest образа вместо тега; фиксирует образ, а не тома и хост[^16][^21] |
| Предпросмотр | `build`, `dry-activate`, `build-vm`; `test` уже активирует систему[^1] | `--check`, «just a simulation»[^5] | Нет на прочитанных страницах |
| Откат | Прошлое поколение, если не удалено GC[^1] | `rescue` и `backup` отдельного файла[^6][^11] | Прошлый образ, тома сохраняются[^14] |
| Данные | Вне модели, миграции отдельно[^1] | Не управляет без явных задач[^11] | Тома переживают пересоздание[^13] |
| Дрейф | Императивный `nix-env` возможен[^1] | Периодический `ansible-pull`[^9] | Пересоздание при изменении описания[^14] |
| Секреты | Nix store читается всеми; шифрование через sops-nix[^1][^4] | Vault шифрует переменные и файлы, только «data at rest»[^24][^25] | Файл в `/run/secrets/` для выбранных сервисов, без заявленного шифрования[^22] |

Из таблицы следуют два наблюдения. Во-первых, «откат» у трёх инструментов означает разное: переключение поколения, ручная компенсация и смена образа при живых томах. Во-вторых, данные приложения ни в одном случае не входят в откатываемую единицу. Это видно по примеру Akkoma[^1], по сохранению томов в `up`[^14] и по тому, что `backup` в Ansible касается одного файла[^11].

## 6. Секреты

Тезис: у всех трёх инструментов главный риск один — секрет попадает туда, где его могут прочитать, или туда, откуда его нельзя откатить. Защищают они при этом разные участки пути секрета[^1][^4][^22][^24].

В NixOS таким местом оказывается сам Nix store. Руководство несколько раз предупреждает об этом. Для Synapse секрет из опции «will end up in the world-readable store», и его рекомендуют вынести в отдельный файл[^1]. Для Pleroma секреты убирают из конфигурации, «because otherwise they will be stored publicly in the Nix store»[^1]. Правило простое: секрет, записанный прямо в выражение Nix, становится частью публично читаемой системы.

sops-nix решает эту задачу шифрованием. Его README заявляет: «Atomic upgrades: New secrets are written to a new directory which replaces the old directory atomically»[^4]. Откат поддерживается условно: «If sops files are added to the Nix store, old secrets can be rolled back. This is optional»[^4]. Ограничения тоже названы. Секреты расшифровываются только при активации, поэтому «It is not possible to use secrets at evaluation time of nix code»[^4]. Секреты для initrd поддерживаются не полностью, потому что `nixos-rebuild switch` ставит загрузчик до хука активации sops-nix[^4]. Атомарность sops-nix — это атомарная замена каталога секретов. Сервисы и данные она не охватывает.

В Compose секреты решают другую задачу: убрать пароли из переменных окружения. Документация объясняет мотив так: переменные окружения «are often available to all processes», и их легко случайно вывести в лог[^22]. Секрет доставляется в контейнер файлом: «Secrets are mounted as a file in `/run/secrets/<secret_name>` inside the container»[^22]. Доступ выдаётся явно: «Compose grants access to secrets on a per-service basis»[^22]. Источник секрета в примере — обычный файл рядом с проектом, `file: ./my_secret.txt`, и в контейнере путь `/run/secrets/my_secret` получает его содержимое[^22]. О шифровании этого файла на хосте страница ничего не говорит. Ограничение платформы: «Secrets are supported on Linux containers only»[^22]. Гарантии Swarm на обычный Compose переносить нельзя. Шифрование заявлено именно для роя: «Secrets are encrypted during transit and at rest in a Docker swarm»[^23]. Получается, что секреты Compose сокращают круг процессов, которые видят значение, но хранение исходного файла остаётся заботой администратора.

Ansible Vault закрывает другой участок — хранение в репозитории. Vault «encrypts variables and files so you can protect sensitive content such as passwords or keys»[^24]. Шифровать можно два вида содержимого: «variables and files»[^25]. Документация сразу ограничивает гарантию: «Encryption with Ansible Vault ONLY protects ‘data at rest’»[^24]. После расшифровки ответственность переходит к авторам play и плагинов, а скрывать вывод предлагается через `no_log`[^24]. Есть и оговорка для целевого хоста. Если зашифрованный файл передаётся модулями `copy`, `template`, `unarchive`, `script` или `assemble`, то «the file will not be encrypted on the target host»[^26]. Шифр один: «Currently `AES256` is the only supported cipher algorithm»[^26]. Пароль Vault передаётся через `--ask-vault-pass`, `--vault-password-file` или `--vault-id`[^26]. Сам файл пароля документация советует не класть в систему контроля версий: «Do not add password files to source control»[^27].

Ротация ключей у Vault неравномерна. Для файлов есть `ansible-vault rekey`, и он меняет пароль сразу у нескольких файлов[^25]. Для зашифрованных переменных так не получится: «You cannot rekey encrypted variables»[^25]. Это прямо влияет на откат. Старый коммит с секретом, зашифрованным прежним паролем, после ротации без старого пароля не расшифровать. Это вывод из описания `rekey`, на практике не проверен.

Итог сравнения. sops-nix и Vault шифруют секреты в репозитории, но расшифрованное значение на хосте каждый защищает по-своему: sops-nix пишет его в отдельный каталог при активации[^4], Vault оставляет файл на целевом хосте открытым[^26]. Для однохостового Compose шифрование на странице о секретах не заявлено, она описывает только доставку файла и ограничение того, какой сервис его видит[^22].

## 7. Практический сценарий: обновление приложения с базой данных

Тезис: на одном хосте инструменты складываются в слои, и порядок действий важнее выбора инструмента. Сценарий ниже собран из документации[^1][^13][^14], на стенде не проверялся.

Исходные условия: домашний сервер `apps.example.org`, на нём приложение и PostgreSQL в Compose, данные в именованных томах. Хост описан либо в NixOS[^1], либо ролью Ansible на обычном дистрибутиве[^8]. Сценарий иллюстративный: домен условный, замеров нет.

1. **Хост.** На NixOS сначала собрать конфигурацию через `nixos-rebuild build` и посмотреть план через `dry-activate`: эти шаги систему не активируют[^1]. `nixos-rebuild test` уже активирует конфигурацию на работающем хосте и может оборвать сеть или SSH[^1]. Запускать его стоит, только если есть консоль или другой внешний доступ для перезагрузки. Через `switch` применять уже проверенную конфигурацию. На Ansible прогнать `--check --diff`, помня, что это симуляция, а `command` без `creates` в ней пропускается[^5][^7].
2. **Образы.** В `compose.yaml` указать образ по digest, например `image: postgres@sha256:<digest>`, а не по изменяемому тегу[^16]. Для многоплатформенных образов проверить, какой digest закреплён: платформенный или списка манифестов[^17].
3. **Бэкап до обновления (рекомендация, не гарантия документации).** Снять согласованную с приложением копию базы штатным механизмом самой СУБД, а не архив каталога работающего тома. Docker показывает копирование тома через `tar` и называет тома удобными для бэкапа[^21]. Но работающая база в момент копирования может быть посреди транзакции. В ветке NixOS Discourse об откате данных это сформулировано прямо: «You still need to put your database in backup mode if you don’t want to accidentally snapshot it mid-transaction»[^20]. Копию нужно проверить восстановлением в отдельный экземпляр до обновления. Docker Docs упоминают такую проверку: «automate backup, migration, and restore testing using your preferred tools»[^21]. Пригодной для отката считать только копию, восстановление которой прошло. Произвольная копия живого тома такой гарантии не даёт.
4. **Запуск.** `docker compose up -d` пересоздаст контейнеры с изменённым образом и сохранит тома[^14]. Для приложения нужен `depends_on` с `service_healthy`, иначе оно может стартовать раньше базы[^18].
5. **Откат.** Вернуть прошлый digest образа или прошлое поколение NixOS. Если миграция прошла, этого мало. Схему нужно откатить средствами приложения, как в примере Akkoma[^1], или восстановить базу из проверенной копии шага 3[^21].
6. **Чего не делать.** Не запускать `docker compose down -v` на хосте с данными: флаг удаляет именованные тома[^15]. Не чистить поколения через `nix-collect-garbage -d` до того, как обновление проверено[^1].

Сценарий показывает, где проходят швы. Каждый инструмент откатывает свой слой[^1][^14], а связывает их порядок операций и проверенный бэкап данных[^20][^21].

## 8. Дрейф и бэкапы

Тезис: дрейф и бэкапы — две стороны одной проблемы. Всё, что не описано в конфигурации, не восстановится из неё[^1][^13].

Для NixOS граница проходит между декларативной конфигурацией и императивными профилями. Пакеты, поставленные через `nix-env`, обновляются отдельно[^1]. Для Ansible состояние между запусками не контролируется, а `ansible-pull` по расписанию превращает дрейф в окно между двумя запусками[^9]. Для Compose описание стека применяется при `up`. Контейнеры с изменённой конфигурацией пересоздаются[^14], а сервисы, удалённые из файла, убирает `--remove-orphans`[^14].

Бэкапы в прочитанных источниках упоминаются только как отдельная ответственность. Compose показывает том, смонтированный в сервис бэкапа[^13]. Docker Engine описывает копирование тома в `tar` и восстановление из него[^21]. Ansible даёт `backup` для одного файла[^11]. NixOS хранит прошлые конфигурации до сборки мусора[^1], но конфигурация — не данные: VM из `build-vm` создаётся без данных хоста[^1]. Ни один из этих механизмов не делает копию работающей базы согласованной. Об этом надо позаботиться отдельно, через режим бэкапа или штатный механизм СУБД[^20]. Документацию конкретных средств бэкапа баз в этой работе не читали.

## Дискуссионные вопросы и противоречия

**Воспроизводимость flakes.** Справочник Nix подаёт lock-файл как средство «to ensure reproducibility»[^2]. nix.dev в сноске уточняет, что даже в pure mode воспроизводимость «is not actually guaranteed», и называет flakes экспериментальным форматом с нерешёнными проблемами[^3]. Противоречие кажущееся. Справочник описывает назначение механизма, а nix.dev — его пределы. Для homelab разумно читать lock-файл как фиксацию входов, а не как гарантию побитово одинакового результата.

**Теги против digest.** Docker называет обновление тегов издателем практикой, которая полезна потребителю. Но тут же признаёт, что она «isn't enforced» и не даёт одинакового результата сборки[^16]. Digest даёт неизменность[^17], но обновления безопасности приходится забирать вручную, меняя digest. Ни один источник не взвешивает эти стороны количественно: выбор зависит от того, что важнее — свежие патчи или повторяемость.

**Полезность check mode.** Документация Ansible одновременно называет check mode «just a simulation» и пишет, что он «great for validating configuration management playbooks that run on one node at a time»[^5]. Обе оценки верны в своих границах. Режим хорош для модулей с поддержкой check mode и плох для `command` и задач с зарегистрированными переменными[^5][^7].

**Секреты Compose и Swarm.** Обе страницы Docker определяют секрет одинаково: данные, которые не должны храниться «unencrypted» в Dockerfile или исходном коде[^22][^23]. Но шифрование при передаче и хранении заявлено только для Swarm[^23]. Страница Compose описывает доставку файла в `/run/secrets/` и о шифровании источника молчит[^22]. Противоречия нет, есть разный объём гарантий. Путать их опасно: секрет в однохостовом Compose защищён ровно настолько, насколько защищён исходный файл на хосте.

**Атомарность секретов.** sops-nix называет обновления секретов атомарными[^4]. Это верно для замены каталога, но тот же README описывает неполную поддержку initrd и обходной путь через `nixos-rebuild test` перед `switch`[^4]. Атомарность одного компонента не делает атомарным всё обновление.

## Недостаточность данных

**Хранение источника секретов Compose.** Страница о секретах Compose прочитана, но о шифровании файла-источника на хосте она ничего не говорит[^22]. Ссылку на модель доверия Compose (`/compose/trust-model/`) с этой страницы не открывали. Поэтому вывод о том, что исходный файл защищён только правами файловой системы, остаётся выводом из умолчания документации.

**Средства бэкапа.** Какие инструменты бэкапа баз надёжны для homelab? В выборке есть только бэкап как отдельная задача, пример копирования тома через `tar` и замечание из форума о режиме бэкапа базы[^13][^20][^21]. Документацию конкретных средств и штатных механизмов СУБД не читали. Поэтому рекомендация о согласованном бэкапе и проверке восстановления в этом обзоре — рекомендация, а не подтверждённая замером практика.

**Количественные данные.** Как часто откат реально спасает и сколько он занимает? Замеров, отчётов об инцидентах и опросов в выборке нет. Обзор описывает гарантии из документации, а не измеренную надёжность[^1][^14].

**Откат в однохостовом Compose.** Применяется ли `rollback_config` вне Swarm? Страница `deploy` описывает его в терминах реплик и узлов и называет раздел необязательным[^19]. Прямого ответа для `docker compose up` на прочитанных страницах нет.

**Первичные публикации о NixOS.** Статья о модели NixOS по известному исследователям адресу вернула 404. Ветка NixOS Discourse об откате данных прочитана: автор вопроса пишет, что откат «only affects files managed by nix, not all system files»[^20]. Но это форум, а не спецификация. Утверждение о том, что откат поколения не затрагивает данные, держится на примере Akkoma и описании `build-vm`[^1], форум его только иллюстрирует[^20].

## Заключение

Три инструмента не конкурируют за один слой. NixOS описывает ОС и откатывает её конфигурацию до тех пор, пока поколения не удалены сборкой мусора[^1]. Ansible выполняет задачи на хостах. Его идемпотентность зависит от модулей, а откат состоит из ручных `rescue` и копий файлов[^6][^7][^8][^11]. Compose описывает стек приложения и при обновлении пересоздаёт контейнеры, сохраняя тома[^14].

Общая атомарность «ОС + приложение + данные + секреты» не обещана ни в одном прочитанном источнике. Ближе всего к ней подходят поколения NixOS и атомарная замена каталога секретов в sops-nix, но обе работают в пределах своего слоя[^1][^4]. Данные остаются отдельной ответственностью: миграции откатываются средствами приложения, а базу возвращают из согласованной копии, восстановление которой проверено заранее[^1][^20][^21]. Копия работающего тома такой гарантии сама по себе не даёт. Закрепление образов по digest тоже не делает воспроизводимым весь стек: оно фиксирует образы, но не данные и не хост[^16][^21].

Практические рекомендации для homelab (это рекомендации автора по прочитанной документации, а не гарантии инструментов):

- закреплять образы Compose по digest и обновлять digest осознанно, помня, что тома и хост этим не фиксируются[^16][^17][^28];
- перед каждым обновлением, которое может применить миграцию, снимать согласованный с приложением бэкап базы и проверять восстановление в отдельный экземпляр[^20][^21];
- на NixOS проверять сборку через `nixos-rebuild build` и `dry-activate`, а `test` запускать только при наличии консоли: он активирует конфигурацию на работающем хосте[^1];
- не чистить поколения NixOS сразу после обновления[^1];
- на Ansible не считать чистый `--check` доказательством и писать `creates`/`removes` для `command`[^5][^7];
- держать секреты вне Nix store, например через sops-nix, с учётом его ограничений[^1][^4];
- в Ansible шифровать секреты Vault и не класть файл пароля в репозиторий, помня, что Vault защищает только «data at rest»[^24][^27];
- в Compose передавать пароли через `secrets`, а не переменные окружения, и отдельно защищать исходный файл на хосте[^22].

Дальше стоит изучить три вещи: модель доверия Compose, конкретные средства бэкапа баз и поведение `rollback_config` в однохостовом Compose[^19][^22].

## Quality Metrics

| Metric | Value |
|--------|-------|
| Sources found | 96 |
| Sources read | 29 |
| Sources cited | 28 |
| Academic sources | 0 |
| Official/documentation | 27 |
| Industry reports | 0 |
| News/journalism | 0 |
| Blog/forum | 1 |
| Citation coverage | 100% |
| Counter-arguments searched | Yes |
| Research rounds | 3 |
| Questions emerged | 9 |
| Questions resolved | 4 |
| Questions insufficient data | 5 |

Sources found — число distinct-адресов кандидатов из журналов исследования: результаты поиска и страницы, которые пытались открыть, включая разные версии одной страницы и адреса, вернувшие 404. Sources read — нижняя граница, а не точный итог: 28 процитированных страниц и оглавление руководства Ansible Vault. Исследователи открыли и другие страницы, но их точное число здесь не утверждается.

[^20]: NixOS Discourse. "Rolling back data as well, not only Nix config." NixOS Discourse, Help, accessed 2026-10-29. https://discourse.nixos.org/t/rolling-back-data-as-well-not-only-nix-config/63169
[^21]: Docker Inc. "Volumes." Docker Docs, accessed 2026-10-29. https://docs.docker.com/engine/storage/volumes/
[^22]: Docker Inc. "Manage secrets securely in Docker Compose." Docker Docs, accessed 2026-10-29. https://docs.docker.com/compose/how-tos/use-secrets/
[^23]: Docker Inc. "Manage sensitive data with Docker secrets." Docker Docs, accessed 2026-10-29. https://docs.docker.com/engine/swarm/secrets/
[^24]: Ansible project. "Ansible Vault." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/vault_guide/vault.html
[^25]: Ansible project. "Encrypting content with Ansible Vault." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/vault_guide/vault_encrypting_content.html
[^26]: Ansible project. "Using encrypted variables and files." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/vault_guide/vault_using_encrypted_content.html
[^27]: Ansible project. "Managing vault passwords." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/vault_guide/vault_managing_passwords.html
[^28]: Docker Inc. "docker compose config." Docker Docs, accessed 2026-10-29. https://docs.docker.com/reference/cli/docker/compose/config/

[^1]: NixOS contributors. "NixOS Manual, Version 26.05." nixos.org, accessed 2026-10-29. https://nixos.org/manual/nixos/stable/
[^2]: Nix contributors. "nix flake — Nix 2.32.8 Reference Manual." nix.dev, accessed 2026-10-29. https://nix.dev/manual/nix/2.32/command-ref/new-cli/nix3-flake.html
[^3]: Kiara Grouwstra. "Flakes." nix.dev documentation, accessed 2026-10-29. https://nix.dev/concepts/flakes.html
[^4]: Mic92 and contributors. "sops-nix: Atomic, declarative, and reproducible secret provisioning for NixOS." GitHub README, accessed 2026-10-29. https://github.com/Mic92/sops-nix
[^5]: Ansible project. "Validating tasks: check mode and diff mode." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/playbook_guide/playbooks_checkmode.html
[^6]: Ansible project. "Blocks." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/playbook_guide/playbooks_blocks.html
[^7]: Ansible project. "ansible.builtin.command module – Execute commands on targets." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/collections/ansible/builtin/command_module.html
[^8]: Ansible project. "ansible.builtin.apt module – Manages apt-packages." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/collections/ansible/builtin/apt_module.html
[^9]: Ansible project. "ansible-pull." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/cli/ansible-pull.html
[^10]: Ansible project. "Error handling in playbooks." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/playbook_guide/playbooks_error_handling.html
[^11]: Ansible project. "ansible.builtin.template module – Template a file out to a target host." Ansible Core Documentation 2.20, accessed 2026-10-29. https://docs.ansible.com/projects/ansible-core/2.20/collections/ansible/builtin/template_module.html
[^12]: Docker Inc. "Compose file reference." Docker Docs, accessed 2026-10-29. https://docs.docker.com/reference/compose-file/
[^13]: Docker Inc. "Define and manage volumes in Docker Compose." Docker Docs, accessed 2026-10-29. https://docs.docker.com/reference/compose-file/volumes/
[^14]: Docker Inc. "docker compose up." Docker Docs, accessed 2026-10-29. https://docs.docker.com/reference/cli/docker/compose/up/
[^15]: Docker Inc. "docker compose down." Docker Docs, accessed 2026-10-29. https://docs.docker.com/reference/cli/docker/compose/down/
[^16]: Docker Inc. "Building best practices." Docker Docs, accessed 2026-10-29. https://docs.docker.com/build/building/best-practices/
[^17]: Docker Inc. "Image digests." Docker Docs, Docker Hardened Images, accessed 2026-10-29. https://docs.docker.com/dhi/explore/security-concepts/digests/
[^18]: Docker Inc. "Control startup and shutdown order in Compose." Docker Docs, accessed 2026-10-29. https://docs.docker.com/compose/how-tos/startup-order/
[^19]: Docker Inc. "Compose Deploy Specification." Docker Docs, accessed 2026-10-29. https://docs.docker.com/reference/compose-file/deploy/
