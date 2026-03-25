---
title: "AI Code Review: проблема воспроизводимости результатов и индустриальные практики"
date: 2026-03-25
---

## Metadata

- **Date**: 2026-03-25
- **Research query**: Проблема нестабильности результатов AI code review при повторных запусках; индустриальные практики проверки кода с помощью ИИ; решение проблемы code style
- **Sources**: 43
- **Citation coverage**: 92%
- **Mode**: deep

## Аннотация

Настоящий обзор исследует фундаментальную проблему недетерминированности результатов AI-powered code review — ситуации, когда повторные запуски ревью на одном и том же коде дают различные замечания с различными уровнями серьёзности. Анализ охватывает академические публикации, индустриальные отчёты, документацию коммерческих инструментов и практический опыт крупных компаний (Microsoft, ByteDance, Google, Ericsson). Основные выводы: недетерминированность является фундаментальным свойством LLM, а не багом конкретной реализации; индустрия решает эту проблему через многоуровневую архитектуру (статический анализ + AST + LLM + фильтрация); наиболее эффективные подходы включают мульти-модельный консенсус, confidence-based фильтрацию и таксономию правил с обратной связью. Code style enforcement эффективнее всего решается детерминистическими инструментами (линтеры, форматтеры), а AI используется для семантических проверок более высокого уровня.

## Введение

Внедрение LLM в процесс code review стало одним из ключевых трендов разработки ПО в 2024–2026 годах. По данным Microsoft, их AI-powered code review assistant обрабатывает более 600 000 pull request в месяц, охватывая свыше 90% PR компании[^1]. Anthropic отмечает, что

> "code review has become a bottleneck"[^2]

— в условиях, когда AI генерирует код в 10 раз быстрее, пропускная способность человеческого ревью становится ограничивающим фактором[^3].

Однако при практическом использовании AI code review обнаруживается фундаментальная проблема: результаты ревью нестабильны. При повторных запусках на одном и том же коде без изменений инструмент выдаёт различные замечания с различными уровнями серьёзности. Это подрывает доверие к результатам и затрудняет интеграцию в CI/CD-пайплайны, где ожидается детерминированное поведение.

Цель обзора — исследовать причины недетерминированности AI code review, систематизировать существующие подходы к решению проблемы и определить оптимальную архитектуру, сочетающую стабильность результатов с глубиной анализа. Обзор охватывает академические исследования, коммерческие инструменты и практический опыт индустрии, но не включает разработку собственных моделей или бенчмаркинг конкретных LLM.

Документ организован следующим образом: сначала рассматриваются технические причины недетерминированности LLM, затем анализируются архитектурные подходы к повышению стабильности, далее — индустриальные практики и инструменты, и наконец — стратегии enforcing code style.

## Природа недетерминированности LLM в контексте code review

### Почему temperature=0 не гарантирует детерминизм

Интуитивное ожидание разработчиков состоит в том, что установка температуры в ноль должна обеспечить полную воспроизводимость результатов. Исследования показывают, что это не так. Как отмечает Schmalbach,

> "Temperature=0 is not a mathematical guarantee of determinism. It is merely a request to the engine to be 'less random'"[^4]

При temperature=0 модель выполняет greedy decoding — выбирает токен с наивысшей вероятностью на каждом шаге. Однако даже при детерминированном sampling итоговый результат может различаться по нескольким причинам. Во-первых, ограничения точности floating-point арифметики: LLM выполняют множество операций с вероятностями в формате чисел с плавающей запятой, и порядок вычислений может варьироваться между запусками, приводя к различным результатам при одинаковых входных данных[^4]. Во-вторых, архитектура Mixture-of-Experts (MoE), которую используют крупные модели вроде GPT-4, добавляет дополнительный уровень недетерминизма — различные запуски могут активировать различные эксперты[^4]. В-третьих, batch-эффекты: модель может быть недетерминирована на уровне отдельной последовательности, оставаясь детерминированной только на уровне batch, поскольку другие входные данные в том же batch влияют на предсказания[^4].

Brenndoerfer дополняет этот анализ, указывая на инфраструктурные факторы:

> "Even if you submit the exact same input multiple times, you may receive different outputs depending on what other inputs are processed in the same batch"[^5]

Для code review это означает принципиальную невозможность получить идентичные результаты при повторных запусках на уровне LLM-вывода, независимо от параметров API.

### Масштаб проблемы в практических задачах

Академическое исследование Ouyang et al. (2024) целенаправленно изучало недетерминизм LLM-настроек, которые позиционируются как «детерминистические»[^6]. Параллельно, исследование консистентности LLM на задачах классификации, анализа тональности, суммаризации, генерации текста и предсказаний с использованием 50 независимых прогонов показало, что простые задачи (бинарная классификация) достигают почти идеальной воспроизводимости, тогда как сложные задачи демонстрируют значительную вариативность[^7]. Code review, будучи сложной задачей, требующей понимания контекста, архитектуры и намерения разработчика, попадает именно в категорию высоковариативных задач.

Наиболее релевантное исследование — работа по измерению детерминизма LLM именно в контексте code review, проведённая на 70 Java-коммитах[^36]. Результаты показали, что даже при temperature=0 обратная связь LLM существенно варьировалась между запусками, с отклонениями accuracy до 15% и разрывом до 70% между лучшим и худшим результатами. Исследование также выявило градиент консистентности между моделями: GPT-4o mini демонстрирует наибольшую вариативность, за ним следуют GPT-4o, Claude 3.5 Sonnet, и наиболее детерминистичной оказалась LLaMA 3.2 90B[^36]. Важный вывод авторов:

> "LLMs' reliability may be comparable to that of human reviewers"[^36]

— что указывает на принципиальную применимость LLM для code review при использовании техник снижения вариативности.

Практическое подтверждение этого даёт отчёт Augment Code, где бенчмарк 7 AI code review инструментов на реальных open-source PR показал существенный разброс в precision и recall между запусками[^8]. Claude Code достигает примерно 51% recall, но при этом значительно ниже precision, что приводит к высокому объёму некорректных или малоценных комментариев[^8].

Таким образом, проблема нестабильности — не баг конкретной реализации, а фундаментальное свойство LLM. Вопрос не в том, как устранить вариативность, а в том, как построить систему, которая работает надёжно несмотря на неё.

## Архитектурные подходы к повышению стабильности

### Мульти-модельный консенсус

Один из наиболее эффективных подходов к снижению вариативности — параллельный запуск нескольких моделей с последующим голосованием. Mozilla AI описывает этот подход как «Star Chamber» — систему, в которой несколько LLM независимо анализируют код, и замечание публикуется только при достижении консенсуса[^9].

CodeAnt AI реализует этот принцип на практике:

> "multi-model consensus validation, running three LLMs in parallel and only surfacing issues when 2+ models agree. This cuts false positives by ~60% compared to single-model approaches while maintaining 92% recall"[^10]

Математически мульти-модельный подход работает по аналогии с ансамблевыми методами в машинном обучении: при независимых ошибках моделей вероятность одновременной ложноположительной ошибки у большинства участников экспоненциально снижается. Для code review это означает, что стилистические «нитпики» и малозначимые замечания, которые нестабильно появляются при одиночном прогоне, фильтруются консенсусом — они, как правило, не воспроизводятся всеми моделями одновременно.

Подход имеет очевидный недостаток — кратное увеличение стоимости и задержки. K-LLM оркестрация, описанная Casanova, предлагает оптимизацию: использовать быструю модель для первичного скрининга и задействовать полный консенсус только для спорных случаев[^11].

### Двухстадийная архитектура: RuleChecker + ReviewFilter

ByteDance в системе BitsAI-CR реализует альтернативный подход — вместо мультимодельного консенсуса используется каскад из двух специализированных моделей[^12]. RuleChecker — fine-tuned LLM, обученная на таксономии из 219 правил ревью — выполняет первичное обнаружение проблем. ReviewFilter — вторая fine-tuned LLM — верифицирует найденные проблемы, отсеивая false positive.

> "BitsAI-CR achieves 75.0% precision in review comment generation"[^12]

Ключевое отличие от мультимодельного консенсуса — использование fine-tuned моделей со специализированной таксономией вместо универсальных LLM. Таксономия правил обеспечивает якорь стабильности: модель проверяет код на соответствие конкретным, заранее определённым правилам, а не генерирует замечания «из воздуха». Это существенно снижает вариативность при повторных запусках, поскольку пространство возможных выводов ограничено.

Система обслуживает более 12 000 активных пользователей в неделю и включает механизм data flywheel — обратной связи через аннотации ревьюеров, которая непрерывно улучшает таксономию правил[^12].

### AST-based context engineering

Третий подход к повышению стабильности — обогащение контекста LLM детерминированной структурной информацией о коде. Вместо подачи «сырых» diff-ов модели, код сначала разбирается в Abstract Syntax Tree, из которого извлекается типизированный контекст[^13].

Kodus, open-source AI code review engine, реализует этот принцип:

> "a deterministic, AST-based rule engine to provide precise, structured context directly to the LLM. The result is a dramatically reduced noise rate, fewer hallucinations, and comments you can actually trust"[^14]

Baz развивает подход далее, комбинируя AST-traversal с семантическим пониманием LLM:

> "The key innovation is combining AST-based code traversal with LLM semantic understanding and extensive context gathering to create reviews that match or exceed what a senior staff engineer would provide"[^15]

CodeRabbit использует Tree-Sitter для парсинга кода и подачи структурированного, иерархического представления кодовой базы в LLM, что значительно превосходит простой line-by-line diff[^16]. Дополнительно CodeRabbit интегрирует более 35 линтеров и статических анализаторов в свой pipeline ревью[^16].

Принцип работы AST-подхода: чем больше детерминированной информации (типы, сигнатуры функций, зависимости, структура проекта) подаётся в промпт LLM, тем меньше пространство для «творчества» модели и тем стабильнее результаты. Это согласуется с общим принципом context engineering — качество и предсказуемость вывода LLM напрямую зависят от качества контекста.

### Confidence-based фильтрация

Четвёртый подход — фильтрация результатов LLM по уровню уверенности. Идея проста: если модель неуверена в замечании (низкая вероятность выходных токенов, высокая энтропия), это замечание с большей вероятностью является нестабильным и должно быть отфильтровано[^17].

Практические рекомендации включают установку порогов:

> "Always set thresholds for acceptable confidence scores. For example, only accept results with confidence scores above 80%. Anything lower should be flagged for review"[^18]

Однако Epiq предупреждает о рисках наивного применения:

> "Confidence scoring with LLMs is dangerous"[^19]

— LLM могут демонстрировать высокую «уверенность» (по self-reported оценкам) в совершенно неверных ответах. Более надёжный подход — использовать token-level probabilities (logprobs) из API модели, а не вербализированные оценки уверенности. Для code review это позволяет автоматически разделять результаты на высокоуверенные (публикуются автоматически) и низкоуверенные (требуют человеческой проверки).

Переходя от архитектуры отдельных систем к индустриальным практикам, рассмотрим, как крупные компании и open-source проекты реализуют AI code review на практике.

## Индустриальные практики AI code review

### Microsoft: от эксперимента к масштабу

Microsoft представляет наиболее зрелый пример внедрения AI code review. Система, начавшаяся как внутренний эксперимент, масштабировалась до поддержки более 90% pull request компании:

> "The learning and experiences developed internally were incorporated into GitHub's AI-powered code review offering and now benefit external customers"[^1]

Академический фундамент системы — модель CodeReviewer, предложенная Li et al., обученная на крупномасштабном датасете реальных code changes и reviews из open-source проектов на 9 наиболее популярных языках программирования[^20]. Модель использует архитектуру из 12 слоёв Transformer encoder и 12 слоёв decoder с 12 attention heads[^20]. Важно, что Microsoft использует pre-trained модели, fine-tuned на внутренних данных, а не универсальные LLM — это обеспечивает более стабильные результаты.

### ByteDance: таксономия и data flywheel

Система BitsAI-CR от ByteDance[^12] демонстрирует альтернативный подход к масштабированию. Вместо единой модели используется каскад RuleChecker → ReviewFilter, привязанный к формализованной таксономии из 219 правил. Механизм data flywheel обеспечивает непрерывное улучшение: каждый комментарий ревью аннотируется разработчиками (принят/отклонён), и эти аннотации используются для уточнения правил и переобучения моделей.

Ericsson также опубликовал experience report по внедрению LLM-based code review[^21], подтверждая тренд на промышленное использование AI в процессе ревью в крупных технологических компаниях.

### Salesforce: количественные результаты

Salesforce предоставляет конкретные метрики эффекта AI на разработку:

> "AI-enabled tooling boosted code output 30% while keeping quality and deployment safety intact"[^22]

Однако этот прирост сопровождается парадоксом продуктивности. Исследования показывают, что команды с высоким уровнем AI-adoption завершают на 21% больше задач и мержат на 98% больше pull request, но время ревью PR увеличивается на 91%[^3]. Senior-инженеры тратят в среднем 4.3 минуты на проверку AI-generated кода против 1.2 минуты для написанного человеком[^3].

### Эффективность AI review: addressing rate

Масштабное эмпирическое исследование 22 000+ комментариев code review в 178 репозиториях выявило драматический разрыв между AI и человеческими ревьюерами[^37]. Комментарии человеческих ревьюеров адресуются разработчиками в 60% случаев, тогда как лучший AI-инструмент (CodeRabbit) достигает лишь 19.2%, а типичные AI-инструменты — 4–8%[^37]. Факторы, повышающие эффективность AI-комментариев: привязка к конкретным строкам кода (hunk-level targeting), наличие code snippets с предложенными исправлениями и краткость формулировок[^37].

GitHub Copilot code review демонстрирует масштаб индустриального применения: 60 миллионов ревью с момента запуска, рост использования в 10 раз, ~20% всех code review на платформе[^38]. При этом Copilot не может самостоятельно approve PR — он позиционируется исключительно как aide[^38].

### Пропускать ли code review?

Альтернативный вопрос — нужно ли code review вообще? Может ли «ship fast, fix later» быть жизнеспособной стратегией? Индустриальные данные однозначны:

> "Teams that skip code reviews ship bugs 40% more often"[^23]

Стоимость исправления бага в продакшене в 10 раз выше, чем на этапе разработки[^24]. Для мобильных приложений этот множитель может быть ещё выше из-за процесса app store review[^24]. Анализ 470 pull request показал, что AI-generated код содержит в 1.7 раза больше дефектов, чем написанный человеком, а тестирование Veracode на 100+ LLM показало, что 45% образцов AI-generated кода содержат уязвимости из OWASP Top 10[^25].

Консенсус индустрии — code review не только не стоит пропускать, но в эпоху AI-generated кода его значимость возрастает. Вопрос в том, как масштабировать пропускную способность ревью.

### Гибридная модель: AI как первый pass

Наиболее распространённая практика — использование AI как первого прохода перед человеческим ревью:

> "AI code review cuts average PR review from 2-3 hours to 20-30 minutes, and automated review eliminates 80% of trivial PR issues before reaching a human reviewer"[^26]

Anthropic позиционирует свои инструменты как помощников, а не замену:

> "AI won't approve PRs but closes the gap so reviewers can actually cover what's shipping"[^2]

Эта модель — AI выполняет рутинные проверки, человек фокусируется на архитектуре, логике и бизнес-требованиях — является доминирующей в индустрии на 2025–2026 годы.

## Ландшафт инструментов AI code review

### Коммерческие решения

Рынок AI code review инструментов быстро растёт. Среди ключевых игроков:

**CodeRabbit** — один из наиболее зрелых инструментов. Клонирует репозиторий в sandbox для полного анализа кодовой базы, интегрирует 35+ линтеров и статических анализаторов, использует context engineering с Learnings engine для запоминания team-specific паттернов[^16]. Поддерживает GitHub, GitLab, Azure DevOps и Bitbucket.

**Qodo Merge** (ранее PR-Agent) — open-source ядро с коммерческой версией. Фокусируется на генерации описаний PR, обнаружении багов и предложении улучшений[^27].

**Augment Code** — позиционирует себя через высокую precision: в собственном бенчмарке на реальных PR демонстрирует лучшее соотношение signal-to-noise среди протестированных инструментов[^8].

**Greptile** — строит полный граф кодовой базы с индексацией каждой функции, класса и зависимости. Демонстрирует 82% bug detection rate в бенчмарках — 41% выше Cursor. Использует самообучение через upvotes/downvotes для подавления нерелевантных комментариев за 2–3 недели[^42].

**Codacy** — гибридный подход: детерминистический rule-based анализ (30+ инструментов, 40+ языков) с контекстно-зависимым AI reasoning поверх. Rule-based фундамент обеспечивает воспроизводимый baseline, AI добавляет семантический анализ[^43].

**CodeAnt AI** — использует мульти-модельный консенсус (3 LLM параллельно) для снижения false positive на ~60%[^10].

**Cubic** — применяет structural analysis и type information перед генерацией комментариев[^28].

**Kodus** — open-source engine, использующий AST-based rule engine для предоставления детерминированного контекста LLM[^14].

### Проблема false positive

Центральная проблема всех AI code review инструментов — false positive. Индустриальный стандарт false-positive rate составляет 5–15%[^29], но на практике ситуация часто хуже:

> "Studies show up to 40% of AI code review alerts get ignored"[^29]

При 90% precision (10% false positive) на команде, ревьюирующей 50 PR в неделю с 5 комментариями на PR, получается 25 ложных срабатываний в неделю — более 20 часов потерянного времени в месяц[^29]. Когда 90% AI-комментариев являются false positive или стилистическими нитпиками, действительно важные замечания (безопасность, архитектурные риски) теряются в шуме[^29].

Именно проблема false positive и объясняет нестабильность, наблюдаемую при повторных запусках: замечания с низкой уверенностью «мерцают» — появляются и исчезают между прогонами, создавая впечатление хаотичности результатов.

### Академические результаты

Исследование «Automated Code Review In Practice» (2024) показало, что 73.8% автоматических комментариев были помечены как resolved, что свидетельствует о практической полезности[^30]. Однако инструмент также привёл к увеличению времени закрытия pull request и порождал faulty reviews, unnecessary corrections и irrelevant comments[^30].

Gupta et al. (2018) из Microsoft представили один из первых подходов к intelligent code review с использованием deep learning, обучив модель на исторических peer reviews из внутренних репозиториев[^31]. Li et al. (2023) развили тему, используя Graph Neural Networks для анализа структуры кода через Abstract Syntax Trees и Control Flow Graphs, что обеспечивает понимание не только синтаксиса, но и семантических взаимодействий[^32].

Бенчмарк SWR-Bench (2025) на 1000 верифицированных pull request с полным контекстом проекта показал, что LLM-based системы «underperform» на задачах общего code review, хотя хорошо справляются с обнаружением функциональных ошибок[^39]. Критически важный результат:

> "Multi-review aggregation strategy increased F1 scores by up to 43.67%"[^39]

— что подтверждает эффективность ансамблевых подходов для повышения стабильности. Исследование также представило объективную LLM-based оценку с ~90% согласия с человеческим суждением[^39].

Google в системе DIDACT демонстрирует масштаб ML-based code review: система обрабатывает миллионы комментариев ревьюеров ежегодно и автоматически резолвит 7.5% всех комментариев через ML-suggested edits, экономя сотни тысяч инженерных часов[^40]. Ключевой фактор успеха — бесшовная интеграция в существующий workflow без нового UI.

Исследование на базе WirelessCar Sweden AB показало, что разработчики в целом предпочитают AI-led reviews, но эффективность критически зависит от контекстной информации — RAG-based подход с семантическим поиском значительно улучшает качество[^41].

## Code style enforcement: детерминистический уровень

### Линтеры и форматтеры как фундамент

Проблема соблюдения code style имеет принципиально иное решение, чем семантическое code review. Ключевое различие:

> "AI can choose to ignore documentation, but cannot ignore linting errors in CI pipelines"[^33]

Линтеры (ESLint, golangci-lint, Pylint) и форматтеры (Prettier, gofmt, Black) обеспечивают 100% детерминированные результаты — одинаковый код всегда даёт одинаковый набор ошибок и предупреждений. Это делает их незаменимыми для базового enforcement code style.

Graphite отмечает:

> "Prettier and ESLint set the gold standard for reliable, rule-based enforcement and are essential for baseline quality; AI should augment—not replace—them"[^34]

При этом AI-инструменты достигают 51–83% accuracy на style-related fixes при корректной настройке[^34], что значительно ниже 100% accuracy детерминистических инструментов.

### Оптимальная стратегия: пирамида автоматизации

Индустриальная best practice формирует пирамиду автоматизации code quality:

1. **Базовый уровень — форматтеры** (gofmt, Prettier, Black): автоматическое форматирование, нулевая конфигурация стиля, 100% детерминизм
2. **Второй уровень — линтеры** (golangci-lint, ESLint, Pylint): статические правила, настраиваемые под проект, детерминированные результаты
3. **Третий уровень — статический анализ** (Semgrep, CodeQL, SonarQube): обнаружение паттернов уязвимостей и ошибок
4. **Верхний уровень — AI review**: семантический анализ, архитектурные замечания, контекстно-зависимые рекомендации

Как отмечается в отчёте DevToolsAcademy:

> "Industry best practice is running AI review, then classic linters, then human review for maximal code quality"[^35]

Критически важный инсайт:

> "Teams that enforce strict linting and code style rules are getting better results from AI agents. This is because consistent, predictable code patterns create a perfect environment for AI to contribute safely and effectively"[^33]

Строгий enforcement code style через линтеры не только решает проблему стабильности стиля, но и повышает качество AI code review — модели лучше анализируют консистентный код.

### AI для стилистических замечаний уровня выше линтера

AI занимает нишу стилистических проверок, которые невозможно формализовать в правилах линтера: выбор имён переменных, структура функций, соответствие архитектурным паттернам проекта. CodeRabbit реализует это через Learnings engine — систему запоминания team-specific паттернов и их применения в будущих ревью[^16]. Addy Osmani описывает аналогичный подход в своём LLM coding workflow:

> "AI operates as a layer between traditional linters and human reviewers, reading rules and understanding the semantic intent behind them"[^33]

## Дискуссионные вопросы и противоречия

### Детерминизм vs глубина анализа

Существует фундаментальное противоречие: чем детерминированнее результаты AI review, тем более они ограничены по глубине. Статические анализаторы дают 100% воспроизводимые результаты, но не способны к семантическому пониманию. LLM обеспечивают глубокий анализ, но с неизбежной вариативностью. Решение — не выбор одного из подходов, а их комбинирование в многоуровневой архитектуре.

### Precision vs recall

Augment Code и Claude Code демонстрируют разные точки на кривой precision-recall[^8]. Claude Code достигает ~51% recall при низкой precision, генерируя много шума. Augment Code приоритизирует precision за счёт recall. Для разработчиков высокий false positive rate разрушительнее, чем пропущенные замечания — шум приводит к «alarm fatigue» и игнорированию всех комментариев инструмента.

### AI code review как замена vs дополнение человека

Microsoft и Anthropic однозначно позиционируют AI как дополнение[^1][^2]. Однако ряд стартапов продвигают полностью автоматическое ревью. Академические данные поддерживают гибридный подход: 73.8% resolved комментариев означают, что ~26% были бесполезны или вредны[^30].

### Стоимость повышения стабильности

Мульти-модельный консенсус снижает false positive на 60%[^10], но утраивает стоимость API-вызовов. Двухстадийная фильтрация BitsAI-CR требует fine-tuning двух моделей[^12]. AST-based context engineering требует инфраструктуры парсинга[^14]. Для малых команд эти подходы могут быть избыточны — в таких случаях достаточно детерминистических инструментов с минимальным AI-дополнением.

## Заключение

### Синтез

Недетерминированность AI code review — фундаментальное свойство LLM, обусловленное архитектурой floating-point вычислений, Mixture-of-Experts, batch-эффектами и стохастической природой генерации. Temperature=0 не решает проблему. Индустрия не пытается устранить вариативность, а строит системы, устойчивые к ней.

### Ключевые выводы

1. **Многоуровневая архитектура** — наиболее эффективный подход: детерминистические инструменты (линтеры, форматтеры, SAST) для базовых проверок, AI для семантического анализа высокого уровня
2. **Мульти-модельный консенсус** снижает false positive на ~60% и стабилизирует результаты, но увеличивает стоимость
3. **Таксономия правил** (подход BitsAI-CR) ограничивает пространство выводов LLM, повышая стабильность без мульти-модельных затрат
4. **AST-based context engineering** обеспечивает детерминированный контекст, снижая вариативность выводов LLM
5. **Confidence-based фильтрация** отсекает нестабильные замечания, публикуя только высокоуверенные результаты
6. **Code style** эффективнее всего решается линтерами и форматтерами; AI используется только для стилистических проверок, не поддающихся формализации

### Практические рекомендации

Для решения описанной в исходном вопросе проблемы рекомендуется:

1. **Разделить проверки по уровням**: code style — детерминистическим инструментам (golangci-lint, ESLint), семантика — AI
2. **Внедрить фильтрацию результатов AI**: мульти-модельный консенсус или confidence-based порог
3. **Ограничить таксономию**: вместо open-ended промпта «найди проблемы» использовать чеклист конкретных категорий (безопасность, конкурентность, обработка ошибок)
4. **Настроить severity фильтр**: публиковать автоматически только high-confidence + high-severity замечания
5. **Использовать AI как первый pass**, а не финальный вердикт: AI находит кандидатов на проблемы, человек решает

### Направления дальнейших исследований

- Методики оценки стабильности AI code review инструментов (benchmark на воспроизводимость)
- Fine-tuning моделей на специфических кодовых базах для повышения precision
- Оптимальные стратегии prompt engineering для code review с учётом стабильности
- Интеграция формальной верификации с AI-анализом

## Источники

[^1]: Microsoft Engineering. "Enhancing Code Quality at Scale with AI-Powered Code Reviews." Engineering@Microsoft, 2025. <https://devblogs.microsoft.com/engineering-at-microsoft/enhancing-code-quality-at-scale-with-ai-powered-code-reviews/>
[^2]: IT Pro. "Anthropic says 'code review has become a bottleneck' – this new Claude Code feature aims to solve that." IT Pro, 2025. <https://www.itpro.com/software/development/anthropic-says-code-review-has-become-a-bottleneck-this-new-claude-code-feature-aims-to-solve-that>
[^3]: Level Up Coding. "The AI Code Review Bottleneck Is Already Here. Most Teams Haven't Noticed." Medium, 2026. <https://levelup.gitconnected.com/the-ai-code-review-bottleneck-is-already-here-most-teams-havent-noticed-1b75e96e6781>
[^4]: Schmalbach, V. "Does Temperature 0 Guarantee Deterministic LLM Outputs?" 2025. <https://www.vincentschmalbach.com/does-temperature-0-guarantee-deterministic-llm-outputs/>
[^5]: Brenndoerfer, M. "Why Temperature=0 Doesn't Guarantee Determinism in LLMs." 2025. <https://mbrenndoerfer.com/writing/why-llms-are-not-deterministic>
[^6]: Ouyang et al. "Non-Determinism of 'Deterministic' LLM Settings." arXiv:2408.04667, 2024. <https://arxiv.org/abs/2408.04667>
[^7]: Assessing Consistency and Reproducibility in the Outputs of Large Language Models. arXiv:2503.16974, 2025. <https://arxiv.org/abs/2503.16974>
[^8]: Augment Code. "We benchmarked 7 AI code review tools on large open-source projects. Here are the results." 2025. <https://www.augmentcode.com/blog/we-benchmarked-7-ai-code-review-tools-on-real-world-prs-here-are-the-results>
[^9]: Mozilla AI. "The Star Chamber: Multi-LLM Consensus for Code Quality." 2025. <https://blog.mozilla.ai/the-star-chamber-multi-llm-consensus-for-code-quality/>
[^10]: CodeAnt AI. "How Many False Positives Are Too Many in AI Code Review." 2025. <https://www.codeant.ai/blogs/ai-code-review-false-positives>
[^11]: Casanova, J. "AI Code Review for OpenCode with K-LLM Orchestration." 2025. <https://www.josecasanova.com/blog/ai-code-review-opencode>
[^12]: Li et al. "BitsAI-CR: Automated Code Review via LLM in Practice." FSE 2025 Industry Papers. arXiv:2501.15134. <https://arxiv.org/abs/2501.15134>
[^13]: VXRL. "Enhancing LLM Code Generation with RAG and AST-Based Chunking." Medium, 2025. <https://vxrl.medium.com/enhancing-llm-code-generation-with-rag-and-ast-based-chunking-5b81902ae9fc>
[^14]: Kodus. "An open source AI code review engine (AST and LLW, less noise)." DEV Community, 2025. <https://dev.to/kodus/kodus-an-open-source-ai-code-review-engine-ast-and-llw-less-noise-3726>
[^15]: Baz. "Building an AI Code Review Agent: Advanced Diffing, Parsing, and Agentic Workflows." 2025. <https://baz.co/resources/building-an-ai-code-review-agent-advanced-diffing-parsing-and-agentic-workflows>
[^16]: CodeRabbit. "How CodeRabbit delivers accurate AI code reviews on massive codebases." 2025. <https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases>
[^17]: Baak, M. "A confidence score for LLM answers." Medium, 2025. <https://medium.com/wbaa/a-confidence-score-for-llm-answers-c668844d52c8>
[^18]: Infrrd. "Confidence Scores in LLMs: Ensure 100% Accuracy in Large Language Models." 2025. <https://www.infrrd.ai/blog/confidence-scores-in-llms>
[^19]: Epiq. "Why Confidence Scoring With LLMs Is Dangerous." 2025. <https://www.epiqglobal.com/en-us/resource-center/articles/why-confidence-scoring-with-llms-is-dangerous>
[^20]: Li, Z. et al. "Automating Code Review Activities by Large-Scale Pre-training." arXiv:2203.09095, 2022. <https://arxiv.org/abs/2203.09095>
[^21]: "Automated Code Review Using Large Language Models at Ericsson: An Experience Report." arXiv, 2025. <https://arxiv.org/html/2507.19115v2>
[^22]: Salesforce Engineering. "How AI-Enabled Tooling Boosted Code Output 30%." 2025. <https://engineering.salesforce.com/how-ai-enabled-tooling-boosted-code-output-30-while-keeping-quality-and-deployment-safety-intact/>
[^23]: LinkedIn. "Why skipping code reviews can be lethal for your organization!" 2024. <https://www.linkedin.com/pulse/why-skipping-code-reviews-can-lethal-your-gopalakrishnan-iyer>
[^24]: testRigor. "Quality vs Speed: The True Cost of 'Ship Now, Fix Later'." 2025. <https://testrigor.com/blog/quality-vs-speed-the-true-cost-of-ship-now-fix-later/>
[^25]: CodeRabbit. "AI vs human code gen report: AI code creates 1.7x more issues." 2025. <https://www.coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report>
[^26]: Graphite. "How AI code review reduces review cycles to improve developer productivity." 2025. <https://graphite.com/blog/how-ai-code-review-reduces-review-cycles>
[^27]: Qodo. "AI Code Review." 2025. <https://www.qodo.ai/>
[^28]: Cubic. "The false positive problem: Why most AI code reviewers fail and how cubic solved it." 2025. <https://www.cubic.dev/blog/the-false-positive-problem-why-most-ai-code-reviewers-fail-and-how-cubic-solved-it>
[^29]: PropelCode. "Reducing AI Code Review False Positives: Practical Techniques." 2025. <https://www.propelcode.ai/blog/ai-code-review-false-positives-reducing-noise>
[^30]: "Automated Code Review In Practice." arXiv:2412.18531, 2024. <https://arxiv.org/abs/2412.18531>
[^31]: Gupta, A. "Intelligent code reviews using deep learning." KDD 2018. <https://www.kdd.org/kdd2018/files/deep-learning-day/DLDay18_paper_40.pdf>
[^32]: "Automatic Code Review by Learning the Structure Information of Code Graph." Sensors, 2023. <https://pmc.ncbi.nlm.nih.gov/articles/PMC10007218/>
[^33]: DEV Community. "Making AI Code Consistent with Linters." 2025. <https://dev.to/fhaponenka/making-ai-code-consistent-with-linters-27pl>
[^34]: Graphite. "How accurate are AI-generated style suggestions compared to ESLint and Prettier?" 2025. <https://graphite.com/guides/ai-style-suggestions-vs-eslint-prettier>
[^35]: DevToolsAcademy. "State of AI Code Review Tools in 2025." 2025. <https://www.devtoolsacademy.com/blog/state-of-ai-code-review-tools-2025/>

[^36]: "Measuring Determinism in Large Language Models for Software Code Review." arXiv:2502.20747, 2025. <https://arxiv.org/abs/2502.20747>
[^37]: "Does AI Code Review Lead to Code Changes? Case Study of GitHub Actions." arXiv:2508.18771, 2025. <https://arxiv.org/abs/2508.18771>
[^38]: GitHub Blog. "60 million Copilot code reviews and counting." 2025. <https://github.blog/ai-and-ml/github-copilot/60-million-copilot-code-reviews-and-counting/>
[^39]: "Benchmarking and Studying the LLM-based Code Review (SWR-Bench)." arXiv:2509.01494, 2025. <https://arxiv.org/abs/2509.01494>
[^40]: Google Research. "Resolving Code Review Comments with Machine Learning." 2023. <https://research.google/pubs/resolving-code-review-comments-with-machine-learning/>
[^41]: "Rethinking Code Review Workflows with LLM Assistance: An Empirical Study." arXiv:2505.16339, 2025. <https://arxiv.org/abs/2505.16339>
[^42]: Greptile. "AI Code Review Benchmarks 2025." <https://www.greptile.com/benchmarks>
[^43]: Codacy. "Security and Code Quality." <https://www.codacy.com/>

## Quality Metrics

| Metric | Value |
| ------ | ----- |
| Total sources | 43 |
| Academic sources | 13 |
| Official/documentation | 5 |
| Industry reports | 10 |
| News/journalism | 3 |
| Blog/forum | 9 |
| Citation coverage | 92% |
| Counter-arguments searched | Yes |
