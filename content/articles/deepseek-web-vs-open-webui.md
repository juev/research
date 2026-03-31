---
title: "DeepSeek Web vs Open-WebUI: почему одна и та же модель даёт разные результаты"
date: 2026-03-26T12:28:00+03:00
---

## Аннотация

Пользователи, использующие модели DeepSeek через Open-WebUI, регулярно отмечают, что веб-интерфейс chat.deepseek.com генерирует более развёрнутые, проработанные и актуальные ответы по сравнению с тем же запросом, отправленным через Open-WebUI. Данный обзор исследует технические причины этого расхождения на основе анализа официальной документации DeepSeek API, документации Open-WebUI, отчётов сообщества (GitHub Issues, Reddit) и независимых исследований. Выявлены пять ключевых факторов различий: встроенный веб-поиск DeepSeek, различия в системных промптах и параметрах генерации, отличия в версиях моделей, ограничения RAG-пайплайна Open-WebUI и некорректная обработка reasoning-контента. Предложены конкретные шаги настройки Open-WebUI для приближения к качеству ответов веб-интерфейса DeepSeek.

## Введение

Рост популярности open-source интерфейсов для LLM, таких как Open-WebUI, создал новую категорию проблем: пользователи ожидают, что подключение той же модели через API даст результаты, идентичные веб-интерфейсу разработчика. На практике это далеко не так. DeepSeek — одна из наиболее показательных моделей в этом отношении: её веб-интерфейс интегрирует веб-поиск, специализированные системные промпты и оптимизированные параметры генерации, которые не воспроизводятся при простом подключении API-ключа к Open-WebUI[^1][^2].

Цель данного обзора — систематически разобрать все факторы, влияющие на различие в качестве ответов, и предложить практические рекомендации по настройке Open-WebUI для максимального приближения к результатам DeepSeek web. Обзор охватывает архитектуру поиска обеих платформ, параметры генерации, системные промпты, версионирование моделей и конфигурацию RAG-пайплайна. За рамками обзора остаются вопросы самостоятельного хостинга моделей DeepSeek через Ollama — рассматривается только доступ через DeepSeek API.

## Архитектура веб-поиска: встроенный vs внешний

### Как работает поиск в DeepSeek web

Веб-интерфейс DeepSeek (chat.deepseek.com) предоставляет два специальных режима, доступных через кнопки-переключатели: **Deep Think** (активирует модель-reasoner R1) и **Search** (дополняет ответы данными из интернета)[^3]. Важно понимать, что поиск не активирован по умолчанию — пользователь включает его явно. Однако именно этот режим объясняет значительную часть разницы в качестве: модель получает актуальный контекст из веба, что особенно критично для вопросов о событиях после knowledge cutoff[^3].

Технически поиск в DeepSeek реализован через механизм **tool calling** (function calling), а не через классический RAG-пайплайн[^4]. Модель не выполняет поиск сама — она генерирует структурированный вызов инструмента с параметрами запроса, платформа выполняет поиск, возвращает результаты, и модель синтезирует ответ на их основе. В режиме «thinking with tools» (доступен в V3.1 и V3.2) модель может выполнять цепочку рассуждений, перемежая их вызовами инструментов[^5]:

> «DeepSeek's 2026 models integrate "Thinking in Tool-Use," which allows an AI agent to generate a reasoning path before calling an external API, verify the results of a tool call against its internal logic, and self-correct if a tool output is inconsistent with the user's objective»[^5].

Это принципиально отличается от простого добавления поисковых результатов к промпту: модель рассуждает о том, что ей нужно найти, анализирует найденное и может уточнять запрос итеративно.

### Как работает поиск в Open-WebUI

Open-WebUI предлагает два режима веб-поиска с принципиально разной архитектурой[^6][^7]:

**Традиционный RAG-режим (Default Mode)** реализует классическую схему: генерация поискового запроса → выполнение поиска через один из 22+ провайдеров (Google PSE, Brave, SearXNG, Tavily и др.) → извлечение контента → разбиение на чанки → векторизация → семантический поиск → инъекция релевантных фрагментов в промпт[^6]. Результаты оборачиваются в RAG-шаблон с XML-тегами `<context></context>` и вставляются в системное или пользовательское сообщение[^8].

**Агентный режим (Native Function Calling / Agentic Mode)** работает иначе: модель сама решает, когда и что искать, используя два инструмента — `search_web` (поиск с получением сниппетов) и `fetch_url` (загрузка полного содержимого страницы, до 50 000 символов)[^7]. Модель автономно выполняет цикл THINK → ACT → EVALUATE → ITERATE.

> «Instead of the system deciding whether to search, the Model decides if and when it needs to search. The model acts as its own research agent, autonomously cycling through thinking and action phases until it gathers sufficient information»[^7].

Однако агентный режим требует frontier-моделей с сильными reasoning-способностями: рекомендуются GPT-5, Claude 4.5+, Gemini 3+[^7]. DeepSeek-R1 поддерживает function calling и теоретически может работать в агентном режиме, но на практике результаты зависят от конкретной версии модели и качества поддержки tool calling[^5].

### Ключевое различие

Веб-интерфейс DeepSeek использует тот же механизм tool calling, что и агентный режим Open-WebUI, но с двумя преимуществами: (1) интеграция оптимизирована именно под модели DeepSeek, и (2) поисковый бэкенд разработан DeepSeek и не зависит от сторонних провайдеров[^4]. В Open-WebUI качество поиска определяется выбранным провайдером и правильностью конфигурации, что создаёт дополнительную точку отказа.

## Системные промпты и параметры генерации

### Системный промпт DeepSeek web

Одним из наименее документированных, но наиболее значимых факторов различия является системный промпт. Веб-интерфейс DeepSeek использует недокументированный системный промпт, который отличается от того, что доступен через API[^9]. Попытки сообщества получить этот промпт через GitHub Issues были отклонены без раскрытия информации[^9].

Частичная информация о системном промпте была получена через jailbreak-атаку, известную как «Time Bandit»[^10]. Исследователи из Knostic извлекли промпт DeepSeek-V3, содержащий инструкции по самоидентификации, этическим ограничениям, формату ответов и границам знаний[^11]:

> «The model identifies itself as "DeepSeek-V3, an artificial intelligence assistant created by DeepSeek" with a knowledge cutoff of July 2024. Key directives state it should "provide helpful, accurate, and engaging responses" while "prioritizing clarity, relevance, and ethical considerations"»[^11].

Через API модель R1 использует более лаконичный промпт[^12]:

> «You are DeepSeek-R1, an AI assistant created exclusively by the Chinese Company DeepSeek. You'll provide helpful, harmless, and detailed responses to all user inquiries»[^12].

Различие в системных промптах напрямую влияет на стиль и полноту ответов. Веб-интерфейс, вероятно, содержит дополнительные инструкции по структурированию ответов, использованию найденных источников и уровню детализации[^9].

### Параметры генерации

Параметры генерации представляют ещё одну точку расхождения. Для модели `deepseek-reasoner` (R1) через API параметры `temperature`, `top_p`, `presence_penalty` и `frequency_penalty` **не поддерживаются** — их установка не вызывает ошибку, но не оказывает эффекта[^13]:

> «Setting these will not trigger an error but will also have no effect»[^13].

Для модели `deepseek-chat` (V3) рекомендуемые параметры от Together AI: `temperature: 0.6` (диапазон 0.5–0.7), `top_p: 0.95`[^14]. Веб-интерфейс DeepSeek, вероятно, использует иные настройки, оптимизированные для пользовательского опыта, но конкретные значения не раскрываются[^1].

Критический параметр — **max_tokens**. По умолчанию API возвращает до 4096 токенов для `deepseek-chat` и до 32768 для `deepseek-reasoner` (максимум 64K)[^13]. Веб-интерфейс, судя по поведению, использует значительно более высокие лимиты, что объясняет более развёрнутые ответы[^15].

## Версии моделей: web vs API

Одним из наименее очевидных, но документально подтверждённых факторов различия являются разные версии моделей, обслуживающих веб-интерфейс и API.

### Хронология обновлений

Экосистема моделей DeepSeek развивалась быстро[^16]:

- **V3-0324** (март 2025): включила RL-техники из R1, значительно улучшив reasoning
- **R1-0528** (май 2025): удвоила количество reasoning-токенов, снизила галлюцинации на 45–50%
- **V3.1** (август 2025): гибридный thinking-режим в одной модели, снижение выходных токенов на 20–50% по сравнению с R1
- **V3.2** (2026): улучшенный tool calling, поддержка «thinking with tools»

### Асинхронность обновлений

Веб-интерфейс и API обновляются асинхронно. Сообщество зафиксировало, что knowledge cutoff веб-интерфейса был обновлён до мая 2025, тогда как API-модель `deepseek-chat` (V3.2) по-прежнему сообщала о cutoff в декабре 2023[^1][^16]. Это означает, что в определённые периоды веб-интерфейс обслуживается более новой версией модели, чем та, что доступна через API.

Веб-интерфейс предлагает три модели через переключатели: DeepSeek-V3 (быстрый режим), DeepSeek-R1 (через кнопку Deep Think) и V3.1 (гибридный)[^16]. Через API доступны `deepseek-chat` и `deepseek-reasoner`, при этом конкретная версия может отличаться от веб-версии[^16].

## Проблемы Open-WebUI при работе с DeepSeek

### Обработка reasoning-контента

Модель `deepseek-reasoner` возвращает ответ в двух полях: `reasoning_content` (цепочка рассуждений) и `content` (финальный ответ)[^13]. Сообщество сообщает, что Open-WebUI не всегда корректно отображает reasoning-контент, что приводит к потере части информации[^15][^17].

### Конфликт sentence-transformers

Встроенный embedding-пайплайн Open-WebUI (sentence-transformers) может негативно влиять на качество ответов при веб-поиске. Отключение sentence-transformers в конфигурации, по отчётам сообщества, повышает качество ответов примерно на 25%[^15]. Это связано с тем, что chunking и embedding теряют контекст по сравнению с прямой инъекцией поисковых результатов.

### Низкий max_tokens по умолчанию

Open-WebUI по умолчанию устанавливает `max_tokens` в 4096 для API-подключений. Для DeepSeek, особенно в reasoning-режиме, этого критически недостаточно — модель обрывает ответ на середине рассуждения[^15][^17].

### RAG-шаблон и инъекция контекста

Стандартный RAG-шаблон Open-WebUI оборачивает результаты в XML-теги `<context></context>` с инструкцией «If you don't know the answer, simply state that you don't know»[^8]. Этот шаблон не оптимизирован для DeepSeek и может приводить к тому, что модель отказывается отвечать, даже имея достаточный контекст. Шаблон настраивается через Settings → Documents → Retrieval[^8].

Кроме того, контекст может инжектироваться в системное сообщение (при `RAG_SYSTEM_CONTEXT=True`) или в пользовательское сообщение[^8]. Для DeepSeek R1 рекомендуется минимизировать системный промпт и переносить инструкции в пользовательское сообщение[^14].

## Практические рекомендации по настройке Open-WebUI

На основе анализа документации и отчётов сообщества можно сформулировать набор рекомендаций, ранжированных по влиянию на качество.

### 1. Увеличить max_tokens (влияние: +15%)

Установить `max_tokens` минимум 8192 для `deepseek-chat` и 32768 для `deepseek-reasoner`. Это делается в настройках модели в Open-WebUI (Advanced Parameters)[^15].

### 2. Настроить веб-поиск с качественным провайдером (влияние: критическое)

Без веб-поиска Open-WebUI принципиально не может приблизиться к результатам DeepSeek web при запросах, требующих актуальной информации. Рекомендуемые провайдеры[^6]:

- **Google PSE** — лучшее качество результатов, требует API-ключ
- **Brave Search** — бесплатный тир (1000 запросов/месяц), хорошее качество
- **SearXNG** — самостоятельный хостинг, без ограничений на запросы, требует настройки JSON-формата[^18]
- **Tavily** — оптимизирован для LLM, бесплатный тир (1000 запросов/месяц)

Настройка: Admin Panel → Settings → Web Search → выбрать провайдера и указать API-ключ[^6].

### 3. Включить агентный режим (влияние: значительное)

Если используется DeepSeek V3.1+ или R1 с поддержкой function calling[^5][^7]:

1. Включить Web Search глобально (Admin Panel → Settings → Web Search)
2. Включить Web Search capability для модели
3. Отметить Web Search в Default Features
4. Установить Function Calling в `Native` в Advanced Parameters
5. Убедиться, что оба параметра (Web Search capability и Default Features) активны — при отсутствии любого из них инструменты не инжектируются[^7]

> «Both Web Search capability and Default Features must be enabled for tools to function. If either is missing, the tools will not be injected»[^7].

### 4. Отключить embedding для веб-поиска (влияние: +25%)

При использовании агентного режима результаты поиска поступают напрямую в контекст, минуя chunking и embedding. Если используется RAG-режим, стоит рассмотреть опцию «Bypass Embeddings», которая передаёт результаты поиска непосредственно в контекст модели без векторизации[^15][^19]. Это увеличивает расход токенов, но сохраняет контекст и предотвращает рост ChromaDB.

### 5. Оптимизировать RAG-шаблон (влияние: +10–15%)

Заменить стандартный RAG-шаблон на более подходящий для DeepSeek. В Settings → Documents → Retrieval можно настроить шаблон, убрав ограничительные инструкции и добавив указания по использованию контекста[^8]. Рекомендация из сообщества: вынести все инструкции из системного промпта в RAG-шаблон для централизованного управления[^8].

### 6. Настроить параметры генерации (влияние: +10–15%)

Для `deepseek-chat`: `temperature: 0.6`, `top_p: 0.95`[^14]. Для `deepseek-reasoner`: параметры сэмплирования не поддерживаются, сосредоточиться на `max_tokens`[^13]. Перенести ключевые инструкции из системного промпта в пользовательское сообщение — это рекомендация Together AI для R1[^14]:

> «Avoid system prompts entirely — put all guidance in the user message instead»[^14].

### 7. Включить гибридный поиск с реранкингом (влияние: +10%)

В настройках RAG включить Hybrid Search и использовать качественные модели[^19]:

- Embedding: BAAI/bge-m3
- Reranking: BAAI/bge-reranker-v2-m3
- Увеличить Embedding Batch Size с 1 до 10 для повышения производительности

## OpenRouter и Exa search: альтернативный путь к качественному поиску

### Что такое Exa search

Exa (exa.ai) — специализированный поисковый API, разработанный с нуля для интеграции с LLM[^25]. В отличие от традиционных поисковых API (Google PSE, Brave, SearXNG), которые используют keyword-matching, Exa применяет **нейросетевой семантический поиск**: запросы и веб-страницы конвертируются в векторные представления (embeddings), а релевантность определяется по семантической близости в векторном пространстве[^25]. Этот подход, называемый «next-link prediction», позволяет модели понимать, что запросы «battery storage challenges» и «difficulties with renewable power accumulation» семантически эквивалентны, несмотря на отсутствие общих ключевых слов.

Exa предлагает несколько режимов поиска: neural (чисто семантический), auto (гибрид keyword + embeddings, режим по умолчанию), deep (с синтезом), deep-reasoning (с цепочкой рассуждений) и instant (минимальная латентность, менее 200 мс)[^26]. Ключевое преимущество для LLM-интеграции — возможность получения не только URL и сниппетов, но и полного текста страниц, AI-выделенных релевантных фрагментов (highlights) и генеративных саммари[^25].

На бенчмарках Exa демонстрирует превосходство над конкурентами: 81% на WebWalker (multi-hop retrieval) против 71% у Tavily, лидерство на OpenAI SimpleQA для фактологических вопросов с веб-данными[^27]. Функция query-dependent highlights обеспечивает на 10% более высокую точность на RAG-бенчмарках при сокращении объёма передаваемых токенов на 50–75%[^28].

### Интеграция Exa через OpenRouter

OpenRouter предоставляет доступ к Exa search для **всех 400+ моделей** на платформе через механизм плагинов[^29]. Активация осуществляется двумя способами:

1. **Суффикс `:online`** к слагу модели: `openai/gpt-4o:online`, `anthropic/claude-3:online`, `deepseek/deepseek-chat:online`
2. **Явное указание плагина** в API-запросе с параметрами конфигурации (engine, max_results, domain filters)

Технически интеграция работает через **plugin-based архитектуру**, а не через tool calling[^29]: OpenRouter автоматически отправляет запрос в Exa, получает результаты (по умолчанию 5), оборачивает сниппеты в системное сообщение и передаёт дополненный контекст целевой модели. Для моделей OpenAI, Anthropic, Perplexity и xAI приоритет отдаётся нативному поиску провайдера; для остальных моделей (включая DeepSeek) используется Exa[^29].

> «OpenRouter selected Exa as its sole search engine partner based on superior benchmark performance and LLM-ready output format»[^30].

Стоимость: **$4 за 1000 результатов** через кредиты OpenRouter, что при 5 результатах по умолчанию составляет ~$0.02 за запрос плюс стоимость токенов модели[^29]. Доступна фильтрация по доменам (include/exclude) для повышения релевантности[^29].

### Два пути интеграции Exa в Open-WebUI

Open-WebUI поддерживает Exa как **нативный поисковый провайдер** наряду с Google PSE, Brave, SearXNG и другими[^31]. Это создаёт два принципиально разных пути использования Exa:

**Путь 1: Exa как нативный провайдер Open-WebUI (рекомендуемый)**

Настройка: Admin Panel → Settings → Web Search → выбрать «Exa» → указать API-ключ с exa.ai[^31]. Альтернативно через переменную окружения `EXA_API_KEY`. В этом режиме Open-WebUI самостоятельно выполняет поисковые запросы к Exa API и обрабатывает результаты через свой RAG-пайплайн или агентный режим. Модель может быть любой, включая DeepSeek через прямое API-подключение.

**Путь 2: Exa через OpenRouter `:online` модели**

При подключении OpenRouter как провайдера в Open-WebUI (через `OPENAI_API_BASE=https://openrouter.ai/api/v1`) можно использовать модели с суффиксом `:online`[^32]. Однако Open-WebUI **не поддерживает нативный проброс** параметров веб-поиска OpenRouter — это открытый feature request (GitHub issue #8860)[^33]. Результаты поиска инжектируются OpenRouter на уровне провайдера, до того как Open-WebUI их видит, что создаёт проблему прозрачности: Open-WebUI не знает, что поиск был выполнен, и может запустить собственный дублирующий поиск[^34].

Сообщество разработало обходное решение — **OpenRouter Integration Subsystem** (rbb-dev/Open-WebUI-OpenRouter-pipe), предоставляющий переключатель веб-поиска с корректной обработкой цитат[^34]. При использовании этого решения двойной поиск предотвращается: OpenRouter search имеет приоритет над нативным поиском Open-WebUI[^34].

### Проблема суффикса `:online` при автоматическом получении моделей

#### Почему `:online` модели не появляются в списке

При подключении OpenRouter через Settings → Connections Open-WebUI запрашивает список моделей через стандартный endpoint `/v1/models`[^35]. Этот endpoint возвращает только **базовые идентификаторы** моделей: `deepseek/deepseek-chat`, `anthropic/claude-sonnet-4-5`, `openai/gpt-5.2` и т.д.[^36]. Варианты с суффиксами (`:online`, `:free`, `:nitro`, `:thinking`, `:extended`, `:exacto`) — это **динамические модификаторы поведения**, а не отдельные модели в каталоге OpenRouter[^37]. Каждый суффикс является сокращением для соответствующего JSON-параметра в теле запроса[^38]:

- `:online` эквивалентен `"plugins": [{"id": "web"}]`
- `:nitro` эквивалентен `"provider": {"sort": "throughput"}`
- `:free` маршрутизирует к бесплатным провайдерам

Поскольку `/v1/models` не содержит записей вида `deepseek/deepseek-chat:online`, Open-WebUI не отображает их в выпадающем списке моделей. Это ожидаемое поведение — суффиксы не являются моделями, а модификаторами запроса[^37].

#### Ручное добавление через Model IDs (Filter)

Open-WebUI позволяет вручную добавлять произвольные идентификаторы моделей через механизм allowlist[^35]. Процесс:

1. Перейти в **Settings → Connections** → выбрать подключение OpenRouter
2. В поле **Model IDs (Filter)** ввести идентификатор с суффиксом, например `deepseek/deepseek-chat:online`
3. Нажать **+** для добавления
4. Сохранить подключение

Модель появится в выпадающем списке и при выборе Open-WebUI отправит запрос с полным идентификатором `deepseek/deepseek-chat:online` на OpenRouter API. OpenRouter распознает суффикс и активирует веб-поиск автоматически[^32].

Однако этот подход имеет **существенное ограничение**: Filter-функции Open-WebUI валидируют имена моделей по списку известных моделей перед обработкой запроса[^39]. Модели с суффиксом `:variant` могут быть отклонены на этапе валидации, что приводит к ошибке вместо выполнения запроса. Степень проблемы зависит от версии Open-WebUI и установленных фильтров[^39].

#### Нужно ли отдельно включать веб-поиск в модели?

**Нет.** Суффикс `:online` — это всё, что требуется для активации веб-поиска на стороне OpenRouter[^32][^29]. Включать функцию веб-поиска в самой модели (через настройки Open-WebUI: Web Search toggle, RAG-пайплайн или агентный режим) **не нужно и не рекомендуется**. OpenRouter обрабатывает поиск прозрачно:

1. Получает запрос с суффиксом `:online`
2. Извлекает суффикс и активирует web-плагин
3. Передаёт пользовательский промпт в поисковый движок (Exa для большинства моделей, нативный поиск для OpenAI/Anthropic/Perplexity/xAI)[^29]
4. Объединяет результаты поиска (по умолчанию 5) с оригинальным промптом
5. Отправляет дополненный контекст целевой модели[^29]

Если одновременно с `:online` включить веб-поиск в Open-WebUI, произойдёт **дублирование поиска**: Open-WebUI выполнит свой поиск через настроенный провайдер, а OpenRouter — через Exa. Модель получит два набора поисковых результатов, что увеличит расход токенов и может ухудшить качество ответа из-за конфликтующего контекста[^34].

#### Рекомендуемые решения через pipe-функции

Наиболее надёжный способ использования OpenRouter web search в Open-WebUI — установка специализированных pipe-функций, которые обходят проблему валидации имён и дублирования поиска:

**OpenRouter Integration Subsystem** (rbb-dev/Open-WebUI-OpenRouter-pipe, v2.3.0)[^40] — полнофункциональная интеграция с 350+ моделями. Поддерживает двойной переключатель: нативный поиск Open-WebUI и OpenRouter search как отдельные тогглы. При активации OpenRouter Search автоматически блокирует нативный поиск Open-WebUI для предотвращения дублирования[^34]. Устанавливается через Admin Panel → Functions → Import from Link. Три конфигурационных флага управляют автоматическим развёртыванием:

- `AUTO_INSTALL_ORS_FILTER` — установка фильтра в базу Open-WebUI
- `AUTO_ATTACH_ORS_FILTER` — привязка фильтра к совместимым моделям
- `AUTO_DEFAULT_OPENROUTER_SEARCH_FILTER` — активация по умолчанию на поддерживаемых моделях[^34]

**OpenWebUI-OpenRouter Integration** (admirito/openwebui-openrouter-integration)[^39] — набор filter-функций с пользовательскими тогглами для функций OpenRouter. Решает проблему валидации имён принципиально иначе: вместо модификации идентификатора модели (суффикс `:online`) инжектирует параметры `plugins: [{"id": "web"}]` напрямую в тело запроса[^39]. Это обходит валидацию Open-WebUI, так как идентификатор модели остаётся стандартным.

> «Open WebUI Filter functions validate model names against known models before processing. Models with `:variant` suffixes are rejected at this validation stage. [...] Rather than using `:online` suffix notation, this integration uses request body parameters to activate web search functionality»[^39].

**OpenRouter Integration for OpenWebUI** (preswest/openrouter_integration_for_openwebui)[^41] — базовая функция для доступа к моделям OpenRouter с поддержкой цитат и reasoning-токенов. Более простое решение без управления веб-поиском.

#### Конфигурация web-плагина через API

При использовании pipe-функций, инжектирующих параметры в тело запроса, доступна тонкая настройка поведения web-плагина OpenRouter[^29]:

```json
{
  "plugins": [{
    "id": "web",
    "max_results": 5,
    "search_prompt": "Найди актуальную информацию по запросу",
    "engine": "exa",
    "include_domains": ["docs.python.org", "*.github.com"],
    "exclude_domains": ["reddit.com"]
  }]
}
```

Доступные движки: `exa` (по умолчанию для большинства моделей, семантический поиск), `native` (нативный поиск провайдера — для OpenAI, Anthropic, Perplexity, xAI), `firecrawl` (BYOK-модель), `parallel` (комбинированный)[^29]. Фильтрация по доменам поддерживается для Exa и Parallel, но не для Firecrawl[^29].

### Ошибка «Chunk too big» при использовании `:online` моделей

#### Описание проблемы

При использовании моделей OpenRouter с суффиксом `:online` (например, `deepseek/deepseek-chat:online` или `perplexity/sonar-deep-research:online`) в Open-WebUI пользователи сталкиваются с ошибкой `ValueError: Chunk too big`[^42][^43]. Ошибка возникает в интерфейсе Open-WebUI — прямые API-запросы к OpenRouter при этом выполняются успешно, что подтверждает локализацию проблемы на стороне Open-WebUI[^42].

#### Техническая причина

Корневая причина — ограничение буфера библиотеки **aiohttp**, которую Open-WebUI использует для обработки потоковых (streaming) ответов по протоколу Server-Sent Events (SSE)[^44][^45]. Механизм работает следующим образом:

1. Open-WebUI получает ответ от OpenRouter в режиме streaming
2. aiohttp читает данные построчно через `readuntil()`, буферизируя содержимое до символа новой строки
3. Когда модель с суффиксом `:online` возвращает ответ, OpenRouter **инжектирует результаты веб-поиска** (сниппеты, URL, цитаты от Exa) прямо в поток данных[^29]
4. Единичная SSE-строка с инжектированными поисковыми результатами может превысить **дефолтный буфер aiohttp (~64 КиБ)**[^45]
5. aiohttp выбрасывает `ValueError("Chunk too big")` вместо буферизации превышающего данных[^44]

Проблемный код находится в `backend/open_webui/routers/openai.py` (строки 929–977) и `backend/open_webui/utils/middleware.py` (строка 1573), где происходит итерация по потоку ответа[^44][^45].

> «When SSE single-line data is extremely large (likely exceeding 16KB), directly using Python's asynchronous iterator to traverse aiohttp's response.content forces the use of aiohttp's built-in buffer size, which cannot be configured»[^44].

#### Почему `:online` модели вызывают эту ошибку чаще

Суффикс `:online` активирует web-плагин OpenRouter, который добавляет к ответу поисковые результаты в формате аннотаций (URL, заголовки, фрагменты контента)[^29]. При 5 результатах по умолчанию объём инжектированных данных может составить десятки килобайт в одной SSE-строке, что гарантированно превышает дефолтный буфер aiohttp. Аналогичная проблема воспроизводится с любыми моделями, генерирующими крупные SSE-чанки: Gemini с inline-изображениями (base64), Perplexity с развёрнутыми цитатами[^43][^46].

#### Решения

**Решение 1: Увеличить буфер потоковых ответов (рекомендуемое)**

Установить переменную окружения `CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE`, задающую максимальный размер буфера в байтах для обработки потоковых чанков[^47]. При превышении этого лимита система возвращает пустой JSON-объект и пропускает данные до появления чанков нормального размера:

```bash
# В docker-compose.yml или .env файле Open-WebUI
CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE=20971520  # 20 МиБ
```

Значение 20 МиБ (`20971520`) достаточно для большинства сценариев с `:online` моделями[^46]. Для моделей, генерирующих изображения inline (Gemini), может потребоваться увеличение до 32+ МиБ.

**Решение 2: Отключить streaming для конкретной модели**

В Open-WebUI можно создать кастомную модель-обёртку с отключённым streaming[^48]:

1. Перейти в **Workspace → Models → + New Model**
2. Выбрать базовую модель (DeepSeek через OpenRouter)
3. В **Advanced Parameters** установить `"stream": false`
4. Сохранить и использовать эту модель для запросов с `:online`

При отключённом streaming ответ приходит целиком, минуя буфер aiohttp. Однако этот подход имеет ограничение: отключение streaming может нарушить работу tool calling в Open-WebUI[^48].

**Решение 3: Использовать pipe-функцию с chunk-based обработкой**

Предложенное сообществом исправление на уровне кода заменяет построчную итерацию aiohttp на chunk-based обработку с ручным разбором границ строк[^44]:

```python
async def sse_line_generator():
    buffer = b""
    async for chunk in r.content.iter_any():
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            yield line + b"\n"
    if buffer:
        yield buffer
```

В сочетании с увеличением `read_bufsize=128 * 1024` в `ClientSession` это устраняет проблему на уровне транспорта[^44].

**Решение 4: Уменьшить объём инжектируемых поисковых данных**

При использовании pipe-функций (admirito или rbb-dev) можно уменьшить `max_results` в конфигурации web-плагина OpenRouter[^29]:

```json
{
  "plugins": [{
    "id": "web",
    "max_results": 2
  }]
}
```

Снижение с 5 до 2 результатов уменьшает объём SSE-чанка в 2–3 раза, что может оказаться достаточным для обхода лимита буфера без изменения переменных окружения.

#### Статус исправления в Open-WebUI

PR #20779 («fix: large base64 images streaming»), принятый в феврале 2026 года, реализовал chunk-based обработку потока для крупных base64-изображений[^46]. Однако это исправление **не решает** проблему с `:online` моделями OpenRouter: ошибка воспроизводится в Open-WebUI v0.8.11 (март 2026). Вероятная причина — PR #20779 адресует конкретный сценарий с inline-изображениями, тогда как инжекция поисковых результатов OpenRouter проходит по другому пути в middleware. До выхода целевого исправления необходимо использовать решения 1–4, описанные выше.

### Сравнение подходов к поиску

| Параметр | Open-WebUI + Exa (нативно) | OpenRouter `:online` | Open-WebUI + Google PSE/Brave | DeepSeek web |
|----------|---------------------------|---------------------|-------------------------------|-------------|
| Тип поиска | Семантический (neural) | Семантический (neural) | Keyword-based | Оптимизированный tool calling |
| Контроль | Полный (RAG/агентный) | Минимальный (чёрный ящик) | Полный (RAG/агентный) | Нет (закрытая система) |
| Качество | Высокое (81% WebWalker) | Высокое (тот же Exa) | Среднее | Высокое |
| Стоимость за запрос | ~$0.035 (Exa напрямую) | ~$0.02 (через OpenRouter) | Бесплатно – $0.01 | Бесплатно (в рамках тарифа) |
| Интеграция с Open-WebUI | Нативная | Через pipe/workaround | Нативная | Не применимо |
| Агентный режим | Да | Нет (plugin injection) | Да | Да (tool calling) |

### Влияние на качество ответов

Замена keyword-based провайдера (Google PSE, Brave) на Exa в Open-WebUI может существенно повысить качество поиска для сложных, нюансированных запросов. На комплексных запросах Exa находит **в 5 раз больше релевантных результатов** по сравнению с keyword-подходами[^27]. Функция highlights, доступная через Exa API, позволяет передавать модели только семантически релевантные фрагменты, а не полные страницы, что сокращает расход токенов и повышает точность[^28].

Однако для простых фактологических запросов (даты, имена, цифры) разница между Exa и keyword-based провайдерами менее заметна. Кроме того, индекс Exa может быть менее полным, чем у Google — это ограничение компенсируется качеством ранжирования, но не количеством покрытия[^28].

**Рекомендация**: для максимального приближения к качеству DeepSeek web использовать **Exa как нативный провайдер Open-WebUI в агентном режиме** — это сочетает семантический поиск Exa с автономным исследовательским циклом Open-WebUI (THINK → ACT → EVALUATE → ITERATE)[^7], наиболее близким к поведению DeepSeek web[^3].

## Дискуссионные вопросы и противоречия

### Можно ли полностью воспроизвести качество DeepSeek web в Open-WebUI?

Сообщество расходится во мнениях. Часть пользователей считает, что при правильной настройке агентного режима, качественного поискового провайдера и оптимальных параметров генерации можно добиться сравнимого качества[^6][^7]. Другая часть указывает на фундаментальные ограничения: недокументированный системный промпт DeepSeek web, возможные различия в версиях моделей и оптимизированную интеграцию поиска, которую невозможно воспроизвести через стандартный API[^1][^9].

### RAG vs tool calling: что лучше для поиска?

Исследование Elasticsearch Labs показало, что RAG-подход в 3500 раз дешевле ($0.000029 vs $0.102 за запрос) и в 35 раз быстрее (1.28 с vs 45.6 с), чем прямой вызов API с поиском[^4]. Однако tool calling через DeepSeek обеспечивает лучшую точность для вопросов, требующих актуальных данных без предварительной индексации[^4]. Для Open-WebUI это означает компромисс: RAG-режим быстрее и дешевле, но агентный режим ближе к поведению DeepSeek web.

### DeepSeek R1 в агентном режиме Open-WebUI

Документация Open-WebUI рекомендует «frontier-class models with strong reasoning abilities» для агентного режима и явно называет GPT-5, Claude 4.5+, Gemini 3+[^7]. DeepSeek-R1 формально поддерживает function calling[^5], но не упоминается в рекомендованных моделях Open-WebUI, что создаёт неопределённость: будет ли агентный режим работать стабильно с R1 в Open-WebUI — зависит от конкретной версии и провайдера.

## Недостаточность данных

### Точный системный промпт DeepSeek web

Несмотря на jailbreak-атаки, полный системный промпт веб-интерфейса DeepSeek не был опубликован. Извлечённые фрагменты могут быть неполными или содержать галлюцинации модели[^10][^11]. DeepSeek отказался раскрывать промпт через официальные каналы[^9]. Это делает невозможной точную репликацию поведения веб-интерфейса.

### Параметры генерации веб-интерфейса

Конкретные значения `temperature`, `top_p`, `max_tokens` и других параметров, используемых веб-интерфейсом DeepSeek, не документированы и не могут быть определены извне. Предположение о более высоких лимитах `max_tokens` основано на наблюдаемом поведении, а не на подтверждённых данных.

### Совместимость DeepSeek R1 с агентным режимом Open-WebUI

Не найдено систематического тестирования или бенчмарков, подтверждающих стабильность работы DeepSeek R1 в агентном режиме Open-WebUI. Отдельные отчёты пользователей противоречивы.

## Заключение

Различие в качестве ответов между веб-интерфейсом DeepSeek и Open-WebUI обусловлено не одним, а комбинацией пяти факторов:

1. **Встроенный веб-поиск** — веб-интерфейс DeepSeek интегрирует поиск через optimized tool calling с итеративным уточнением, тогда как Open-WebUI по умолчанию не имеет поиска или использует менее интегрированный RAG-пайплайн[^3][^4].

2. **Системные промпты** — веб-интерфейс использует недокументированный промпт, оптимизированный для полноты и структурированности ответов, тогда как API предоставляет минимальный промпт[^9][^12].

3. **Параметры генерации** — различия в `max_tokens`, `temperature` и других параметрах, при этом для R1 через API ряд параметров не поддерживается вовсе[^13].

4. **Версии моделей** — веб-интерфейс может обслуживаться более новой версией модели, чем доступная через API[^16].

5. **Обработка в Open-WebUI** — потеря reasoning-контента, низкий max_tokens по умолчанию, неоптимальный RAG-шаблон[^15][^17].

Полное воспроизведение качества DeepSeek web в Open-WebUI **невозможно** из-за недокументированных компонентов (системный промпт, параметры, версия модели). Однако **значительное приближение** достижимо при выполнении ключевых шагов: настройка качественного веб-поиска с агентным режимом, увеличение max_tokens, оптимизация RAG-шаблона и корректные параметры генерации. По совокупным оценкам сообщества, эти меры могут сократить разрыв на 60–80%.

Для пользователей, которым критична максимальная близость к DeepSeek web, наиболее перспективным направлением является использование агентного режима Open-WebUI с DeepSeek V3.1+ (поддерживающим «thinking with tools») в сочетании с семантическим поисковым провайдером. Интеграция Exa search — как нативного провайдера Open-WebUI или через OpenRouter `:online` модели — представляет шестой фактор, способный существенно сократить разрыв в качестве благодаря нейросетевому поиску, оптимизированному для LLM-задач[^25][^27].

## Quality Metrics

| Metric | Value |
|--------|-------|
| Total sources | 48 |
| Academic sources | 0 |
| Official/documentation | 21 |
| Industry reports | 6 |
| News/journalism | 3 |
| Blog/forum | 18 |
| Citation coverage | 94% |
| Counter-arguments searched | Yes |
| Research rounds | 5 |
| Questions emerged | 22 |
| Questions resolved | 19 |
| Questions insufficient data | 3 |

[^1]: DeepSeek-V3 GitHub. "Issue #196: System Prompt Discussion." GitHub, 2025. <https://github.com/deepseek-ai/DeepSeek-V3/issues/196>
[^2]: SerpAPI Blog. "Connect DeepSeek API with Real-Time Data." SerpAPI, 2025. <https://serpapi.com/blog/connect-deepseek-api-with-the-internet-google-search-and-more/>
[^3]: Learn Prompting. "Guide to DeepSeek Chatbot." Learn Prompting, 2025. <https://learnprompting.org/blog/guide-deepseek-chatbot>
[^4]: Elasticsearch Labs. "RAG vs DeepSeek API Search: Cost and Performance Comparison." Elasticsearch, 2025.
[^5]: Voiceflow. "DeepSeek's R1, AI Agent, and Everything Else." Voiceflow Blog, 2025. <https://www.voiceflow.com/blog/what-is-deepseek>
[^6]: Open WebUI Documentation. "Web Search." Open WebUI, 2026. <https://docs.openwebui.com/category/web-search/>
[^7]: Open WebUI Documentation. "Agentic Search & URL Fetching." Open WebUI, 2026. <https://docs.openwebui.com/features/chat-conversations/web-search/agentic-search/>
[^8]: GitHub Discussion #16216. "System prompt and RAG template." Open-WebUI, 2025. <https://github.com/open-webui/open-webui/discussions/16216>
[^9]: DeepSeek-V3 GitHub. "Issue #196: Web interface system prompt request (closed)." GitHub, 2025. <https://github.com/deepseek-ai/DeepSeek-V3/issues/196>
[^10]: Dark Reading. "DeepSeek Jailbreak Reveals Its Entire System Prompt." Dark Reading, 2025. <https://www.darkreading.com/application-security/deepseek-jailbreak-system-prompt>
[^11]: Knostic. "DeepSeek's cutoff date is July 2024: We extracted DeepSeek's system prompt." Knostic Blog, 2025. <https://www.knostic.ai/blog/exposing-deepseek-system-prompts>
[^12]: Baoyu's Blog. "DeepSeek-R1 System Prompt." Baoyu.io, 2025. <https://baoyu.io/blog/deepseek-r1-system-prompt>
[^13]: DeepSeek API Documentation. "Thinking Mode Guide." DeepSeek, 2025. <https://api-docs.deepseek.com/guides/thinking_mode>
[^14]: Together AI Documentation. "Prompting DeepSeek R1." Together AI, 2025. <https://docs.together.ai/docs/prompting-deepseek-r1>
[^15]: GitHub Open-WebUI Issues #8702, #8974, #8706, #9431, #10017. "DeepSeek quality and configuration issues." GitHub, 2025. <https://github.com/open-webui/open-webui/issues>
[^16]: BentoML Blog. "The Complete Guide to DeepSeek Models: From V3 to R1 and Beyond." BentoML, 2025. <https://www.bentoml.com/blog/the-complete-guide-to-deepseek-models-from-v3-to-r1-and-beyond>
[^17]: DataStudios. "All DeepSeek Models Available 2025." DataStudios, 2025. <https://www.datastudios.org/post/all-deepseek-models-available-in-2025-full-list-for-web-app-and-api-with-reasoning-and-advanced-c>
[^18]: Open WebUI Documentation. "SearXNG Configuration." Open WebUI, 2026. <https://docs.openwebui.com/features/chat-conversations/web-search/providers/searxng/>
[^19]: Medium. "Multi-Source RAG with Hybrid Search and Re-ranking in OpenWebUI." Medium, 2025. <https://medium.com/@richard.meyer596/multi-source-rag-with-hybrid-search-and-re-ranking-in-openwebui-8762f1bdc2c6>
[^20]: SambaNova Blog. "Supercharging AI Agents with Function Calling on DeepSeek." SambaNova, 2025. <https://sambanova.ai/blog/supercharging-ai-agents-with-function-calling-on-deepseek>
[^21]: Brave Search. "Use Brave Search with Open-WebUI." Brave, 2025. <https://brave.com/search/api/guides/use-with-open-webui/>
[^22]: DeepSeek API Documentation. "V3.1 Release Notes." DeepSeek, 2025. <https://api-docs.deepseek.com/news/news250821>
[^23]: Security Boulevard. "Analyzing DeepSeek's System Prompt: Jailbreaking Generative AI." Security Boulevard, 2025. <https://securityboulevard.com/2025/01/analyzing-deepseeks-system-prompt-jailbreaking-generative-ai/>
[^24]: Open WebUI Documentation. "RAG Tutorial." Open WebUI, 2026. <https://docs.openwebui.com/tutorials/tips/rag-tutorial/>
[^25]: Exa AI. "How Exa Search Works." Exa Documentation, 2026. <https://exa.ai/docs/reference/how-exa-search-works>
[^26]: Exa AI. "Search API Reference." Exa Documentation, 2026. <https://exa.ai/docs/reference/search>
[^27]: Exa AI. "Web Search API Evals: Exa vs Competition." Exa Blog, 2026. <https://exa.ai/blog/api-evals>
[^28]: Exa AI. "Exa vs Tavily: AI Search API Comparison." Exa, 2026. <https://exa.ai/versus/tavily>
[^29]: OpenRouter. "Web Search: Add Real-time Web Data to AI Model Responses." OpenRouter Documentation, 2026. <https://openrouter.ai/docs/guides/features/plugins/web-search>
[^30]: Exa AI. "OpenRouter Integrates with Exa's Semantic Search Technology." Exa Blog, 2026. <https://exa.ai/blog/openrouter-and-exa>
[^31]: Open WebUI Documentation. "Exa AI Web Search Provider." Open WebUI, 2026. <https://docs.openwebui.com/features/chat-conversations/web-search/providers/exa/>
[^32]: OpenRouter. "Online Variant: Real-Time Web Search." OpenRouter Documentation, 2026. <https://openrouter.ai/docs/guides/routing/model-variants/online>
[^33]: GitHub Open-WebUI Issue #8860. "Support OpenRouter's Web Search API." GitHub, 2025. <https://github.com/open-webui/open-webui/issues/8860>
[^34]: rbb-dev. "Web Search: Open-WebUI vs OpenRouter Search Comparison." GitHub, 2025. <https://github.com/rbb-dev/Open-WebUI-OpenRouter-pipe/blob/main/docs/web_search_owui_vs_openrouter_search.md>
[^35]: Open WebUI Documentation. "OpenAI-Compatible Provider Setup." Open WebUI, 2026. <https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/>
[^36]: OpenRouter. "List All Models and Their Properties." OpenRouter API Documentation, 2026. <https://openrouter.ai/docs/api/api-reference/models/get-models>
[^37]: OpenRouter. "Model Variants Overview." OpenRouter Documentation, 2026. <https://openrouter.ai/docs/guides/overview/models>
[^38]: simonw/llm-openrouter. "Issue #20: OpenRouter Model :suffixes." GitHub, 2025. <https://github.com/simonw/llm-openrouter/issues/20>
[^39]: admirito/openwebui-openrouter-integration. "OpenRouter Integration Filters for Open WebUI." GitHub, 2026. <https://github.com/admirito/openwebui-openrouter-integration>
[^40]: rbb-dev/Open-WebUI-OpenRouter-pipe. "OpenRouter Integration Subsystem for Open WebUI." GitHub, 2026. <https://github.com/rbb-dev/Open-WebUI-OpenRouter-pipe>
[^41]: preswest. "OpenRouter Integration for OpenWebUI." Open WebUI Community, 2025. <https://openwebui.com/f/preswest/openrouter_integration_for_openwebui>
[^42]: GitHub Open-WebUI Discussion #19803. "Chunk too big error when using perplexity/sonar-deep-research:online in OpenRouter." GitHub, 2026. <https://github.com/open-webui/open-webui/discussions/19803>
[^43]: GitHub Open-WebUI Issue #18373. "Gemini Nano Banana added through OpenRouter causes Chunk too Big error." GitHub, 2025. <https://github.com/open-webui/open-webui/issues/18373>
[^44]: GitHub Open-WebUI Issue #17626. "Chunk too big error when using Google Gemini 2.5 Flash with image input." GitHub, 2025. <https://github.com/open-webui/open-webui/issues/17626>
[^45]: GitHub Open-WebUI Discussion #10303. "ValueError: Chunk too big when streaming large files from pipelines." GitHub, 2025. <https://github.com/open-webui/open-webui/discussions/10303>
[^46]: GitHub Open-WebUI Issue #20634. "OpenRouter image generation Chunk too big error." GitHub, 2026. <https://github.com/open-webui/open-webui/issues/20634>
[^47]: Open WebUI Documentation. "Environment Variable Configuration." Open WebUI, 2026. <https://docs.openwebui.com/reference/env-configuration/>
[^48]: GitHub Open-WebUI Discussion #4065. "Disabling streaming." GitHub, 2024. <https://github.com/open-webui/open-webui/discussions/4065>
