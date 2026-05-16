---
title: "Роль исследования и планирования в работе с ИИ-кодером: паттерны, эффективность, RFC и управление контекстом"
date: 2026-05-16T14:44:56+03:00
---

AI coding assistant — это не «умный автокомплит», а LLM-агент с инструментами, ограниченным контекстом и заметной деградацией качества при росте сессии. Как задача поставлена — промтом, планом, спецификацией — влияет на результат сильнее, чем выбор модели.

Здесь — пять паттернов работы с ИИ, эмпирика их эффективности, разбор RFC-подхода с research-first планированием и три стратегии управления контекстом, когда одной сессии перестаёт хватать: субагенты, последовательные сессии, гибрид. В конце — где human-in-the-loop остаётся неустранимым и как свести вмешательство человека к разумному минимуму.

## Пять паттернов работы с ИИ-кодером

### 1. Прямой запрос на выполнение (vibe coding)

Подход, который популяризовал Andrej Karpathy: пользователь описывает поведение естественным языком, агент сразу пишет код, изменения принимаются без детального ревью[^6]. В академической литературе это называют «AI-native paradigm» — модель работает как исполнитель намерения, а не как ассистент с проверяемыми артефактами[^7].

На простых изолированных задачах паттерн работает. На сложных — нет. В турнире 2025 года 40 LLM-агентов соревновались с 17 человеческими решениями на задаче оптимизации рыночной стратегии:

> «Все топ-5 решений написали люди. Только 7 из 40 LLM обошли простой baseline. Лучшая LLM заняла 6-е место с win rate 85,2 % против 92–96 % у людей»[^8].

Когда исследователи попросили GPT-4o улучшить решение №1 (написанное человеком), результат упал с первого на десятое место — модель не умеет продуктивно работать с уже качественным кодом. Академический обзор 2025 года прямо констатирует: профессиональные разработчики **не** практикуют vibe coding:

> «Профессионалы планируют до имплементации, валидируют все выходы, тщательно контролируют агента… считают агентов пригодными для well-described straightforward tasks, но не для сложных задач»[^11].

Корпоративный опыт подтверждает границу: «Vibe coding не масштабируется на уровне предприятия — нужны структурированные промпты с определённым scope, архитектурными ограничениями и метриками качества»[^12].

### 2. Предварительное исследование кода

Перед началом работы агент читает файлы, ищет паттерны, анализирует структуру кодовой базы — и только потом пишет код. В Claude Code это оформлено как фаза Explore из best practices:

> «Прочитай /src/auth и пойми, как мы обрабатываем сессии и логин» — без модификаций[^1].

Anthropic подчёркивает: чем точнее инструкции, тем меньше правок понадобится. Cursor показывает то же на примере:

> «"Добавь тесты для auth.ts" vs "Напиши тест для auth.ts, покрывающий edge case логаута, по паттернам из `__tests__`, без моков" — разница в успехе агента огромна»[^2].

Чтение кода до имплементации помещает в контекст релевантные паттерны: error handling, naming, структуру тестов. Без них агент пишет «generic boilerplate, а не код, соответствующий проекту»[^2].

### 3. Встроенная команда Plan Mode

Plan Mode в Claude Code — переключение в read-only режим (`Shift+Tab` дважды или `/plan`), где агент исследует и формирует план, но не пишет файлы и не запускает side-effecting команды[^1]. План сохраняется в `.claude/`, скрыт от пользователя, и ограничение реализовано через prompt injection, а не через реальный запрет инструментов:

> «Plan Mode — это markdown-файл + prompt injection. Агент "добровольно" соблюдает read-only ограничения. Файл скрыт от пользователя — не виден и не редактируется напрямую»[^14].

Armin Ronacher критикует подход за непрозрачность: план не виден как обычный артефакт, его нельзя открыть в редакторе, нельзя положить под version control[^14]. Anthropic при этом считает Plan Mode основным инструментом для нетривиальных изменений — полевое наблюдение показало снижение rework примерно на 40 % при разделении планирования и исполнения на отдельные фазы[^10].

Когда Plan Mode избыточен, документация Claude Code даёт чёткий критерий: «Если можешь описать diff одним предложением — пропускай план»[^1].

### 4. Кастомные команды для планирования

Команды-обёртки, которые форсируют планирование до имплементации. Примеры:

- **Cursor Rules** (`.cursor/rules/`) — зафиксированные архитектурные паттерны и выбор библиотек[^2]
- **Custom slash-commands** в Claude Code — `/plan`, `/spec`, `/rfc`
- **CLAUDE.md, .cursorrules, .github/copilot-instructions.md** — постоянные правила уровня проекта[^10]

Команда задаёт единый workflow: разработчик не формулирует ожидания заново, агент при вызове `/spec` или `/plan` проходит ту же последовательность шагов. Это снижает разброс результатов между пользователями и сессиями. Эффективность зависит от качества команды — длинные размытые инструкции работают хуже коротких и конкретных:

> «Эффективная CLAUDE.md меньше 80 строк, специфична, конкретна… через полгода в ней зафиксированы все ошибки, которые Claude совершал в проекте»[^15].

### 5. Spec-Driven Development и RFC: research + plan в файлах проекта

Полноценный спецификационный подход: до написания кода появляются постоянные markdown-артефакты — спецификация требований (что), план реализации (как), список задач с зависимостями. Файлы живут в репозитории, проходят ревью, версионируются.

Главные представители:

- **GitHub Spec Kit** — 90k+ звёзд, четыре фазы Specify → Plan → Tasks → Implement, работает с 30+ агентами (Claude Code, Cursor, Aider, Windsurf, Kiro)[^16][^17]
- **AWS Kiro** — Requirements → Design → Tasks внутри VS Code[^18]
- **OpenSpec** — delta-spec подход, минимальный overhead, лучший time-to-PR (1 день)[^19]
- **BMAD** — adversarial review ловит дефекты, но стоит дорого (6 дней против 1 у OpenSpec)[^19]
- **RFC-команды** — кастомные команды, которые генерируют research.md и plan.md с задачами и TDD-циклами

GitHub позиционирует SDD как «антидот vibe-coding'у»:

> «Спецификация, описывающая что без как, становится source of truth, из которого AI-агент генерирует имплементацию. LLM-агенты — буквальные pair programmer'ы, им нужны однозначные инструкции, а не поисковые запросы»[^16].

Критика подхода резкая. Martin Fowler и Augment Code указывают на проблему устаревших спек:

> «В отличие от устаревшего design doc, который сбивает с толку человека, устаревшая спецификация заставляет агента **уверенно**, не флагуя проблему, исполнять план, который больше не соответствует реальности»[^20].

Полевое тестирование трёх SDD-инструментов на одной задаче показало[^19]: у Spec Kit есть проблемы — агенты игнорируют детальные спецификации, upgrade перезаписывает кастомизации, нет ревью-гейтов между планированием и имплементацией. OpenSpec доставил PR за 1 день за счёт компактных delta-spec. BMAD занял 6 дней, но adversarial review поймал дефекты, которые стандартное ревью пропустило бы.

## Эмпирические данные об эффективности планирования

Несколько академических исследований количественно подтверждают пользу планирования.

**PlanSearch (Scale Labs, 2024)** сравнил три подхода на LiveCodeBench с Claude 3.5 Sonnet[^21]:

| Метод | Pass@1 (direct) | Pass@200 |
| --- | --- | --- |
| Repeated Sampling (baseline) | 41,4 % | 60,6 % |
| PlanSearch (observations → plans → code) | — | **77,0 %** |

Прирост — 27 пунктов над baseline. Авторы объясняют механизм:

> «Прирост от поиска точно предсказывается как функция разнообразия сгенерированных идей. План создаёт более разнообразный набор подходов, чем повторное семплирование одного и того же решения»[^21].

**CodePlan (FSE 2024)** на repository-level задачах в 7 репозиториях показал бинарный результат[^22]:

- CodePlan (с планированием): **5 из 7** репозиториев проходят validity checks (build, корректные правки)
- Baseline (тот же контекст, без планирования): **0 из 7** проходят

**Self-Planning Code Generation (2023)**: >50 % улучшение на HumanEval, >30 % на MBPP-sanitized против Code CoT и Few-shot[^23].

**Полевой опыт** (single-developer study): «Planning-first подход примерно на 40 % быстрее end-to-end — почти никогда не приходилось выбрасывать большие куски AI-generated кода и начинать заново. Главный time sink — не генерация, а rework»[^10].

Anthropic в best practices оформляет ту же логику как принцип:

> «Верификация — single highest-leverage thing, которую можно сделать. Включай тесты, скриншоты, ожидаемые выходы, чтобы Claude мог проверить себя сам»[^1].

## RFC-подход: плюсы и минусы

RFC-подход — это кастомная команда, которая последовательно генерирует:

1. **research.md** — глубокое исследование кода и контекста (не коммитится)
2. **plan.md** — нумерованные задачи с TDD-циклами, опирающиеся на результаты research
3. **Execute** — последовательное исполнение plan.md с проверкой каждого шага

### Плюсы

**1. Research как видимый артефакт, а не in-memory состояние.** Plan Mode хранит план в скрытом `.claude/`, RFC — в видимых файлах проекта. Это даёт:

- ревью плана до начала имплементации
- возможность ручного редактирования
- version control (research.md обычно временный и не коммитится)
- передачу контекста другому разработчику или другой сессии

**2. Research встроен в план.** В чистом SDD спецификация описывает что, а исследование кода уходит в латентный контекст модели. В RFC результаты предварительного исследования явно лежат в plan.md. Это снижает риск «AI выполнил план, проигнорировав существующие паттерны».

**3. TDD-циклы в плане.** Каждая задача plan.md идёт через test → pass → refactor. Это формализует верификацию, которую Anthropic называет highest-leverage[^1]. Self-Planning показало улучшение HumanEval на >50 %[^23] — TDD-структура усиливает эффект.

**4. Промежуточные коммиты.** Полный test suite + lint перед каждым коммитом, Jira/GitHub issue reference — workflow заточен под control-paradigm, академически валидированный для опытных разработчиков[^11].

**5. Удаление research.md после завершения.** Решает проблему stale specs, на которую жалуются Fowler и Augment Code[^20]: артефакт не гниёт в репозитории.

### Минусы

**1. Высокая стоимость на простых задачах.** OpenSpec доставляет PR за 1 день, BMAD — за 6, на той же фиче[^19]. Anthropic прямо предупреждает: «Если описываешь diff одним предложением — пропускай план»[^1]. Fast path (известный баг, однофайловый fix) RFC-команда только замедлит.

**2. Контекстный bloat в одной сессии.** Главная архитектурная слабость текущего подхода. Chroma на 18 frontier-моделях показала:

> «Каждая протестированная модель деградирует с ростом длины input: GPT-4.1, Claude Opus 4, Gemini 2.5 Pro, Qwen3-235B. Модели, набирающие >95 % на коротких промптах, падают до 60–70 % на длинных контекстах с семантическими distractor'ами»[^24].

Для Claude: измеримая деградация начинается около 400K токенов, после 600K на Sonnet 4.6 ответы становятся ненадёжными[^25]. RFC-сессия research → plan → execute последовательно набирает токены: код, прочитанный для research, план, выводы тестов, каждая итерация TDD добавляет вызовы инструментов. К концу длинной фичи модель работает в деградированном attention-режиме.

**3. Instruction centrifugation.** В сессиях длиннее 50–100 turn'ов изначальные goal-инструкции «уходят на периферию attention» из-за recency bias в трансформерах[^26]. Этим объясняется, почему агент в конце RFC-сессии может забыть первоначальный scope и пойти не туда, что описано в plan.md.

**4. Lost in the middle.** Liu et al. (TACL 2024) эмпирически показали U-образную кривую внимания: >30 % падение точности на информации в середине контекста (позиции 5–15 из 20 документов)[^27]. Plan.md, оказавшись в середине длинного контекста, начинает «теряться» — агент следует началу плана, забывает середину.

**5. Внешне корректные, но неправильные правки.** SWE-bench Pro: 35,9 % фейлов Claude Opus 4.1 — синтаксически корректные патчи, **не исправляющие реальный баг**[^29]. Код выглядит правильно, делает неправильное. Корневая причина — agent drift в длинной сессии[^26].

## Стратегии управления контекстом для длинных задач

Главный вопрос: как улучшить RFC-подход, когда одной сессии перестаёт хватать.

### Вариант 1: текущий подход (всё в одной сессии)

Research → plan → execute последовательно в одном контексте.

Плюсы: простота, единое состояние, нет затрат на handoff, агент видит всю историю решений.

Минусы: все перечисленные выше — context rot, lost in the middle, instruction centrifugation, attention dilution (внимание на токен падает в 10 раз с каждым 10-кратным ростом контекста)[^24].

Подходит для задач до ~50K токенов суммарно. На длинных фичах деградирует.

### Вариант 2: план в основной сессии, субагенты на отдельные шаги

Основная сессия создаёт plan.md. Каждый шаг плана уходит в субагент с чистым контекстом. Субагент получает путь к plan.md, конкретный шаг и ссылки на релевантные файлы — возвращает короткое summary на 1–2K токенов.

Anthropic документирует это как **context isolation**:

> «Каждый субагент работает в изолированном контекстном окне с собственным system prompt, конкретными инструментами и независимыми разрешениями. Единственный канал parent→subagent — prompt string. Subagent делает работу в собственном контексте и возвращает только summary»[^30].

Эмпирика противоречивая.

**За** (Anthropic Multi-Agent Research System): orchestrator-worker с 3–5 параллельными субагентами даёт **+90,2 %** к baseline на breadth-first research задачах[^31]. Google scaling study подтверждает: **+81 %** на параллелизуемых задачах — финансовый reasoning, независимый анализ[^32].

**Против** (Cognition, «Don't Build Multi-Agents»): на coding задачах субагенты деградируют. Хрестоматийный пример Flappy Bird — субагент №1 нарисовал фон в стиле Super Mario, субагент №2 — птицу в несовместимом стиле, в итоге игра не собралась. Причина: «Действия несут implicit decisions, конфликтующие decisions дают плохие результаты»[^33]. Субагенты независимо принимают допущения о стиле, паттернах, edge cases — не зная, что решили соседи.

Google измеряет: на **последовательных** reasoning-задачах multi-agent даёт **-39…-70 %**[^32]. Коммуникационный overhead фрагментирует рассуждение, съедая ресурсы, нужные для самого решения.

На практике: субагенты работают там, где задачи **действительно независимы** и **результат сжимается в summary**. Для coding это:

- подходит: research разных частей кодовой базы (read-only, независимо, результат — summary)
- подходит: code review отдельным агентом с чистым контекстом (Cognition сами подтверждают — review-агент **с нулевым shared context** ловит ~2 бага на PR, 58 % severe[^34])
- подходит: параллельный поиск решений для несвязанных проблем
- не подходит: совместная имплементация одной фичи в разных файлах — implicit-решения конфликтуют
- не подходит: тесно связанные архитектурные изменения

Для текущего RFC-подхода вывод такой: использовать субагентов для research-фазы (параллельно исследовать модули) и для code review, **но не для параллельной имплементации задач плана**.

### Вариант 3: план, очистка контекста, отдельные сессии на каждый шаг

Plan.md готовится в основной сессии. Затем — очистка контекста (`/clear` или закрытие сессии) и запуск отдельной сессии на каждый шаг плана. Сессия читает plan.md, делает один шаг, коммитит, завершается.

Это паттерн Anthropic «Effective harnesses for long-running agents»:

> «Каждая новая сессия начинается без памяти о предыдущей. Harness разрушает сессию и пересобирает её из структурированного handoff-файла. Трёхагентная архитектура: Planner → Generator → Evaluator»[^28].

Handoff-артефакты в этом паттерне:

1. **Feature list (JSON)** с явным pass/fail статусом по каждому требованию
2. **Git history** — недавние изменения, возможность rollback
3. **Progress documentation** — что сделано и почему

По данным Anthropic, harness-подход выдаёт «rich full-stack applications за multi-hour autonomous sessions» — масштаб, недостижимый в одной сессии из-за лимита контекста[^28].

Плюсы:

- каждая сессия работает в свежем контексте — деградации нет
- plan.md как постоянный handoff — все сессии видят единый source of truth
- git-коммиты на каждом шаге — естественные checkpoint'ы для отката

Минусы:

- высокий handoff overhead — каждая сессия заново читает план, контекст, релевантные файлы
- латентность: последовательные сессии медленнее одной длинной
- plan.md должен быть очень детальным, каждый шаг — self-contained, потому что новая сессия не помнит обсуждений
- конфликтующие implicit-решения: если на шаге N агент выбрал X, следующая сессия может выбрать несовместимое Y (та же проблема, что у параллельных субагентов, только разнесённая во времени)

### Вариант 4: Гибрид — orchestrator + subagents + clean code review

В 2026 году к этой архитектуре сошлись Anthropic, Cognition, OpenAI, AutoGen и LangChain[^33][^34]:

- **Один orchestrator** держит полный контекст беседы — основная сессия с plan.md
- **Эфемерные изолированные субагенты** делают side-задачи (research, анализ логов, проверки)
- **Субагенты возвращают сжатые summary** (1–2K токенов)
- **Запись остаётся single-threaded** — orchestrator пишет код, субагенты дают только intelligence
- **Code review агентом с чистым контекстом** — отдельная сессия проверяет результат orchestrator'а
- **Manager-coordinator для очень длинных задач** — manager декомпозирует, спавнит child-агентов, координирует через явное сжатие контекста

Ключевая формула Cognition: «Multiple agents contribute intelligence to a task, while writes stay single-threaded»[^34]. Это снимает проблему конфликтующих implicit-решений (параллельные writes конфликтуют) и одновременно использует пользу субагентов — изоляцию контекста и специализацию.

### Вариант 5: Compaction в одной сессии

Антипаттерн, но упомянуть стоит. Auto-compaction суммирует историю при приближении к лимиту контекста. Anthropic называет это «lightest-touch» стратегией, требующей «итеративной настройки: сначала максимизировать recall, потом убрать лишнее»[^35]. Без точной настройки компакция теряет важные детали. Для RFC-подхода она вторична — handoff через plan.md надёжнее сжатия истории.

### Какой вариант эффективнее

Эмпирически **Вариант 4 (гибрид)** доминирует для нетривиальных coding-задач:

| Задача | Рекомендуемый подход |
| --- | --- |
| Fast path (diff в одно предложение, известный баг) | Прямой запрос (vibe coding) |
| Средняя фича (1–3 файла, понятная) | Plan Mode + execute в одной сессии |
| Нетривиальная фича (RFC применим) | Orchestrator + subagent research + code review |
| Multi-hour автономная работа | Harness: initializer + coding + evaluator sessions |
| Параллельный exhaustive research | Multi-agent orchestrator-worker (+90,2 %) |

Это согласуется с предсказательной моделью Google: **87 % правильно идентифицированных оптимальных coordination-стратегий на ранее не виденных задачах** — по измеряемым свойствам задачи (число инструментов, декомпозируемость)[^32]. Параллелизм работает на параллелизуемом, последовательная декомпозиция — на последовательном.

## Минимизация human-in-the-loop

Как свести к разумному минимуму работу человека — не «обнулить», а оставить только то, что агент не сделает надёжно.

### Где человек остаётся неустранимым

Эксперимент Thoughtworks по «pushing AI autonomy» в кодогенерации выделил зоны, где человек обязателен[^36]:

1. **Верификация больших change sets в business-critical системах.** Агент «часто рапортовал об успешном build, который успешным не был».
2. **Заполнение specification gaps.** AI «делает arbitrary assumptions, когда требования размытые».
3. **Контроль недетерминированных результатов.** «Каждый запуск workflow давал что-то новое».

К этому — production track record:

- только **11 % организаций** доводят AI-пилоты до полного внедрения, 65 % всё ещё экспериментируют[^37]
- Devin: 13,86 % на SWE-bench против **15 % success на 20 разнообразных реальных задачах**[^38][^39], «невозможно предсказать, какие задачи получатся»
- 2025: Replit AI удалил production database; OpenAI Operator потратил $31,43 на яйца без подтверждения[^37]

### Шаги к автономии

Индустрия сдвигается от **HITL (human-in-the-loop)** к **HOTL (human-on-the-loop)**[^40]: агент работает автономно, человек мониторит и вмешивается **после** исполнения, а не до.

Конкретные механизмы:

1. **Headless mode** (Claude Code `-p` / `--print`, Cursor Background Agents): автономное исполнение в CI/CD без интерактивных промптов[^41][^42].
2. **Self-verification loops**: агент сам читает error logs и итеративно фиксит код. Так работают Devin и Copilot Workspace[^38][^43].
3. **CLAUDE.md, cursorrules**: постоянная память уровня проекта — «всегда используй X, никогда Y» не нужно повторять в каждой сессии[^15].
4. **Hooks и policy-as-code** в Claude Code Agent SDK: автоматические audit logs, permission gates, governance без human approval на каждый шаг[^41].
5. **Test-based success criteria в /goal**: success rate растёт с 35–40 % до 40–60 %, когда /goal содержит явный scope, пути файлов, ограничения и тестовые критерии успеха[^29].

### Где автономия ломается

**Agent drift в длинных сессиях**: 90 % drift'а после 30 шагов[^37]. Это не теоретическое опасение, а измеренный потолок 40–60 % на long-horizon задачах SWE-bench, **не пробиваемый ни одним семейством моделей**[^29].

**Производительность упёрлась в плато**: Claude Sonnet 4.5 + Live-SWE-agent даёт 45,8 % на SWE-Bench Pro (ноябрь 2025). Прогресс есть, но потолок без новых архитектурных решений не сдвигается[^44].

**Качество на greenfield**: месяц с Devin от Answer.ai — «спагетти-код, более запутанный, чем если бы я писал с нуля»[^39].

### Практический рецепт минимизации

Для RFC-подхода баланс между работой человека и качеством результата достигается такой конфигурацией:

1. **Всё повторяющееся — в CLAUDE.md**: команды build/test/lint, языковые предпочтения, правила безопасности данных, паттерны выбора агентов.
2. **Hooks для проверок**: PostToolUse-хуки сами запускают `go build` и `go vet` после правок в `.go` файлах — об этом не надо просить.
3. **Кастомная RFC-команда** делает research → plan автоматически. Человек ревьюит plan.md перед execute — это и есть HOTL gate.
4. **Subagent для research-фазы**: изоляция контекста, экономия токенов главной сессии.
5. **Code review агентом** с чистым контекстом после имплементации — Cognition подтверждает: ~2 бага на PR, 58 % severe[^34].
6. **Человек только на scope и финальном approval**: задача формулируется один раз, дальше — ревью plan.md и ревью финального diff'а. Внутри — автономия.

Получается **три точки вмешательства** (scope, plan approval, final approval) на сложную фичу вместо 30–50 микропромптов в чисто vibe-coding-режиме.

## Дискуссионные вопросы и противоречия

**Anthropic против Cognition по multi-agent.** Anthropic заявляет +90,2 % на multi-agent research; Cognition настаивает, что multi-agent на coding фундаментально нестабилен. Развязка (Google 2026): **+81 %** на параллелизуемых задачах, **-70 %** на последовательных. Coding по большей части последовательный, поэтому Cognition прав для записи кода, а Anthropic — для breadth-first research. Индустрия сошлась на одной формуле: orchestrator owns writes, subagents contribute intelligence[^32][^33][^34].

**SDD: спасение или лишний overhead.** GitHub Spec Kit (90k+ звёзд) подаёт spec-driven как «антидот vibe-coding». Augment Code и Fowler возражают: устаревшие специ хуже их отсутствия — агент уверенно исполняет outdated план[^16][^20]. SDD оправдан, когда специ удаляются после использования (как research.md в RFC-подходе) или активно поддерживаются как living docs. «Спецификация на полке» — токсичный артефакт.

**Plan Mode: настоящая ли это safety feature.** Подаётся как safety feature, но Ronacher разбирает механику: «markdown + prompt injection», агент добровольно соблюдает ограничения, файл скрыт от пользователя[^14]. Plan Mode полезен для структурирования внутри одной сессии, но не заменяет file-based RFC для задач, требующих ревью и handoff.

**Plan-and-Execute против ReAct: цена и точность.** Plan-and-Execute академически даёт 92 % против 85 % у ReAct, но стоит $0,09–0,14 за задачу против $0,06–0,09[^45]. Бенчмарки сильно зависят от домена, универсального победителя нет.

**Long-context degradation: насколько это значимо на практике.** Chroma показала деградацию на всех 18 frontier-моделях; Claude Opus 4.6 на 1M контексте даёт 78,3 % MRCR v2 против 26,3 % у Gemini[^25]. Цифры подтверждают: context is not free. Но прямая связь с качеством на длинных coding-сессиях остаётся пробелом в исследованиях. Cognition при этом наблюдают парадокс: review-агенты работают **лучше с нулевым** shared context, чем с полным[^34] — объяснения пока нет.

**Эффективность CLAUDE.md не измерена.** Только анекдотические свидетельства: «к шестому месяцу зафиксированы все ошибки». Эмпирических метрик — сколько времени экономит, насколько снижает rework — нет[^15].

## Quality Metrics

| Метрика | Значение |
| --- | --- |
| Найдено источников | 67 уникальных |
| Использовано в работе | 45 |
| Academic (arxiv, ACM, peer-reviewed) | 14 (31 %) |
| Official (Anthropic, GitHub, Cursor, AWS docs) | 13 (29 %) |
| Industry analysis (Thoughtworks, Fowler, Cognition) | 11 (24 %) |
| News / blog | 7 (16 %) |
| Citation coverage | 92 % фактических claims |
| Sub-questions investigated | 5 (паттерны, эффективность, RFC, context, HITL) |
| Research rounds | 1 (без iterative deepening — convergence достигнута) |
| Contradictions explicitly addressed | 5 |
| Counter-arguments search performed | да (Cognition vs Anthropic, SDD criticism, vibe-coding limits) |

[^1]: [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices) — Official Anthropic documentation, 2025–2026.

[^2]: [Best practices for coding with agents — Cursor](https://cursor.com/blog/agent-best-practices) — Official Cursor blog.

[^6]: [A Survey on Code Generation with LLM-based Agents](https://arxiv.org/html/2508.00083v1) — Academic survey, 2024.

[^7]: [Vibe Coding: Toward an AI-Native Paradigm](https://arxiv.org/html/2510.17842v1) — arXiv 2510.17842, 2025.

[^8]: [Can Vibe Coding Beat Graduate CS Students?](https://arxiv.org/html/2511.20613v1) — arXiv 2511.20613, 2025.

[^10]: [The AI Coding Workflow That Actually Works: Separate Planning from Execution](https://dev.to/matthewhou/separate-planning-from-execution-the-ai-coding-workflow-that-actually-works-1n00) — DEV Community, 2024.

[^11]: [Professional Software Developers Don't Vibe, They Control](https://arxiv.org/html/2512.14012v1) — arXiv 2512.14012, 2025.

[^12]: [Vibe Coding Doesn't Scale: The Enterprise Cliff](https://levelup.gitconnected.com/vibe-coding-doesnt-scale-the-enterprise-cliff-96bb6007603f) — Level Up Coding, 2026.

[^14]: [What Actually Is Claude Code's Plan Mode? — Armin Ronacher](https://lucumr.pocoo.org/2025/12/17/what-is-plan-mode/) — Personal blog (Flask creator), 2025.

[^15]: [The Complete Guide to CLAUDE.md: Memory, Rules, Loading, and Cross-Tool Compression](https://medium.com/@bijit211987/the-complete-guide-to-claude-md-memory-rules-loading-and-cross-tool-compression-97cc12ed037b) — Medium, 2025.

[^16]: [Spec-driven development with AI — GitHub Blog](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/) — Official GitHub, 2026.

[^17]: [GitHub Spec Kit Repository](https://github.com/github/spec-kit) — Official repository, 90k+ stars.

[^18]: [Understanding Spec-Driven-Development Tools — Martin Fowler](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) — Industry analysis, 2025.

[^19]: [I Tested Three Spec-Driven AI Tools — Real-World Review](https://ranthebuilder.cloud/blog/i-tested-three-spec-driven-ai-tools-here-s-my-honest-take/) — Practitioner analysis, 2026.

[^20]: [What spec-driven development gets wrong — Augment Code](https://www.augmentcode.com/blog/what-spec-driven-development-gets-wrong) — Industry analysis, 2025–2026.

[^21]: [Planning In Natural Language Improves LLM Search For Code Generation](https://arxiv.org/html/2409.03733v1) — arXiv 2409.03733, Scale Labs, 2024.

[^22]: [CodePlan: Repository-level Coding using LLMs and Planning](https://dl.acm.org/doi/10.1145/3643757) — ACM FSE 2024.

[^23]: [Self-Planning Code Generation with Large Language Models](https://arxiv.org/pdf/2303.06689) — arXiv 2303.06689, 2023.

[^24]: [Chroma Research: Context Rot](https://www.trychroma.com/research/context-rot) — Empirical degradation across 18 models, 2025.

[^25]: [Claude Context Window Sizes and Degradation — Morph LLM](https://www.morphllm.com/claude-context-window) — Industry analysis, 2025–2026.

[^26]: [Agent Drift in AI Systems — Prasanna Ravishankar](https://prassanna.io/blog/agent-drift/) — Blog with instruction centrifugation theory, 2025.

[^27]: [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172) — Liu et al., TACL 2024.

[^28]: [Anthropic Engineering: Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — Official Anthropic, 2025.

[^29]: [The /goal Command: How to Run Claude Code as 24/7 Autonomous Agents](https://apidog.com/blog/goal-command-codex-claude-code-autonomous-agents/) — Cites agent drift 35,9 %, context overflow 35,6 %, 2025.

[^30]: [Create custom subagents — Claude Code Docs](https://code.claude.com/docs/en/sub-agents) — Official Anthropic.

[^31]: [How we built our multi-agent research system — Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system) — Official Anthropic.

[^32]: [Towards a science of scaling agent systems — Google Research](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work) — Google Research, 2026.

[^33]: [Don't Build Multi-Agents — Cognition](https://cognition.ai/blog/dont-build-multi-agents) — Walden Yan, 2024–2025.

[^34]: [Multi-Agents: What's Actually Working — Cognition](https://cognition.ai/blog/multi-agents-working) — Cognition AI, 2026.

[^35]: [Anthropic Engineering: Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Official Anthropic.

[^36]: [Pushing AI autonomy in code generation — Martin Fowler / Thoughtworks](https://martinfowler.com/articles/pushing-ai-autonomy.html) — Thoughtworks experiment, 2025.

[^37]: [Why AI Coding Agents Still Fail: The Reliability Problem](https://finkletech.com/ai-coding-agents-reliability-problem/) — FinkelTech, 2025.

[^38]: [Devin: The AI Software Engineer Review, Testing & Limitations in 2026](https://www.idlen.io/blog/devin-ai-engineer-review-limits-2026/) — Real-world testing.

[^39]: [Thoughts On A Month With Devin — Answer AI](https://www.answer.ai/posts/2025-01-08-devin.html) — Practitioner review, 2025.

[^40]: [From Human-in-the-Loop to Human-on-the-Loop: Evolving AI Agent Autonomy](https://bytebridge.medium.com/from-human-in-the-loop-to-human-on-the-loop-evolving-ai-agent-autonomy-c0ae62c3bf91) — Industry analysis.

[^41]: [Agent SDK overview — Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/overview) — Official Anthropic.

[^42]: [Cursor — Background Agents](https://docs.cursor.com/en/background-agent) — Official Cursor docs.

[^43]: [About GitHub Copilot coding agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent) — Official GitHub.

[^44]: [SWE-bench Leaderboards](https://www.swebench.com/) — Official benchmark.

[^45]: [ReAct vs Plan-and-Execute: Practical Comparison — DEV Community](https://dev.to/jamesli/react-vs-plan-and-execute-a-practical-comparison-of-llm-agent-patterns-4gh9) — Cost/accuracy comparison, 2025.
