---
title: "AI Code Review: проблема воспроизводимости результатов и индустриальные практики"
date: 2026-03-25T12:38:00+03:00
---

## Аннотация

Настоящий обзор исследует фундаментальную проблему недетерминированности результатов AI-powered code review — ситуации, когда повторные запуски ревью на одном и том же коде дают различные замечания с различными уровнями серьёзности. Анализ охватывает академические публикации (включая arXiv 2502.20747, 2506.09501, 2509.01494, 2412.18531, 2412.00543, 2203.11171, 2508.02994), индустриальные отчёты (SonarSource 2026, CodeRabbit, Qodo, Datadog), документацию коммерческих инструментов и практический опыт крупных компаний (Microsoft, ByteDance, Google, Ericsson). Основные выводы: недетерминированность является фундаментальным свойством LLM, причём консистентность не коррелирует с точностью; индустрия решает проблему через многоуровневую архитектуру (статический анализ + AST + LLM + фильтрация); наиболее эффективные подходы включают self-consistency voting, multi-agent debate (Agent-as-Judge, 99.7% согласия с экспертами), SAST-guided LLM filtering (91% снижение false positives), промпт-инжиниринг для консистентности (JSON Schema, evidence-grounding, explicit scope), hunk-based chunking и confidence-weighted aggregation. Обзор завершается практическим планом достижения 80% воспроизводимости через четырёхуровневую гибридную архитектуру.

## Введение

Внедрение LLM в процесс code review стало одним из ключевых трендов разработки ПО в 2024–2026 годах. По данным Microsoft, их AI-powered code review assistant обрабатывает более 600 000 pull request в месяц, охватывая свыше 90% PR компании[^1]. GitHub Copilot Code Review провёл 60 миллионов ревью с рост использования в 10 раз с момента запуска, составляя более 20% всех code review на платформе[^2]. По данным SonarSource, к началу 2026 года 42% всех коммитов являются AI-assisted[^3].

Однако при практическом использовании AI code review обнаруживается фундаментальная проблема: результаты ревью нестабильны. При повторных запусках на одном и том же коде без изменений инструмент выдаёт различные замечания с различными уровнями серьёзности. Это подрывает доверие к результатам и затрудняет интеграцию в CI/CD-пайплайны, где ожидается детерминированное поведение. По данным Stack Overflow 2025, 46% разработчиков активно не доверяют точности AI-кода (рост с 31%), а 45% указывают на «решения, которые почти правильны, но не совсем»[^4].

Цель обзора — исследовать причины недетерминированности AI code review, систематизировать существующие подходы к решению проблемы и определить оптимальную архитектуру, сочетающую стабильность результатов с глубиной анализа. Обзор охватывает академические исследования, коммерческие инструменты и практический опыт индустрии, но не включает разработку собственных моделей.

Документ организован следующим образом: технические причины недетерминированности LLM, архитектурные подходы к повышению стабильности, индустриальные практики и инструменты, стратегии enforcing code style, критика и ограничения AI-подхода.

## Природа недетерминированности LLM в контексте code review

### Почему temperature=0 не гарантирует детерминизм

Интуитивное ожидание разработчиков состоит в том, что установка температуры в ноль должна обеспечить полную воспроизводимость результатов. Исследования показывают, что это не так. Как отмечает Schmalbach,

> "Temperature=0 is not a mathematical guarantee of determinism. It is merely a request to the engine to be 'less random'"[^5]

При temperature=0 модель выполняет greedy decoding — выбирает токен с наивысшей вероятностью на каждом шаге. Однако даже при детерминированном sampling итоговый результат может различаться по нескольким причинам.

**Floating-point арифметика.** Корневая причина — неассоциативность операций с плавающей запятой: (a+b)+c ≠ a+(b+c) из-за конечной точности и ошибок округления. GPU-ядра выполняют параллельные вычисления и могут суммировать значения в различном порядке в зависимости от размера batch, модели оборудования и количества GPU, что приводит к каскадным ошибкам округления, способным изменить выбор токена с наивысшей вероятностью[^6][^7].

**Mixture-of-Experts (MoE).** Крупные модели (GPT-4, GPT-4o) используют архитектуру MoE, где токены конкурируют за ёмкость экспертов. Некоторые токены маршрутизируются к вторичным экспертам в зависимости от текущего состава batch, создавая вариативность на уровне batch[^8].

**Inference-time оптимизации.** Continuous batching, chunk prefilling и prefix caching — инженерные оптимизации для скорости — вносят недетерминизм. Исследование показало, что

> "models and GPUs themselves are not the only source of non-determinism"[^7]

— локальное тестирование Llama-3-8B без оптимизаций давало детерминированные результаты.

**Input buffer packing.** В облачных средах входные данные нескольких пользователей упаковываются в общие буферы, что приводит к взаимному влиянию запросов на порядок вычислений[^8].

Brenndoerfer резюмирует:

> "Even if you submit the exact same input multiple times, you may receive different outputs depending on what other inputs are processed in the same batch"[^9]

### Масштаб проблемы: эмпирические измерения

Исследование Measuring Determinism in LLMs for Software Code Review (arXiv:2502.20747) на 70 Java-коммитах показало, что даже при temperature=0 обратная связь LLM существенно варьировалась между запусками[^10]:

- Отклонения accuracy **до 15%** между прогонами
- Разрыв **до 70%** между лучшим и худшим результатами
- Градиент консистентности между моделями: GPT-4o mini (наименее стабильна) → GPT-4o → Claude 3.5 Sonnet → LLaMA 3.2 90B (наиболее стабильна)

Важный вывод авторов:

> "LLMs' reliability may be comparable to that of human reviewers"[^10]

Параллельно, исследование Ouyang et al. (2024) целенаправленно изучало недетерминизм «детерминистических» LLM-настроек[^6]. На множестве задач при `temperature=0` и `seed=fixed` совпадение выходов (TARr@10) оказалось катастрофически низким[^6]:

| Модель | Задача | Совпадение выходов (TARr@10) |
| ------ | ------ | ---------------------------- |
| Mixtral-8x7B | College Math | **7%** |
| GPT-4o | Accounting | **4.6%** |
| Llama-3-70B | Geometric Shapes | **18%** |

Исследование консистентности на 50 независимых прогонах показало, что простые задачи (бинарная классификация) достигают почти идеальной воспроизводимости, тогда как сложные задачи демонстрируют значительную вариативность[^11]. Code review, будучи сложной задачей с необходимостью понимания контекста, попадает именно в высоковариативную категорию.

**Критический фактор — длина выхода.** Длина генерируемого ответа прямо коррелирует с нестабильностью — чем длиннее ответ, тем ниже консистентность[^6]. Для code review, где ответы содержат десятки findings с описаниями, это катастрофически усиливает расхождения между запусками.

### Консистентность ≠ Точность

Chen et al. (2024) показали фундаментальный результат: **сильная точность LLM не гарантирует сильную консистентность**[^42]. Модель может давать правильные ответы, но *разные* правильные ответы при каждом запуске. Это означает, что оптимизация только точности промптов не решает проблему воспроизводимости — консистентность необходимо верифицировать как отдельную метрику.

Для code review это проявляется наглядно: LLM может корректно находить баги, но при каждом запуске находить *разные* баги из одного diff. Каждый отдельный finding может быть валидным, однако набор findings нестабилен.

Таким образом, проблема нестабильности — не баг конкретной реализации, а фундаментальное свойство LLM. Вопрос не в том, как устранить вариативность, а в том, как построить систему, устойчивую к ней.

## Архитектурные подходы к повышению стабильности

### Мульти-модельный консенсус

Один из наиболее эффективных подходов — параллельный запуск нескольких моделей с последующим голосованием. Mozilla AI описывает систему «Star Chamber», где несколько LLM независимо анализируют код с тремя уровнями уверенности: consensus (все согласны), majority (большинство), individual (одна модель)[^12].

CodeAnt AI реализует этот принцип:

> "multi-model consensus validation, running three LLMs in parallel and only surfacing issues when 2+ models agree. This cuts false positives by ~60% compared to single-model approaches while maintaining 92% recall"[^13]

Академическое исследование показало, что для задач верификации знаний (к которым относится code review) **consensus outperforms majority voting** — улучшение на 2.8%, поскольку консенсус требует межмодельного согласования и обеспечивает «repeated checks across agents to find small errors»[^14].

**EnsLLM** — альтернативный подход на основе similarity-based selection: комбинирование выходов нескольких LLM с использованием синтаксического/семантического сходства (AST matching, CodeBLEU) и поведенческого сходства (execution-based differential analysis). В 131 из 164 тестовых случаев минимум две модели независимо генерировали корректные решения, и ансамбль успешно их отбирал[^15].

### Self-Consistency через голосование

Фундаментальный подход описан Wang et al. (2022): генерация N разнообразных цепочек рассуждений (с `temperature > 0`), сбор ответов и агрегация через majority voting[^43]. Вместо одного greedy-ответа система сэмплирует множество путей рассуждения — разнообразие компенсирует стохастичность отдельных запусков, а голосование фильтрует артефакты. Результаты на математических задачах показывают значительное улучшение по сравнению с greedy decoding: +17.9% на GSM8K, +11.0% на SVAMP, +12.2% на AQuA[^43].

**Оптимизация стоимости.** Li et al. (2025) показали, что confidence-weighted voting снижает требуемое число сэмплов на 40–60% при сохранении точности[^44]. Вместо 10–20 запусков достаточно 4–8 — модель сама оценивает уверенность каждого ответа, и высокоуверенные ответы получают больший вес при агрегации.

### Higher-Order агрегация

Grazzi et al. (2025) продемонстрировали, что продвинутые методы агрегации превосходят простое majority voting на +1.16% — +3.36%[^45]. Ключевая идея: учитывать не только «за/против», но и паттерны согласия между конкретными моделями или запусками, используя информацию о том, какие агенты чаще ошибаются вместе. Это особенно релевантно для code review, где разные модели имеют систематические bias в определённых категориях findings.

### Agent-as-Judge: multi-agent debate

Zhuge et al. (2024) исследовали структурированную multi-agent debate model для оценки кода, где агентам назначаются специализированные роли (Judge, Prosecutor, Defense Attorney)[^46]:

- Одиночный LLM judge расходится с человеческими экспертами в **31%** случаев
- Agent-as-Judge (multi-agent debate) расходится лишь в **0.3%** случаев на задачах кода

Структурированная дискуссия между агентами с разными ролями элиминирует индивидуальные bias — каждый агент вынужден обосновывать позицию перед «оппонентом», что отсекает слабо подкреплённые findings.

### Двухстадийная архитектура: BitsAI-CR

ByteDance в системе BitsAI-CR реализует каскад из двух специализированных моделей[^16]. RuleChecker — fine-tuned LLM на таксономии из 219 правил ревью — выполняет первичное обнаружение. ReviewFilter — вторая fine-tuned LLM — верифицирует находки.

> "BitsAI-CR achieves 75.0% precision in review comment generation"[^16]

Механизм data flywheel обеспечивает непрерывное улучшение: аннотации ревьюеров (принят/отклонён) используются для уточнения таксономии и переобучения моделей. Система обслуживает более 12 000 активных пользователей в неделю[^16].

### AST-based context engineering

Обогащение контекста LLM детерминированной структурной информацией. Kodus — open-source engine:

> "a deterministic, AST-based rule engine to provide precise, structured context directly to the LLM. The result is a dramatically reduced noise rate, fewer hallucinations, and comments you can actually trust"[^17]

CodeRabbit использует Tree-Sitter для иерархического представления кода и интегрирует 35+ линтеров в pipeline[^18]. Дополнительно CodeRabbit использует LanceDB для vector embeddings, создавая «living knowledge graph» — непрерывно обновляемые векторы, адаптирующиеся к эволюции кодовой базы, обрабатывающие 50K+ PR ежедневно[^19]. Это обеспечивает consistency через семантический контекст: при ревью одного и того же кода система находит одни и те же релевантные паттерны, тесты и исторические изменения.

### Confidence-based фильтрация

**FineCE** (Fine-Grained Confidence Estimation) вычисляет confidence scores на уровне генерации токенов, позволяя идентифицировать ненадёжные выходы уже после ~30% генерации и достигая **39.5% улучшения accuracy** на GSM8K через раннее отклонение[^20].

Однако Epiq предупреждает: LLM confidence estimates остаются «severely miscalibrated» — Expected Calibration Error 0.108–0.427, что значительно превышает допустимые пороги для критических систем[^21]. Более надёжный подход — token-level probabilities (logprobs) из API, а не вербализированные оценки.

### SAST-guided LLM filtering

Datadog предлагает паттерн инверсии ролей, где LLM используется не как основной сканер, а как **фильтр для SAST-находок**[^53]:

1. SAST генерирует alerts (детерминированно)
2. LLM оценивает контекст каждого alert (data flow, validation, exploitation feasibility)
3. LLM объясняет reasoning для каждого решения
4. Feedback loop уточняет performance

Результат: **91% снижение false positives** при SAST-Genius approach[^53]. Этот подход особенно интересен тем, что детерминированный инструмент обеспечивает стабильный набор candidates, а LLM работает только как классификатор (true/false positive) — задача, значительно более стабильная, чем генерация findings с нуля.

### LLM4FPM: точный контекст для LLM

Li et al. (2024) разработали специализированный framework для снижения false positives через точное определение контекста[^54]. Система строит extended Code Property Graph (eCPG), извлекает только релевантные строки кода через graph slicing, находит связанные файлы через FARF-алгоритм (без анализа всей кодовой базы) и передаёт этот точный контекст в LLM с CoT + few-shot промптом, специфичным для типа уязвимости.

Результат: **86% accuracy** на реальном коде, **F1 > 99%** на бенчмарке[^54]. Ключевой insight: не весь файл, а только relevant lines — критически важны для accuracy LLM. Избыточный контекст снижает точность.

### Confidence thresholding с abstention

Gekhman et al. (2025) показали, что ensemble с политикой abstention (отказ от ответа при низкой уверенности) повышает trustworthiness[^55]. Подход trade coverage for precision: лучше пропустить неуверенное finding, чем выдать false positive. Порог 0.7+ confidence для фильтрации эффективен, но требует per-project tuning — оптимальный threshold зависит от соотношения стоимости пропущенного бага к стоимости false positive.

### Системный уровень: LayerCast и LLM-42

На инфраструктурном уровне появляются новые подходы. **LayerCast** хранит веса в BF16 (экономия памяти), но выполняет все вычисления в FP32 (численная стабильность), достигая детерминизма уровня FP32 с 34% меньшим потреблением памяти[^7].

**LLM-42** (Decode-Verify-Rollback) генерирует токены оптимистично с dynamic batching (быстро), периодически воспроизводит недавние токены при фиксированных размерах batch (детерминистично) и откатывается при обнаружении расхождений. Применяется селективно — только к запросам с флагом `is_deterministic=True`[^22].

## Промпт-инжиниринг для консистентности

### Structured Output (JSON Schema)

Структурированный формат ответа — одна из наиболее эффективных техник стабилизации. Вместо свободного текста LLM генерирует JSON с фиксированной схемой[^47]:

- Устраняет вариативность формата (severity: «high» vs «critical» vs «блокирующий»)
- Сокращает длину выхода (меньше длина → больше консистентность[^6])
- Позволяет автоматическую дедупликацию по `file:line`

Бенчмарк JSONSchemaBench протестировал 10 000 JSON-схем на различных моделях и показал, что constrained decoding значительно повышает compliance rate[^47], хотя и не устраняет семантическую вариативность — модель всё ещё может описать одну и ту же проблему разными словами внутри фиксированной структуры.

### Chain-of-Thought с верификацией

Wei et al. (2022) показали, что CoT prompting с exemplars даёт state-of-the-art точность на reasoning-задачах[^48]. Для code review это трансформируется в 4-шаговый процесс, где каждый шаг ограничивает пространство вариантов для следующего:

1. **Процитировать конкретный код** (line:number + snippet из diff)
2. **Объяснить проблему** с отсылкой к цитате
3. **Оценить severity** по фиксированной рубрике
4. **Сформулировать finding**

Принуждение к цитированию кода на первом шаге привязывает рассуждение к конкретным строкам, что повышает воспроизводимость — модели сложнее «изобрести» проблему, если она обязана указать точное место.

### Evidence-grounded findings

Требование цитировать конкретные строки кода как доказательства — ключевой антигаллюцинационный механизм. Исследования показывают 42–68% снижение галлюцинаций при использовании Retrieval-Augmented Generation подходов[^49]. Для code review правило простое: если LLM не может указать конкретную строку и код — finding отклоняется автоматически. Это одновременно повышает precision и делает validation детерминированным.

### Explicit scope и Permission for uncertainty

Два дополняющих друг друга приёма:

- **Explicit scope** («найди только security и correctness проблемы в изменённых файлах») снижает noise на ~50% по сравнению с open-ended промптами[^49]
- **Permission for uncertainty** (разрешение LLM сказать «не могу определить без дополнительного контекста») драматически снижает генерацию ложной информации[^49]

Промпт, содержащий фразу «If you cannot verify a finding with specific code evidence, do not report it» элиминирует значительную часть false positives.

### Few-shot calibration

Few-shot examples калибруют severity scale LLM. Без них каждый запуск интерпретирует «S1 Blocker» по-своему. С 3–5 примерами конкретных findings для каждого severity level пороги выравниваются между запусками:

- S1 Blocker: hardcoded credentials → пример с кодом и обоснованием
- S2 Critical: fail-open security → пример
- S3 Major: pattern deviation → пример
- S4 Minor: naming nit → пример

Однако следует учитывать, что **ordering примеров влияет критически**: разные перестановки одних и тех же few-shot examples могут дать разницу до **76 accuracy points**[^50]. Для стабильности необходимо фиксировать порядок примеров и не менять его между запусками.

## Стратегия chunking и контекст

### Корневая причина нестабильности chunking

> "When companies get results from LLMs that don't have the right context or provide inaccurate information, the root cause likely isn't the model — it's how the data was chunked"[^51]

Если diff разбивается на chunks по-разному между запусками (из-за недетерминированного splitting), каждый chunk reviewer видит разный контекст → разные findings. Находки, требующие cross-file reasoning, особенно нестабильны — они зависят от того, попали ли связанные файлы в один chunk.

### Детерминированный chunking

Ключевые принципы для стабильного chunking[^52]:

1. **Git hunk boundaries** как primary split points — они представляют логически связные изменения
2. **3-строчное перекрытие** на границах chunks для предотвращения семантического разрыва
3. **File ordering preservation** — семантическая близость файлов важна для inference
4. **Trim low-entropy content** (lock files, auto-generated код) до ~100 токенов
5. **Контекстный бюджет 50–70%** от максимума модели, не наивное заполнение

### Semantic vs Fixed chunking

| Стратегия | Консистентность | Точность | Скорость |
| --------- | --------------- | -------- | -------- |
| Fixed-size | Стабильный размер, но режет mid-statement | -5–15% vs semantic | Микросекунды |
| Semantic | Высокая (уважает границы кода) | +5–15%, меньше галлюцинаций | 50–100x медленнее |
| Recursive | Хорошая (paragraph → sentence → char) | Хорошая | Умеренная |
| **Hunk-based (Git-native)** | **Высокая (уважает intent)** | **Высокая** | **Быстрая** |

Для code review оптимален **hunk-based chunking** — он одновременно быстрый и семантически корректный, поскольку git hunks уже представляют логически связные изменения[^52].

### Ограничения cross-file reasoning

Findings, требующие связать факты из нескольких файлов, зависят от попадания связанных файлов в один chunk. Даже с overlap и hunk-based splitting, находки типа «context.Background() в файле A нарушает lifecycle из файла B» нестабильны.

Возможное решение — специализированный cross-file reviewer с полным контекстом проекта (модели с 1M+ context window). Однако исследования показывают проблему «lost-in-the-middle» — информация в середине длинного контекста систематически игнорируется[^59], что может сделать длинный контекст контрпродуктивным.

## Метрики воспроизводимости

### Inter-rater agreement

Для оценки консистентности между запусками LLM review применимы классические метрики межэкспертного согласия[^56]:

- **Cohen's Kappa (κ)**: для сравнения 2 запусков. κ > 0.80 = near-perfect agreement, κ = 0.60–0.80 = substantial agreement
- **Fleiss' Kappa**: обобщение для 3+ запусков
- **ICC (Intraclass Correlation)**: для continuous severity ratings (когда severity — числовая шкала)

Целевой κ для 80% детерминированности: **≥ 0.75** (substantial agreement).

### Precision/Recall для code review

Qodo benchmark определяет стандартные метрики в контексте code review[^57]: Precision = TP / (TP + FP), Recall = TP / (TP + FN). Текущий state-of-art: **F1 = 60.1%** на 580 дефектах[^57]. Martian benchmark на 200K+ PR показывает precision 40–70% для лучших инструментов[^58].

### Метрика воспроизводимости

Для измерения прогресса в стабилизации code review предлагается метрика:

```text
Reproducibility@N = |Findings в ≥2 из N запусков| / |Union всех Findings из N запусков|
```

Эта метрика измеряет долю стабильных findings — тех, которые воспроизводятся при повторных запусках. Значение Reproducibility@4 = 20% означает, что лишь каждый пятый finding стабилен; цель — 80%.

## Индустриальные практики AI code review

### Microsoft: от эксперимента к масштабу

Microsoft масштабировал AI code review до поддержки 90%+ PR (600K+ в месяц) с 10–20% улучшением медианного времени завершения PR[^1]. Академический фундамент — модель CodeReviewer (Li et al., arXiv:2203.09095), обученная на 9 языках[^23]. Опыт внутреннего внедрения лёг в основу GitHub Copilot Code Review[^1].

### Google DIDACT: ML для резолюции комментариев

Google использует подход DIDACT — обучение на *процессе* разработки (не на полированном коде):

> "The novelty of DIDACT is that it uses the process of software development as the source of training data"[^24]

Система автоматически резолвит ~7.5% комментариев ревьюеров через ML-suggested edits, экономя сотни тысяч инженерных часов ежегодно[^24]. После UX-улучшений — 2X coverage по комментариям, 40–50% предложенных правок применяются[^24].

### Эффективность AI review: addressing rate и парадокс продуктивности

Эмпирическое исследование 22 000+ комментариев в 178 репозиториях выявило драматический разрыв[^25]:

| Ревьюер | Addressing Rate |
| ------- | --------------- |
| Человек | 60% |
| CodeRabbit (лучший AI) | 19.2% |
| Типичные AI-инструменты | 4–8% |

Факторы повышения эффективности AI: привязка к конкретным строкам (hunk-level targeting), code snippets с предложенными исправлениями, краткость[^25].

Парадокс продуктивности: AI генерирует 6.4x больше кода, но время ревью PR увеличивается на 91%[^26]. Senior-инженеры тратят 4.3 минуты на AI-код vs 1.2 минуты на человеческий[^26]. SonarSource фиксирует:

> "The explosion in code volume has not delivered expected improvements in efficiency; instead, the surge in output has created a new bottleneck at the verification stage"[^3]

38% респондентов считают, что ревью AI-кода требует больше усилий, чем ревью человеческого[^3].

### Пропускать ли code review?

Индустриальные данные однозначны: команды, пропускающие code review, выпускают баги на 40% чаще[^27]. Стоимость исправления в продакшене — 10x от стоимости на этапе разработки[^28]. AI-generated код содержит в 1.7x больше дефектов, чем человеческий, а 45% образцов AI-кода содержат уязвимости из OWASP Top 10[^29].

> "PRs are getting larger (~18% more additions as AI adoption increases), incidents per PR are up ~24%, and change failure rates up ~30%"[^30]

В эпоху AI-generated кода значимость code review возрастает, а не уменьшается.

### Qodo Merge 1.0: Focus Mode

Qodo Merge 1.0 ввёл Focus Mode — режим, приоритизирующий критические проблемы (баги, безопасность, поддерживаемость) и фильтрующий стилистический шум. Тестирование показало увеличение acceptance rate на ~50%[^31]. Платформа также использует dynamic learning — автоматическое обнаружение принятых предложений и формирование «dynamic best practices wiki»[^31].

## Критика и ограничения AI code review

### Confirmation bias при self-review

Использование одной и той же AI-системы для генерации и ревью кода создаёт confirmation bias на масштабе:

> "When you use the same AI system to both write and review code, you're not getting a second opinion—you're getting confirmation bias at scale"[^30]

LLM демонстрируют склонность к подтверждению собственных выводов, генерируя информацию, согласующуюся с предыдущими выходами[^30].

### Отсутствие проектного контекста

> "AI review without project context is just another linter with better prose"[^32]

Без знания командных конвенций, доменных требований и архитектурных стандартов AI применяет генерический чеклист, дающий генерические и часто вводящие в заблуждение результаты[^32].

### Бенчмарки: реальная производительность

SWR-Bench (2025) на 1000 верифицированных PR показал отрезвляющие результаты[^33]:

- Лучшая конфигурация (PR-Review + Gemini-2.5-Pro): **всего 19.38% F1**
- Большинство систем: **менее 10% precision**
- LLM лучше обнаруживают функциональные ошибки (F1 >21%) чем «эволюционные» улучшения (документация, стиль — F1 <16%)

Однако multi-review aggregation улучшает F1 Gemini-2.5-Flash на **43.67%**, recall — на **118.83%**[^33]. GPT-4o достигает 68.50% accuracy на классификации корректности кода, но до 24.80% корректного кода получает ошибочные предложения (риск регрессий)[^34].

### Безопасность: AI coding agents повторяют ошибки

Исследование 2026 года показало, что AI coding agents (Claude Code, OpenAI Codex, Gemini) систематически воспроизводят давно известные security-ошибки: небезопасные JWT-defaults, отсутствие brute-force protection, невоотзываемые refresh tokens[^35]. OpenAI Codex Security просканировал 1.2 миллиона коммитов и обнаружил 10 561 high-severity issue[^35].

## Code style enforcement: детерминистический уровень

### Линтеры и форматтеры как фундамент

Ключевое различие между AI и детерминистическими инструментами:

> "AI can choose to ignore documentation, but cannot ignore linting errors in CI pipelines"[^36]

Линтеры (ESLint, golangci-lint) и форматтеры (Prettier, gofmt, Black) обеспечивают 100% детерминированные результаты. Graphite отмечает:

> "Prettier and ESLint set the gold standard for reliable, rule-based enforcement and are essential for baseline quality; AI should augment—not replace—them"[^37]

AI достигает 51–83% accuracy на style-related fixes[^37] — значительно ниже 100% у детерминистических инструментов.

### Пирамида автоматизации code quality

Индустриальная best practice формирует четырёхуровневую пирамиду:

1. **Форматтеры** (gofmt, Prettier, Black): автоматическое форматирование, 100% детерминизм
2. **Линтеры** (golangci-lint, ESLint): статические правила, детерминированные результаты
3. **Статический анализ** (Semgrep, CodeQL, SonarQube): обнаружение паттернов уязвимостей
4. **AI review**: семантический анализ, архитектурные замечания

> "Teams that enforce strict linting and code style rules are getting better results from AI agents"[^36]

Строгий enforcement через линтеры не только решает стабильность стиля, но и повышает качество AI review — модели лучше анализируют консистентный код.

### AI для стилистических замечаний выше уровня линтера

AI занимает нишу проверок, не формализуемых в правилах: выбор имён, структура функций, архитектурные паттерны. CodeRabbit реализует это через code guidelines — определение preferred file structure, module boundaries и dependency rules, которые применяются к каждому PR[^18]. Qodo Merge использует dynamic learning для автоматического обнаружения принятых паттернов[^31].

## Дискуссионные вопросы и противоречия

### Детерминизм vs глубина анализа

Фундаментальное противоречие: чем детерминированнее результаты, тем более они ограничены. Статические анализаторы — 100% воспроизводимость, но не способны к семантическому пониманию. LLM — глубокий анализ, но с неизбежной вариативностью. Решение — комбинирование в многоуровневой архитектуре, а не выбор одного подхода.

### Precision vs recall: signal-to-noise tradeoff

Augment Code и Claude Code демонстрируют разные точки на кривой precision-recall[^38]. Augment: 65% precision, 55% recall (59% F-score). Claude Code: ~51% recall, значительно ниже precision (~49% F-score)[^38]. Для разработчиков высокий false positive rate разрушительнее пропущенных замечаний — шум приводит к «alarm fatigue». Индустриальный стандарт false positive rate: 5–15%, но до 40% AI-алертов игнорируются на практике[^39].

### Консистентность vs Recall trade-off

Жёсткая фильтрация (только high-confidence, только 2+/3 consensus) повышает precision и reproducibility, но снижает recall. Multi-run voting с threshold 2/3 теряет ~33% уникальных правильных findings.

Рекомендация: для S1/S2 (Blocker/Critical) — приоритет recall, поскольку пропуск blocker хуже false positive. Для S3/S4 (Major/Minor) — приоритет precision, поскольку noise хуже пропуска nit. Это приводит к дифференцированной стратегии фильтрации: критические findings проходят при consensus 1/3, остальные — при 2/3.

### Стоимость multi-run подхода

3–5 запусков на один diff × стоимость LLM API = 3–5x расход. Для крупных diff (100+ файлов) это может составлять $5–15 за review. Confidence-weighted voting[^44] снижает необходимое число запусков, но не устраняет мультипликатор полностью. Вопрос ROI зависит от стоимости пропущенного бага в продакшене (10x от стоимости на этапе разработки[^28]).

### 2025 — год скорости, 2026 — год качества

CodeRabbit формулирует смену парадигмы:

> "2025 was the year of AI speed. 2026 will be the year of AI quality"[^40]

Индустрия смещает метрики от velocity (PR throughput) к reliability (defect density, merge confidence, test coverage, maintainability)[^40]. Adoption code review agents вырос с 14.8% (январь 2025) до 51.4% (октябрь 2025)[^2].

### AI code review vs human: не замена, а дополнение

73.8% автоматических комментариев resolved[^41], но PR closure time при этом увеличивается с 5h 52m до 8h 20m[^41]. Acceptance rate AI-кода: 32.7% vs 84.4% для человеческого[^4]. Академический консенсус: полная автоматизация ненадёжна; гибридный human-in-the-loop — практический стандарт[^34].

## Практический план достижения 80% воспроизводимости

На основе систематизированных подходов формируется четырёхуровневая архитектура, где каждый слой решает свою задачу.

### Уровень 1: Детерминистический слой (~40% coverage)

Вынести pattern-matched checks из LLM в статический анализ: hardcoded credentials (gitleaks), missing error checks (golangci-lint: rowserrcheck, bodyclose), undefined functions (go build), security patterns (CodeQL, Semgrep). Эти checks воспроизводимы на 100%.

**Стоимость**: одноразовая настройка linter rules, затем бесплатно.

### Уровень 2: Structured LLM Review (~25% дополнительного coverage)

Фиксированный промпт с JSON schema, evidence-grounded findings, explicit scope и few-shot calibration. Каждый finding обязан содержать `code_quote` — точную цитату из diff. Findings без конкретного `file:line` отклоняются автоматически. `confidence: low` findings отбрасываются по умолчанию.

### Уровень 3: Multi-Run Voting (~15% дополнительного coverage)

3 запуска с confidence-weighted aggregation[^44]: разные формулировки промпта, дедупликация по `file:line + category`, finding валиден при consensus ≥2/3, severity = медиана из всех запусков.

**Стоимость**: 3x compute, но confidence-weighted voting позволяет снизить до 3 запусков вместо 10–20.

### Уровень 4: Детерминированная валидация

Заменить LLM-based validation на rule-based: finding ссылается на несуществующую строку → discard (grep check), finding ссылается на функцию с неверной сигнатурой → discard (go vet check), finding дублирует существующий linter warning → discard (dedup), finding не содержит `code_quote` → discard.

### Итоговая формула

| Слой | Метод | Coverage | Reproducibility |
| ---- | ----- | -------- | --------------- |
| 1 | Static analysis (linters, grep) | ~40% findings | **100%** |
| 2 | Structured LLM (JSON + evidence) | ~25% findings | **60–70%** |
| 3 | Multi-run voting (3 runs) | ~15% findings | **80–90%** |
| 4 | Deterministic validation | filter layer | **100%** |
| **Total** | **Hybrid pipeline** | **~80% findings** | **~80–85%** |

Estimated Reproducibility@4: union слоёв 1–3, отфильтрованный слоем 4 → **~80%** находок воспроизводятся в 2+ запусках.

## Заключение

### Синтез

Недетерминированность AI code review — фундаментальное свойство LLM, обусловленное floating-point арифметикой, MoE-маршрутизацией, batch-эффектами и inference-time оптимизациями. Ни один крупный провайдер LLM не гарантирует полностью детерминированных выходов (2025). Индустрия не пытается устранить вариативность, а строит системы, устойчивые к ней.

### Ключевые выводы

1. **Многоуровневая архитектура** — наиболее эффективный подход: детерминистические инструменты (линтеры, форматтеры, SAST) для базовых проверок, AI для семантического анализа
2. **Консистентность ≠ Точность** — модель может быть точной, но давать разные правильные ответы; консистентность нужно верифицировать отдельно[^42]
3. **Мульти-модельный консенсус** снижает false positive на ~60%, multi-review aggregation улучшает F1 на 43%+, Agent-as-Judge достигает 99.7% согласия с экспертами[^46]
4. **Таксономия правил** (BitsAI-CR) ограничивает пространство выводов LLM, достигая 75% precision
5. **Промпт-инжиниринг** (JSON Schema, CoT, evidence-grounding, explicit scope) снижает noise на 50%+ и галлюцинации на 42–68%
6. **SAST-guided filtering** (Datadog) — LLM как фильтр для SAST, 91% снижение false positives[^53]
7. **Hunk-based chunking** обеспечивает детерминированное разделение diff без потери семантики[^52]
8. **Confidence-based фильтрация** с abstention отсекает нестабильные замечания
9. **Code style** решается линтерами и форматтерами; AI — только для неформализуемых проверок
10. **Verification bottleneck** — новая проблема: AI генерирует быстрее, чем люди могут ревьюить

### Практические рекомендации

1. **Разделить проверки по уровням**: code style — линтерам, семантика — AI
2. **Structured Output**: JSON schema с обязательным `code_quote` и `file:line`
3. **Evidence-grounding**: findings без цитаты конкретного кода отклоняются автоматически
4. **Multi-run voting**: 3 запуска с confidence-weighted aggregation, consensus ≥2/3
5. **Детерминированная валидация**: rule-based проверка findings вместо LLM-based
6. **Дифференцированная фильтрация**: S1/S2 — приоритет recall, S3/S4 — приоритет precision
7. **Focus Mode**: публиковать только high-confidence + high-severity замечания (подход Qodo Merge, +50% acceptance)
8. **Избегать self-review**: не использовать одну модель для генерации и ревью
9. **Формализовать метрики**: Reproducibility@N, Cohen's Kappa ≥ 0.75 как целевой порог

### Направления дальнейших исследований

- **Оптимальное N для voting**: confidence-weighted voting снижает N с 10–20 до 4–8[^44], но для code review оптимальное N не исследовано
- **Semantic dedup для findings**: как надёжно определить, что два findings об одной проблеме при различных формулировках
- **Per-project calibration**: few-shot examples из истории проекта для улучшения severity consistency
- **Long-context degradation**: модели с 1M context обещают видеть весь проект, но «lost-in-the-middle»[^59] может сделать это контрпродуктивным
- Эффективность LayerCast/LLM-42 для production code review
- Fine-tuning на специфических кодовых базах vs универсальные модели

## Quality Metrics

| Metric | Value |
| ------ | ----- |
| Total sources | 59 |
| Academic sources | 24 |
| Official/documentation | 7 |
| Industry reports | 15 |
| News/journalism | 4 |
| Blog/forum | 9 |
| Citation coverage | 95% |
| Counter-arguments searched | Yes |
| Research rounds | 4 (1 initial + 2 iterative deepening + 1 targeted expansion) |
| Questions emerged | 17 |
| Questions resolved | 14 |
| Questions insufficient data | 3 |

[^1]: Microsoft Engineering. "Enhancing Code Quality at Scale with AI-Powered Code Reviews." Engineering@Microsoft, 2025. <https://devblogs.microsoft.com/engineering-at-microsoft/enhancing-code-quality-at-scale-with-ai-powered-code-reviews/>
[^2]: GitHub Blog. "60 million Copilot code reviews and counting." 2025. <https://github.blog/ai-and-ml/github-copilot/60-million-copilot-code-reviews-and-counting/>
[^3]: SonarSource. "State of Code Developer Survey Report 2026." 2026. <https://www.sonarsource.com/blog/state-of-code-developer-survey-report-the-current-reality-of-ai-coding/>
[^4]: Stack Overflow. Developer Survey 2025; referenced in SonarSource 2026 report. <https://www.sonarsource.com/company/press-releases/sonar-data-reveals-critical-verification-gap-in-ai-coding/>
[^5]: Schmalbach, V. "Does Temperature 0 Guarantee Deterministic LLM Outputs?" 2025. <https://www.vincentschmalbach.com/does-temperature-0-guarantee-deterministic-llm-outputs/>
[^6]: Ouyang et al. "Non-Determinism of 'Deterministic' LLM Settings." arXiv:2408.04667, 2024. <https://arxiv.org/abs/2408.04667>
[^7]: "Understanding and Mitigating Numerical Sources of Nondeterminism in LLM Inference." arXiv:2506.09501, 2025. <https://arxiv.org/abs/2506.09501>
[^8]: "Non-Determinism of 'Deterministic' LLM System Settings in Hosted Environments." ACL 2025 eval4nlp. <https://aclanthology.org/2025.eval4nlp-1.12/>
[^9]: Brenndoerfer, M. "Why Temperature=0 Doesn't Guarantee Determinism in LLMs." 2025. <https://mbrenndoerfer.com/writing/why-llms-are-not-deterministic>
[^10]: "Measuring Determinism in Large Language Models for Software Code Review." arXiv:2502.20747, 2025. <https://arxiv.org/abs/2502.20747>
[^11]: "Assessing Consistency and Reproducibility in the Outputs of Large Language Models." arXiv:2503.16974, 2025. <https://arxiv.org/abs/2503.16974>
[^12]: Mozilla AI. "The Star Chamber: Multi-LLM Consensus for Code Quality." 2025. <https://blog.mozilla.ai/the-star-chamber-multi-llm-consensus-for-code-quality/>
[^13]: CodeAnt AI. "How Many False Positives Are Too Many in AI Code Review." 2025. <https://www.codeant.ai/blogs/ai-code-review-false-positives>
[^14]: "Voting or Consensus? Decision-Making in Multi-Agent Debate." arXiv:2502.19130, 2025. <https://arxiv.org/abs/2502.19130>
[^15]: "Enhancing LLM Code Generation with Ensembles: A Similarity-Based Selection Approach." arXiv:2503.15838, 2025. <https://arxiv.org/abs/2503.15838>
[^16]: Li et al. "BitsAI-CR: Automated Code Review via LLM in Practice." FSE 2025. arXiv:2501.15134. <https://arxiv.org/abs/2501.15134>
[^17]: Kodus. "An open source AI code review engine (AST and LLW, less noise)." DEV Community, 2025. <https://dev.to/kodus/kodus-an-open-source-ai-code-review-engine-ast-and-llw-less-noise-3726>
[^18]: CodeRabbit. "How CodeRabbit delivers accurate AI code reviews on massive codebases." 2025. <https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases>
[^19]: LanceDB. "Case Study: How CodeRabbit Leverages LanceDB for AI-Powered Code Reviews." 2025. <https://lancedb.com/blog/case-study-coderabbit/>
[^20]: "Mind the Generation Process: Fine-Grained Confidence Estimation During LLM Generation." arXiv:2508.12040, 2025. <https://arxiv.org/abs/2508.12040>
[^21]: "Quantifying the Consistency, Fidelity, and Reliability of LLM Verbalized Confidence." OpenReview, 2025. <https://openreview.net/forum?id=qTU69oIBLZ>
[^22]: "LLM-42: Enabling Determinism in LLM Inference with Verified Speculation." arXiv:2601.17768, 2026. <https://arxiv.org/abs/2601.17768>
[^23]: Li, Z. et al. "Automating Code Review Activities by Large-Scale Pre-training." arXiv:2203.09095, 2022. <https://arxiv.org/abs/2203.09095>
[^24]: Google Research. "Resolving Code Review Comments with Machine Learning." 2023. <https://research.google/blog/resolving-code-review-comments-with-ml/>
[^25]: "Does AI Code Review Lead to Code Changes? Case Study of GitHub Actions." arXiv:2508.18771, 2025. <https://arxiv.org/abs/2508.18771>
[^26]: Level Up Coding. "The AI Code Review Bottleneck Is Already Here." Medium, 2026. <https://levelup.gitconnected.com/the-ai-code-review-bottleneck-is-already-here-most-teams-havent-noticed-1b75e96e6781>
[^27]: LinkedIn. "Why skipping code reviews can be lethal for your organization!" 2024. <https://www.linkedin.com/pulse/why-skipping-code-reviews-can-lethal-your-gopalakrishnan-iyer>
[^28]: testRigor. "Quality vs Speed: The True Cost of 'Ship Now, Fix Later'." 2025. <https://testrigor.com/blog/quality-vs-speed-the-true-cost-of-ship-now-fix-later/>
[^29]: CodeRabbit. "AI vs human code gen report: AI code creates 1.7x more issues." 2025. <https://www.coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report>
[^30]: Qodo. "Why Your AI Code Reviews Are Broken (And How to Fix Them)." 2025. <https://www.qodo.ai/blog/why-your-ai-code-reviews-are-broken-and-how-to-fix-them/>
[^31]: Qodo. "Qodo Merge 1.0: solving key challenges in AI-assisted code reviews." 2025. <https://www.qodo.ai/blog/qodo-merge-solving-key-challenges-in-ai-assisted-code-reviews/>
[^32]: DEV Community. "Why AI Code Review Fails Without Project Context." 2025. <https://dev.to/zeflq/why-ai-code-review-fails-without-project-context-4f60>
[^33]: "Benchmarking and Studying the LLM-based Code Review (SWR-Bench)." arXiv:2509.01494, 2025. <https://arxiv.org/abs/2509.01494>
[^34]: "Evaluating Large Language Models for Code Review." arXiv:2505.20206, 2025. <https://arxiv.org/abs/2505.20206>
[^35]: Help Net Security. "AI coding agents keep repeating decade-old security mistakes." 2026. <https://www.helpnetsecurity.com/2026/03/13/claude-code-openai-codex-google-gemini-ai-coding-agent-security/>
[^36]: DEV Community. "Making AI Code Consistent with Linters." 2025. <https://dev.to/fhaponenka/making-ai-code-consistent-with-linters-27pl>
[^37]: Graphite. "How accurate are AI-generated style suggestions compared to ESLint and Prettier?" 2025. <https://graphite.com/guides/ai-style-suggestions-vs-eslint-prettier>
[^38]: Augment Code. "We benchmarked 7 AI code review tools on large open-source projects." 2025. <https://www.augmentcode.com/blog/we-benchmarked-7-ai-code-review-tools-on-real-world-prs-here-are-the-results>
[^39]: PropelCode. "Reducing AI Code Review False Positives: Practical Techniques." 2025. <https://www.propelcode.ai/blog/ai-code-review-false-positives-reducing-noise>
[^40]: CodeRabbit. "2025 was the year of AI speed. 2026 will be the year of AI quality." 2026. <https://www.coderabbit.ai/blog/2025-was-the-year-of-ai-speed-2026-will-be-the-year-of-ai-quality>
[^41]: "Automated Code Review In Practice." arXiv:2412.18531, 2024. <https://arxiv.org/abs/2412.18531>
[^42]: Chen, Y. et al. "Evaluating the Consistency of LLM Evaluators." COLING 2025. arXiv:2412.00543, 2024. <https://arxiv.org/abs/2412.00543>
[^43]: Wang, X. et al. "Self-Consistency Improves Chain of Thought Reasoning in Language Models." ICLR 2023. arXiv:2203.11171, 2022. <https://arxiv.org/abs/2203.11171>
[^44]: Li, H. et al. "Confidence Improves Self-Consistency in LLMs." arXiv:2502.06233, 2025. <https://arxiv.org/abs/2502.06233>
[^45]: Grazzi, R. et al. "Beyond Majority Voting: LLM Aggregation by Leveraging Higher-Order Information." arXiv:2510.01499, 2025. <https://arxiv.org/abs/2510.01499>
[^46]: Zhuge, M. et al. "When AIs Judge AIs: The Rise of Agent-as-a-Judge Evaluation for LLMs." arXiv:2508.02994, 2024. <https://arxiv.org/abs/2508.02994>
[^47]: "JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models." arXiv:2501.10868, 2025. <https://arxiv.org/abs/2501.10868>
[^48]: Wei, J. et al. "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." arXiv:2201.11903, 2022. <https://arxiv.org/abs/2201.11903>
[^49]: Anthropic. "Reduce Hallucinations — Claude API Docs." 2025. <https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations>
[^50]: "Unleashing the potential of prompt engineering for large language models." ScienceDirect, 2025. <https://www.sciencedirect.com/science/article/pii/S2666389925001084>
[^51]: Redis. "LLM Chunking — How to Improve Retrieval & Accuracy." 2025. <https://redis.io/blog/llm-chunking/>
[^52]: "Precision Dissection of Git Diffs for LLM Consumption." Medium, 2025. <https://medium.com/@yehezkieldio/precision-dissection-of-git-diffs-for-llm-consumption-7ce5d2ca5d47>
[^53]: Datadog. "Using LLMs to filter out false positives from static code analysis." 2025. <https://www.datadoghq.com/blog/using-llms-to-filter-out-false-positives/>
[^54]: Li, Z. et al. "Utilizing Precise and Complete Code Context to Guide LLM in Automatic False Positive Mitigation." arXiv:2411.03079, 2024. <https://arxiv.org/abs/2411.03079>
[^55]: Gekhman, Z. et al. "Increasing LLM response trustworthiness using voting ensembles." arXiv:2510.04048, 2025. <https://arxiv.org/abs/2510.04048>
[^56]: Galileo AI. "Cohen's Kappa for AI Evaluation." 2025. <https://galileo.ai/blog/cohens-kappa-metric>
[^57]: Qodo. "Why Code Review Needs Its Own AI with State-of-the-Art Precision-Recall." 2025. <https://www.qodo.ai/blog/why-code-review-needs-its-own-ai-with-state-of-the-art-precision-recall/>
[^58]: CodeAnt. "AI Code Review Benchmark Results from 200,000 Real Pull Requests." 2026. <https://www.codeant.ai/blogs/ai-code-review-benchmark-results-from-200-000-real-pull-requests>
[^59]: "Long-Context vs. RAG Evaluation." arXiv:2501.01880, 2025. <https://arxiv.org/abs/2501.01880>
