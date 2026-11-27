---
title: "Lanzaboote и TPM2 на NixOS: как сохранить откат после включения measured boot"
date: 2026-11-27T09:38:49+03:00
description: "Почему старого поколения в меню NixOS недостаточно для отката: подписи UEFI, политика PCR 4, лимит Lanzaboote и независимое восстановление LUKS2."
showToc: true
tocOpen: true
---

## Аннотация

Старое поколение в меню NixOS ещё не означает, что с него удастся открыть корневой том. Запись должна ссылаться на сохранившиеся загрузочные файлы, UEFI должен принять их, а TPM — разрешить выдачу секрета при измерениях именно этой загрузки. В Lanzaboote v1.2.0 обновление `systemd-boot` и вытеснение загруженного поколения из набора на ESP — разные события. Релиз исправил первое при условии перезагрузки между обновлениями загрузчика. Исправление второго вошло в код уже после тега.[^1][^2][^13][^16]

Данные на **2026-11-27**. Допущение: один UEFI-хост, один EFI System Partition (ESP), `systemd-boot`, системный initrd на systemd и корневой LUKS2 с TPM2. Основной срез — Lanzaboote **v1.2.0**; различия `systemd-pcrlock` сверены для **v261.2** и **v262.2**, изменения после тега разобраны отдельно. Это обзор исходников, документации, тестовых сценариев и сообщений сопровождающих; реальные перезагрузки, миграция ключей и проверка конкретной прошивки не проводились.[^2][^6][^10][^20][^22]

## Введение

Measured Boot через `systemd-pcrlock` появился в Lanzaboote v1.1.0; в v1.2.0 от 26 сентября 2026 года изменился порядок сохранения измерений при обновлении загрузчика и сократился верхний предел числа поколений с восьми до четырёх. Уже после релиза закрыли issue о сохранении загруженного поколения, а в systemd приняли другую реализацию `PolicyOR`. Все три изменения относятся к разным слоям; закрытая задача в GitHub не показывает, что установлено на хосте.[^1][^2][^14][^16][^19]

В [обзоре NixOS, Ansible и Compose](/articles/nixos-ansible-compose/) откат означал возврат конфигурации, а в [обзоре бэкапов](/articles/backup-restic-borg-kopia/) — возможность прочитать и восстановить данные. Здесь промежуточный вопрос: как добраться от выбора прошлого поколения до доступного корня, не ослабляя незаметно условия TPM? Руководство NixOS описывает откат профиля; Lanzaboote отдельно от него отбирает набор загрузочных файлов, а `pcrlock` строит собственный набор допустимых состояний.[^23][^13][^6]

## 1. Подпись разрешает загрузку, PCR описывает её

Secure Boot проверяет, приемлем ли EFI-образ по текущей политике прошивки. UEFI различает разрешающую базу `db` и запрещающую `dbx`. Подпись, принимавшаяся вчера, не обещает допуска после изменения политики. Lanzaboote помещает в stub хеши вынесенных ядра и initrd и включает туда командную строку. Stub сам проверяет загружаемые компоненты; при проверке доверенной цепочки нужно учитывать и подпись stub, и эту проверку связанного с ним содержимого.[^3][^4][^1]

Measured Boot описывает путь, который машина действительно прошла. При `Extend` TPM хеширует прежнее значение PCR вместе с новым дайджестом; порядок измерений имеет значение. Сам регистр не выдаёт перечень файлов. События и их дайджесты записываются в журнал, который можно проиграть и сверить с PCR. Совпадение подтверждает согласованность журнала и регистра, но не то, что всё важное вообще было измерено. Исследователи TPMSpy отдельно проверяли полноту наблюдения в виртуализированном окружении — это другая проверка, чем обычный replay.[^5][^6][^7]

В этой схеме PCR 4 включает измерения `systemd-boot` и Lanzaboote stub. PCR 7 относится к состоянию и политике Secure Boot; по нему нельзя установить, какое конкретно поколение выбрано. PCR 0 относится к коду прошивки, а 1–3 добавляют другие измерения платформы, часть которых на некоторых машинах нестабильна. Руководство предлагает `[ 0 4 7 ]` как пример, а не как обещание для любой платы. В исходниках модуля допустимы 0, 1, 2, 3, 4 и 7. Наличие отдельных измерений PCR 11 в тесте Lanzaboote не делает его доступным в `measuredBoot.pcrs` этого тега.[^4][^5][^6][^10][^11][^30]

## 2. Что разрешает LUKS2 после смены поколения

Привязка `systemd-cryptenroll --tpm2-pcrs=` к значению PCR проста, но новое поколение может дать другой дайджест. У systemd есть две модели, позволяющие обновлять набор: подписи над допустимыми значениями PCR, проверяемые заранее указанным публичным ключом, и локальная политика `pcrlock`. Это не два имени одной функции. Lanzaboote v1.2.0 использует вторую модель: разрешённые состояния вычисляются на хосте, а политика хранится в NV index TPM.[^6][^9][^10]

`pcrlock` сопоставляет объединённый event log текущей загрузки с `.pcrlock`-компонентами и реальными PCR. Затем он перебирает варианты компонентов и рассчитывает допустимые будущие значения. Например, у одного компонента могут быть варианты разных версий загрузчика, у другого — варианты разных поколений. Политика строится из `PolicyPCR` и `PolicyOR`; секрет привязан к этой политике через `PolicyAuthorizeNV`. При штатном обновлении содержимого того же NV index не нужно пересоздавать TPM enrollment LUKS2 для каждого нового ядра.[^6][^8][^9][^11]

> The NV index is allocated on first invocation, and updated on subsequent invocations.[^6]

В v1.2.0 установщик создаёт PE-измерения через `lock-pe`: загрузчик попадает в `630-bootloader.pcrlock.d`, поколения — в `635-lanzaboote.pcrlock.d`. После установки файлов хук модуля запускает `make-policy` с каталогами компонентов, выбранными PCR и границей фазы `--location=770`; модуль также определяет вызов `make-policy` при загрузке. Метаданные на диске и политика в TPM — разные вещи. Справочник systemd описывает передачу копии метаданных через credential на загрузочном разделе для расшифровки корня: основной файл под `/var/lib` недоступен, пока сам корень закрыт. Одна копия `pcrlock.json` не восстанавливает утраченный TPM или его NV index.[^6][^10][^12][^13]

## 3. Две причины потери PCR 4 и два исправления

**Обновление `systemd-boot`.** Диск уже содержит новый загрузчик, а журнал запущенной системы ещё описывает загрузчик, который действительно стартовал. PR #637 сохраняет предыдущее измерение рядом с новым; это изменение вошло в v1.2.0. `current.pcrlock` и `previous.pcrlock` — измерения, не две установленные копии загрузчика, между которыми можно переключаться. Код предполагает перезагрузку между последовательными обновлениями самого загрузчика. Откат ядра через меню обычно проходит через установленный сейчас `systemd-boot`, а не через исторический экземпляр загрузчика.[^1][^13][^15]

**Вытеснение загруженного поколения.** Другая причина из #614: профиль NixOS и уже запущенная система могут ещё существовать, но при очередной ротации Lanzaboote v1.2.0 сохраняет только последние поколения в пределах `configurationLimit`. Установщик при штатной очистке удаляет старые загрузочные файлы и их `.pcrlock`. Если из набора выбыло именно поколение, которое загрузило текущую систему, журнал TPM по-прежнему содержит его измерение. Смена `current` и `previous` для `systemd-boot` этого несоответствия не исправляет.[^13][^14][^15]

PR #667, слитый 29 сентября, закрывает вторую задачу, но отсутствует в релизе от 26 сентября. Модуль в слитом коммите по умолчанию защищает `/run/booted-system`. Установщик сопоставляет его с существующей ссылкой поколения. Если она есть, но не попала в отобранный набор, код заменяет ею самый старый элемент набора, а не добавляет пятое поколение. Поэтому правило сохраняет место для проверенного кандидата, но не восстанавливает ссылку, которую уже удалили из профиля, и не делает любое старое поколение пригодным к расшифровке.[^2][^16][^17][^25]

Отсюда важное различие для эксплуатации: «запущено G» и «G сохранено для следующей загрузки» — два утверждения. Не проверяйте первое по номеру поколения в конфигурации, а второе — по одному наличию ссылки в Nix store. Для v1.2.0 при планировании окна обновления сверьте видимые записи и отведите место поколению, которое действительно проверено перезагрузкой. Для кода с #667 проверяйте также, что защищаемый путь всё ещё разрешается через одну из переданных ссылок.[^10][^13][^17][^23]

## 4. Почему предел равен четырём, даже если systemd развивается

`pcrlock` перебирает комбинации, а не складывает файлы в один список. Если у компонента загрузчика два различных варианта и у компонента NixOS четыре, для PCR 4 получается до восьми различных значений. Пятый вариант NixOS при тех же предпосылках даёт до десяти: каждый вариант поколения сочетается с каждым вариантом загрузчика. Четыре поколения в профиле — ещё не гарантия четырёх вариантов: upstream-тест показывает отдельный `.pcrlock` для specialisation того же поколения. Считать нужно результаты предсказания для каждого PCR, а не номера профилей.[^1][^6][^8][^12][^15][^22]

В исходниках systemd v261.2 и v262.2 реализация, собирающая политику из предсказания, отвергает более восьми альтернатив одного PCR с `E2BIG`. PR #43982 добавил дерево вложенных `PolicyOR` в ветку разработки; сам факт merge не меняет исходники v262.2. И даже с реализацией дерева именно модуль Lanzaboote v1.2.0 отдельно требует `0 < configurationLimit <= 4` при включённом Measured Boot. Подмена версии systemd без изменения и проверки модуля этот барьер не снимает.[^10][^18][^19][^27]

Запишите версию `systemd-pcrlock` из того system closure, который выполняет операцию. В `flake.lock` тега Lanzaboote указан Nixpkgs revision, где пакет systemd имеет версию 261.2; хук, однако, вызывает `config.systemd.package`, а не жёстко заданный бинарник из этого lock-файла. Версию тестового входа проекта нельзя использовать как доказательство версии на конкретной машине.[^10][^28][^29]

## 5. Что проверять до следующей перезагрузки

**1. Сохранить независимый вход.** До enrollment убедитесь, что отдельно хранимый пароль или recovery key действительно открывает этот LUKS2-том без TPM и доступен с консоли. Не путайте его с TPM PIN при выдаче секрета и с recovery PIN для записи в NV index: последний предназначен для восстановления права обновить политику, а не для самостоятельной расшифровки диска. Для удалённого хоста заранее нужен способ попасть в консоль. Не удаляйте рабочий слот только потому, что тест одного автоматического запуска прошёл.[^6][^9][^11][^26]

**2. Проверить действующий и запасной варианты.** Сохраните в журнале обслуживания поколение, реально прошедшее загрузку, запланированное поколение, набор установленных записей ESP и ожидаемые PCR. После установки проверьте и список записей, и итоговую политику. В тесте Lanzaboote присутствие нужных регистров проверяется по полю `pcrValues` в `pcrlock.json`; это лучше, чем считать сам факт существования файла подтверждением. Также проверьте результат вычисления новой политики: старый файл не доказывает, что операция обновления удалась.[^6][^10][^13][^21][^22]

**3. Считать пропавший PCR неуспешной проверкой.** В v261.2 код пишет `PCRs dropped from protection mask` и может продолжать с суженной маской. В v262.2 руководство описывает `--strict=yes` для `predict` и `make-policy`: если выбранный PCR нельзя включить, операция завершается ошибкой. По умолчанию режим отключён, а хук Lanzaboote v1.2.0 его не передаёт. На v262.2 его можно использовать при отдельном `predict` с теми же PCR, компонентами и границей фазы, что у установщика: это проверка расчёта без обновления политики, не доказательство успешного будущего unseal. На версии без этого флага проверяйте маску и журнал, а не один код возврата.[^6][^10][^20][^21]

**4. Проверить откат до очистки, а не после.** Загрузите целевой вариант под наблюдением и запишите, открыл ли корень TPM, потребовался ли пользовательский PIN или сработал запасной ключ. Отдельно проверьте возврат в последнее известное рабочее поколение через установленный загрузчик. Если автоматика не сработала, но ручной ключ открывает том, ручное восстановление живо, автоматический откат — нет. Boot counting умеет изменить выбор записи после неудачных попыток; он не хранит отсутствующие файлы, не пересчитывает PCR и не открывает LUKS2 сам.[^6][^9][^13][^23][^24]

## Дискуссионные вопросы и противоречия

**«Повторный enrollment не нужен» и жалоба в #614 совместимы.** Руководство описывает обновление предсказания при сохранении действующей привязки. Автор issue сообщил, что после удаления политики ему понадобилось снова зарегистрировать TPM-слот. По руководству systemd `remove-policy` удаляет не только файл, но и NV index. Это разные операции. Отказ предсказания — повод разобраться с компонентами и доступом к recovery key, а не начинать с удаления политики. Раздел upstream о выключении Measured Boot описывает демонтаж, а не безопасный универсальный ремонт.[^6][^11][^14][^26]

**Успешный unseal и полнота политики не равнозначны.** Upstream-тест v1.2.0 прямо ожидает отсутствие PCR 4 в сценарии первоначального создания политики до перехода на измеренное поколение, проверяет token LUKS2, а после reboot требует наличия PCR 4. Это полезный тест миграции без Secure Boot и с виртуальным TPM, но не испытание старта нескольких прежних поколений на реальной плате. Если корень открывается по политике без ожидаемого PCR, доступность сохранилась, а объём защиты изменился. Если переоценка в строгом режиме отклонена, новая политика не записана; перед перезагрузкой нужно сверить сохранённую политику с тем путём, который предстоит загрузить.[^6][^20][^21][^22]

## Недостаточность данных

Из опубликованных материалов нельзя вывести универсальный список PCR для каждой прошивки или вероятность ручного unlock после обновления. TPMSpy сравнивает трассы на виртуальных стендах для systemd 245–258, а цитируемые тесты Lanzaboote проверяют отдельные сценарии, не связку обновления прошивки, смены UEFI-ключей, нескольких ESP и нескольких поколений. Эти случаи требуют отдельных проверок на целевой конфигурации; ни номера релизов, ни скриншота меню для этого недостаточно.[^7][^22][^30]

## Заключение

Откат с TPM2 можно считать готовым, когда проверены запись и её файлы, допуск UEFI, предсказание с обязательными PCR и фактическая расшифровка; ручной ключ должен оставаться отдельным путём. На Lanzaboote v1.2.0 планируйте максимум четыре поколения и перезагрузку между обновлениями загрузчика. Не считайте защиту загруженного поколения из #667 частью этого релиза. Прежде чем сокращать историю или менять ключи, проверьте обе загрузки — новую и запасную — и не принимайте отсутствие PCR 4 за успешное обновление политики.[^1][^6][^10][^11][^16][^21]

## Quality Metrics

| Metric | Value |
|---|---|
| Sources found | 74 |
| Sources read | 30 |
| Sources cited | 30 |
| Count units | Found: URL-кандидаты; read/cited: документы, версии и отдельные артефакты; зеркала одного документа не дублируются |
| Academic sources | 1 |
| Official/documentation | 28 |
| Blog/forum | 1 |
| Citation coverage | 100% (26/26 содержательных абзацев) |
| Article words | 1865 (без frontmatter, метрик и сносок) |
| Counter-arguments searched | Yes |
| Research rounds | 3 |
| Questions emerged | 7 |
| Questions resolved | 6 |
| Questions insufficient data | 1 |
| Access scope | Релевантные разделы, исходники и тесты; публикаций только по аннотации нет |

[^1]: Lanzaboote contributors. "Changelog." Lanzaboote v1.2.0. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/CHANGELOG.md>
[^2]: Lanzaboote contributors. "1.2.0." GitHub Releases, 2026-09-26. <https://github.com/nix-community/lanzaboote/releases/tag/v1.2.0>
[^3]: UEFI Forum. "32. Secure Boot and Driver Signing." UEFI Specification 2.11. <https://uefi.org/specs/UEFI/2.11/32_Secure_Boot_and_Driver_Signing.html>
[^4]: Lanzaboote contributors. "Measured Boot." Lanzaboote v1.2.0. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/docs/explanation/measured-boot.md>
[^5]: UAPI Group. "Linux TPM PCR Registry." UAPI.7. <https://uapi-group.org/specifications/specs/linux_tpm_pcr_registry/>
[^6]: systemd contributors. "systemd-pcrlock." systemd v262.2. <https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd-pcrlock.xml>
[^7]: Roman Lacko, Petr Švenda. "TPMSpy: Validation of Measured Boot Systems by Low-Level Tracing of TPM Usage." arXiv:2609.05011v1, 2026-09-04. <https://arxiv.org/html/2609.05011v1>
[^8]: systemd contributors. "systemd.pcrlock." systemd v262.2. <https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd.pcrlock.xml>
[^9]: systemd contributors. "systemd-cryptenroll." systemd v262.2. <https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd-cryptenroll.xml>
[^10]: Lanzaboote contributors. "lanzaboote.nix." Lanzaboote v1.2.0, NixOS module. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/nix/modules/lanzaboote.nix>
[^11]: Lanzaboote contributors. "Enable Measured Boot." Lanzaboote v1.2.0. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/docs/how-to-guides/enable-measured-boot.md>
[^12]: Lanzaboote contributors. "pcrlock.rs." Lanzaboote v1.2.0. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/rust/tool/systemd/src/pcrlock.rs>
[^13]: Lanzaboote contributors. "install.rs." Lanzaboote v1.2.0. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/rust/tool/systemd/src/install.rs>
[^14]: Lanzaboote contributors. "Measure Boot: Always keep currently booted measurements." GitHub issue #614, opened 2026-06-04. <https://github.com/nix-community/lanzaboote/issues/614>
[^15]: Lanzaboote contributors. "tool: make Measured Boot policy cover PCR4 throughout bootloader update." GitHub PR #637, merged 2026-09-25. <https://github.com/nix-community/lanzaboote/pull/637>
[^16]: Lanzaboote contributors. "module: add protectedSystem option." GitHub PR #667, merged 2026-09-29. <https://github.com/nix-community/lanzaboote/pull/667>
[^17]: Lanzaboote contributors. "install.rs." Lanzaboote, commit 663642398525f1d46163553d32853325b6b6de08. <https://raw.githubusercontent.com/nix-community/lanzaboote/663642398525f1d46163553d32853325b6b6de08/rust/tool/systemd/src/install.rs>
[^18]: systemd contributors. "tpm2-util.c." systemd v262.2. <https://raw.githubusercontent.com/systemd/systemd/v262.2/src/shared/tpm2-util.c>
[^19]: systemd contributors. "tpm2-util: support more than 8 branches in PolicyOR expressions." GitHub PR #43982, merged 2026-11-03. <https://github.com/systemd/systemd/pull/43982>
[^20]: systemd contributors. "pcrlock.c." systemd v261.2. <https://raw.githubusercontent.com/systemd/systemd/v261.2/src/pcrlock/pcrlock.c>
[^21]: systemd contributors. "pcrlock.c." systemd v262.2. <https://raw.githubusercontent.com/systemd/systemd/v262.2/src/pcrlock/pcrlock.c>
[^22]: Lanzaboote contributors. "measured-boot.nix." Lanzaboote v1.2.0, NixOS test. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/nix/tests/lanzaboote/measured-boot.nix>
[^23]: NixOS contributors. "NixOS Manual." Version 26.05, section Upgrading NixOS. <https://nixos.org/manual/nixos/stable/>
[^24]: systemd contributors. "systemd-boot." systemd v262.2. <https://raw.githubusercontent.com/systemd/systemd/v262.2/man/systemd-boot.xml>
[^25]: Lanzaboote contributors. "lanzaboote.nix." Lanzaboote, commit 663642398525f1d46163553d32853325b6b6de08. <https://raw.githubusercontent.com/nix-community/lanzaboote/663642398525f1d46163553d32853325b6b6de08/nix/modules/lanzaboote.nix>
[^26]: Lanzaboote contributors. "Disable Measured Boot." Lanzaboote v1.2.0. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/docs/how-to-guides/disable-measured-boot.md>
[^27]: systemd contributors. "tpm2-util.c." systemd v261.2. <https://raw.githubusercontent.com/systemd/systemd/v261.2/src/shared/tpm2-util.c>
[^28]: NixOS contributors. "default.nix (systemd)." Nixpkgs, commit 20b1ddd1aa5ace70c9468305030aa4f9ef79671b. <https://raw.githubusercontent.com/NixOS/nixpkgs/20b1ddd1aa5ace70c9468305030aa4f9ef79671b/pkgs/os-specific/linux/systemd/default.nix>
[^29]: Lanzaboote contributors. "flake.lock." Lanzaboote v1.2.0. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/flake.lock>
[^30]: Lanzaboote contributors. "systemd-pcrlock.nix." Lanzaboote v1.2.0, NixOS test. <https://raw.githubusercontent.com/nix-community/lanzaboote/v1.2.0/nix/tests/lanzaboote/systemd-pcrlock.nix>
