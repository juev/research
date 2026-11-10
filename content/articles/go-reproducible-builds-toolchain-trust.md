---
title: "Воспроизводимый Go-бинарник: почему go.sum недостаточно для доверия к релизу"
date: 2026-11-10T09:42:04+03:00
description: "Границы go.sum, автоматический выбор toolchain, CGO, VCS и упаковка: как независимо пересобрать Go-релиз и что доказывает совпадение байтов."
showToc: true
tocOpen: true
---

## Аннотация

`go.sum` помогает проверить содержимое скачиваемых модулей. Он не задаёт все входы сборки и не доказывает, что опубликованный executable получен из объявленных исходников. Для такого утверждения нужны доступные исходники, зафиксированный рецепт и сравнение опубликованного артефакта с независимой пересборкой. Подпись и provenance добавляют сведения об авторе и процессе, но не заменяют это сравнение.[^1][^2][^14][^15]

**Данные на 2026-11-10.** Рабочая версия — **Go 1.27.3**, указанная официальным каталогом как stable; поведение флагов и VCS сверено с исходниками тега `go1.27.3`. Допущение автономного обзора: администратор распространяет небольшой Go-сервис для Linux/amd64 и хочет проверяемый release executable, а не сертификацию всей цепочки поставки. Помимо анализа документов выполнен ограниченный прогон: две минимальные программы, pure Go и cgo, разные каталоги и отдельные пустые build caches. Это **локальная демонстрация на одном хосте**, не независимая пересборка toolchain, не аудит реального сервиса и не бенчмарк.[^4][^19]

Результат прогона: с фиксированными входами и `-trimpath` совпали обе пары executable, включая cgo с одним и тем же GCC. Без `-trimpath` пары различались. Изменение linker-параметра меняло pure-Go-бинарник даже с `-trimpath`, а одинаковый executable давал разные tar-архивы при разных file mtimes. Следовательно, проверять нужно весь объявленный release artifact, отдельно оговаривая границы бинарника, упаковки и подписи.

## Введение

Повод для обзора — автоматическое управление Go toolchain: команда `go` может использовать не ту версию компилятора, рядом с которой она установлена, а найденную в `PATH` или скачанную. При этом `go` в `go.mod` задаёт минимальную версию, а `toolchain` — предлагаемую, не универсальный запрет на более новый компилятор. Поэтому «у нас есть go.mod и go.sum» ещё не означает «у нас один и тот же компилятор».[^3][^17]

Цель — разделить проверку модулей, фиксацию входов, воспроизводимость артефакта и доверие к сборщику. В отличие от обзора [NixOS, Ansible и Compose](/articles/nixos-ansible-compose/), здесь единица проверки — байты релиза, а не откат конфигурации. От статей про [LSP](/articles/lsp-3-18-internals/) и [AI Code Review](/articles/ai-code-review-consistency/) текст отличается предметом воспроизводимости: не согласованность протокольного состояния и не повторяемость экспертного суждения.

Обзор не выбирает «самый безопасный» CI и не распространяет результаты маленького примера на все Go-проекты. Исследование Lamb и Zacchiroli различает неконтролируемые входы и собственно недетерминированность сборки; изоляция окружения помогает с первыми, но сама по себе не устраняет вторую. Ниже это различие используется как способ диагностики, а не как обещание универсального рецепта.[^21]

## 1. Четыре разных доказательства

Операционное определение Reproducible Builds прямо включает исходный код, окружение, инструкции и **все указанные артефакты**. Воспроизводимость нельзя объявить для «релиза вообще», если проверялся лишь исполняемый файл внутри него.[^1]

> A build is reproducible if given the same source code, build environment and build instructions, any party can recreate bit-by-bit identical copies of all specified artifacts.[^1]

Первое доказательство — **целостность входа**: полученные файлы модуля соответствуют ожидаемому checksum. Второе — **повторяемость рецепта**: при согласованных входах он снова даёт те же байты. Третье — **независимая проверка выхода**: другой сборщик получил тот же артефакт, который опубликован. Четвёртое — **происхождение**: проверяемое заявление о том, где, когда и каким процессом артефакт произведён. В SLSA два последних свойства различены: `verified reproducible` требует независимых build platforms, provenance описывает производство.[^2][^14][^15]

Для потребителя это разные вопросы. «Файл скачан без повреждения» не означает «файл соответствует source commit». «Файл подписан ожидаемой стороной» не означает «её сборщик не был скомпрометирован». Даже честное совпадение байтов не делает исходный код безопасным: SLSA отдельно предупреждает, что reproducible builds не закрывают угрозы в source и dependencies. Проверяемость сборки дополняет review исходников, а не отменяет его.[^14][^15]

## 2. Что именно проверяют go.sum и checksum database

В `go.sum` хранятся hashes прямых и косвенных module dependencies. Строка с версией, заканчивающейся на `/go.mod`, относится только к `go.mod`; строка без этого суффикса — к содержимому module zip. Это не SHA-256 финального executable и не полный рецепт его получения.[^2]

При скачивании Go сравнивает вычисленный hash с записью `go.sum`; если её нет, для подходящих модулей обращается к checksum database. `go.sum` может содержать несколько версий модуля. Выбор build list выполняется по графу требований и правилам module system, включая `replace` и `exclude`, а не простым перечислением всех строк checksum-файла. Поэтому его неверно воспринимать как самостоятельный lockfile всей сборки.[^2]

Особенно важны три исключения из бытовой модели «всё захешировано». Локальный `replace` может подставлять каталог, и документация допускает пустой либо отсутствующий `go.sum`, когда все зависимости заменены локально. Workspace способен менять набор main modules и replacements. В режиме vendoring используются файлы `vendor`, а не обычный путь загрузки из module cache. Эти входы надо сохранять и проверять отдельно.[^2][^4]

`go mod verify` решает более узкую задачу: сравнивает скачанные module zip и распакованные каталоги в cache с hash, записанным при скачивании. Он полезен для обнаружения изменений cache, но не проверяет соответствие release executable исходникам, не удостоверяет содержимое C toolchain и не заменяет аудит локальных replacements или `vendor`. Режим `-mod=readonly` запрещает требующие обновления `go.mod` изменения, но тоже не является контролем целостности всего дерева.[^2]

У toolchain есть ещё одна граница. Скачиваемый через механизм Go compiler упакован как специальный модуль `golang.org/toolchain`, но его checksum не записывается в проектный `go.sum`. По документации такие загрузки проверяются checksum database и при `GOSUMDB=off` завершаются ошибкой проверки. Из отсутствия compiler hash в `go.sum` нельзя заключить, что загрузка вообще не проверялась; нельзя и заключить, что этот файл закрепил compiler.[^3]

## 3. Закрепить версию — значит проверить исполняемый toolchain

Для Go 1.27.3 выбор начинается с `GOTOOLCHAIN`. В форме `auto` версия может измениться под влиянием `go.work` или `go.mod`. Значение `go1.27.3` без `+auto` выбирает конкретное имя; сначала возможен поиск одноимённой программы в `PATH`, затем загрузка. Поэтому имя — ещё не удостоверение байтов найденного executable.[^3][^17]

`GOTOOLCHAIN=local` отключает переключение и оставляет bundled toolchain конкретной команды `go`. Но само по себе слово `local` не фиксирует версию: если `PATH` завтра приведёт к другому `go`, результат тоже изменится. Для release-рецепта разумнее задавать проверенную установку абсолютным путём, отключать переключение и записывать фактически возвращённый `go version`.[^3][^17]

```sh
GO=/work/toolchain/go/bin/go
export GOTOOLCHAIN=local GOENV=off GOWORK=off
export GOFLAGS= GOOS=linux GOARCH=amd64 GOAMD64=v1
"$GO" version
"$GO" env GOTOOLCHAIN GOWORK GOOS GOARCH GOAMD64 CGO_ENABLED
```

Здесь `GOENV=off` убирает пользовательский файл настроек `go env -w`, `GOWORK=off` — неявный родительский workspace, а пустой `GOFLAGS` — унаследованные default flags. Это не полная санация environment: остаются, например, `GOEXPERIMENT`, cgo-параметры и программы из `PATH`. Их надо либо явно задавать в рецепте, либо исключать при запуске в согласованном окружении. Не следует выгружать весь process environment в публичные логи: для проверки нужен ограниченный список входов.[^4][^5]

В этой работе архив Go 1.27.3 для Linux/amd64 скачан, его SHA-256 сопоставлен с официальным download JSON, затем использован executable из распакованного архива. Такая проверка удостоверяет совпадение с опубликованным Go checksum, **не** независимую компиляцию Go из исходников. Разница существенна: официальный `gorebuild` делает именно пересборку и публикует отдельный отчёт; наш маленький прогон её не выполнял.[^10][^19]

## 4. Пути, VCS и метаданные — такие же входы

В Go 1.27.3 `-trimpath` заменяет файловые пути в результирующем executable на module/import paths. Это устраняет зависимость от checkout directory в соответствующих compiler metadata. В upstream есть отдельный test script: одинаковые пакеты собираются в разных каталогах и сравниваются командой `cmp`. Это конкретный проверяемый контракт, а не обещание удалить произвольные пути из пользовательских строк или любых внешних инструментов.[^4][^16]

По умолчанию `-buildvcs=auto` добавляет VCS information при выполнении описанных условий: main package, main module и текущий каталог находятся в одном repository. `-trimpath` не отключает этот механизм. В `runtime/debug` перечислены `vcs.revision`, `vcs.time` и `vcs.modified`; tagged source формирует эти поля и может менять main module version при dirty tree. Следовательно, checkout и source archive без VCS metadata нельзя автоматически считать эквивалентными входами.[^4][^7][^8]

Есть два допустимых release-контракта. Первый сохраняет stamping: фиксируются commit, доступность VCS и состояние дерева. Второй использует `-buildvcs=false`, а связь с commit хранится в проверяемом внешнем manifest/provenance. Второй удобнее для одинаковой сборки из разных представлений source tree, но уменьшает самоописание executable. Это выбор автора рецепта, не обязательная «оптимизация безопасности».[^4][^15]

`-ldflags=-X importpath.name=value` меняет подходящую строковую переменную. Если CI передаёт туда текущее время запуска, оно становится явным входом бинарника; одинаковые source и module checksums этого не отменяют. Для version string стоит использовать значение из закреплённого релиза, а для необходимого timestamp — заранее определённое source-derived значение. Спецификация `SOURCE_DATE_EPOCH` требует детерминированной величины, но переменная помогает только процессам, которые её действительно потребляют.[^6][^13]

Генерация тоже не исчезает после фиксации `go.sum`: `go generate` не запускается автоматически командой `go build`. Если release job предварительно генерирует Go-файлы или assets, самостоятельным входом становятся generator, его версия, аргументы и результаты. Альтернатива — включить проверенные generated files в source release и не повторять генерацию при пересборке. В обоих случаях рецепт должен явно сообщать, какой именно путь используется.[^4][^21]

## 5. CGO расширяет область фиксации, но не запрещает воспроизводимость

Отключение cgo удаляет host C toolchain из входов там, где программа может быть собрана без него. Это удобное сокращение задачи, а не доказательство того, что cgo всегда создаёт случайный output. Официальный разбор Go предлагает для cgo фиксировать C toolchain, например через определённое окружение VM или container image.[^9]

В документации cgo для Go 1.27.3 перечислены дополнительные каналы входа: `CC`, `CGO_CFLAGS`, `CGO_CPPFLAGS`, `CGO_CXXFLAGS`, `CGO_LDFLAGS`, директивы `#cgo`, `pkg-config`, headers и библиотеки. `${SRCDIR}` раскрывается в абсолютный source path. Ссылка `-L${SRCDIR}/libs` корректно помогает найти библиотеку, но требует внимания при сравнении build metadata и linker inputs в разных каталогах.[^5]

Поэтому для cgo release manifest должен описывать не только «GCC такой-то», но и sysroot, headers, библиотечные inputs, режим линковки и flags. Если остаются dynamic dependencies, тождество самого executable не означает тождества всего runtime environment. Это отдельная область проверки; даже справочник Go linker отдельно описывает external linker и путь ELF interpreter.[^5][^6]

Контрпример к совету «добавьте один флаг» — issue Go **#77086**, озаглавленный «cmd/go: non reproducible builds since cgo_ldflag that contains build path». Автор описывает Buildah с Go 1.25.3 и различие build ID при разных путях; обсуждение связывает его с path-bearing cgo flags. Это **сообщение о конкретной конфигурации**, не наш воспроизведённый дефект Go 1.27.3 и не основание объявить все cgo builds невоспроизводимыми.[^18]

Удалять build ID вслепую тоже не стоит. В Go linker `-buildid` задаёт записываемый идентификатор; это ещё не указание, что по умолчанию он случаен. В нашем прогоне совпадение достигнуто без `-buildid=` и без удаления debug information. Если байты различаются, сначала следует понять различие, а не удалять метаданные, пока сравнение не станет зелёным.[^6][^21]

## 6. Локальный прогон: что действительно получилось

Ниже собственные результаты этого запуска. До сборки были заданы сравнения: смена checkout path без trimming; та же смена с trimming; изменение `-X` при trimming; повтор для cgo; одинаковое содержимое tar с разными mtimes и с нормализованными metadata. Ожидаемые отношения равенства не менялись после наблюдения. На каждую строку executable выполнены две сборки, каждая с отдельным изначально пустым `GOCACHE`; повторных статистических испытаний не было.

Среда: Linux/amd64, Go 1.27.3, `GOAMD64=v1`, GCC **14.2.0** из Debian package **14.2.0-19**, GNU tar **1.35**. Оба executable запускались после каждой сборки. Pure-Go-пример печатал `fixture fixed`, cgo — `42 fixed`; для изменённых linker labels pure-Go output был `fixture one` и `fixture two`. Это smoke-проверка выполненных файлов, не проверка функциональности какого-либо сервиса.

| Сравнение | Различавшийся вход | Байты совпали |
|---|---|---|
| Pure Go без `-trimpath` | Source path и отдельный cache | Нет |
| Pure Go с `-trimpath` | Source path и отдельный cache | Да |
| Pure Go с `-trimpath`, `-X` | `main.buildLabel=one` / `two`, path и cache | Нет |
| CGO без `-trimpath` | Source path и отдельный cache | Нет |
| CGO с `-trimpath` | Source path и отдельный cache, один GCC | Да |
| GNU tar, обычные metadata | File mtime при одинаковом executable | Нет |
| GNU tar, нормализованные metadata | Исходный file mtime | Да |

SHA-256 совпавшей pure-Go-пары — `9c94a9b1a9c0ae40284b3bf33590d30066072332aad771e18eb1f4134a485d18`, размер каждого файла **2337709 байт**. У cgo-пары — `b1dfbea6e3c108ce43c2a61a7a0ab1886e3d82549e5deb3f5da2647a6f832d20`, **2298344 байта**. Hashes повторно вычислены из сохранённых executable отдельно от кода, формировавшего итоговую таблицу. Они характеризуют только эти fixtures и согласованные входы, не произвольную установку GCC или libc.

Для повторения достаточно двух каталогов с одинаковым `go.mod` и соответствующим `main.go`. В обоих случаях module path — `example.org/reprofixture`, строка версии — `go 1.27.0`; фактический compiler закреплён отдельно на Go 1.27.3. Внешних module dependencies и `go.sum` у примеров нет. Именно поэтому результат демонстрирует влияние дополнительных входов, но не является испытанием checksum database.

```go
// pure/main.go
package main

import "fmt"

var buildLabel = "fixed"

func main() { fmt.Println("fixture", buildLabel) }
```

```go
// cgo/main.go
package main

/*
static int answer(void) { return 42; }
*/
import "C"
import "fmt"

var buildLabel = "fixed"

func main() { fmt.Println(C.answer(), buildLabel) }
```

В каждом source directory выполнялась команда следующего вида; для cgo менялось `CGO_ENABLED=1` и явно задавался `CC=/usr/bin/gcc`. Для нетриммированных вариантов убирался `-trimpath`, для варианта labels менялись только значения `fixed` на `one` и `two`. `out` находился вне source directory. Наследованные `GO*`/`CGO*` settings предварительно исключались, затем задавались параметры ниже и отдельные cache/tmp directories. Это описание выполненного рецепта, не готовая конфигурация production CI.

```sh
GOTOOLCHAIN=local GOENV=off GOWORK=off GOFLAGS= \
GOOS=linux GOARCH=amd64 GOAMD64=v1 CGO_ENABLED=0 \
GOPROXY=off GOSUMDB=off GOCACHEPROG= GOTELEMETRY=off \
GOCACHE="$cache" GOTMPDIR="$tmp" GOMODCACHE="$modcache" \
"$GO" build -mod=readonly -buildvcs=false -trimpath \
  -ldflags='-X main.buildLabel=fixed' -o "$out" .
"$GO" version -m "$out"
sha256sum "$out"
```

`GOSUMDB=off` здесь допустим только как часть **dependency-free offline fixture с уже установленным toolchain**. Это не рекомендация отключать проверку в обычном release job. Пять сравнений показали ожидаемые различия и совпадения, но охватывают только одну ОС, один compiler и один C toolchain; VCS stamping в них намеренно выключен. Из этого нельзя вывести межплатформенную воспроизводимость или независимость сборщиков.[^3][^14]

## 7. Релиз заканчивается не на go build

В тесте упаковки в два каталога помещён **один и тот же** pure-Go executable с mode `0755`. Его mtime задан явно: `1000000000` и `1000000100`. Обычные tar-архивы различались; после задания общих metadata совпали, SHA-256 обоих — `dde354b4676d6294ade8dcd1da5b3a0043515875531b036b7e1dd82af4fd4e8f`. Проверялся tar, не `.tar.gz`, installer или container image.

```sh
tar --format=gnu --sort=name --mtime=@0 \
  --owner=0 --group=0 --numeric-owner --mode=0755 \
  -cf release.tar fixture
```

Для этого однофайлового примера mode фиксирован целиком. В реальном архиве нельзя бездумно делать все файлы executable: следует определить политику permissions для файлов и каталогов. Reproducible Builds перечисляет дополнительные источники различий: порядок файлов, owner/group, numeric IDs, timestamps и PAX headers. Если дальше используется gzip, его metadata и версию также нужно учитывать; руководство отдельно предлагает `gzip -n`. Этот дополнительный слой в нашем прогоне не измерялся.[^12]

Подписи стоит рассматривать отдельно от подписываемого содержимого. У macOS toolchain есть наглядная граница: Andrew Ayer описывает сравнение после удаления недоступных ему подписей Google, а официальный отчёт также отмечает stripping signatures для Darwin. Это не побитовое воспроизведение подписанного контейнера «целиком». Такой контракт приемлем лишь при явно описанной нормализации и отдельной проверке подписи.[^10][^11]

Provenance полезен для публикации рецепта: SLSA Build Provenance описывает `buildDefinition`, `resolvedDependencies`, `runDetails.builder` и выходные `subject`. Но полнота `resolvedDependencies` даже до Build L3 включительно обозначена как **best effort**. Значит, наличие attestation не освобождает от проверки, достаточно ли в ней информации для конкретной пересборки. Проверять надо и ожидаемую пару signer–builder, а не просто существование подписи.[^15]

## 8. Практический протокол независимой пересборки сервиса

Первый шаг — объявить объект проверки: например, unsigned Linux/amd64 executable и отдельный нормализованный archive. Для каждого указать опубликованный digest, исходный commit либо digest source archive, recipe и допустимые преобразования. Если проверяется лишь executable внутри package, результат следует так и назвать. Это прямое следствие определения reproducible artifact.[^1][^12]

Далее составляется manifest входов. Это инженерная рекомендация на основе разобранных механизмов, а не новый формат стандарта:[^2][^4][^5][^15]

- Source tree, включая generated files, assets, submodules и local replacements; отдельно — правила получения отсутствующих generated inputs.
- `go.mod`, `go.sum`, режим modules/vendor/workspace и конкретное содержимое используемого `vendor` или workspace.
- Байты и версия Go toolchain; target `GOOS`, `GOARCH`, architecture features, tags, build mode и полный список compiler/linker flags.
- Политика VCS stamping, version strings и timestamps; при cgo — C compiler, sysroot, headers, library inputs и параметры линковки.
- Правила packaging: состав, порядок, modes, timestamps, ownership, archiver/compressor и граница подписи.

Затем другой сборщик получает source и inputs, выполняет объявленный рецепт и сравнивает **результат с опубликованным артефактом**, а не два собственных результата между собой. Два локальных совпавших файла — полезный regression check, но ещё не проверка релиза поставщика. Для усиления результата нужны отдельные административные границы и исключение общей уязвимой pipeline-инфраструктуры; именно это подчёркивает SLSA FAQ.[^14]

При несовпадении сначала сравнивают module/build information через `go version -m`, затем содержимое executable и упаковки. `runtime/debug.BuildInfo` помогает понять version и часть settings, но не является самодостаточным внешним свидетельством. Для сложных различий Lamb и Zacchiroli описывают diffoscope, который раскрывает вложенные форматы и показывает содержательные дельты. Несовпадение требует расследования; само по себе оно ещё не доказывает атаку.[^4][^7][^21]

Успешный протокол должен завершаться ограниченным утверждением: «при таком source digest и таком recipe независимо получен executable с таким digest, совпадающий с опубликованным». Утверждение «в продукте нет уязвимостей» из него не следует. Результаты, identity сборщика и область сравнения стоит публиковать рядом, чтобы потребитель мог проверить именно нужную связь, а не угадывать её по зелёному значку CI.[^1][^14][^15]

## Дискуссионные вопросы и противоречия

**«Go уже perfectly reproducible» против «мой сервис не пересобирается».** Russ Cox описывает специальное достижение **самого Go toolchain**, начиная с Go 1.21.0: устранение host-specific inputs его сборки. Это не тождественно обещанию для любого приложения, C library и release script. Наши разные outputs при изменении `-X` не опровергают Go: они показывают разные входы. Issue #77086 дополнительно показывает, почему оптимистичный pure-Go рецепт нельзя без проверки переносить на сложный cgo pipeline.[^9][^18]

**«Два CI лучше одного» против общей компрометации.** SLSA допускает verified reproducible builds как путь к более надёжной платформе, но требует настоящей независимости. Две jobs одного workflow, исполняющие одинаковые непроверенные helpers, не дают той же модели угроз, что два разных оператора. Ayer приводит полезный независимый пример мониторинга toolchain и checksum database, но его статья от 29 октября 2025 года — описание своего процесса на ту дату, не наше подтверждение текущего покрытия всех релизов.[^11][^14]

**«Совпал compiler» против Trusting Trust.** При одинаково скомпрометированном bootstrap compiler обычная пересборка может повторить внедрение. Wheeler описывает Diverse Double-Compiling: дополнительную цепочку с другим доверенным compiler и последующее сравнение. Здесь эта работа использована только в пределах прочитанного abstract; формальное доказательство и экспериментальные детали не оценивались. Локальный fixture-прогон вообще не проверял bootstrap chain.[^20]

**Удобство локализации против минимального окружения.** `CGO_ENABLED=0` и отключение VCS уменьшают число входов, однако меняют доступные пакеты и объём embedded metadata. Они допустимы только если соответствуют требованиям продукта. Воспроизводимость cgo-пары в нашем тесте показывает, что отказываться от cgo ради самого ярлыка необязательно; она не доказывает переносимость этой пары на другой sysroot.[^4][^5][^7]

## Недостаточность данных

Не проводилась независимая пересборка Go 1.27.3 через альтернативную bootstrap chain. Официальный отчёт и описание Ayer подтверждают существование таких проверочных процессов, но не заменяют собственное исполнение. Не проверялись реальные release archives конкретного self-hosted сервиса, signatures, `.tar.gz`, macOS/Windows signing и разные libc или GCC. Поэтому рекомендация — протокол проверки, а не сертификат какого-либо проекта.[^10][^11]

Не измерялись частота компрометаций, стоимость независимого rebuild service и вероятность, с которой совпадение байтов исключает вредоносную цепочку. В собранных источниках нет основания приписать нашему тесту такие числа. Академическая статья Lamb и Zacchiroli используется для анализа механизмов и диагностики; её исторические показатели Debian не перенесены на нынешний Go ecosystem.[^21]

## Заключение

`go.sum` нужен, но отвечает лишь за часть входов: modules. Проверяемый Go-релиз требует отдельного контракта на toolchain, source tree, flags, metadata, cgo environment и packaging. `-trimpath` сокращает один важный канал различий; `GOTOOLCHAIN=local` запрещает переключение у выбранной команды; ни один из этих флагов не делает весь release pipeline автоматически проверенным.[^2][^3][^4][^5]

Для небольшого сервиса разумная первая цель — независимо воспроизвести один unsigned executable для одной platform, затем расширить проверку на archive и подписанное распространение. Наш локальный прогон подтвердил ожидаемые свойства двух fixtures и упаковки, включая возможность воспроизводимого cgo build с фиксированным GCC. Он не установил независимое соответствие чужого релиза source code. Именно эту разницу надо сохранять в release notes: возможность пересборки, выполненная локальная проверка и независимая проверка опубликованного артефакта — разные результаты.[^1][^14]

## Quality Metrics

| Metric | Value |
|--------|-------|
| Sources found | 55 |
| Sources read | 22 |
| Sources cited | 21 |
| Academic sources | 2 |
| Official/documentation | 17 |
| Industry reports | 0 |
| News/journalism | 0 |
| Blog/forum | 2 |
| Citation coverage | 77% (44/57 содержательных абзацев по check_report.py) |
| Counter-arguments searched | Yes |
| Research rounds | 3 |
| Questions emerged | 6 |
| Questions resolved | 5 |
| Questions insufficient data | 1 |
| Count units | Found — URL кандидатов в журнале поиска; read/cited — отдельные документы, tagged source files и публикации, без удвоения альтернативных представлений |
| Access scope | Из 22 прочитанных документов у 21 доступны релевантные разделы полного текста; Wheeler — abstract only; общий обзор provenance прочитан, но не цитируется |
| Main text words | 3045, без frontmatter, code blocks, Quality Metrics и библиографии |
| Independence | Большинство первичных сведений о Go исходит от Go project; несколько его страниц не равны независимым подтверждениям |
| Empirical scope | 10 сборок fixtures, 7 парных сравнений с учётом упаковки, один хост; независимая пересборка toolchain не выполнялась |
| Open empirical question | Независимое соответствие реального release artifact объявленным исходникам здесь не проверялось |

[^1]: Reproducible Builds. "Definitions." Документация, прочитано 2026-11-10. https://reproducible-builds.org/docs/definition/
[^2]: Go project. "Go Modules Reference." Официальный справочник, срез 2026-11-10. https://go.dev/ref/mod
[^3]: Go project. "Go Toolchains." Официальная документация, срез 2026-11-10. https://go.dev/doc/toolchain
[^4]: Go Authors. "alldocs.go." Справочник cmd/go в исходном коде Go 1.27.3, прочитано 2026-11-10. https://raw.githubusercontent.com/golang/go/go1.27.3/src/cmd/go/alldocs.go
[^5]: Go Authors. "doc.go." Документация cmd/cgo, Go 1.27.3, прочитано 2026-11-10. https://raw.githubusercontent.com/golang/go/go1.27.3/src/cmd/cgo/doc.go
[^6]: Go Authors. "doc.go." Документация cmd/link, Go 1.27.3, прочитано 2026-11-10. https://raw.githubusercontent.com/golang/go/go1.27.3/src/cmd/link/doc.go
[^7]: Go Authors. "mod.go." runtime/debug: BuildInfo и BuildSetting, Go 1.27.3, прочитано 2026-11-10. https://raw.githubusercontent.com/golang/go/go1.27.3/src/runtime/debug/mod.go
[^8]: Go Authors. "pkg.go." cmd/go/internal/load: VCS stamping, Go 1.27.3, прочитано 2026-11-10. https://raw.githubusercontent.com/golang/go/go1.27.3/src/cmd/go/internal/load/pkg.go
[^9]: Russ Cox. "Perfectly Reproducible, Verified Go Toolchains." The Go Blog, 2023-08-28. https://go.dev/blog/rebuild
[^10]: Go project. "Go Reproducible Build Report." Официальный отчёт, срез 2026-11-10. https://go.dev/rebuild
[^11]: Andrew Ayer. "I'm Independently Verifying Go's Reproducible Builds." Авторский отчёт, 2025-10-29, прочитано 2026-11-10. https://www.agwa.name/blog/post/verifying_go_reproducible_builds
[^12]: Reproducible Builds. "Archive metadata." Документация, прочитано 2026-11-10. https://reproducible-builds.org/docs/archives/
[^13]: Chris Lamb, Ximin Luo. "SOURCE_DATE_EPOCH specification." Revision 1.1, 2017-11-27. https://reproducible-builds.org/specs/source-date-epoch/
[^14]: SLSA. "Frequently asked questions." Specification v1.2, прочитано 2026-11-10. https://slsa.dev/spec/v1.2/faq
[^15]: SLSA. "Build: Provenance." Specification v1.2, прочитано 2026-11-10. https://slsa.dev/spec/v1.2/build-provenance
[^16]: Go Authors. "build_trimpath.txt." Regression test cmd/go, Go 1.27.3, прочитано 2026-11-10. https://raw.githubusercontent.com/golang/go/go1.27.3/src/cmd/go/testdata/script/build_trimpath.txt
[^17]: Go Authors. "select.go." cmd/go/internal/toolchain, Go 1.27.3, прочитано 2026-11-10. https://raw.githubusercontent.com/golang/go/go1.27.3/src/cmd/go/internal/toolchain/select.go
[^18]: golang/go contributors. "cmd/go: non reproducible builds since cgo_ldflag that contains build path." GitHub issue #77086, прочитано 2026-11-10; сообщения участников, не самостоятельное подтверждение дефекта. https://github.com/golang/go/issues/77086
[^19]: Go project. "All releases." Официальный download catalog и его JSON metadata, срез 2026-11-10. https://go.dev/dl/
[^20]: David A. Wheeler. "Countering Trusting Trust through Diverse Double-Compiling." ACSAC 2005; arXiv:1004.5548v1, 2010-04-30; прочитан abstract. https://arxiv.org/abs/1004.5548v1
[^21]: Chris Lamb, Stefano Zacchiroli. "Reproducible Builds: Increasing the Integrity of Software Supply Chains." arXiv:2104.06020v1, 2021-04-13; релевантные разделы полного текста. https://arxiv.org/html/2104.06020v1
