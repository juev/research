---
title: "Jujutsu/jj: что это, как пользоваться и как подключить к Git-проекту"
date: 2026-04-27T11:28:00+03:00
---

## Исследовательский вопрос

Цель обзора: понять, что такое Jujutsu (`jj`), какие концепции отличают его от Git, как выглядит базовый рабочий процесс, в чем преимущества и ограничения, а также насколько разумно подключать `jj` к существующему проекту, который уже работает в Git.

## Краткий вывод

`jj` стоит рассматривать не как замену Git-хостинга, а как альтернативный клиент и модель работы поверх Git-репозитория: официальный проект описывает Jujutsu как Git-compatible VCS, а документация по совместимости прямо говорит, что Git backend позволяет сотрудничать с Git-пользователями так, что им не нужно знать, что вы используете не `git` CLI.[^1][^2] Для текущего проекта наиболее практичный путь внедрения - colocated-режим в существующем checkout: он добавляет `.jj` рядом с `.git`, оставляет Git-инструменты доступными и автоматически синхронизирует представления Git и Jujutsu при `jj`-командах.[^3]

Главная причина попробовать `jj` - более удобная работа с локальной историей: working copy является коммитом, нет отдельного index/staging area, rewrite-операции и rebase цепочек становятся обычными командами, а `jj undo`/operation log дают более широкую точку отката, чем привычная работа через Git reflog.[^4][^5][^6] Главный риск для данного репозитория - submodule `themes/<theme-submodule>`: официальная таблица Git compatibility помечает Git submodules как unsupported, хотя обещает, что они не будут потеряны.[^7] Поэтому внедрение лучше начать как личный локальный эксперимент, без требования к остальным участникам перейти на `jj`.

## Что такое jj

Jujutsu - это система контроля версий и CLI `jj`, спроектированные как более простая пользовательская модель поверх разных storage backend; в практическом Git-мире важен Git backend, который позволяет хранить данные в обычном Git-репозитории и работать с GitHub/GitLab remote.[^1][^2] Официальный README одновременно предупреждает, что проект остается experimental: Git compatibility описана как стабильная для повседневного использования многими разработчиками, но UX, отдельные функции и workflow gaps могут быть незрелыми для конкретного проекта.[^1]

В отличие от Git, где working tree, index и commit являются разными сущностями, `jj` превращает working copy в настоящий "working-copy commit": когда вы меняете файлы, следующий `jj` command автоматически снимет snapshot и перепишет этот рабочий коммит.[^4][^8] У каждого изменения есть change ID и commit ID: commit hash меняется при amend/rebase, а change ID остается стабильным и поэтому удобнее для ссылок на логическое изменение.[^8]

Минимальная модель такая:

- `@` - текущий working-copy commit.[^9]
- `@-` - родитель текущего коммита; часто это последний "готовый" коммит перед пустым working copy.[^8]
- `jj new` - закончить текущую change и начать новую поверх нее.[^8]
- `jj describe` или `jj commit -m` - дать описание текущему изменению; `jj commit` обычно описывает текущий коммит и создает новый working copy поверх него.[^8][^10]
- `jj squash` и `jj split` - перемещать изменения между коммитами вместо работы через staging area.[^6][^11]
- `jj rebase`, `jj edit`, `jj abandon`, `jj restore` - обычные команды для перестройки локального DAG.[^11]
- `jj op log`, `jj undo`, `jj op restore` - журнал операций и откат состояния репозитория.[^5]

## Основные концепции

### Working-copy commit вместо index

Официальная документация формулирует ключевое отличие прямо: Jujutsu автоматически создает commits из содержимого working copy, а добавленные файлы по умолчанию implicitly tracked, если они не попадают под ignore rules.[^4] Это делает обычный цикл короче, но меняет привычки: нет обязательного `git add`, а новые файлы лучше заранее покрывать `.gitignore`, иначе они будут попадать в snapshot.[^4][^7]

Эквивалент `git add -p && git commit` в Jujutsu - не "добавить часть в index", а разделить уже существующий working-copy commit через `jj split -i` или использовать `jj commit -i`; эквивалент частичного amend - `jj squash -i`.[^11] Это мощнее для patch-stack workflow, но первое время ощущается непривычно для людей, которые в IDE активно пользуются staging hunks.

### Changes и evolution

Change ID - центральная идея, потому что логическое изменение сохраняет идентичность при rewrite.[^8] Если вы поправили commit message, изменили файл или rebaseнули patch stack, Git commit hash может измениться, но `jj` продолжает понимать это как новую версию той же change.[^8] Историю эволюции одного изменения можно смотреть через `jj evolog`; FAQ уточняет, что `jj log` показывает parent-child graph, а не микрошаги изменения working copy.[^12]

### Revsets

Revset - функциональный язык выбора ревизий; большинство `jj` commands принимает revset, а символ `@` обозначает текущий working-copy commit.[^9] Примеры, которые быстро становятся полезны:

```sh
jj log -r '@ | @-'
jj diff -r @-
jj log -r 'bookmarks() & ~(main | remote_bookmarks())'
```

Такая модель сильна в больших локальных DAG и stacked changes, потому что операции применяются к выражениям, а не только к текущей branch.[^9][^10]

### Bookmarks вместо Git branches

В `jj` Git branches отображаются как bookmarks; bookmark - это именованный указатель, который нужен, когда вы хотите экспортировать изменения в Git remote.[^13] Документация для GitHub/GitLab workflow рекомендует сначала создавать stack commits, а bookmark заводить только перед push, либо пушить change с автосгенерированным именем через `jj git push --change @-`.[^10]

Важная разница: если вы заранее создали bookmark и продолжаете делать commits, Jujutsu не будет автоматически двигать bookmark так же, как Git двигает текущую branch; bookmark нужно сдвигать явно.[^10] При push `jj` делает safety checks и отказывается перезаписывать remote bookmark, если состояние remote не совпадает с последним известным положением.[^13]

### First-class conflicts

Jujutsu умеет записывать conflicted states в commits: rebase/merge может завершиться успешно, оставив конфликт как часть commit state, а исправить его можно позже.[^14] Это снижает количество режимов вида `rebase --continue` и позволяет держать stack поверх upstream даже при временных конфликтах.[^14] Но при обмене с Git-пользователями такие состояния лучше не публиковать: Git tools видят конфликтные файлы иначе, а colocated workspaces имеют специальные ограничения для conflicted revisions.[^3][^14]

### Operation log

Каждая изменяющая операция записывается в operation log; `jj undo` отменяет операцию, а `jj op restore` может восстановить весь view репозитория к более раннему состоянию.[^5] Для Git-экспертов официальная документация подчеркивает, что operation log хранит состояние всего репозитория, а не только историю отдельной ref, как reflog.[^6]

## Как пользоваться: базовый рабочий процесс

Установка на macOS через Homebrew описана официально как `brew install jj`; runtime requirement - Git 2.41.0 или новее.[^15] В текущем окружении проверен Git `2.54.0`, то есть requirement выполнен, но бинарь `jj` сейчас не найден в `PATH`.

Начальная конфигурация:

```sh
brew install jj
jj config set --user user.name "Your Name"
jj config set --user user.email "you@example.com"
```

Базовый цикл для GitHub/GitLab:

```sh
jj st
jj new main
# редактируете файлы
jj diff
jj commit -m "feat: add something"
# редактируете следующий коммит
jj commit -m "test: cover something"
jj git push --change @-
```

Если нужен именованный bookmark:

```sh
jj bookmark create feature-name -r @-
jj bookmark track feature-name
jj git push
```

Обновление с remote пока не является прямым `git pull`: официальная GitHub/GitLab инструкция описывает двухшаговый процесс `jj git fetch`, затем rebase локальных branches/changes поверх `main`, например `jj rebase -o main`.[^10]

Полезная шпаргалка для привычек Git:

| Git привычка | jj-эквивалент |
|---|---|
| `git status` | `jj st` |
| `git diff` | `jj diff` |
| `git add -p && git commit` | `jj split -i` или `jj commit -i` |
| `git commit --amend -p` | `jj squash -i` |
| `git checkout <commit>` | `jj edit <rev>` или `jj new <rev>` в зависимости от цели |
| `git rebase -i` для squash/split/reorder | `jj squash`, `jj split`, `jj rebase`, экспериментальный `jj arrange` |
| `git reflog` + reset | `jj op log`, `jj undo`, `jj op restore` |
| `git push --force-with-lease` | `jj git push` с bookmark safety checks |

## Преимущества

Первое преимущество - меньше состояний в повседневной работе: нет отдельного staging area, а рабочее дерево всегда представлено commit-like объектом.[^4][^6] Это делает amend, split и squash обычными операциями над commits, а не комбинацией index, temporary commits и interactive rebase.[^6][^11]

Второе - сильная поддержка rewrite-heavy workflow. Официальная страница для Git experts показывает пример, где вместо `git commit --fixup` и `git rebase -i --autosquash` можно сразу сделать `jj squash --into abc`, после чего descendants будут автоматически rebased поверх исправленного коммита.[^6] Для stacked PRs и аккуратной истории это практично.

Третье - более надежный локальный recovery model: operation log позволяет видеть и откатывать операции на уровне всего repository view.[^5][^6] Это особенно полезно при ошибочном rebase, abandon, restore или движении bookmarks.

Четвертое - миграция не требует отказаться от Git: colocated workspace позволяет использовать `jj` и `git` рядом, а GitHub/GitLab остаются обычными Git remote.[^3][^6][^10] Для команды это снижает организационный риск: один разработчик может пользоваться `jj`, остальные продолжают работать через Git.

Пятое - first-class conflicts убирают часть аварийности rebase/merge: конфликт можно хранить как состояние commit и разрешить позже.[^14] Это меняет психологию работы с длинными локальными stack: можно чаще rebase на upstream и не блокироваться на первом конфликте.

## Недостатки и ограничения

Первый недостаток - проект официально experimental, несмотря на стабильную Git compatibility для многих daily workflows.[^1] Это означает, что перед командным внедрением стоит проверить конкретные сценарии: IDE, hooks, CI, GitHub CLI, submodules, LFS, signing, release tooling.

Второй - несовместимость с рядом Git features. В официальной Git compatibility таблице `.gitattributes`, hooks, submodules, partial clones, Git worktree и Git LFS отмечены как unsupported или partial; staging area игнорируется.[^7] Для текущего проекта особенно важны submodules, потому что `themes/<theme-submodule>` подключен как Git submodule.

Третий - colocated mode удобен, но не бесплатен. Документация разрешает смешивать `jj` и `git` commands, но рекомендует в основном использовать Git read-only и делать изменения через `jj`, потому что mutating interleaving повышает шанс branch/bookmark conflicts или divergent change IDs.[^3] IDE, которые автоматически делают `git fetch`, тоже могут создавать неожиданные операции импорта refs.[^3]

Четвертый - Git HEAD в colocated workspace часто будет detached, потому что в `jj` нет идеи "current tracked branch" в том же смысле, что в Git.[^3][^10] Для людей и инструментов, которые ожидают branch checkout, это может выглядеть странно.

Пятый - модель auto-track требует дисциплины с ignore files. Jujutsu автоматически snapshot-ит добавленные файлы, поэтому generated files надо заранее исключать через `.gitignore` или настраивать `snapshot.auto-track`; иначе придется делать `jj file untrack`.[^4][^7]

## Подключение к существующему Git-проекту

Типичный репозиторий для пилота уже находится на `main`, отслеживает `origin/main`, имеет чистое рабочее дерево и использует Git-версию выше минимального требования `2.41.0`.[^15] Если в проекте есть Git submodule, его стоит считать отдельным риском:

```text
themes/<theme-submodule> -> <theme-repository-url>
```

Из-за submodule лучше не начинать с `jj git clone` в новый каталог как основной путь, а подключить `jj` к уже существующему Git checkout в colocated mode и держать `git submodule` операции в Git. Практический старт:

```sh
brew install jj
cd <repo>
git status --short --branch
jj git init --colocate
jj st
jj log
```

Если `jj git init --colocate` отработал, в корне появится `.jj`; `.git` останется на месте. Для личного использования `.jj` не нужно коммитить; обычно это локальная metadata-директория, как `.git`.

Рекомендуемый pilot workflow:

```sh
jj git fetch
jj new main
# правки только в superproject, без изменения themes/<theme-submodule>
jj diff
jj commit -m "docs: update note"
jj git push --change @-
```

Для submodule-действий безопаснее явно использовать Git:

```sh
git submodule update --init --recursive
cd themes/<theme-submodule>
git fetch
git checkout <needed-commit>
cd ../..
git status
jj st
```

Если нужно отказаться от эксперимента до публикации изменений, удаление `.jj` вернет checkout к обычному Git-использованию; перед этим стоит убедиться, что все нужное экспортировано в Git и видимо в `git log`/`git status`.

## Практические правила внедрения

1. Начинать только с личного colocated workspace. Команде не нужно менять процессы, пока вы не проверите push, PR, submodule update и Hugo build.
2. Использовать `git` read-only или для submodules; изменения в superproject делать через `jj`.
3. Не публиковать conflicted commits в remote, если downstream tools или другие участники используют Git CLI.
4. Настроить `.gitignore` до активного использования, потому что auto-track быстро подхватывает новые файлы.
5. Для GitHub/GitLab сохранять привычную границу: remote - Git, локальная история - `jj`.
6. Если IDE начинает путать branch/HEAD, либо отключить mutating Git-интеграции, либо вернуться к Git для этого проекта.

## Лучшие практики использования jj

### Начинайте работу с change, а не заканчивайте ей

В Git привычный ритм часто выглядит как "сначала работаю, потом собираю commit"; в `jj` естественнее сначала создать или выбрать change, описать намерение и дальше уточнять описание по мере работы.[^19] Это соответствует модели working-copy commit: текущая change уже существует, а `jj describe` можно вызывать до, во время или после редактирования.[^8][^19]

Практический шаблон:

```sh
jj new main
jj describe -m "docs: explain jj pilot workflow"
# правки
jj diff
jj new
```

Если вы не уверены, как именно разобьете работу, не пытайтесь заранее идеально разложить все по commits. Сначала сделайте рабочее состояние, затем используйте `jj split`, `jj squash -i` или `jj absorb`, потому что официальная модель `jj` ожидает, что commits можно дешево переписывать и переносить.[^6][^11]

### Держите `@` пустым перед push

В GitHub/GitLab workflow официальные примеры пушат `@-`, потому что после `jj commit -m` текущий `@` обычно становится новым пустым working-copy commit, а содержательная работа лежит в его родителе.[^10] Хорошая привычка перед push:

```sh
jj st
jj log -r 'remote_bookmarks()..@'
jj diff
```

Если `jj diff` показывает неожиданные изменения в `@`, сначала решите, что это: отдельная следующая change (`jj commit -m ...`), поправка к предыдущей (`jj squash`/`jj squash -i`) или мусор, который надо убрать через `jj restore`/ignore rules.[^4][^11]

### Используйте squash workflow вместо Git index

Для людей, привыкших к `git add -p`, самая стабильная ментальная модель - считать текущий `@` временной рабочей корзиной, а затем переносить нужные куски в родительский commit через `jj squash -i`.[^11][^24] Это дает эквивалент staging без отдельного index: текущий commit хранит все WIP, а интерактивный squash выбирает, что войдет в предыдущую change.[^6][^24]

Типовой цикл:

```sh
jj new main
# много правок
jj diff
jj squash -i
jj describe -r @- -m "feat: focused change"
jj new
```

Если нужно разложить один большой WIP на несколько последовательных commits, используйте `jj split -i`. При этом стоит помнить замечание Chris Krycho: разбиение большой кучи изменений в `jj` все еще может иметь больше cognitive load, чем привычные GUI/IDE workflows с Git index, потому tooling вокруг split пока менее зрелый.[^23]

### Делайте маленькие stack changes, а bookmark создавайте поздно

Официальный GitHub/GitLab guide прямо рекомендует сначала создавать stack commits, а bookmark заводить только перед публикацией.[^10] Это снижает шум в локальных refs и лучше соответствует `jj`: локальный DAG может быть богаче, чем набор веток, а remote все равно увидит обычный Git bookmark/branch.[^10][^13]

Для одноразового PR удобно:

```sh
jj git push --change @-
```

Для долгоживущей ветки удобнее именованный bookmark:

```sh
jj bookmark create feature-name -r @-
jj bookmark track feature-name
jj git push
```

Если после review вы добавляете commit сверху, сдвигайте bookmark явно через `jj bookmark move your-feature --to @-`; если переписываете clean commits, используйте `jj squash` и затем `jj git push --bookmark your-feature`.[^10] Не рассчитывайте, что bookmark будет двигаться сам как текущая Git branch: документация специально предупреждает, что при Git-like предварительном bookmark workflow его нужно двигать вручную.[^10]

### Fetch и rebase держите раздельно

В `jj` нет полного аналога `git pull`: обновление remote state и изменение локальной истории разделены на `jj git fetch` и rebase локальных changes поверх trunk.[^10][^23] Это не просто недостающая команда, а полезная дисциплина: сначала посмотреть, что пришло, потом явно решить, что именно rebase-ить.

Практический цикл для одного stack:

```sh
jj git fetch
jj log -r 'remote_bookmarks()..@'
jj rebase -o main
```

Если есть несколько активных bookmarks/branches, rebase нужно делать для каждого stack или передавать несколько `-b`, как описывает официальный guide.[^10] Для fork/upstream схемы настройте default remotes явно, например `git.fetch = "upstream"` и `git.push = "origin"`, чтобы не отправить изменения не туда.[^10][^21]

### Проверяйте bookmarks перед push

`jj git push` делает safety checks, похожие по цели на `git push --force-with-lease`, и откажется пушить при конфликтном или неожиданно сдвинутом remote bookmark.[^13] Но локальная дисциплина все равно важна:

```sh
jj bookmark list
jj st
jj git fetch
jj git push --bookmark feature-name
```

Если bookmark конфликтный, `jj status`, `jj bookmark list` и `jj log` покажут состояние, а исправление обычно сводится к `jj bookmark move`, merge через `jj new` или rebase одной стороны на другую.[^13] Для текущего проекта с одним `origin` достаточно простого правила: перед push всегда `jj git fetch`, затем `jj st`.

### Используйте operation log как штатный recovery-инструмент

Лучший способ не бояться rewrite-heavy workflow - регулярно смотреть `jj op log` и помнить про `jj undo`.[^5][^6] Официальный Git experts guide подчеркивает, что operation log хранит состояние всего repository view, поэтому откат не требует угадывать, какая именно ref подвинулась.[^6]

Практический минимум:

```sh
jj undo
jj op log -p
jj --at-operation <op-id> log
```

Если проблема не в последней операции, сначала найдите нужную операцию через `jj op log -p`, затем смотрите состояние через `--at-operation`; только после этого делайте restore/undo. Это особенно полезно после неудачного `rebase`, `squash`, `abandon` или ошибочного движения bookmark.[^5][^6]

### Настройте защиту от случайного push WIP

Если вы часто оставляете локальные черновики, настройте `git.private-commits`, чтобы `jj` отказывался пушить commits с описаниями вроде `wip:*` или `private:*`.[^20] Это особенно полезно, потому что `jj` делает publishing через bookmarks/changes, а не через текущую Git branch, и легко забыть, что ancestor приватного WIP нужен для push потомков.[^20]

Пример user config:

```toml
[git]
private-commits = "description(glob:'wip:*') | description(glob:'private:*')"
```

В том же config стоит настроить editor/diff tooling и completion. Официальная установка описывает standard и dynamic completions, а settings docs дают готовые точки настройки для bookmark advance и templates.[^15][^20]

### В colocated Git-проекте смешивайте инструменты осознанно

Colocated mode полезен именно тем, что можно вернуться к Git-командам, если конкретная операция проще в Git или нужна tooling-интеграция.[^3][^6][^23] Но официальная Git compatibility page предупреждает: interleaving mutating `jj` и `git` commands повышает шанс запутанных branch/bookmark conflicts или divergent change IDs, а `jj` игнорирует Git staging area и не понимает unfinished Git rebase states.[^3]

Для текущего репозитория разумная политика такая:

- `jj`: commits, rebase, squash/split, push/fetch, локальная история.
- `git`: submodule operations, read-only inspection, emergency fallback.
- IDE Git UI: read-only status/diff, если она корректно ведет себя с detached HEAD.

Из-за `themes/<theme-submodule>` все операции вида `git submodule update`, checkout commit внутри submodule и проверка `.gitmodules` должны оставаться Git-driven, пока submodule support в `jj` не станет полноценным.[^7][^18]

### Учитесь по уровням, а не через полную миграцию сразу

Jujutsu for everyone рекомендует после базового уровня отложить учебник и попрактиковаться, а для командной работы пройти минимум уровни solo и collaboration.[^22] Это хорошее правило и для Git-опытных пользователей: сначала `st/new/describe/diff/commit/log`, затем `squash/split`, затем bookmarks/push, и только после этого stacked PRs, multiple workspaces, custom revsets и advanced config.[^19][^22]

Минимальный learning path:

1. День 1: `jj st`, `jj log`, `jj new`, `jj describe`, `jj diff`.
2. День 2: `jj commit -m`, `jj squash -i`, `jj split -i`.
3. День 3: `jj git fetch`, `jj rebase -o main`, `jj git push --change @-`.
4. После первой ошибки: `jj undo`, `jj op log -p`, `jj evolog`.
5. После первого PR: named bookmarks и review-comment workflow.

### Для проекта с Hugo и submodule: рекомендуемый daily workflow

С учетом Git remote, Hugo-проекта и submodule `themes/<theme-submodule>`, оптимальный повседневный workflow выглядит так:

```sh
cd <repo>
jj git fetch
jj new main

# редактируете content/assets/config, не трогая submodule без отдельного намерения
jj st
jj diff
jj commit -m "docs: update article"

# локальная проверка сайта обычными проектными командами
# например: hugo server / hugo

jj git push --change @-
```

Если правка случайно затронула `themes/<theme-submodule>`, сначала остановитесь и проверьте это Git-командами. Пока submodules unsupported в `jj`, обновление темы лучше оформлять как отдельную Git-aware задачу: `git submodule update`, проверка `git status`, затем уже `jj st` в superproject.[^7][^18]

## Дискуссионные вопросы и противоречия

Главное противоречие в источниках касается "latest" версии: docs changelog содержит `0.40.0 - 2026-04-01`, но GitHub `releases/latest`, проверенный 2026-04-27, редиректит на `v0.39.0`, опубликованный 2026-03-04.[^16][^17] Поэтому в практических командах лучше не фиксировать версию вручную, а ставить официальный latest через Homebrew/Cargo/GitHub release channel и проверять `jj --version` локально.

Второй открытый вопрос - зрелость submodules. Официальная compatibility page сейчас говорит "Submodules: No", а design doc по submodules является aspirational/work-in-progress документом с roadmap фазами.[^7][^18] Для этого репозитория это не блокирует личный pilot, но блокирует уверенное командное внедрение без отдельного теста theme update workflow.

Третий вопрос - tooling. Официальные docs предупреждают, что GitHub CLI имеет проблемы в non-colocated repos и предлагает `GIT_DIR=$(jj git root)` workaround; colocated mode для текущего проекта этого почти наверняка избежит, но IDE с background Git operations все равно может создавать лишнее смешивание Git/JJ операций.[^10][^3]

## Quality Metrics

- Sources found: 32
- Sources cited: 24
- Source types: official: 18, industry/blog: 5, community: 9
- Citation coverage estimate: 90%
- Sub-questions investigated: 9
- Research rounds: 3
- Questions emerged during analysis: 5
- Questions resolved: 4
- Questions with insufficient data: 1

[^1]: Jujutsu GitHub README, project overview and experimental-status note. https://github.com/jj-vcs/jj
[^2]: Jujutsu docs, "Git compatibility", Git backend and Git collaboration model. https://docs.jj-vcs.dev/latest/git-compatibility/
[^3]: Jujutsu docs, "Colocated Jujutsu/Git workspaces", automatic import/export and caveats. https://docs.jj-vcs.dev/latest/git-compatibility/
[^4]: Jujutsu docs, "Working copy", automatic snapshots and implicit tracking. https://docs.jj-vcs.dev/latest/working-copy/
[^5]: Jujutsu docs, "Operation Log", undo/restore and concurrency notes. https://docs.jj-vcs.dev/v0.23.0/operation-log/
[^6]: Jujutsu docs, "Jujutsu for Git experts", side-by-side Git use, no index, safer history editing, operation log. https://docs.jj-vcs.dev/latest/git-experts/
[^7]: Jujutsu docs, "Git compatibility", supported/unsupported Git features. https://docs.jj-vcs.dev/latest/git-compatibility/
[^8]: Jujutsu docs, "Tutorial and bird's eye view", working-copy commit, change ID, `jj new`, `jj squash`, `jj edit`. https://docs.jj-vcs.dev/latest/tutorial/
[^9]: Jujutsu docs, "Revsets", revset language and `@` symbol. https://docs.jj-vcs.dev/latest/revsets/
[^10]: Jujutsu docs, "Using Jujutsu with GitHub and GitLab Projects", basic workflow, push, update, colocated workflow. https://docs.jj-vcs.dev/latest/github/
[^11]: Jujutsu docs, "FAQ", `jj split -i`, `jj squash -i`, interactive rebase equivalents. https://docs.jj-vcs.dev/latest/faq/
[^12]: Jujutsu docs, "FAQ", working-copy saves and `jj evolog`. https://docs.jj-vcs.dev/latest/faq/
[^13]: Jujutsu docs, "Bookmarks", bookmark updates, push safety checks, conflicts. https://docs.jj-vcs.dev/latest/bookmarks/
[^14]: Jujutsu docs, "First-class conflicts", conflict commits and advantages. https://docs.jj-vcs.dev/latest/conflicts/
[^15]: Jujutsu docs, "Installation and setup", install commands and Git 2.41.0 runtime requirement. https://docs.jj-vcs.dev/latest/install-and-setup/
[^16]: Jujutsu docs, "Changelog", entries including 0.40.0 dated 2026-04-01. https://docs.jj-vcs.dev/latest/changelog/
[^17]: GitHub releases/latest for jj-vcs/jj, observed redirect to v0.39.0 release page. https://github.com/jj-vcs/jj/releases/latest
[^18]: Jujutsu design docs, "Git submodules", aspirational work-in-progress roadmap. https://docs.jj-vcs.dev/latest/design/git-submodules/
[^19]: Steve Klabnik, "A recap and some thoughts", Jujutsu Tutorial: start work by creating/describing changes. https://steveklabnik.github.io/jujutsu-tutorial/hello-world/recap.html
[^20]: Jujutsu docs, "Settings", private commits, bookmark advance, templates, config examples. https://docs.jj-vcs.dev/latest/config/
[^21]: Jujutsu docs, "Multiple remotes", upstream/origin workflow and fetch/push defaults. https://docs.jj-vcs.dev/latest/guides/multiple-remotes/
[^22]: "Jujutsu for everyone", tutorial structure and learning levels. https://jj-for-everyone.github.io/structure.html
[^23]: Chris Krycho, "jj init", practical Git interop experience and tooling caveats. https://v5.chriskrycho.com/essays/jj-init/
[^24]: "Getting Started with Jujutsu", "The Squash Workflow", using `jj squash -i` as an index-like workflow. https://jj-tutorial.github.io/tutorial/two-basic-workflows/the-squash-workflow.html
