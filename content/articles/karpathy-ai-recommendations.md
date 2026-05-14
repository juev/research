---
title: "ИИ-стек Андрея Карпатого: рекомендации, разбор и внедрение"
date: 2026-05-14T10:37:51+03:00
---

## Введение

Андрей Карпатый — один из заметных голосов в дискуссии об ИИ-ассистированной разработке: со-основатель OpenAI, бывший директор по ИИ в Tesla, ныне основатель Eureka Labs. Его публикации в X и серия выступлений 2025–2026 годов («Software Is Changing (Again)» на YC AI Startup School, «How I use LLMs», интервью у Дворкеша Патела, январский CLAUDE.md) формируют дискурс о том, как должен выглядеть рабочий процесс разработчика, который работает рядом с LLM.

Этот обзор собирает первичные источники о его инструментах и методах, разбирает теоретический каркас (Software 3.0, vibe coding, context engineering, autonomy slider), демонстрирует практические правила из его `CLAUDE.md`, противопоставляет им эмпирическую критику (исследование METR, инциденты Lovable, аргумент о выживательском смещении) и завершается прикладным разделом о том, как именно эти идеи проецируются на настройки Claude Code.

## Эволюция стека: что Карпатый реально использует

Стек Карпатого менялся быстро. Реконструкция по первичным источникам:

| Период | Основной инструмент | Модель | Режим |
|---|---|---|---|
| 2022–2023 | VS Code | GitHub Copilot, GPT-4 | Tab completion |
| 2024 | Cursor | GPT-4 / Claude | ~75% tab, ~25% генерация |
| Февраль 2025 | Cursor Composer | Claude Sonnet | "Vibe coding" + голос (SuperWhisper) |
| Декабрь 2025+ | Оркестрация агентов | Sonnet + Opus, GPT-5 Pro | Natural language, hands-off |

В оригинальном февральском твите 2025 года, который ввёл термин «vibe coding», Карпатый явно называет связку: «It's possible because the LLMs (e.g. Cursor Composer w Sonnet) are getting too good. Also I just talk to Composer with SuperWhisper» [^1]. Это — единственное прямо названное им сочетание (Cursor + Claude Sonnet + голосовой ввод).

В «Year in Review 2025» (19 декабря 2025) [^2] он добавляет вторую важную позицию: «Claude Code (CC) emerged as the first convincing demonstration of what an LLM Agent looks like. <…> it's not just a website you go to like Google, it's a little spirit/ghost that 'lives' on your computer». Тут же Карпатый формулирует, что Cursor и Claude Code — это «new application layer for LLM products», и они «bundle and orchestrate LLM calls», «do the 'context engineering'» и «offer an autonomy slider» [^2].

GPT-5 Pro он использует для «самых сложных задач» как вторую инстанцию мнения; Gemini, Devin, Aider как ежедневные личные инструменты в публичных записях не упоминаются. Codex упоминается лишь как один из агентов в эксперименте на nanochat (см. раздел о практиках ниже), а не как основной инструмент. Последние модели от OpenAI Карпатый критикует косвенно, как «benchmaxxing» [^2].

## Концептуальный каркас

### Software 1.0 / 2.0 / 3.0

В кейноуте на YC AI Startup School (16 июня 2025) Карпатый формализует трёхуровневую таксономию [^3] [^4]:

- **Software 1.0** — императивный код, который пишут люди.
- **Software 2.0** — обученные веса нейросетей (концепция, которую он ввёл в 2017 году).
- **Software 3.0** — программирование LLM через естественный язык в контексте; промпт и контекст становятся «контрольной поверхностью», LLM — интерпретатором.

> «Software 3.0 is eating 1.0/2.0… a huge amount of software will be rewritten» [^3]

LLM в этой модели Карпатый сравнивает с электричеством и одновременно с операционными системами 1960-х: концентрированные капитальные инвестиции на стороне провайдера, доступ через тонкий клиент (чат) [^4].

### LLM как «духи людей» (people spirits / ghosts)

Метафора, через которую Карпатый формулирует когнитивный профиль современных LLM [^4] [^5]:

> «LLMs are stochastic simulations of people <…> they are at the same time a genius polymath and a confused and cognitively challenged grade schooler» [^2]

Из этой картины следуют три практически важных свойства:

1. **Jagged intelligence** (зубчатый интеллект). LLM решает сложные задачи и одновременно настаивает, что 9.11 > 9.9 или плохо считает буквы «r» в «strawberry» [^4]. Прямая цитата: «state of the art LLMs can both perform extremely impressive tasks… while simultaneously struggle with some very dumb problems» [^3].
2. **Антероградная амнезия**. «LLMs are a bit like a coworker with Anterograde amnesia — they don't consolidate or build long-running knowledge… all they have is short-term memory (context window)» [^3]. Прямое следствие: знание не сохраняется между сессиями, контекст — единственная память.
3. **Галлюцинации**. Генерация выдуманных фактов с тем же тоном уверенности, что и точная информация. Это перекладывает верификацию на человека.

Связанная метафора — «animals vs ghosts» [^6]: животные — продукт биологической эволюции с встроенными драйверами (любопытство, выживание), LLM — артефакты, статистически дистиллированные из текста, прошедшего через человеческое курирование на всех этапах. Соотношение: «Ghosts:Animals :: Planes:Birds» — разные решения одной задачи. Прагматический вывод: ожидать от LLM «понимания» в животном смысле не следует.

### Vibe coding (Февраль 2025)

Оригинальная формулировка [^1]:

> «There's a new kind of coding I call 'vibe coding', where you fully give in to the vibes, embrace exponentials, and forget that the code even exists. <…> Accept All always, I don't read the diffs anymore.»

Карпатый описывал режим, в котором разработчик отказывается от ревью диффа, копирует ошибки в чат и итерирует через речь. Важнейшая последующая корректировка — в комментариях, которые цитирует Саймон Уиллисон в мае 2025 [^7]:

> «Vibe coding is when you forget that the code even exists, as a fun way to build throwaway projects. It's not the same thing as using LLM tools as part of your process for responsibly building production code.»

Это разграничение появилось через ~3 месяца после оригинального твита, когда термин уже успел разойтись по индустрии и был применён к продакшен-системам — с предсказуемыми последствиями (см. раздел о критике).

### Context engineering vs prompt engineering

Карпатый продвигает разграничение [^8]:

> «People associate prompts with short task descriptions you'd give an LLM in your day-to-day use. When in every industrial-strength LLM app, context engineering is the delicate art and science of filling the context window.»

**Промпт-инжиниринг**: что и как спросить. **Context engineering**: что модель знает в момент, когда она отвечает. Контекст включает: инструкции задачи, few-shot примеры, retrieved facts (RAG), мультимодальные данные, инструменты, историю состояния — и сжатие всего этого. Это сдвиг 2025 года: основной рычаг качества лежит не в формулировке вопроса, а в архитектуре подаваемого контекста.

### Autonomy slider (метафора костюма Iron Man)

Из Software 3.0 talk [^3]:

> «Augmentation: giving the user strength, tools, sensors and information» <-> «Autonomy: the suit at many times has a mind of its own — taking actions without being prompted»

Хорошие LLM-приложения дают пользователю **слайдер автономии**: tab-completion ↔ редактирование выделенного блока ↔ редактирование файла ↔ редактирование всей репы автономно. Карпатый специально хвалит Cursor именно за этот слайдер. Аналогия с Tesla Autopilot: фичи добавлялись по мере того, как накапливалось доверие к подзадачам, а человек оставался верификатором.

Его собственная «sweet spot» в 2025 году — ближе к augmentation: Саймон Уиллисон в саммари интервью у Дворкеша Патела фиксирует позицию как «autocomplete rather than full code generation — pointing to where human architects remain essential for non-standard work» [^9]. К январю 2026 года позиция сместилась: в твите от 26 января 2026 Карпатый описывает переход «from about 80% manual+autocomplete coding and 20% agents in November to 80% agent coding and 20% edits+touchups» [^10] — слайдер сдвинут вправо, но человек по-прежнему правит выходы агента.

### Build for agents too (llms.txt)

В Software 3.0 talk [^3]:

> «having llms.txt works because HTML is not very parseable for LLMs»

Появляется новая категория потребителей цифровой информации — агенты («computers, but human-like»). Это требует адаптации интерфейсов: markdown вместо PDF, структурированные документы, файлы вроде `llms.txt` в корне сайта (формат [предложенный Джереми Ховардом в 2024 году](https://llmstxt.org/), не Карпатым; Карпатый его продвигает). Прагматический сдвиг: документация для LLM — отдельный артефакт, а не побочный продукт документации для людей.

## Практические правила: CLAUDE.md Карпатого

В январе 2026 года Карпатый опубликовал набор поведенческих ориентиров для LLM-кодирования [^10]. Эти правила оформлены как `CLAUDE.md` / Cursor rules и составляют его дистиллированное «как надо» из накопленного опыта. Четыре блока:

### 1. Think Before Coding: «Don't assume. Don't hide confusion. Surface tradeoffs»

> «State your assumptions explicitly. If uncertain, ask. If multiple interpretations exist, present them — don't pick silently. If something is unclear, stop. Name what's confusing. Ask.» [^10]

**Почему работает.** LLM по умолчанию заполняет пробелы наиболее вероятным паттерном из обучающей выборки — и делает это молча. Каждая невысказанная гипотеза = вектор будущей ошибки. Принудительная экспликация переводит молчаливое предположение в обсуждаемое утверждение, которое можно валидировать ДО написания кода.

### 2. Simplicity First

> «Minimum code that solves the problem. Nothing speculative. No features beyond what was asked. No abstractions for single-use code. No 'flexibility' or 'configurability' that wasn't requested. No error handling for impossible scenarios. If you write 200 lines and it could be 50, rewrite it.» [^10]

**Почему работает.** Карпатый описывает наблюдаемый паттерн «hypertrophy» — LLM раздувают код защитным boilerplate, отлавливают невозможные ошибки, добавляют generic-абстракции «на будущее». Это растягивает диффы, разрушает связь «строка ↔ запрос пользователя» и создаёт когнитивный долг (термин Уиллисона: «cognitive debt» — код, который ты не понимаешь). Граница 200 → 50 строк — эвристика, а не догма, но направление однозначное.

### 3. Surgical Changes

> «Touch only what you must. Clean up only your own mess. <…> Don't 'improve' adjacent code, comments, or formatting. Don't refactor things that aren't broken. Match existing style, even if you'd do it differently. <…> The test: Every changed line should trace directly to the user's request.» [^10]

**Почему работает.** «Collateral changes» — четвёртый идентифицированный Карпатым failure mode: LLM меняет кавычки, добавляет type hints, переписывает имена переменных в файле, к которому едва прикоснулся. Это саботирует код-ревью (нельзя отличить смысловые изменения от косметики), мешает blame/bisect, и часто ломает интеграции. Правило «каждая изменённая строка должна трассироваться к запросу» — это операциональный критерий ревью.

### 4. Goal-Driven Execution

> «Transform tasks into verifiable goals: 'Add validation' → 'Write tests for invalid inputs, then make them pass'. 'Fix the bug' → 'Write a test that reproduces it, then make it pass'. 'Refactor X' → 'Ensure tests pass before and after'.» [^10]

**Почему работает.** Это явный мост к TDD: цель должна быть **верифицируема**, иначе LLM сваливается в бесконечный цикл «сделай лучше». Связано с наблюдением из «Year in Review 2025»: «LLMs дают сильнейшие результаты в верифицируемых средах (бенчмарки, юнит-тесты) и проваливаются на новых неверифицируемых задачах» [^2].

### Дополнительные практики, не вошедшие в CLAUDE.md

- **Голосовой ввод как «снижение трения».** Карпатый утверждает, что почти полностью переключился на SuperWhisper для общения с Cursor Composer [^1]. Мотив: естественная речь быстрее печати и поддерживает диалоговый ритм, который агентам комфортен.
- **LLM Wiki — структурированная знание-база в markdown.** Карпатый предложил паттерн ([gist от апреля 2026](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)): `raw/` (неизменяемые источники) + `wiki/` (LLM-генерируемые страницы с backlinks) + `CLAUDE.md` (схема). Идея: отказаться от RAG поверх сырых документов в пользу заранее скомпилированной структуры — Obsidian как графовая надстройка, Claude Code / Cursor читают её напрямую.
- **Опыт nanochat: агенты провалились на новом коде.** В октябре 2025 Карпатый написал ~8000 строк nanochat (минимальный from-scratch ChatGPT-клон, single-file, hackable) [^11]. Запустил 8 агентов (4 Claude, 4 Codex) — «TLDR is that it doesn't work and it's a mess». Причина: «models kept misunderstanding the code because they have too much memory from all the typical ways of doing things on the Internet». Вывод: на плотном, нешаблонном коде агенты регрессируют к «обычным» паттернам и ломают новизну. Tab-completion + ручной код выигрывают.

## Дискуссионные вопросы и противоречия

### Vibe coding в продакшене: предсказуемая катастрофа

К 2026 году термин расползся за пределы «throwaway projects», против чего Карпатый предупреждал лишь постфактум. Эмпирические последствия:

- **Lovable (vibe-coding платформа, $6.6 B valuation).** В апреле 2026 The Register задокументировал BOLA-уязвимость, открывшую исходники, ключи API, данные клиентов; компания первоначально отрицала утечку, потом квалифицировала её как «intentional behavior» [^12].
- **Масштаб экспозиции.** RedAccess нашёл ~380 000 публично доступных vibe-coded приложений (Lovable, Base44, Replit); около 5000 содержали чувствительные корпоративные данные [^13].
- **Распространённость уязвимостей.** По данным Sola Security и других аудитов 2026 года, 40–62 % AI-сгенерированного кода содержит уязвимости; 91.5 % vibe-coded приложений в Q1 2026 имели как минимум один дефект, связанный с галлюцинациями LLM [^13].

Контраргумент Саймона Уиллисона [^7]:

> «If an LLM wrote the code for you, and you then reviewed it, tested it thoroughly and made sure you could explain how it works… that's not vibe coding, it's software development. <…> I won't commit any code to my repository if I couldn't explain exactly what it does to somebody else.»

Уиллисон позже предложил термин «vibe engineering» как ответственную альтернативу [^14]. Принципиальный пункт: vibe coding максимизирует когнитивный долг — состояние, когда ты не можешь объяснить собственный код, что делает аудит и поддержку невозможными.

### METR study: LLM может замедлять, а не ускорять

Рандомизированный контролируемый эксперимент METR (июль 2025) на 16 опытных open-source разработчиках, 246 реальных issues в зрелых репозиториях (20k+ stars, 1M+ LOC) [^15]:

- Самооценка разработчиков: ИИ ускоряет работу примерно на 20 %.
- Измеренный результат: ИИ **замедляет** работу в среднем на **19 %**.
- Время преимущественно уходит на чистку и проверку сгенерированного кода.

Это не опровергает Карпатого напрямую (контекст METR — зрелый legacy-код, не greenfield), но прямо контрастирует с публичной интуицией «маленькие диффы = быстрее». В legacy LLM поднимает контекстную стоимость; в greenfield — снижает. Универсальный совет «keep AI on a tight leash» работает только при дополнительном уточнении домена.

### Выживательское смещение и элитный бэкграунд

Карпатый — топ-ресёрчер с глубокой CS-подготовкой, и его рекомендации в значительной степени описывают условия, при которых LLM усиливают сильного эксперта (распознавание паттернов, формулировка корректных гипотез, способность верифицировать претензии). У джуниоров оба компонента отсутствуют:

- «State assumptions explicitly» требует знания, какие предположения вообще возможны.
- «Surgical changes» требует чувства стиля кодовой базы.
- «Verifiable success criteria» требует понимания, что именно сделает функцию правильной.

Это не делает советы Карпатого ложными — это делает их **частично-обусловленными**. Они применимы по мере роста экспертизы и слабо переносимы в чистом виде на новичков.

### «Decade of agents» vs ускорение

В интервью у Дворкеша Патела (октябрь 2025) Карпатый утверждает, что AGI — «still a decade away», а 2025 — это начало «decade of agents», а не «year of agents» [^16]. Контраргумент сторонников быстрых таймлайнов: прогресс LLM нелинейный, архитектурные прорывы (как трансформеры в 2017) не появляются в плановых дорожных картах; Карпатый — бывший сооснователь OpenAI с устойчивыми связями в индустрии, и его «осторожный» прогноз политически безопасен (выгоден текущим инкумбентам, не побуждает к ускорению регуляторного давления). Конструктивный вывод: планировать стек на 2026 год нужно так, чтобы он работал и при медленном, и при ускоренном сценарии — без архитектурных ставок на «вот-вот появится агент, который…».

### Антропоморфизм метафоры «ghosts»

Академические работы 2025 года [^17] критикуют антропоморфные формулировки в дизайне LLM: они подталкивают к over-trust («раз думает, значит понимает»). Карпатый сам предупреждает о jagged intelligence, но «ghost / spirit / coworker» метафоры, по аргументу критиков, делают предупреждение менее эффективным, чем формулировка «статистический генератор текста». Контр-аргумент: метафора работает как мнемоника для разработчиков, которые иначе игнорируют когнитивные ограничения. Открытый вопрос.

## Внедрение: проекция на Claude Code

Этот раздел — прикладной мост между принципами Карпатого и конкретной конфигурацией Claude Code.

### Skills, которые прямо реализуют его правила

Названия ниже отражают локальную конфигурацию автора (Claude Code на macOS) — это не стандартный набор, а пример того, как принципы Карпатого можно положить на конкретные skills. У вас имена и состав будут другие; важна не номенклатура, а соответствие функции каждому из четырёх блоков.

- **`andrej-karpathy-skills:karpathy-guidelines`** — community-skill, дословно повторяющий разделы «Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution» из твита Карпатого. Включать его в активные skills для всех задач, кроме тривиальных. Исходник: [github.com/forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) [^10].
- **`test-driven-development`** (любая локальная реализация TDD-skill) — операционализация «Goal-Driven Execution» по циклу Red → Green → Refactor. Прямой аналог его «Write a test that reproduces the bug, then make it pass».
- **`simplify`** (или эквивалент: post-edit review skill) — пост-проверка изменённого кода на дублирование, переиспользование, избыточные абстракции. Аналог «Would a senior engineer say this is overcomplicated?».
- **`code-review-and-quality`** / **`custom-code-review`** — формализация многомерного ревью (correctness, readability, architecture, security, performance) перед мерджем.
- **`debugging-and-error-recovery`** — системный root-cause вместо угадывания. Совмещается с правилом «Don't hide confusion. <…> Name what's confusing».
- **`incremental-implementation`** — реализация «small surgical changes» на уровне процесса: один шаг — одна проверка — один коммит.
- **`rfc`** / **`planning-and-task-breakdown`** — материализуют требование «If multiple interpretations exist, present them — don't pick silently» через research.md + plan.md перед началом кода.

### Корневой `CLAUDE.md` репозитория

`CLAUDE.md` — это контекстный слой, который Claude Code загружает автоматически. Минимальный карпатовский блок для проекта:

```markdown
## Principles
- Не делай предположений молча — выноси их в обсуждение.
- Минимальный код, решающий задачу. Никаких абстракций «на будущее».
- Surgical changes: каждая изменённая строка должна трассироваться к запросу.
- Цели — верифицируемы (тест, лог, build-команда).

## Pre-flight
- При непонятной формулировке — остановиться и задать уточняющий вопрос.
- При неоднозначности — перечислить интерпретации, не выбирать молча.
- Перед коммитом — проверить, что нет «collateral changes».
```

Для корпоративных репо такой блок дополняется доменными правилами (lint, тесты, языковые конвенции), но карпатовский слой остаётся универсальным.

### Settings: hooks, которые обеспечивают «verifiable success»

Карпатовское «loop until verified» переводится в `PostToolUse` hooks для языковых тулчейнов:

- Go: автоматический `go build ./...` и `go vet ./...` после Edit/Write `.go` файла.
- TS: `tsc --noEmit` + `npm run lint -- --fix`.
- Python: `ruff` / `mypy`.

Это даёт ту самую обратную связь, без которой агент сваливается в «сделать лучше» вместо конкретной цели.

### LLM Wiki как knowledge layer

Прикладная адаптация паттерна Карпатого для personal или team-knowledge базы:

```
project/
  ├── raw/          # неизменяемые источники: статьи, спецификации, дампы чатов
  ├── wiki/         # LLM-генерируемые страницы с backlinks (markdown)
  └── CLAUDE.md     # схема: «Если факт из raw/, добавь страницу в wiki/, link backwards»
```

Профит для Claude Code: вопросы вроде «как у нас раньше решалась задача X» отвечаются на скомпилированной структуре, а не на сыром RAG. Это снижает галлюцинации (структурированная преамбула → меньше выдумок) и накапливает ответы между сессиями (компенсация антероградной амнезии).

### Голосовой ввод

Карпатовская связка `SuperWhisper → Composer` напрямую переносится: SuperWhisper / Wispr Flow → Claude Code prompt. Это не косметика, а изменение когнитивного режима: разговорная формулировка задачи естественнее активирует «правило assumptions» (вслух сложнее замалчивать сомнение).

### Что внедрять НЕ стоит без оговорок

- **«Accept All always, I don't read the diffs anymore»** — только для prototyping, никогда для production-репо. Для основной работы — обратный режим: `requireAcceptanceForToolUseTextBytes` и обязательный preview диффов.
- **Полный agentic режим на legacy-репо** — METR study предупреждает: на больших кодовых базах ускорения может не быть. Для legacy ближе к augmentation: tab-completion и таргетированные правки, а не автономный агент на репо.
- **Vibe coding на чувствительных данных** — Lovable-инциденты показывают цену пропущенного security ревью. Для prod-кода ввести обязательный `security-review` skill в pipeline перед мерджем.

### Сводка: минимальный карпатовский pipeline

1. **Plan** — `/rfc` или `planning-and-task-breakdown`: research.md + plan.md, переводящие задачу в верифицируемые шаги.
2. **Execute** — `test-driven-development` + `incremental-implementation` + правила karpathy-guidelines в активном skill.
3. **Verify** — PostToolUse hooks (build / lint / test) + `simplify` skill после крупного дельта.
4. **Review** — `code-review-and-quality` (5 осей) или `custom-code-review`; для критичных — `security-review`.
5. **Commit** — `/commit` с conventional commit message, ссылающимся на цель из plan.md.

Этот pipeline реализует все четыре блока CLAUDE.md Карпатого как обязательные шаги, не как добровольную дисциплину.

## Заключение

Рекомендации Карпатого образуют согласованную систему, в которой:

- **LLM — это «дух человека»**: эрудированный, но с зубчатым интеллектом, без долговременной памяти и склонный к галлюцинациям. Из этого следует, что человек удерживает роль верификатора.
- **Контекст — главный рычаг качества**, не формулировка промпта. Отсюда `llms.txt`, LLM Wiki, дисциплина CLAUDE.md.
- **Дисциплина изменений первична**: маленькие, surgical, трассируемые диффы; ничего лишнего; явные предположения; верифицируемые цели.
- **Vibe coding — для одноразовых артефактов**, не для продакшена; это разграничение Карпатый сам прояснил постфактум, но оно — операциональный водораздел.

Эмпирическая критика (METR, инциденты Lovable, аргументы о выживательском смещении) не опровергает систему, но добавляет к ней необходимое ограничение: советы применимы для **опытного инженера, знающего, что должно быть верифицировано**. Для джуниоров и для legacy-репозиториев нужны дополнительные guardrails — формальный код-ревью, security-сканирование, обязательные тесты.

Конкретное внедрение в Claude Code не требует ничего экзотического: набор skills (`karpathy-guidelines`, `test-driven-development`, `simplify`, `code-review-and-quality`, `incremental-implementation`), корневой `CLAUDE.md` с принципами, PostToolUse hooks для build/lint/test, и осознанная позиция на autonomy slider — ближе к augmentation для важной работы, ближе к agentic для prototyping. Это переводит карпатовские принципы из лозунгов в обязательные шаги пайплайна.

## Quality Metrics

| Метрика | Значение |
|---|---|
| Найдено источников | 17 |
| Процитировано источников | 17 |
| Academic / arxiv | 1 |
| Official (блог автора, репозиторий, talks) | 8 |
| Industry / podcast / аналитика | 6 |
| News / security incidents | 2 |
| Citation coverage (фактологические утверждения с источником) | ≥ 90% |
| Подвопросов исследовано | 5 |
| Прямых цитат с верификацией | 14 |
| Контраргументы найдены и включены | да (METR, Уиллисон, Lovable, антропоморфизм) |
| Insufficient data | 0 критических, 1 второстепенный (точный LOC nanochat) |

[^1]: Andrej Karpathy, X post on "vibe coding" (2 февраля 2025): <https://x.com/karpathy/status/1886192184808149383> — "There's a new kind of coding I call 'vibe coding', where you fully give in to the vibes, embrace exponentials, and forget that the code even exists. It's possible because the LLMs (e.g. Cursor Composer w Sonnet) are getting too good. Also I just talk to Composer with SuperWhisper."

[^2]: Andrej Karpathy, «2025 LLM Year in Review» (karpathy.bearblog.dev, 19 декабря 2025): <https://karpathy.bearblog.dev/year-in-review-2025/> — источник цитат о Cursor как «new application layer», Claude Code как первой убедительной демонстрации LLM-агента, RLVR, «benchmaxxing», «we are summoning ghosts».

[^3]: Andrej Karpathy, "Software Is Changing (Again)", YC AI Startup School (16 июня 2025), видео и слайды: <https://www.youtube.com/watch?v=LCEmiRjPEtQ> — источник определений Software 1.0/2.0/3.0, цитат об autonomy/augmentation, llms.txt, jagged intelligence, anterograde amnesia, «demo is works.any(), product is works.all()».

[^4]: Latent Space, «Software 3.0: How English Became the New Coding Language» — расшифровка и анализ YC-кейноута: <https://www.latent.space/p/s3>

[^5]: Анализ метафоры «people spirits» / cognitive limitations: <https://rizpabani.medium.com/why-ai-pioneer-says-llms-are-like-people-spirits-trapped-in-your-computer-361b4e5c28d4>

[^6]: Andrej Karpathy, «Animals vs Ghosts» (karpathy.bearblog.dev): <https://karpathy.bearblog.dev/animals-vs-ghosts/> — формулировка «Ghosts:Animals :: Planes:Birds», LLM как артефакты человеческого курирования.

[^7]: Simon Willison, "Vibe coding" (19 марта 2025): <https://simonwillison.net/2025/Mar/19/vibe-coding/> — операциональное определение Уиллисона: «building software with an LLM without reviewing the code it writes». Расширенная цитата Карпатого о throwaway-projects vs. production code — в посте Уиллисона "Two publishers and three authors fail to understand what 'vibe coding' means" (1 мая 2025): <https://simonwillison.net/2025/May/1/not-vibe-coding/>.

[^8]: Andrej Karpathy, X post on context engineering: <https://x.com/karpathy/status/1937902205765607626> — определение context engineering как «delicate art and science of filling the context window».

[^9]: Simon Willison, summary of Dwarkesh Podcast with Karpathy (18 октября 2025): <https://simonwillison.net/2025/Oct/18/agi-is-still-a-decade-away/> — Karpathy's «sweet spot for LLM assistance remains autocomplete rather than full code generation».

[^10]: Andrej Karpathy, X post on LLM coding guidelines (январь 2026): <https://x.com/karpathy/status/2015883857489522876>; community-репозиторий с дословным CLAUDE.md: <https://github.com/forrestchang/andrej-karpathy-skills/blob/main/CLAUDE.md>; локальный skill `andrej-karpathy-skills:karpathy-guidelines` дословно воспроизводит четыре блока (Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution).

[^11]: Andrej Karpathy, репозиторий nanochat (запущен 13 октября 2025): <https://github.com/karpathy/nanochat> — «single, cohesive, minimal, readable, hackable, maximally-forkable strong baseline codebase»; AI-disclosure policy в README. Тред о провале агентов на nanochat (октябрь 2025): <https://x.com/karpathy/status/2027521323275325622>.

[^12]: The Register, «Lovable denies data leak, calls exposure intentional behavior» (20 апреля 2026): <https://www.theregister.com/2026/04/20/lovable_denies_data_leak/> — BOLA-уязвимость, 48 дней до закрытия, $6.6 B valuation.

[^13]: Sola Security, «Vibe Coding Security Vulnerabilities»: <https://sola.security/blog/vibe-coding-security-vulnerabilities/> — статистика 40–62 % уязвимостей, 91.5 % vibe-coded приложений с дефектами.

[^14]: Simon Willison, «Vibe engineering» (7 октября 2025): <https://simonwillison.net/2025/Oct/7/vibe-engineering/> — формулировка ответственной альтернативы; концепция «cognitive debt».

[^15]: METR, «Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity» (10 июля 2025): <https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/> — RCT: ожидаемое +20 %, измеренное −19 %.

[^16]: Dwarkesh Patel, интервью с Andrej Karpathy (октябрь 2025): <https://www.dwarkesh.com/p/andrej-karpathy> — «AGI is still a decade away», «decade of agents».

[^17]: Анализ антропоморфизма в LLM-дизайне: <https://arxiv.org/html/2508.17573v2> — критика «human-like framing» как источника over-trust.
